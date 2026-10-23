r"""Build the data for the footprint review page (October 23, 2026).

    python -I reviews/2026-10-23/footprint-review/build_review_data.py DATA [--pilot]

ArcGIS Pro env millcreek-py3 (geopandas, rasterio, duckdb, Pillow), PYTHONNOUSERSITE=1. Read-only on the library, the
LiDAR candidates, the hosted-feature copies and the Overture comparison; writes only under DATA. Three queues:
- candidates: the 6,213 LiDAR candidates (footprint-candidates-lidar-20261023), in three groups, in this order: large and
  tall (150 m2 or more and P95 at least 6 m), detached (more than 2 m from a county footprint), attached (2 m or less).
  Within a group, by CAND_ID (north to south), so neighbours come one after another. Blind to Overture.
- county: county footprints with under 10% LiDAR roof support (or none) in buildings.gdb/building_heights.
- newbuild: places where a building may have gone up after the 2023 flight. The hint list is the Overture comparison's
  OVERTURE_ONLY + NO_ROOF outlines, used internally to say where to look. The page shows a hint box (the outline's
  bounding box plus 5 m) and a marker, never the Overture outline, and items are numbered NB0001...; the id mapping stays
  in DATA/newbuild-hints.json on the SSD. Confirmed buildings are to be digitised from imagery or flagged to the county.
Items are written 50 to a file, DATA/bundles/bNNNN.json (the SSD allocates 1 MB per file, so one file per item would
take some 14 GB). Each holds the map outlines in WGS84 from the ITRF08 Web Mercator copies, the chip outlines in pixels
and the chip itself as a PNG data URI, a LiDAR view at 0.5 m: hillshade of the surface (terrain plus the higher of roof and canopy), roofs
coloured by height above terrain, canopy of 2 m or more in green. DATA/index.json lists every item in queue order with
its bundle.
"""
import argparse
import datetime
import json
import math
from pathlib import Path
import sys

import numpy as np

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[3]))
from canopy.lidar_root import lidar_root  # noqa: E402

RUNS = lidar_root()/"2023-salt-lake-valley"/"runs"
LIB = RUNS/"millcreek-products-20261022"
CAND = RUNS/"footprint-candidates-lidar-20261023"
COUNTY_WEB = RUNS/"hosting-features-20261023"/"features.gdb"     # county footprints in 3857 via ITRF08
PARCELS = RUNS/"city-count-20261008"/"inputs.gdb"/"parcels"
COMPARE = Path(r"Z:\GIS\overture\2026-10-21.0\millcreek\lidar-compare\overture_vs_lidar.gpkg")
OVERTURE_PARQUET = Path(r"Z:\GIS\overture\2026-10-21.0\millcreek\buildings.parquet")
CELL = 0.5
FEET = 3.280839895
BUNDLE = 50
GROUPS = (("large_tall", "Large and tall"), ("detached", "Detached"), ("attached", "Against a county building"))


def rings_of(geom):
    polys = [geom] if geom.geom_type == "Polygon" else list(geom.geoms)
    return [list(p.exterior.coords) for p in polys] + [list(r.coords) for p in polys for r in p.interiors]


def merc_to_ll(rings):
    """EPSG 3857 to WGS84 latitude/longitude (same datum; spherical Mercator inverse)."""
    out = []
    for ring in rings:
        out.append([[round(math.degrees(2 * math.atan(math.exp(y / 6378137.0)) - math.pi / 2), 7),
                     round(math.degrees(x / 6378137.0), 7)] for x, y in ring])
    return out


