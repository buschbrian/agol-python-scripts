r"""FEMA / ORNL USA Structures as a third footprint source for the Millcreek review (October 23, 2026).

    python -I reviews/2026-10-23/usa-structures/usa_structures.py fetch OUT      pull the city's structures (once)
    python -I reviews/2026-10-23/usa-structures/usa_structures.py compare OUT    votes on the review items

ArcGIS Pro env millcreek-py3, PYTHONNOUSERSITE=1. Source: Esri US Federal Data's "USA Structures" feature layer
(item 0ec8512ad21e4bb987d7e848d14e7e24; FEMA Geospatial Response Office and Oak Ridge National Laboratory; data
current to June 6, 2025; Utah updated in that cycle), licensed CC BY 4.0: attribution, no share-alike. It holds
structures over 450 ft2 (about 42 m2) only, so it says nothing about small sheds.
- fetch: the structures intersecting the city's bounding box, in pages of 2,000 as GeoJSON (WGS84), kept raw under
  OUT/raw; then projected to EPSG 6341 with WGS_1984_(ITRF08)_To_NAD_1983_2011 (as the county footprints, Overture
  and every hosted package) and kept where they touch the municipal boundary: OUT/usa_structures.gpkg.
- compare: one vote per review item. A LiDAR candidate or a county footprint is "in USA Structures" when it and a
  structure overlap by at least 30% of either (the witness rule used for Overture). A new-building hint box is when a
  structure lies at least half inside it. Each vote carries the structure's occupancy, outbuilding flag, height and
  imagery date. Written to OUT/votes.csv and OUT/compare.json; the review page reads votes.csv.
"""
import argparse
import datetime
import json
from pathlib import Path
import sys
import time
import urllib.parse
import urllib.request

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[3]))
from canopy.lidar_root import lidar_root  # noqa: E402

RUNS = lidar_root()/"2023-salt-lake-valley"/"runs"
LIB = RUNS/"millcreek-products-20261022"
CAND = RUNS/"footprint-candidates-lidar-20261023"
REVIEW = RUNS/"footprint-review-20261023"/"data"
BOUNDARY = RUNS/"city-count-20261008"/"inputs.gdb"/"municipal_boundary"
COMPARE = Path(r"Z:\GIS\overture\2026-10-21.0\millcreek\lidar-compare\overture_vs_lidar.gpkg")
SERVICE = "https://services2.arcgis.com/FiaPA4ga0iQKduv3/arcgis/rest/services/USA_Structures_View/FeatureServer/0/query"
ITEM = "https://www.arcgis.com/home/item.html?id=0ec8512ad21e4bb987d7e848d14e7e24"
BBOX = (-111.921104, 40.6590836, -111.7768114, 40.7143706)   # the city's extent (as the Overture extract)
PAGE = 2000
TRANSFORM = "WGS_1984_(ITRF08)_To_NAD_1983_2011"
MIN_M2 = 450 / 10.7639          # the inventory's own size floor
OVERLAP = 0.3
ATTRIBUTION = "USA Structures: FEMA Geospatial Response Office and Oak Ridge National Laboratory, via Esri (CC BY 4.0)"


def get(params):
    url = SERVICE + "?" + urllib.parse.urlencode(params)
    for attempt in range(4):
        try:
            with urllib.request.urlopen(url, timeout=120) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception:
            if attempt == 3:
                raise
            time.sleep(5 * (attempt + 1))


