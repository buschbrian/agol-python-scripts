r"""Candidate footprints (October 23, 2026): Overture buildings on a 2023 LiDAR roof with no county footprint, with the
county footprints' roof-height statistics, ready for a Field Maps review and for massing.

    python reviews/2026-10-23/footprint-candidates/footprint_candidates.py check OUT     method check only
    python reviews/2026-10-23/footprint-candidates/footprint_candidates.py build OUT     check, then OUT\candidates.gdb
    python reviews/2026-10-23/footprint-candidates/footprint_candidates.py web OUT       OUT\web.gdb (Web Mercator)
    python reviews/2026-10-23/footprint-candidates/footprint_candidates.py pilot OUT     LOD1.2 blocks for 20 candidates
    python reviews/2026-10-23/footprint-candidates/footprint_candidates.py massing OUT   LOD1.2 blocks for all of them

ArcGIS Pro Python with 3D Analyst and Spatial Analyst (env millcreek-py3, PYTHONNOUSERSITE=1, -I). Read-only on the
Overture extract and the October 22 library; writes only under OUT. Nothing is uploaded and no county or city data is
edited.
- Which buildings: `lidar-compare\overture_vs_lidar.gpkg / overture_buildings` rows with MATCH = OVERTURE_ONLY and
  LIDAR = ROOF, by Overture id. Their outlines are read from `buildings.parquet` (WGS84) and projected to EPSG 6341 with
  WGS_1984_(ITRF08)_To_NAD_1983_2011, the transformation the county footprints came in with and every hosted package uses.
- Roof statistics: `summarize()` from the October 19 `summarize_city_buildings.py`, the code that made
  `buildings.gdb/building_heights`, on the library's `roof_elevation_m.tif` and `terrain_m.tif`, clipped to the same
  municipal boundary. `check` first reruns it on 2,000 county footprints and requires every field to equal
  `building_heights` exactly, and `build` repeats that script's ArcGIS CELL_CENTER rasterization pilot on the candidates.
- Nearest county footprint (GenerateNearTable, planar metres) and the parcel holding most of the outline (the 2025-tax-year
  snapshot, `city-count-20261008\inputs.gdb\parcels`).
- Empty review fields for Field Maps: REVIEW_STATUS (coded domain ACCEPT / REJECT / UNSURE), REVIEW_NOTE, REVIEWER.
- `web`: a Web Mercator copy by the October 22 feature-layer code (`prepare_features.project` and `projection_check`).
- `pilot` / `massing`: flat LOD1.2 blocks by the October 22 massing method (Extract LOD2 Buildings on the consensus roof,
  terrain elsewhere), then the same empty-block cleanup and summaries.
"""
import argparse
import collections
import datetime
import importlib.util
import json
from pathlib import Path
import random
import sys

import numpy as np

HERE = Path(__file__).resolve()
TOOLBOX = HERE.parents[3]
REVIEWS = HERE.parents[2]
sys.path.insert(0, str(TOOLBOX))
sys.path.insert(0, str(REVIEWS/"2026-10-19"))
from canopy.lidar_root import lidar_root  # noqa: E402

VALLEY = lidar_root()/"2023-salt-lake-valley"
LIB = VALLEY/"runs"/"millcreek-products-20261022"
BUILDINGS = LIB/"buildings.gdb"/"building_heights"
ROOF = LIB/"roof_elevation_m.tif"
TERRAIN = LIB/"terrain_m.tif"
TERRAIN_CONTEXT = VALLEY/"runs"/"millcreek-products-20261019"/"terrain_context.tif"
INPUTS = VALLEY/"runs"/"city-count-20261008"/"inputs.gdb"
BOUNDARY, PARCELS = INPUTS/"municipal_boundary", INPUTS/"parcels"
COUNTY_FETCH = VALLEY/"runs"/"millcreek-products-20261019"/"footprints"
OVERTURE = Path(r"Z:\GIS\overture\2026-10-21.0\millcreek")
COMPARE = OVERTURE/"lidar-compare"/"overture_vs_lidar.gpkg"
SELECT = "MATCH = 'OVERTURE_ONLY' AND LIDAR = 'ROOF'"
TRANSFORM = "WGS_1984_(ITRF08)_To_NAD_1983_2011"
CRS = 6341
CHECK_SAMPLE = 2000
SIZES = ((0, 20, "under 20 m2"), (20, 40, "20-40 m2"), (40, 80, "40-80 m2"), (80, 150, "80-150 m2"),
         (150, 300, "150-300 m2"), (300, 1e12, "300 m2 and over"))