class Chips:
    def __init__(self):
        import rasterio
        self.ds = {k: rasterio.open(LIB/f) for k, f in
                   (("roof", "roof_height_m.tif"), ("chm", "chm_m.tif"), ("dtm", "terrain_m.tif"))}
        t = self.ds["roof"].transform
        for d in self.ds.values():
            assert d.transform == t and d.shape == self.ds["roof"].shape
        self.t = t

    def window(self, bounds, min_half=25.0):
        x0, y0, x1, y1 = bounds
        half = max(min_half, 0.75 * max(x1 - x0, y1 - y0) + 10)
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        left = math.floor((cx - half - self.t.c) / CELL) * CELL + self.t.c
        top = self.t.f - math.floor((self.t.f - (cy + half)) / CELL) * CELL
        n = int(round(2 * half / CELL))
        return left, top, n

    def read(self, key, left, top, n):
        from rasterio.windows import Window
        col, row = int(round((left - self.t.c) / CELL)), int(round((self.t.f - top) / CELL))
        d = self.ds[key]
        a = d.read(1, window=Window(col - 1, row - 1, n + 2, n + 2), boundless=True, fill_value=d.nodata)
        a = a.astype(np.float32)
        a[(a == d.nodata) | ~np.isfinite(a)] = np.nan
        return a

    def render(self, bounds, min_half=25.0):
        """The LiDAR view of a square window around bounds: its grid and a PNG data URI."""
        import base64
        import io
        from PIL import Image
        left, top, n = self.window(bounds, min_half)
        roof, chm, dtm = (self.read(k, left, top, n) for k in ("roof", "chm", "dtm"))
        over = np.fmax(np.nan_to_num(roof, nan=0), np.nan_to_num(chm, nan=0)).clip(min=0)
        dsm = np.nan_to_num(dtm, nan=np.nanmean(dtm) if np.isfinite(dtm).any() else 0) + over
        gy, gx = np.gradient(dsm, CELL)
        slope = np.arctan(np.hypot(gx, gy))
        aspect = np.arctan2(-gx, gy)
        az, alt = math.radians(315), math.radians(45)
        shade = (np.sin(alt) * np.cos(slope) + np.cos(alt) * np.sin(slope) * np.cos(az - aspect)).clip(0, 1)
        shade = shade[1:-1, 1:-1]
        roof, chm, dtm = roof[1:-1, 1:-1], chm[1:-1, 1:-1], dtm[1:-1, 1:-1]
        base = 0.35 + 0.65 * shade
        rgb = np.stack([base * 200, base * 200, base * 200], -1)
        canopy = np.isfinite(chm) & (chm >= 2) & ~np.isfinite(roof)
        rgb[canopy] = np.stack([base[canopy] * 60, base[canopy] * 150 + 40, base[canopy] * 60], -1)
        r = np.isfinite(roof)
        h = np.clip(np.nan_to_num(roof, nan=0) / 12.0, 0, 1)[r]            # 0 m yellow -> 6 m orange -> 12 m+ magenta
        col = np.stack([255 - 40 * h, 230 - 200 * h, 60 + 120 * h], -1)
        rgb[r] = col * (0.55 + 0.45 * base[r, None])
        rgb[~np.isfinite(dtm)] = 255
        buf = io.BytesIO()
        Image.fromarray(rgb.clip(0, 255).astype(np.uint8)).save(buf, "PNG", optimize=True)
        uri = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")
        return {"left": left, "top": top, "n": n, "cell": CELL}, uri

    @staticmethod
    def px(rings, chip):
        return [[[round((x - chip["left"]) / CELL, 2), round((chip["top"] - y) / CELL, 2)] for x, y in ring]
                for ring in rings]


def canopy_share(chips, geom):
    """Share of the outline's cell centres with canopy of 2 m or more (a hint for 'under trees')."""
    from rasterio.features import geometry_mask
    left, top, n = chips.window(geom.bounds, 5)
    chm = chips.read("chm", left, top, n)[1:-1, 1:-1]
    from rasterio.transform import from_origin
    inside = ~geometry_mask([geom], out_shape=chm.shape, transform=from_origin(left, top, CELL, CELL))
    v = chm[inside]
    return round(100 * float((np.nan_to_num(v) >= 2).mean()), 1) if v.size else None


def missing(v):
    return v is None or (isinstance(v, float) and math.isnan(v)) or (isinstance(v, str) and not v.strip())


def txt(v, fmt="{}"):
    """A fact for the page: '—' for a missing value (None, NaN or blank), else the value formatted."""
    return "—" if missing(v) else fmt.format(v)


LOT_USE = {"R": "residential", "C": "commercial", "I": "industrial"}


def pnorm(parcel):
    return None if missing(parcel) else "".join(ch for ch in str(parcel) if ch.isalnum())


def roof_form(p50, p95):
    """Flat or sloped, from the spread of roof heights: a gable rises a quarter of its span or so, so P95 - median is
    about 0.5 m or more on a pitched roof of 4 m span and up; under 0.2 m the roof is flat or nearly so."""
    if missing(p50) or missing(p95):
        return None
    d = p95 - p50
    return "flat or nearly flat" if d < 0.2 else ("low slope" if d < 0.45 else "pitched")