def fetch(out):
    import arcpy
    import geopandas as gpd
    import shapely
    raw = out/"raw"
    raw.mkdir(parents=True, exist_ok=False)
    common = {"where": "1=1", "geometry": ",".join(map(str, BBOX)), "geometryType": "esriGeometryEnvelope",
              "inSR": 4326, "spatialRel": "esriSpatialRelIntersects"}
    total = get({**common, "returnCountOnly": "true", "f": "json"})["count"]
    features = []
    for offset in range(0, total, PAGE):
        page = get({**common, "outFields": "*", "outSR": 4326, "orderByFields": "OBJECTID", "resultOffset": offset,
                    "resultRecordCount": PAGE, "f": "geojson"})
        (raw/f"page-{offset // PAGE:03d}.geojson").write_text(json.dumps(page), encoding="utf-8")
        features += page["features"]
        print(f"  {len(features)}/{total}", flush=True)
    assert len(features) == total, (len(features), total)
    g = gpd.GeoDataFrame.from_features(features, crs=4326)
    wgs, sr = arcpy.SpatialReference(4326), arcpy.SpatialReference(6341)
    g = g.set_geometry([shapely.from_wkb(bytes(arcpy.FromWKB(bytes(shapely.to_wkb(geom)), wgs)
                                               .projectAs(sr, TRANSFORM).WKB)) for geom in g.geometry], crs=6341)
    city = gpd.read_file(BOUNDARY.parent, layer=BOUNDARY.name).geometry.union_all()
    g = g[g.intersects(city)].copy()
    for col in ("IMAGE_DATE", "PROD_DATE"):
        g[col] = gpd.pd.to_datetime(g[col], unit="ms", errors="coerce").dt.date.astype(str)
    g.to_file(out/"usa_structures.gpkg", layer="usa_structures", driver="GPKG")
    record = {"source": SERVICE, "item": ITEM, "licence": "CC BY 4.0", "attribution": ATTRIBUTION,
              "fetched": datetime.datetime.now().isoformat(timespec="seconds"), "bbox_wgs84": BBOX,
              "in_bbox": total, "touching_city": len(g), "transformation": TRANSFORM,
              "image_dates": g.IMAGE_DATE.value_counts().head(15).to_dict(),
              "occupancy": g.OCC_CLS.value_counts().to_dict(), "outbuilding": g.OUTBLDG.value_counts(dropna=False).to_dict()}
    (out/"fetch.json").write_text(json.dumps(record, indent=1, default=str), encoding="utf-8")
    print(json.dumps(record, indent=1, default=str))


def overlaps(left, right, rid):
    """For each left geometry, the right feature with the largest overlap if it covers at least OVERLAP of either."""
    import shapely
    tree = shapely.STRtree(list(right.geometry))
    best = []
    for g in left.geometry:
        top = None
        for j in tree.query(g, "intersects"):
            h = right.geometry.iloc[j]
            a = g.intersection(h).area
            if a and max(a / g.area, a / h.area) >= OVERLAP and (top is None or a > top[0]):
                top = (a, j)
        best.append(None if top is None else right[rid].iloc[top[1]])
    return best