SOURCES = {"OpenStreetMap": "OSM", "Microsoft ML Buildings": "Microsoft ML",
           "Microsoft ML Buildings; OpenStreetMap": "OSM + Microsoft ML", "Esri Community Maps": "Esri Community Maps"}
REVIEW_CODES = (("ACCEPT", "Accept: a building the county layer lacks"), ("REJECT", "Reject: not a building"),
                ("UNSURE", "Unsure"))
ALIASES = {
    "OVERTURE_ID": "Overture building ID", "SOURCES": "Outline source", "SOURCE_DATASETS": "Overture source datasets",
    "OSM_RECORD": "OpenStreetMap record", "OV_CLASS": "Overture class", "OV_SUBTYPE": "Overture subtype",
    "OV_HEIGHT_M": "Overture height (m, Microsoft ML estimate)", "SIZE_CLASS": "Size class",
    "FOOTPRINT_M2": "Outline area (m2)", "AOI_PCT": "Outline inside the city (%)",
    "ROOF_COV_PCT": "Roof support (% of outline cells)", "ROOF_Z50_M": "Median roof elevation (m, NAVD88)",
    "GROUND_Z50_M": "Median ground elevation (m, NAVD88)", "HEIGHT_P50_M": "Median roof height (m)",
    "HEIGHT_P95_M": "95th percentile roof height (m)", "HEIGHT_MAX_M": "Maximum roof height (m)",
    "GRID_CELLS": "Outline cells", "ROOF_CELLS": "Roof cells", "NEG_H_CELLS": "Cells with roof below terrain",
    "PARTIAL_AOI": "Partly outside the city", "HEIGHT_STATUS": "Height flags",
    "NEAR_FP_SOURCE_ID": "Nearest county building ID", "NEAR_FP_DIST_M": "Distance to nearest county building (m)",
    "NEAR_FP_PARCEL_ID": "Nearest county building's parcel",
    "PARCEL_ID": "Parcel ID (2025 tax year)", "PARCEL_ADDRESS": "Parcel address (2025 tax year)",
    "SAME_PARCEL": "Same parcel as nearest county building",
    "REVIEW_STATUS": "Review decision", "REVIEW_NOTE": "Review note", "REVIEWER": "Reviewer",
}
PILOT_N = 20
WARNING_EXTRA = (" Candidate outlines are Overture Maps buildings (OpenStreetMap, Microsoft ML Buildings, Esri Community "
                 "Maps), not county footprints; they have not been reviewed.")


def _module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _json(path, data):
    Path(path).write_text(json.dumps(data, indent=1, default=str), encoding="utf-8")


def _city():
    import arcpy
    parts = [r[0] for r in arcpy.da.SearchCursor(str(BOUNDARY), ["SHAPE@"])]
    city = parts[0]
    for part in parts[1:]:
        city = city.union(part)
    return city


def _windows():
    import summarize_city_buildings as scb
    return scb.Windows({"terrain": str(TERRAIN), "roof_elevation": str(ROOF)})