def likely_type(area, p95, form, near_m, lot_use, county_on_parcel, units=None, built=None):
    """A guess for the reviewer from size, height, roof form, distance to a county building and the parcel's use
    (the assessor's housing units and year built). LiDAR can't see walls, so a carport and a garage of the same size
    and roof look alike."""
    if near_m <= 2:
        return "Attached to a county building: addition, porch, patio cover or eave"
    flat_low = form == "flat or nearly flat" and p95 < 3.2
    single_home = lot_use == "R" and units == 1
    if single_home and area >= 80 and p95 >= 4.5:
        if county_on_parcel == 0:
            year = f", built {built:.0f}" if not missing(built) and built > 0 else ""
            return f"House: the parcel's main building{year}, with no county footprint"
        return "House-sized: ADU, second house or large garage with living space"
    if lot_use in ("C", "I") and area >= 40:
        kind = ("Commercial/industrial building" if p95 >= 4.5 else
                "Covered parking, canopy or low commercial structure")
    elif area < 15:
        kind = "Small shed, playhouse or shade structure"
    elif area < 40:
        kind = "Carport, shade or patio cover" if flat_low else ("Shed or single garage" if p95 < 4.5 else
                                                                 "Small tall structure (shed, tower, tree?)")
    elif area < 80:
        kind = "Carport or covered parking" if flat_low else ("Garage or large shed" if p95 < 4.5 else
                                                             "Two-storey garage or small ADU")
    elif area < 150:
        kind = "Large garage, workshop or covered parking" if p95 < 4.5 else "House-sized: ADU or unmapped house"
    elif area < 300:
        kind = "Large garage, barn or carport row" if p95 < 4.5 else "House or small multi-unit building"
    else:
        kind = ("Large low structure: covered parking, warehouse or canopy" if p95 < 4.5 else
                "Large building: apartments, commercial or institutional")
    if county_on_parcel == 0 and area >= 80 and p95 >= 4.5:
        kind += "; no county building on this parcel"
    return kind


def parcel_text(row):
    """The parcel's use and the assessor's figures, from the 2025-tax-year snapshot."""
    if row is None:
        return "—", "—"
    lot = None if missing(row.lot_use) else str(row.lot_use).strip()
    ptype = None if missing(row.property_type) else str(row.property_type).strip()
    use = f"{LOT_USE.get(lot, txt(lot))} · property type {txt(ptype)}"
    bits = []
    if not missing(row.year_built) and row.year_built > 0:
        bits.append(f"built {row.year_built:.0f}")
    if not missing(row.total_sq_ft) and row.total_sq_ft > 0:
        bits.append(f"{row.total_sq_ft:,.0f} ft² of building")
    if not missing(row.num_housing_units) and row.num_housing_units > 0:
        bits.append(f"{row.num_housing_units:.0f} unit{'s' if row.num_housing_units != 1 else ''}")
    return use, (", ".join(bits) or "—")


def candidate_facts(r, parcels, county_per_parcel):
    key = pnorm(r.PARCEL_ID)
    pr = parcels.get(key)
    on_parcel = county_per_parcel.get(key, 0) if pr is not None else None
    lot = None if pr is None or missing(pr.lot_use) else str(pr.lot_use).strip()
    form = roof_form(r.HEIGHT_P50_M, r.HEIGHT_P95_M)
    use, assessor = parcel_text(pr)
    address = "" if missing(r.PARCEL_ADDRESS) else r.PARCEL_ADDRESS
    units = None if pr is None or missing(pr.num_housing_units) else pr.num_housing_units
    built = None if pr is None else pr.year_built
    return {"Likely type (a guess)": likely_type(r.FOOTPRINT_M2, r.HEIGHT_P95_M, form, r.NEAR_FP_DIST_M, lot, on_parcel,
                                                 units, built),
            "Candidate": r.CAND_ID, "Area": f"{r.FOOTPRINT_M2:.0f} m² ({r.FOOTPRINT_M2 * 10.7639:.0f} ft²)",
            "Height (median / P95)": f"{r.HEIGHT_P50_M:.1f} / {r.HEIGHT_P95_M:.1f} m "
                                     f"({r.HEIGHT_P50_M * FEET:.0f} / {r.HEIGHT_P95_M * FEET:.0f} ft)",
            "Roof form (LiDAR)": txt(form), "Roof support": f"{r.ROOF_COV_PCT:.0f}%",
            "Nearest county building": f"{r.NEAR_FP_DIST_M:.1f} m (ID {r.NEAR_FP_SOURCE_ID})",
            "Parcel": f"{txt(r.PARCEL_ID)} {address}".strip(),
            "Parcel use": use, "Assessor (main building)": assessor,
            "County buildings on parcel": txt(on_parcel),
            "Same parcel as nearest county building": txt(r.SAME_PARCEL)}