def compare(out):
    import geopandas as gpd
    import pandas as pd
    us = gpd.read_file(out/"usa_structures.gpkg", layer="usa_structures")
    us["US_ID"] = us.BUILD_ID.astype(str)
    usi = us.set_index("US_ID")
    cand = gpd.read_file(CAND/"candidates.gdb", layer="candidates")
    county = gpd.read_file(LIB/"buildings.gdb", layer="building_heights")
    idx = json.loads((REVIEW/"index.json").read_text(encoding="utf-8"))
    group = {it["id"]: it["group"] for it in idx["items"]}
    rows = []

    def add(item_id, kind, area, sid):
        r = {"ITEM_ID": item_id, "KIND": kind, "AREA_M2": round(area, 1), "US_ID": sid}
        if sid is not None:
            s = usi.loc[sid]
            r.update(US_OCC=s.OCC_CLS, US_PRIM=s.PRIM_OCC, US_OUTBLDG=s.OUTBLDG, US_HEIGHT=s.HEIGHT,
                     US_SQM=round(float(s.SQMETERS), 1) if s.SQMETERS == s.SQMETERS else None,
                     US_IMAGE_DATE=s.IMAGE_DATE, US_SOURCE=s.SOURCE)
        rows.append(r)
    for (cid, area), sid in zip(zip(cand.CAND_ID, cand.FOOTPRINT_M2), overlaps(cand, us, "US_ID")):
        add(cid, "candidate", area, sid)
    low = county[county.ROOF_COV_PCT.isna() | (county.ROOF_COV_PCT < 10)]
    for (fid, area), sid in zip(zip(low.SOURCE_ID, low.FOOTPRINT_M2), overlaps(low, us, "US_ID")):
        add(f"CF{fid}", "county_no_roof", area, sid)
    # the county layer as a whole, for context
    all_match = overlaps(county, us, "US_ID")
    # new-building hints: a structure at least half inside the hint box
    hints = gpd.read_file(COMPARE, layer="overture_buildings", where="MATCH = 'OVERTURE_ONLY' AND LIDAR = 'NO_ROOF'")
    hints = hints.sort_values("id").reset_index(drop=True)
    tree = gpd.GeoSeries(us.geometry).sindex
    for k, h in hints.iterrows():
        box = gpd.GeoSeries([h.geometry.buffer(5).envelope]).iloc[0]
        inside = [j for j in tree.query(box, "intersects") if us.geometry.iloc[j].intersection(box).area
                  >= 0.5 * us.geometry.iloc[j].area]
        sid = us.US_ID.iloc[max(inside, key=lambda j: us.geometry.iloc[j].area)] if inside else None
        add(f"NB{k + 1:04d}", "newbuild_hint", box.area, sid)
    v = pd.DataFrame(rows)
    v["GROUP"] = v.ITEM_ID.map(group)
    v.to_csv(out/"votes.csv", index=False)

    def share(d):
        return {"n": int(len(d)), "in_usa_structures": int(d.US_ID.notna().sum()),
                "share": round(float(d.US_ID.notna().mean()), 3) if len(d) else None}
    c = v[v.KIND == "candidate"]
    big = c[c.AREA_M2 >= MIN_M2]
    lidar_flight = "2023-11-30"
    nb = v[v.KIND == "newbuild_hint"]
    cf = v[v.KIND == "county_no_roof"]
    matched_us = {s for s in all_match if s is not None} | set(c.US_ID.dropna())
    us_only = us[~us.US_ID.isin(matched_us) & (us.geometry.area >= MIN_M2)]
    summary = {
        "usa_structures_in_city": len(us), "attribution": ATTRIBUTION,
        "image_dates": us.IMAGE_DATE.value_counts().head(10).to_dict(),
        "county_footprints_in_usa_structures": share(pd.DataFrame({"US_ID": all_match})),
        "candidates_all": share(c), "candidates_42m2_and_over": share(big),
        "candidates_42m2_and_over_by_group": {g: share(d) for g, d in big.groupby("GROUP")},
        "county_no_roof": share(cf), "county_no_roof_42m2_and_over": share(cf[cf.AREA_M2 >= MIN_M2]),
        "county_no_roof_imagery_after_lidar": int((cf.US_IMAGE_DATE > lidar_flight).sum()),
        "newbuild_hints": share(nb), "newbuild_hints_imagery_after_lidar": int((nb.US_IMAGE_DATE > lidar_flight).sum()),
        "usa_structures_in_no_county_or_candidate": int(len(us_only)),
    }
    (out/"compare.json").write_text(json.dumps(summary, indent=1, default=str), encoding="utf-8")
    us_only[["US_ID", "OCC_CLS", "PRIM_OCC", "OUTBLDG", "HEIGHT", "SQMETERS", "IMAGE_DATE", "geometry"]].to_file(
        out/"usa_structures.gpkg", layer="not_in_county_or_candidates", driver="GPKG")
    print(json.dumps(summary, indent=1, default=str))


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("step", choices=("fetch", "compare"))
    p.add_argument("out", type=Path)
    a = p.parse_args(argv)
    {"fetch": fetch, "compare": compare}[a.step](a.out.resolve())


if __name__ == "__main__":
    main()