def method_check(out):
    """Rerun the building_heights zonal code on county footprints; every field must be equal, not close."""
    import arcpy
    import summarize_city_buildings as scb
    from canopy import common
    windows, city = _windows(), _city()
    rows = list(arcpy.da.SearchCursor(str(BUILDINGS), ["SOURCE_ID", "SHAPE@"] + scb.FIELDS))
    sample = random.Random(1).sample(rows, CHECK_SAMPLE)
    differing = collections.Counter()
    examples, rows_differing, fallbacks = [], 0, 0
    with common.scratch() as (_, scratch_gdb):
        for row in sample:
            got, fallback = scb.summarize(row[1], city, windows, scratch_gdb)
            fallbacks += fallback
            stored = dict(zip(scb.FIELDS, row[2:]))
            stored["HEIGHT_STATUS"] = stored["HEIGHT_STATUS"].replace(";GEOMETRY_REPAIRED", "")
            bad = [f for f in scb.FIELDS if got[f] != stored[f]]
            differing.update(bad)
            rows_differing += bool(bad)
            if bad and len(examples) < 10:
                examples.append({"SOURCE_ID": row[0], **{f: [got[f], stored[f]] for f in bad}})
    result = {"footprints": len(rows), "sample": len(sample), "seed": 1, "fields": scb.FIELDS,
              "rows_differing": rows_differing, "field_differences": dict(differing), "examples": examples,
              "boundary_fallbacks": fallbacks, "exact": not rows_differing,
              "rasters": {"roof_elevation": str(ROOF), "terrain": str(TERRAIN)}, "boundary": str(BOUNDARY)}
    _json(out/"method-check.json", result)
    print("method check:", json.dumps({k: result[k] for k in ("sample", "exact", "field_differences")}), flush=True)
    return result


def overture_rows():
    """The selected buildings by id, with their WGS84 outline and attributes from buildings.parquet."""
    import duckdb
    import geopandas as gpd
    sel = gpd.read_file(COMPARE, layer="overture_buildings", where=SELECT)
    ids = list(sel["id"])
    assert len(ids) == len(set(ids))
    rows = duckdb.connect().execute(f"""
        select b.id, b.source_datasets, b.class, b.subtype, b.height, b.names.primary as name,
               [s.record_id for s in b.sources if s.dataset = 'OpenStreetMap'] as osm, b.geometry
        from '{OVERTURE/"buildings.parquet"}' b where list_contains(?, b.id) order by b.id""", [ids]).fetchall()
    assert len(rows) == len(ids), (len(rows), len(ids))
    return sel, rows


def size_class(area):
    return next(label for lo, hi, label in SIZES if lo <= area < hi)


def _add_review_fields(gdb, fc):
    import arcpy
    arcpy.management.CreateDomain(gdb, "REVIEW_STATUS", "Footprint candidate review decision", "TEXT", "CODED")
    for code, text in REVIEW_CODES:
        arcpy.management.AddCodedValueToDomain(gdb, "REVIEW_STATUS", code, text)
    arcpy.management.AddField(fc, "REVIEW_STATUS", "TEXT", field_length=10, field_alias=ALIASES["REVIEW_STATUS"])
    arcpy.management.AssignDomainToField(fc, "REVIEW_STATUS", "REVIEW_STATUS")
    arcpy.management.AddField(fc, "REVIEW_NOTE", "TEXT", field_length=500, field_alias=ALIASES["REVIEW_NOTE"])
    arcpy.management.AddField(fc, "REVIEWER", "TEXT", field_length=100, field_alias=ALIASES["REVIEWER"])