def county_facts(r, chips, parcels):
    cov = "no roof cells" if missing(r.ROOF_COV_PCT) else f"{r.ROOF_COV_PCT:.0f}%"
    use, assessor = parcel_text(parcels.get(pnorm(r.PARCEL_ID)))
    return {"County building ID": r.SOURCE_ID, "Address": txt(r.ADDRESS), "Parcel": txt(r.PARCEL_ID),
            "Type / year built": f"{txt(r.BuildType)} / {txt(r.BuiltYear, '{:.0f}')}",
            "Area": f"{r.FOOTPRINT_M2:.0f} m² ({r.FOOTPRINT_M2 * 10.7639:.0f} ft²)",
            "2023 LiDAR roof support": cov, "Under canopy (2 m or more)": txt(canopy_share(chips, r.geometry), "{}%"),
            "Parcel use": use, "Assessor (main building)": assessor, "Height flags": txt(r.HEIGHT_STATUS)}


def newbuild_facts(item, r, chips, county, parcels, parcel_of):
    x0, y0, x1, y1 = r.geometry.buffer(5).bounds
    near = county.geometry.distance(r.geometry.centroid).min()
    use, assessor = parcel_text(parcels.get(pnorm(parcel_of)))
    return {"Hint": item, "Hint box": f"{(x1 - x0):.0f} × {(y1 - y0):.0f} m",
            "Nearest county building": f"{near:.1f} m",
            "2023 LiDAR roof under it": txt(r.L_ROOF_COV_PCT, "{:.0f}%"),
            "Under canopy (2 m or more)": txt(canopy_share(chips, r.geometry), "{}%"),
            "Parcel": txt(parcel_of), "Parcel use": use, "Assessor (main building)": assessor}


def load_parcels():
    """The 2025-tax-year parcel snapshot: attributes by normalised parcel id, and the frame for point lookups."""
    import geopandas as gpd
    p = gpd.read_file(PARCELS.parent, layer=PARCELS.name,
                      columns=["parcel_id", "lot_use", "property_type", "year_built", "total_sq_ft", "num_housing_units"])
    table = {pnorm(r.parcel_id): r for r in p.itertuples() if not missing(r.parcel_id)}
    return p, table


def load(pilot):
    import geopandas as gpd
    cand = gpd.read_file(CAND/"candidates.gdb", layer="candidates")
    cand_web = gpd.read_file(CAND/"web.gdb", layer="candidates").set_index("CAND_ID")
    county = gpd.read_file(LIB/"buildings.gdb", layer="building_heights")
    county_web = gpd.read_file(COUNTY_WEB, layer="buildings").set_index("SOURCE_ID")
    assert cand.crs.to_epsg() == 6341 and cand_web.crs.to_epsg() == 3857 and county_web.crs.to_epsg() == 3857
    big = (cand.FOOTPRINT_M2 >= 150) & (cand.HEIGHT_P95_M >= 6)
    cand["GROUP"] = np.where(big, "large_tall", np.where(cand.NEAR_FP_DIST_M > 2, "detached", "attached"))
    cand = cand.sort_values(["GROUP", "CAND_ID"], key=lambda s: s.map({g: i for i, (g, _) in enumerate(GROUPS)})
                            if s.name == "GROUP" else s)
    low = county[(county.ROOF_COV_PCT.isna()) | (county.ROOF_COV_PCT < 10)].sort_values("SOURCE_ID")
    hints = gpd.read_file(COMPARE, layer="overture_buildings", where="MATCH = 'OVERTURE_ONLY' AND LIDAR = 'NO_ROOF'")
    assert hints.crs.to_epsg() == 6341
    hints = hints.sort_values("id").reset_index(drop=True)
    if pilot:
        cand = cand.groupby("GROUP", sort=False).head(7).head(20)
        low, hints = low.head(0), hints.head(0)
    return cand, cand_web, county, county_web, low, hints