def build(out):
    import arcpy
    import shapely
    import summarize_city_buildings as scb
    from canopy import common, planning
    done = out/"method-check.json"
    check = json.loads(done.read_text(encoding="utf-8")) if done.exists() else method_check(out)
    if not check["exact"]:
        raise RuntimeError("The zonal code does not reproduce building_heights; candidate figures not computed")
    sel, rows = overture_rows()
    print(f"{len(rows)} candidates", flush=True)
    wgs, sr = arcpy.SpatialReference(4326), arcpy.SpatialReference(CRS)
    arcpy.env.geographicTransformations = None
    gdb = arcpy.management.CreateFileGDB(str(out), "candidates.gdb")[0]
    fc = str(Path(gdb)/"candidates")
    arcpy.management.CreateFeatureclass(gdb, "candidates", "POLYGON", spatial_reference=sr)
    text = [("OVERTURE_ID", 64), ("SOURCES", 30), ("SOURCE_DATASETS", 80), ("OSM_RECORD", 40), ("OV_CLASS", 40),
            ("OV_SUBTYPE", 40), ("SIZE_CLASS", 20)]
    for name, length in text:
        arcpy.management.AddField(fc, name, "TEXT", field_length=length, field_alias=ALIASES[name])
    arcpy.management.AddField(fc, "OV_HEIGHT_M", "DOUBLE", field_alias=ALIASES["OV_HEIGHT_M"])
    for name in scb.NUMERIC:
        arcpy.management.AddField(fc, name, "DOUBLE", field_alias=ALIASES[name])
    for name in scb.INTEGER:
        arcpy.management.AddField(fc, name, "LONG", field_alias=ALIASES[name])
    arcpy.management.AddField(fc, "HEIGHT_STATUS", "TEXT", field_length=160, field_alias=ALIASES["HEIGHT_STATUS"])
    for name, kind, length in (("NEAR_FP_SOURCE_ID", "TEXT", 40), ("NEAR_FP_DIST_M", "DOUBLE", None),
                               ("NEAR_FP_PARCEL_ID", "TEXT", 25), ("PARCEL_ID", "TEXT", 25),
                               ("PARCEL_ADDRESS", "TEXT", 75), ("SAME_PARCEL", "TEXT", 3)):
        arcpy.management.AddField(fc, name, kind, field_length=length, field_alias=ALIASES[name])
    _add_review_fields(gdb, fc)

    windows, city = _windows(), _city()
    entries, compare_shift = [], []
    by_id = sel.set_index("id")
    for oid_, src, cls, sub, height, name, osm, wkb in rows:
        shape = arcpy.FromWKB(bytes(wkb), wgs).projectAs(sr, TRANSFORM)
        # the comparison's outline should be this one (it was projected the same way since its 11:31 rerun)
        old = by_id.loc[oid_, "geometry"]
        new = shapely.from_wkb(bytes(shape.WKB))
        compare_shift.append(float(shapely.hausdorff_distance(old, new)))
        entries.append((oid_, shape, src, cls, sub, height, osm))
    with arcpy.da.InsertCursor(fc, ["SHAPE@", "OVERTURE_ID", "SOURCES", "SOURCE_DATASETS", "OSM_RECORD", "OV_CLASS",
                                    "OV_SUBTYPE", "SIZE_CLASS", "OV_HEIGHT_M"]) as cursor:
        for oid_, shape, src, cls, sub, height, osm in entries:
            cursor.insertRow([shape, oid_, SOURCES[src], src, osm[0] if osm else None, cls, sub,
                              size_class(shape.area), height])
    # Statistics on the stored (resolution-snapped) shapes, as building_heights was measured on its stored copy;
    # the unsnapped shapes clip to the city with a sliver of difference and would all be flagged PARTIAL_AOI.
    stored = list(arcpy.da.SearchCursor(fc, ["OVERTURE_ID", "SHAPE@"]))
    with common.scratch() as (_, scratch_gdb):
        pilot = scb.pilot(stored, city, windows, scratch_gdb)
        print(f"rasterization pilot: {len(pilot)} ArcGIS CELL_CENTER matches", flush=True)
        fallbacks = 0
        with arcpy.da.UpdateCursor(fc, ["SHAPE@"] + scb.FIELDS) as cursor:
            for i, row in enumerate(cursor, 1):
                summary, fallback = scb.summarize(row[0], city, windows, scratch_gdb)
                fallbacks += fallback
                cursor.updateRow([row[0]] + [summary[f] for f in scb.FIELDS])
                if i % 250 == 0:
                    print(f"  {i}/{len(entries)}", flush=True)

    # nearest county footprint
    near = str(Path(gdb)/"near_tmp")
    arcpy.analysis.GenerateNearTable(fc, str(BUILDINGS), near, closest="CLOSEST", method="PLANAR")
    county = {r[0]: r[1:] for r in arcpy.da.SearchCursor(str(BUILDINGS), ["OID@", "SOURCE_ID", "PARCEL_ID"])}
    nearest = {r[0]: (r[1], r[2]) for r in arcpy.da.SearchCursor(near, ["IN_FID", "NEAR_FID", "NEAR_DIST"])}
    arcpy.management.Delete(near)
    # parcel holding most of each outline
    pgeom, pid = [], []
    for wkb, parcel, address in arcpy.da.SearchCursor(str(PARCELS), ["SHAPE@WKB", "parcel_id", "prop_location"]):
        pgeom.append(shapely.from_wkb(bytes(wkb)))
        pid.append((parcel, address.strip() if address and address.strip() else None))
    tree = shapely.STRtree(pgeom)
    with arcpy.da.UpdateCursor(fc, ["OID@", "SHAPE@WKB", "NEAR_FP_SOURCE_ID", "NEAR_FP_DIST_M", "NEAR_FP_PARCEL_ID",
                                    "PARCEL_ID", "PARCEL_ADDRESS", "SAME_PARCEL"]) as cursor:
        for oid, wkb, *_ in cursor:
            g = shapely.from_wkb(bytes(wkb))
            hits = [(shapely.intersection(g, pgeom[j]).area, j) for j in tree.query(g, "intersects")]
            parcel, address = pid[max(hits)[1]] if hits and max(hits)[0] > 0 else (None, None)
            fid, dist = nearest.get(oid, (None, None))
            source_id, fp_parcel = county[fid] if fid is not None else (None, None)
            same = None if not parcel or not fp_parcel else ("YES" if _pnorm(parcel) == _pnorm(fp_parcel) else "NO")
            cursor.updateRow([oid, wkb, source_id, dist, fp_parcel, parcel, address, same])
    dropped = dropped_county_overlaps(fc, gdb)
    planning._metadata(fc, "Candidate building footprints: Overture Maps 2026-10-21.0 buildings that sit on a 2023 LiDAR "
                           "roof (at least 50% consensus roof cells) but match no county footprint. Roof statistics by "
                           "the county building_heights code: roof minus interpolated terrain at paired cell centres. "
                           "For review; REVIEW_STATUS is empty until reviewed." + WARNING_EXTRA)
    count = int(arcpy.management.GetCount(fc)[0])
    assert count == len(sel), (count, len(sel))
    record = {"schema": "footprint-candidates/1", "created": datetime.datetime.now().isoformat(timespec="seconds"),
              "selection": {"source": str(COMPARE), "layer": "overture_buildings", "where": SELECT, "n": len(sel)},
              "outlines": {"source": str(OVERTURE/"buildings.parquet"), "transformation": TRANSFORM, "crs": CRS,
                           "hausdorff_m_vs_comparison_outline": _q(compare_shift)},
              "rasters": {"roof_elevation": str(ROOF), "terrain": str(TERRAIN), "boundary": str(BOUNDARY)},
              "parcels": str(PARCELS), "county_footprints": str(BUILDINGS),
              "method_check": {k: check[k] for k in ("sample", "exact", "field_differences")},
              "rasterization_pilot": pilot, "boundary_fallbacks": fallbacks, "output": fc, "count": count,
              "boundary_candidates_vs_dropped_county_footprints": dropped}
    record["summary"] = summarize_candidates(fc, sel)
    _json(out/"candidates.json", record)
    print(json.dumps(record["summary"]["headline"], indent=1), flush=True)


def dropped_county_overlaps(fc, gdb):
    """County footprints were kept when they touch the city, so only a candidate that crosses the boundary can hide a
    county footprint lying wholly outside it. Overlap of those candidates with the county's full fetch."""
    import arcpy
    import shapely
    fetch = json.loads((COUNTY_FETCH/"footprints.json").read_text(encoding="utf-8"))
    kept = {r[0] for r in arcpy.da.SearchCursor(str(BUILDINGS), ["SOURCE_ID"])}
    native = str(COUNTY_FETCH/"footprints.gdb"/"county_native")
    projected = str(Path(gdb)/"county_native_tmp")
    arcpy.management.Project(native, projected, arcpy.SpatialReference(CRS),
                             [t.strip() for t in fetch["transform"].split("+")])
    county = [(sid, shapely.from_wkb(bytes(w))) for sid, w in arcpy.da.SearchCursor(projected, ["SOURCE_ID", "SHAPE@WKB"])
              if sid not in kept]
    arcpy.management.Delete(projected)
    tree = shapely.STRtree([g for _, g in county])
    out = []
    for oid, overture_id, aoi, wkb in arcpy.da.SearchCursor(fc, ["OID@", "OVERTURE_ID", "AOI_PCT", "SHAPE@WKB"]):
        if aoi >= 100 - 1e-6:
            continue
        g = shapely.from_wkb(bytes(wkb))
        hits = [(county[j][0], shapely.intersection(g, county[j][1]).area / g.area) for j in tree.query(g, "intersects")]
        out.append({"OBJECTID": oid, "OVERTURE_ID": overture_id, "AOI_PCT": round(aoi, 2),
                    "dropped_county_overlap": [(s, round(f, 3)) for s, f in hits if f > 0]})
    return {"county_fetched": int(fetch["fetched"]), "kept_in_city": len(kept), "dropped": len(county),
            "boundary_candidates": len(out), "with_overlap_over_10pct": sum(
                1 for r in out if any(f > 0.1 for _, f in r["dropped_county_overlap"])), "candidates": out}