def refresh_facts(data, facts):
    """Replace the facts in every existing bundle, one bundle at a time (a partial file, then a rename), so a running
    page keeps working. Chips, outlines and item ids stay as they are; the answers are untouched."""
    import os
    changed = 0
    for path in sorted((data/"bundles").glob("b*.json")):
        bundle = json.loads(path.read_text(encoding="utf-8"))
        for item_id, detail in bundle.items():
            detail["facts"] = facts[item_id]
            changed += 1
        partial = path.with_suffix(".partial")
        partial.write_text(json.dumps(bundle, separators=(",", ":"), allow_nan=False), encoding="utf-8")
        os.replace(partial, path)
    assert changed == len(facts), (changed, len(facts))
    print(f"facts refreshed on {changed} items")


def main(argv=None):
    import duckdb
    import geopandas as gpd
    import shapely
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("data", type=Path)
    p.add_argument("--pilot", action="store_true", help="20 candidates only (7 large and tall, 7 detached, 6 attached)")
    p.add_argument("--facts-only", action="store_true",
                   help="recompute the side-panel facts in existing bundles (atomically), leaving chips and outlines")
    a = p.parse_args(argv)
    data = a.data.resolve()
    cand, cand_web, county, county_web, low, hints = load(a.pilot)
    chips = Chips()
    parcel_frame, parcels = load_parcels()
    county_per_parcel = county.assign(P=county.PARCEL_ID.map(pnorm)).groupby("P").size().to_dict()
    hint_parcel = {}
    if len(hints):
        points = hints.assign(geometry=hints.geometry.centroid)[["id", "geometry"]]
        hp = gpd.sjoin(points, parcel_frame[["parcel_id", "geometry"]], how="left", predicate="within").drop_duplicates("id")
        hint_parcel = dict(zip(hp["id"], hp["parcel_id"]))
    facts = {r.CAND_ID: candidate_facts(r, parcels, county_per_parcel) for r in cand.itertuples()}
    facts.update({f"CF{r.SOURCE_ID}": county_facts(r, chips, parcels) for r in low.itertuples()})
    facts.update({f"NB{k + 1:04d}": newbuild_facts(f"NB{k + 1:04d}", r, chips, county, parcels, hint_parcel.get(r.id))
                  for k, r in enumerate(hints.itertuples())})
    if a.facts_only:
        return refresh_facts(data, facts)
    (data/"bundles").mkdir(parents=True, exist_ok=False)
    county_tree = shapely.STRtree(list(county.geometry))
    cand_all = gpd.read_file(CAND/"candidates.gdb", layer="candidates")
    cand_tree = shapely.STRtree(list(cand_all.geometry))
    county_ids, cand_ids = list(county.SOURCE_ID), list(cand_all.CAND_ID)
    index, bundle = [], {}

    def flush():
        if bundle:
            name = f"b{(len(index) - 1) // BUNDLE + 1:04d}.json"
            (data/"bundles"/name).write_text(json.dumps(bundle, separators=(",", ":"), allow_nan=False), encoding="utf-8")
            bundle.clear()

    def context(chip, exclude_county=None, exclude_cand=None):
        """County footprints and other candidates inside the chip: pixel rings, and WGS84 rings for the map."""
        n = chip["n"] * CELL
        box = shapely.box(chip["left"], chip["top"] - n, chip["left"] + n, chip["top"])
        out = {"county_px": [], "county_ll": [], "cand_px": [], "cand_ll": []}
        for j in county_tree.query(box, "intersects"):
            sid = county_ids[j]
            if sid == exclude_county:
                continue
            out["county_px"] += Chips.px(rings_of(county.geometry.iloc[j]), chip)
            if sid in county_web.index:
                out["county_ll"] += merc_to_ll(rings_of(county_web.loc[sid].geometry))
        for j in cand_tree.query(box, "intersects"):
            cid = cand_ids[j]
            if cid == exclude_cand:
                continue
            out["cand_px"] += Chips.px(rings_of(cand_all.geometry.iloc[j]), chip)
            out["cand_ll"] += merc_to_ll(rings_of(cand_web.loc[cid].geometry))
        return out

    def write(item_id, queue, group, facts, rings6341, rings_ll, chip_bounds, exclude_county=None, exclude_cand=None,
              hint=None):
        """hint: (rings in EPSG 6341, rings in WGS84) of a hint box, drawn instead of an outline."""
        chip, uri = chips.render(chip_bounds)
        detail = {"id": item_id, "queue": queue, "group": group, "facts": facts,
                  "outline_ll": rings_ll or [], "outline_px": Chips.px(rings6341, chip) if rings6341 else [],
                  "hint_ll": hint[1] if hint else None, "hint_px": Chips.px(hint[0], chip) if hint else None,
                  "chip": {"uri": uri, "size": chip["n"], "metres": chip["n"] * CELL},
                  **context(chip, exclude_county, exclude_cand)}
        index.append({"id": item_id, "queue": queue, "group": group, "order": len(index) + 1,
                      "bundle": f"b{len(index) // BUNDLE + 1:04d}.json"})
        bundle[item_id] = detail
        if len(index) % BUNDLE == 0:
            flush()

    for _, r in cand.iterrows():
        g = r.geometry
        write(r.CAND_ID, "candidates", r.GROUP, facts[r.CAND_ID], rings_of(g), merc_to_ll(rings_of(cand_web.loc[r.CAND_ID].geometry)),
              g.bounds, exclude_cand=r.CAND_ID)
        if len(index) % 500 == 0:
            print(f"  {len(index)} items", flush=True)

    for _, r in low.iterrows():
        g = r.geometry
        item = f"CF{r.SOURCE_ID}"
        ll = merc_to_ll(rings_of(county_web.loc[r.SOURCE_ID].geometry)) if r.SOURCE_ID in county_web.index else []
        write(item, "county", "low_roof", facts[item], rings_of(g), ll, g.bounds, exclude_county=r.SOURCE_ID)

    mapping = []
    if len(hints):
        con = duckdb.connect()
        ids = list(hints["id"])
        wgs = {i: shapely.from_wkb(bytes(w)) for i, w in con.execute(
            f"select id, geometry from '{OVERTURE_PARQUET}' where list_contains(?, id)", [ids]).fetchall()}
    for k, r in hints.iterrows():
        item = f"NB{k + 1:04d}"
        mapping.append({"item": item, "overture_id": r["id"]})
        x0, y0, x1, y1 = r.geometry.buffer(5).bounds
        box6341 = [[(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)]]
        lx0, ly0, lx1, ly1 = wgs[r["id"]].bounds          # Overture's own WGS84 coordinates (no datum change needed)
        dlat, dlon = 5 / 111320, 5 / (111320 * math.cos(math.radians((ly0 + ly1) / 2)))
        box_ll = [[[ly0 - dlat, lx0 - dlon], [ly0 - dlat, lx1 + dlon], [ly1 + dlat, lx1 + dlon], [ly1 + dlat, lx0 - dlon],
                   [ly0 - dlat, lx0 - dlon]]]
        write(item, "newbuild", "hint", facts[item], None, None, (x0, y0, x1, y1), hint=(box6341, box_ll))
    flush()
    if mapping:
        (data/"newbuild-hints.json").write_text(json.dumps({"note": "Internal: Overture ids behind the NB hints "
                                                            "(ODbL). Never copy into an output layer.",
                                                            "hints": mapping}, indent=1), encoding="utf-8")
    counts = {}
    for it in index:
        counts.setdefault(it["queue"], {}).setdefault(it["group"], 0)
        counts[it["queue"]][it["group"]] += 1
    (data/"index.json").write_text(json.dumps({
        "schema": "footprint-review/1", "built": datetime.datetime.now().isoformat(timespec="seconds"),
        "pilot": a.pilot, "counts": counts, "groups": dict(GROUPS), "items": index,
        "sources": {"candidates": str(CAND/"candidates.gdb"), "county": str(LIB/"buildings.gdb"),
                    "rasters": str(LIB)}}, separators=(",", ":")), encoding="utf-8")
    print(json.dumps(counts, indent=1))


if __name__ == "__main__":
    main()