def _pnorm(parcel):
    return "".join(ch for ch in str(parcel) if ch.isalnum())


def _q(values, ps=(5, 25, 50, 75, 95)):
    v = np.array([x for x in values if x is not None and x == x], float)
    if not len(v):
        return {"n": 0}
    return {"n": int(len(v)), **{f"p{p:02d}": round(float(np.percentile(v, p)), 2) for p in ps},
            "max": round(float(v.max()), 2)}


def summarize_candidates(fc, sel):
    import arcpy
    import pandas as pd
    cols = ["OVERTURE_ID", "SOURCES", "OV_CLASS", "OV_SUBTYPE", "SIZE_CLASS", "FOOTPRINT_M2", "ROOF_COV_PCT",
            "HEIGHT_P50_M", "HEIGHT_P95_M", "HEIGHT_MAX_M", "HEIGHT_STATUS", "NEAR_FP_DIST_M", "PARCEL_ID", "SAME_PARCEL"]
    df = pd.DataFrame(list(arcpy.da.SearchCursor(fc, cols)), columns=cols)
    order = [label for _, _, label in SIZES]
    df["SIZE_CLASS"] = pd.Categorical(df["SIZE_CLASS"], order, ordered=True)
    df["OV_CLASS"] = df["OV_CLASS"].fillna("(none)")
    df["OV_SUBTYPE"] = df["OV_SUBTYPE"].fillna("(none)")
    old = sel.set_index("id")["L_ROOF_COV_PCT"]
    df["ROOF_COV_CHANGE"] = df["ROOF_COV_PCT"] - df["OVERTURE_ID"].map(old)

    def table(col):
        t = pd.crosstab(df[col], df["SIZE_CLASS"], dropna=False)
        t["all"] = t.sum(axis=1)
        return t.sort_values("all", ascending=False).to_dict(orient="index")
    flags = collections.Counter(f for s in df["HEIGHT_STATUS"] for f in s.split(";"))
    return {
        "headline": {"candidates": len(df), "with_height": int(df["HEIGHT_P50_M"].notna().sum()),
                     "roof_cov_under_50_on_these_outlines": int((df["ROOF_COV_PCT"] < 50).sum()),
                     "roof_cov_under_80": int((df["ROOF_COV_PCT"] < 80).sum()),
                     "area_m2": _q(df["FOOTPRINT_M2"]), "height_p95_m": _q(df["HEIGHT_P95_M"]),
                     "roof_cov_pct": _q(df["ROOF_COV_PCT"]),
                     "roof_cov_change_vs_comparison_pct_points": _q(df["ROOF_COV_CHANGE"]),
                     "near_county_footprint_m": _q(df["NEAR_FP_DIST_M"]),
                     "no_parcel": int(df["PARCEL_ID"].isna().sum()),
                     "same_parcel_as_nearest_county_building": df["SAME_PARCEL"].fillna("(unknown)").value_counts().to_dict()},
        "by_size": {str(k): {"n": int(len(g)), "height_p50_m": _q(g["HEIGHT_P50_M"]), "height_p95_m": _q(g["HEIGHT_P95_M"]),
                             "roof_cov_pct": _q(g["ROOF_COV_PCT"])}
                    for k, g in df.groupby("SIZE_CLASS", observed=False)},
        "class_by_size": table("OV_CLASS"), "subtype_by_size": table("OV_SUBTYPE"), "sources_by_size": table("SOURCES"),
        "height_status_flags": dict(flags),
        "height_p95_bands": pd.cut(df["HEIGHT_P95_M"], [-100, 2, 3, 4.5, 6, 9, 100],
                                   labels=["under 2 m", "2-3 m", "3-4.5 m", "4.5-6 m", "6-9 m", "9 m and over"]
                                   ).value_counts(sort=False).to_dict(),
    }


def web(out):
    """Web Mercator copy with the October 22 feature-layer projection and its vertex check."""
    import arcpy
    pf = _module(REVIEWS/"2026-10-22"/"hosting"/"feature-layers"/"prepare_features.py", "prepare_features")
    assert pf.TRANSFORM == TRANSFORM
    work = out/"candidates.gdb"
    gdb = Path(arcpy.management.CreateFileGDB(str(out), "web.gdb")[0])
    path = pf.project(work, gdb, "candidates")
    from canopy import planning
    planning._metadata(path, (arcpy.metadata.Metadata(str(work/"candidates")).description or "").split("\n\n")[0] +
                       " Projected to Web Mercator with " + TRANSFORM + "." + WARNING_EXTRA)
    check = pf.projection_check(work, gdb, "candidates")
    domains = {d.name: dict(d.codedValues) for d in arcpy.da.ListDomains(str(gdb))}
    assigned = {f.name: f.domain for f in arcpy.ListFields(path) if f.domain}
    check.update(domains=domains, fields_with_domain=assigned)
    assert check["features"] == check["projected"] and check["attribute_rows_differing"] == 0
    assert check["vertex_count_mismatches"] == 0 and check["max_vertex_distance_m_vs_transformed"] < 0.001
    assert assigned.get("REVIEW_STATUS") == "REVIEW_STATUS" and set(domains.get("REVIEW_STATUS", {})) == {
        c for c, _ in REVIEW_CODES}
    record = json.loads((out/"candidates.json").read_text(encoding="utf-8"))
    record["web"] = {"output": path, "coordinate_system": "WGS 1984 Web Mercator (auxiliary sphere), EPSG 3857",
                     "transformation": TRANSFORM, "check": check}
    _json(out/"candidates.json", record)
    print(json.dumps(check, indent=1), flush=True)


def massing(out, pilot):
    """LOD1.2 blocks by the October 22 method; FP_ID is the candidate's OBJECTID in candidates.gdb/candidates."""
    import arcpy
    from arcpy.sa import Con, IsNull, Raster
    from canopy import planning
    rm = _module(REVIEWS/"2026-10-22"/"massing"/"run_massing.py", "run_massing")
    assert Path(rm.ROOF) == ROOF and Path(rm.TERRAIN) == TERRAIN_CONTEXT
    arcpy.CheckOutExtension("3D")
    arcpy.CheckOutExtension("Spatial")
    source = str(out/"candidates.gdb"/"candidates")
    rows = sorted(arcpy.da.SearchCursor(source, ["OID@", "FOOTPRINT_M2", "SHAPE@"], "ROOF_Z50_M IS NOT NULL"),
                  key=lambda r: r[1])
    if pilot:
        rows = [rows[i] for i in np.linspace(0, len(rows)-1, PILOT_N, dtype=int)]
    target = out/("massing-pilot" if pilot else "massing")
    target.mkdir(exist_ok=False)
    gdb = Path(arcpy.management.CreateFileGDB(str(target), "massing.gdb")[0])
    footprints = str(gdb/"footprints")
    oids = [r[0] for r in rows]
    layer = arcpy.management.MakeFeatureLayer(source, "cand", f"OBJECTID IN ({','.join(map(str, oids))})").getOutput(0)
    arcpy.management.CopyFeatures(layer, footprints)
    arcpy.management.AddField(footprints, "FP_ID", "LONG")
    with arcpy.da.UpdateCursor(footprints, ["OVERTURE_ID", "FP_ID"]) as cursor:
        ids = {r[0]: r[1] for r in arcpy.da.SearchCursor(source, ["OVERTURE_ID", "OID@"])}
        for overture_id, _ in cursor:
            cursor.updateRow([overture_id, ids[overture_id]])
    ext = arcpy.Describe(footprints).extent
    window = (ext.XMin-50, ext.YMin-50, ext.XMax+50, ext.YMax+50)
    dsm = str(target/"height_source.tif")
    with arcpy.EnvManager(scratchWorkspace=str(target), extent=" ".join(map(str, window)), snapRaster=str(ROOF),
                          cellSize=str(ROOF), compression="LZW", parallelProcessingFactor="100%"):
        Con(IsNull(Raster(str(ROOF))), Raster(str(TERRAIN_CONTEXT)), Raster(str(ROOF))).save(dsm)
    n = int(arcpy.management.GetCount(footprints)[0])
    print(f"{n} footprints", flush=True)
    tmin = rm.terrain_min(footprints, gdb, target)
    lod = str(gdb/"lod12")
    started = datetime.datetime.now()
    with arcpy.EnvManager(scratchWorkspace=str(target)):
        arcpy.ddd.ExtractLOD2Buildings(dsm, footprints, lod, "LOD1.2")
    seconds = round((datetime.datetime.now()-started).total_seconds())
    from_tool = int(arcpy.management.GetCount(lod)[0])
    rm.annotate(lod, tmin)
    planning._metadata(lod, "3D massing, LOD1.2, of the footprint candidates (Overture outlines with no county footprint) "
                            "from the consensus roof surface (Extract LOD2 Buildings). Heights are roof-minus-terrain "
                            "estimates, not code-defined building heights." + WARNING_EXTRA)
    # the October 22 cleanup: drop empty features (zero area, Z = 0)
    removed = []
    with arcpy.da.UpdateCursor(lod, ["SHAPE@", "FP_ID"]) as cursor:
        for shape, fp in cursor:
            if shape is None or shape.area == 0 or shape.extent.ZMax == 0:
                removed.append(fp)
                cursor.deleteRow()
    kept = [r[0] for r in arcpy.da.SearchCursor(lod, ["FP_ID"])]
    high = [{"FP_ID": fp, "base_minus_terrain_min": round(d, 2), "block_height": round(t-b, 2)}
            for fp, d, b, t in arcpy.da.SearchCursor(lod, ["FP_ID", "BASE_MINUS_TMIN", "BASE_Z", "TOP_Z"])
            if d is not None and d > 2]
    off = [{"FP_ID": fp, "top_minus_roof50": round(d, 2), "roof_cov_pct": round(c, 1)}
           for fp, d, c in arcpy.da.SearchCursor(lod, ["FP_ID", "TOP_MINUS_ROOF50", "ROOF_COV_PCT"])
           if d is not None and abs(d) > 1]
    result = {"schema": "massing/1", "method": "reviews/2026-10-22/massing/run_massing.py (LOD1.2 only)",
              "pilot": pilot, "footprints": n, "fp_ids": oids if pilot else None, "window": window,
              "height_source": {"roof": str(ROOF), "terrain": str(TERRAIN_CONTEXT), "path": dsm},
              "tool": "arcpy.ddd.ExtractLOD2Buildings(height_source, footprints, out, 'LOD1.2'), defaults otherwise",
              "seconds": seconds, "features_from_tool": from_tool, "removed_empty": sorted(removed), "blocks": len(kept),
              "footprints_with_a_block": len(set(kept)), "footprints_with_two_blocks": len(kept)-len(set(kept)),
              "fp_ids_with_two_blocks": sorted(fp for fp, c in collections.Counter(kept).items() if c > 1),
              "footprints_without_a_block": sorted(set(oids)-set(kept)),
              "base_over_2m_above_terrain_min": high, "top_over_1m_from_roof50": off,
              "summary": rm.summary(lod), "warning": planning.WARNING}
    _json(target/"massing.json", result)
    print(json.dumps({k: v for k, v in result.items() if k not in ("fp_ids", "summary")}, indent=1), flush=True)
    print(json.dumps(result["summary"]["top_minus_roof50"]), json.dumps(result["summary"]["base_minus_terrain_min"]))


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("step", choices=("check", "build", "web", "pilot", "massing"))
    p.add_argument("out", type=Path)
    a = p.parse_args(argv)
    out = a.out.resolve()
    if a.step in ("check", "build"):
        out.mkdir(parents=True, exist_ok=True)
    if a.step == "check":
        method_check(out)
    elif a.step == "build":
        build(out)
    elif a.step == "web":
        web(out)
    else:
        massing(out, a.step == "pilot")


if __name__ == "__main__":
    main()
