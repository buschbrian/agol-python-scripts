"""Overture 2026-10-21.0 land cover and land use against the 2023 LiDAR canopy.

    python -I landcover_compare.py        (ArcGIS Pro env millcreek-py3; writes landcover-compare/)

Everything is counted on the LiDAR's own 0.5 m grid (EPSG 6341), inside the city zone the canopy cover
figures were measured in (cover.gdb/zones CITY). Canopy is CHM >= 2 m on observed cells, as in
canopy.cover.summarize; unobserved cells are left out of every share.
1. Method check: the city zone, rasterized here, must reproduce cover_rebuilt CITY (observed and canopy
   cells, 25.59%) before anything else is measured.
2. Overture land cover (ESA WorldCover, the detailed min_zoom 8-15 tier only; the min_zoom 0-7 tier is a
   generalized copy of the same cover) and land use (OpenStreetMap) are clipped to the city and counted
   cell by cell against the canopy. Land cover classes overlap one another; each cell takes the class
   Overture draws on top (highest cartography.sort_key), and each class's whole polygons are counted too.
   Land use polygons overlap as well, so each land use class is counted on its own.
3. Disagreements at WorldCover's scale: canopy and Overture forest are summed over 30 m blocks, and
   connected blocks where the two disagree (forest with little canopy, dense canopy not called forest)
   become polygons of at least 1 ha, named from overlapping Overture land use, places and roads.

Overture land cover is ESA WorldCover 2021 (10 m Sentinel imagery); the LiDAR was flown October-November
2023, so some differences are two years of change.
"""
import json
import os
import sys

import duckdb
import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
import shapely
from affine import Affine
from rasterio.features import rasterize, shapes
from rasterio.windows import from_bounds
from scipy import ndimage

HERE = os.path.dirname(os.path.abspath(__file__))
PROD = "H:/lidar/2023-salt-lake-valley/runs/millcreek-products-20261022"
OUT = os.path.join(HERE, "landcover-compare")
CRS = 6341
CANOPY_M = 2.0       # canopy height threshold, as the cover figures
BLOCK = 60           # cells per block side (30 m) for the disagreement map
BLOCK_MIN_OBS = 0.5  # a block counts when at least this share of it is observed city
FOREST_BLOCK = 0.5   # a block is Overture forest when at least this share of its city cells is forest
LOW_CANOPY = 0.20    # forest blocks with less canopy than this disagree
DENSE_CANOPY = 0.60  # non-forest blocks with at least this much canopy disagree
MIN_HA = 1.0         # smallest disagreement polygon kept
DB = duckdb.connect()
BANDS_M = [0.5, 2, 5, 10]  # CHM height bands reported for each class and region: <0.5, 0.5-2, 2-5, 5-10, >=10
BAND_NAMES = ["lt_0.5m", "0.5_2m", "2_5m", "5_10m", "ge_10m"]
LC_CODES = {"forest": 1, "shrub": 2, "grass": 3, "crop": 4, "barren": 5, "urban": 6}
UNCOVERED = 0        # city cells no Overture land cover polygon covers
# cell states counted against every zone
OUTSIDE, UNOBS, OPEN, CANOPY = 0, 1, 2, 3
TREE_LU = {("protected", "forest"), ("protected", "nature_reserve"), ("protected", "wilderness_area"),
           ("park", "park"), ("park", "dog_park"), ("cemetery", "cemetery"), ("horticulture", "garden"),
           ("horticulture", "plant_nursery"), ("horticulture", "allotments"), ("managed", "grass"),
           ("recreation", "recreation_ground"), ("religious", "religious"), ("education", "school")}


def load_city():
    zones = gpd.read_file(f"{PROD}/cover.gdb", layer="zones")
    city = zones.loc[zones.ZONE_ID == "CITY"].to_crs(CRS)
    return city.geometry.union_all()


def load_overture(name, cols, city, where=""):
    """Overture features clipped to the city: cut to the city's box in lon/lat first (the national forest
    in land use is far larger than the city), then projected and intersected."""
    box = gpd.GeoSeries([shapely.box(*city.bounds).buffer(1000)], crs=CRS).to_crs(4326).total_bounds
    df = DB.sql(f"select {cols}, geometry from '{HERE}/{name}.parquet' {where}").df()
    geom = shapely.clip_by_rect(shapely.from_wkb(df.pop("geometry").map(bytes)), *box)
    g = gpd.GeoDataFrame(df, geometry=geom, crs=4326)
    g = g[~g.geometry.is_empty].to_crs(CRS)
    g["geometry"] = g.intersection(city)
    polygon = g.geom_type.isin(["Polygon", "MultiPolygon", "GeometryCollection"])
    return g[~g.geometry.is_empty & (~polygon | (g.area > 0))].copy()


class Grid:
    def __init__(self, city):
        with rasterio.open(f"{PROD}/chm_m.tif") as c, rasterio.open(f"{PROD}/observed.tif") as o:
            assert c.transform == o.transform and c.shape == o.shape and c.crs.to_epsg() == CRS
            self.transform, self.shape = c.transform, c.shape
            obs = o.read(1)
            chm = c.read(1)
            canopy = (chm >= CANOPY_M) & (chm != c.nodata)
            # height band of every observed cell (5 = unobserved or outside); the CHM is 0 on bare ground and roofs
            band = np.digitize(chm, BANDS_M).astype(np.uint8)
            band[obs != 1] = len(BANDS_M) + 1
            del chm
        self.zone = rasterize([city], out_shape=self.shape, transform=self.transform, fill=0, default_value=1,
                              dtype="uint8").astype(bool)
        self.obs_city = (obs != 3)
        state = np.full(self.shape, UNOBS, np.uint8)
        state[(obs == 1) & ~canopy] = OPEN
        state[(obs == 1) & canopy] = CANOPY
        state[~self.zone] = OUTSIDE
        self.state = state
        self.band = band
        self.check_obs, self.check_canopy = obs, canopy  # kept for the method check only

    def counts(self, geoms, where=None, arr=None):
        """Cell-centre counts of each state inside the geometries (a windowed rasterize), optionally only
        where a full-grid boolean array is true."""
        geoms = [g for g in geoms if g is not None and not g.is_empty]
        if not geoms:
            return np.zeros(4, np.int64)
        w = from_bounds(*shapely.total_bounds(geoms), transform=self.transform)
        r0, c0 = max(int(np.floor(w.row_off)), 0), max(int(np.floor(w.col_off)), 0)
        r1 = min(int(np.ceil(w.row_off + w.height)) + 1, self.shape[0])
        c1 = min(int(np.ceil(w.col_off + w.width)) + 1, self.shape[1])
        if r1 <= r0 or c1 <= c0:
            return np.zeros(4, np.int64)
        t = rasterio.windows.transform(rasterio.windows.Window(c0, r0, c1 - c0, r1 - r0), self.transform)
        m = rasterize(geoms, out_shape=(r1 - r0, c1 - c0), transform=t, fill=0, default_value=1, dtype="uint8")
        m = m == 1
        if where is not None:
            m &= where[r0:r1, c0:c1]
        if arr is None:
            return np.bincount(self.state[r0:r1, c0:c1][m], minlength=4)
        return np.bincount(arr[r0:r1, c0:c1][m], minlength=len(BAND_NAMES) + 1)


def row(counts, cell_m2=0.25):
    n_city = int(counts[UNOBS] + counts[OPEN] + counts[CANOPY])
    n_obs = int(counts[OPEN] + counts[CANOPY])
    return {"city_ha": round(n_city * cell_m2 / 1e4, 2), "observed_ha": round(n_obs * cell_m2 / 1e4, 2),
            "observed_pct": round(100 * n_obs / n_city, 2) if n_city else None,
            "canopy_ha": round(int(counts[CANOPY]) * cell_m2 / 1e4, 2),
            "canopy_pct_of_observed": round(100 * int(counts[CANOPY]) / n_obs, 2) if n_obs else None,
            "cells": {"unobserved": int(counts[UNOBS]), "observed_open": int(counts[OPEN]), "canopy": int(counts[CANOPY])}}


def band_pct(counts):
    n = int(counts[:len(BAND_NAMES)].sum())
    return {k: round(100 * int(v) / n, 1) for k, v in zip(BAND_NAMES, counts)} if n else {}


def geometry_detail(lc, city):
    """How fine the vectorized WorldCover actually is inside the city."""
    parts = lc.explode(index_parts=False)
    parts = parts[parts.geom_type == "Polygon"]
    whole = gpd.GeoSeries(parts.geometry, crs=CRS)
    # parts and holes cut by the city line are not WorldCover's own shapes; measure those wholly inside
    inner = parts[whole.within(city.buffer(-1))]
    holes = np.array([shapely.Polygon(r).area for p in inner.geometry for r in p.interiors])
    seg = np.concatenate([np.hypot(*np.diff(np.asarray(p.exterior.coords), axis=0).T) for p in inner.geometry])
    q = lambda a: {f"p{p:02d}": round(float(np.percentile(a, p)), 1) for p in (0, 5, 25, 50, 75)} if len(a) else {}
    return {"polygons_in_city": int(len(parts)), "polygons_wholly_inside": int(len(inner)),
            "part_area_m2": q(inner.area.values), "hole_area_m2": {"n": int(len(holes)), **q(holes)},
            "edge_segment_m": q(seg)}


def blocks(a, op=np.sum):
    """Sum a full-grid array over BLOCK x BLOCK blocks (padded with zeros)."""
    r, c = (-a.shape[0]) % BLOCK, (-a.shape[1]) % BLOCK
    a = np.pad(a, ((0, r), (0, c)))
    return a.reshape(a.shape[0] // BLOCK, BLOCK, a.shape[1] // BLOCK, BLOCK).sum(axis=(1, 3), dtype=np.int64)


def name_regions(reg, lu, places, roads):
    """Real names only: the named land use feature, places and roads each region overlaps."""
    reg = reg.copy()
    named = lu[lu["name"].notna()][["name", "subtype", "class", "geometry"]]
    hit = gpd.overlay(reg[["REGION", "geometry"]], named, how="intersection", keep_geom_type=True)
    hit["A"] = hit.area
    best = hit.sort_values("A", ascending=False).drop_duplicates("REGION").set_index("REGION")
    reg["LU_NAME"] = reg.REGION.map(best["name"])
    reg["LU_CLASS"] = reg.REGION.map(best["subtype"] + "/" + best["class"])
    reg["LU_SHARE"] = (reg.REGION.map(best["A"]) / reg.area).round(3)
    pj = gpd.sjoin(places[["name", "geometry"]].dropna(subset=["name"]), reg[["REGION", "geometry"]], predicate="within")
    reg["PLACES"] = reg.REGION.map(pj.groupby("REGION")["name"].apply(lambda s: "; ".join(sorted(set(s))[:4])))
    rd = roads[roads["name"].notna()]
    rj = gpd.overlay(rd[["name", "geometry"]], reg[["REGION", "geometry"]].assign(geometry=reg.buffer(15)),
                     how="intersection", keep_geom_type=True)
    rj["L"] = rj.length
    top = rj.groupby(["REGION", "name"])["L"].sum().reset_index().sort_values("L", ascending=False)
    reg["ROADS"] = reg.REGION.map(top.groupby("REGION")["name"].apply(lambda s: "; ".join(list(s)[:3])))
    return reg


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    os.makedirs(OUT, exist_ok=True)
    city = load_city()
    print("loading rasters")
    grid = Grid(city)
    cell_m2 = abs(grid.transform.a * grid.transform.e)

    # 1. Method check against cover_rebuilt CITY.
    cov = gpd.read_file(f"{PROD}/cover.gdb", layer="cover_rebuilt")
    cov = cov.loc[cov.ZONE_ID == "CITY"].iloc[0]
    zone_cells = int(grid.zone.sum())
    obs_cells = int(((grid.check_obs == 1) & grid.zone).sum())
    can_cells = int((grid.check_canopy & (grid.check_obs == 1) & grid.zone).sum())
    check = {"zone_cells": zone_cells, "zone_cells_expected": int(round(cov.GRID_M2 / cell_m2)),
             "observed_cells": obs_cells, "observed_cells_expected": int(round(cov.OBSERVED_M2 / cell_m2)),
             "canopy_cells": can_cells, "canopy_cells_expected": int(round(cov.CANOPY_M2 / cell_m2)),
             "canopy_pct": round(100 * can_cells / obs_cells, 4), "canopy_pct_expected": round(float(cov.OBS_CANOPY_PCT), 4),
             "zone_cells_equal_observed_raster_city": bool((grid.zone == grid.obs_city).all()),
             "observed_raster_city_cells": int(grid.obs_city.sum())}
    print("method check:", json.dumps(check))
    assert (obs_cells, can_cells) == (check["observed_cells_expected"], check["canopy_cells_expected"]), check
    del grid.check_obs, grid.check_canopy

    bnd = load_overture("millcreek_boundary", "id", shapely.box(*city.bounds).buffer(5000))
    ov_city = bnd.geometry.union_all()
    check["overture_boundary_ha"] = round(ov_city.area / 1e4, 1)
    check["city_zone_ha"] = round(city.area / 1e4, 1)
    check["boundary_symmetric_difference_ha"] = round(ov_city.symmetric_difference(city).area / 1e4, 1)

    # 2a. Land cover.
    lc_all = DB.sql(f"""select subtype, cartography.min_zoom as min_zoom, cartography.max_zoom as max_zoom,
        source_datasets, count(*) n from '{HERE}/land_cover.parquet' group by all order by all""").df()
    srcs = DB.sql(f"""select distinct s.dataset, s.provider, s.resource, s.version, s.license, s.update_time
        from (select unnest(sources) s from '{HERE}/land_cover.parquet')""").df()
    lc = load_overture("land_cover", "id, subtype, cartography.sort_key as sort_key, source_datasets", city,
                       "where cartography.min_zoom >= 8")
    lc["CITY_HA"] = lc.area / 1e4
    detail = geometry_detail(lc, city)
    overlap_ha = round((lc.area.sum() - lc.geometry.union_all().area) / 1e4, 3)
    unions = {s: g.union_all() for s, g in lc.groupby("subtype")}
    overlaps = {f"{a}/{b}": round(unions[a].intersection(unions[b]).area / 1e4, 2)
                for i, a in enumerate(sorted(unions)) for b in sorted(unions)[i + 1:]}

    # The classes overlap: Overture stacks them, drawing higher sort_key on top (urban is the bottom layer).
    # Each cell takes the class drawn on top, as the map shows it.
    draw = lc.sort_values("sort_key", kind="stable")
    cls = rasterize(zip(draw.geometry, draw.subtype.map(LC_CODES)), out_shape=grid.shape, transform=grid.transform,
                    fill=UNCOVERED, dtype="uint8")
    by_cls = np.stack([np.bincount(grid.state[cls == c], minlength=4) for c in range(7)])
    band_cls = np.stack([np.bincount(grid.band[(cls == c) & grid.zone], minlength=len(BAND_NAMES) + 1) for c in range(7)])
    names = {v: k for k, v in LC_CODES.items()} | {UNCOVERED: "(no Overture land cover)"}
    sort_keys = lc.groupby("subtype").sort_key.agg(lambda s: sorted(set(s.astype(int))))
    lc_table = {names[c]: {"polygons": int((lc.subtype == names[c]).sum()),
                           "sort_key": sort_keys.get(names[c]), **row(by_cls[c], cell_m2)}
                for c in range(7) if by_cls[c, 1:].sum()}
    # and the whole polygons of each class, counting the parts other classes are drawn over
    for sub, u in unions.items():
        lc_table.setdefault(sub, {})["whole_polygons"] = row(grid.counts([u]), cell_m2)
    city_counts = by_cls.sum(axis=0)
    for v in lc_table.values():
        if "cells" not in v:
            continue
        v["share_of_city_pct"] = round(100 * (v["cells"]["unobserved"] + v["cells"]["observed_open"] + v["cells"]["canopy"])
                                       / int(city_counts[1:].sum()), 2)
        v["share_of_city_canopy_pct"] = round(100 * v["cells"]["canopy"] / int(city_counts[CANOPY]), 2)
    for c in range(7):
        if names[c] in lc_table and "cells" in lc_table[names[c]]:
            lc_table[names[c]]["chm_band_pct_of_observed"] = band_pct(band_cls[c])
    print(json.dumps(lc_table, indent=1))

    # forest against the LiDAR canopy, both ways, on observed cells
    obs = grid.state >= OPEN
    forest = cls == LC_CODES["forest"]
    can = grid.state == CANOPY
    n_obs = int(obs.sum())
    # the LiDAR's own "tree-dominated 10 m pixels": a WorldCover-sized cell with canopy on most of it
    b10 = 20
    r, c = (-grid.shape[0]) % b10, (-grid.shape[1]) % b10
    pad = lambda a: np.pad(a, ((0, r), (0, c)))
    s10 = lambda a: pad(a).reshape((grid.shape[0] + r) // b10, b10, (grid.shape[1] + c) // b10, b10).sum(axis=(1, 3), dtype=np.int64)
    o10, c10 = s10(obs), s10(can)
    full10 = o10 >= 0.5 * b10 * b10
    vs = {"observed_cells": n_obs,
          "overture_forest_pct_of_observed_city": round(100 * int((forest & obs).sum()) / n_obs, 2),
          "lidar_canopy_pct_of_observed_city": round(100 * int(can.sum()) / n_obs, 2),
          "lidar_canopy_inside_overture_forest_pct": round(100 * int((can & forest).sum()) / int(can.sum()), 2),
          "overture_forest_cells_with_canopy_pct": round(100 * int((can & forest).sum()) / int((forest & obs).sum()), 2),
          "lidar_10m_cells_majority_canopy_pct": round(100 * int((full10 & (2 * c10 > o10)).sum()) / int(full10.sum()), 2),
          "lidar_10m_cells_any_canopy_10pct_pct": round(100 * int((full10 & (10 * c10 >= o10)).sum()) / int(full10.sum()), 2),
          "lidar_10m_cells_counted": int(full10.sum())}
    del o10, c10, full10
    print(json.dumps(vs, indent=1))

    # 2b. Land use (OSM), each class on its own.
    lu = load_overture("land_use", "id, subtype, class, names.primary as name, source_datasets", city)
    lu = lu[lu.geom_type.isin(["Polygon", "MultiPolygon"])]
    lu_table = {}
    for (sub, k), g in lu.groupby(["subtype", "class"]):
        cts = grid.counts(list(g.geometry))
        lu_table[f"{sub}/{k}"] = {"polygons": int(len(g)), "tree_related": (sub, k) in TREE_LU,
                                  "names": sorted(set(g["name"].dropna()))[:6], **row(cts, cell_m2)}
        f = grid.counts(list(g.geometry), where=forest)
        lu_table[f"{sub}/{k}"]["overture_forest_pct"] = round(100 * int(f[1:].sum()) / max(int(cts[1:].sum()), 1), 1)
    # each named tree-related polygon too (parks, cemeteries, reserves)
    lu_named = []
    for _, f in lu[lu[["subtype", "class"]].apply(tuple, axis=1).isin(TREE_LU)].iterrows():
        cts = grid.counts([f.geometry])
        if cts[1:].sum() * cell_m2 >= 5000:
            fc = grid.counts([f.geometry], where=forest)
            lu_named.append({"id": f.id, "name": f["name"], "class": f"{f.subtype}/{f['class']}", **row(cts, cell_m2),
                             "overture_forest_pct": round(100 * int(fc[1:].sum()) / int(cts[1:].sum()), 1)})

    # 3. Disagreement blocks at 30 m.
    n_city_b = blocks(grid.state >= UNOBS)
    n_obs_b = blocks(obs)
    n_can_b = blocks(can)
    n_for_b = blocks(forest & (grid.state >= UNOBS))
    del obs, can, forest
    lc_b = {sub: blocks((cls == code) & (grid.state >= UNOBS)) for sub, code in LC_CODES.items()}
    ok = n_obs_b >= BLOCK_MIN_OBS * BLOCK * BLOCK
    with np.errstate(invalid="ignore", divide="ignore"):
        cf = n_can_b / n_obs_b
        ff = n_for_b / n_city_b
    kind = np.zeros(n_obs_b.shape, np.uint8)
    kind[ok & (ff >= FOREST_BLOCK) & (cf < LOW_CANOPY)] = 1
    kind[ok & (ff < FOREST_BLOCK) & (cf >= DENSE_CANOPY)] = 2
    bt = grid.transform * Affine.scale(BLOCK)
    regs = []
    for k, label in ((1, "FOREST_LOW_CANOPY"), (2, "DENSE_CANOPY_NOT_FOREST")):
        lab, n = ndimage.label(kind == k, structure=np.ones((3, 3)))
        idx = np.arange(1, n + 1)
        sums = {f: ndimage.sum_labels(a, lab, idx) for f, a in
                [("CITY", n_city_b), ("OBS", n_obs_b), ("CAN", n_can_b), ("FOR", n_for_b)] + [(s, v) for s, v in lc_b.items()]}
        polys = {}
        for geom, v in shapes(lab.astype(np.int32), mask=lab > 0, transform=bt, connectivity=8):
            polys.setdefault(int(v), []).append(shapely.geometry.shape(geom))
        for i in idx:
            g = shapely.union_all(polys[int(i)]).intersection(city)
            ha = sums["CITY"][i - 1] * cell_m2 / 1e4
            if ha < MIN_HA:
                continue
            mix = {s: sums[s][i - 1] / sums["CITY"][i - 1] for s in LC_CODES}
            regs.append({"KIND": label, "CITY_HA": round(ha, 2), "OBS_PCT": round(100 * sums["OBS"][i - 1] / sums["CITY"][i - 1], 1),
                         "CANOPY_PCT": round(100 * sums["CAN"][i - 1] / sums["OBS"][i - 1], 1),
                         "OV_FOREST_PCT": round(100 * sums["FOR"][i - 1] / sums["CITY"][i - 1], 1),
                         "OV_MAIN_CLASS": max(mix, key=mix.get),
                         **{f"OV_{s.upper()}_PCT": round(100 * m, 1) for s, m in mix.items()}, "geometry": g})
    reg = gpd.GeoDataFrame(regs, crs=CRS).sort_values(["KIND", "CITY_HA"], ascending=[True, False]).reset_index(drop=True)
    reg.insert(0, "REGION", np.arange(1, len(reg) + 1))
    places = load_overture("places", "id, names.primary as name", city)
    roads = load_overture("road_segments", "id, names.primary as name", city, "where subtype = 'road'")
    reg = name_regions(reg, lu, places, roads)
    bands = pd.DataFrame([band_pct(grid.counts([g], arr=grid.band)) for g in reg.geometry], index=reg.index)
    for k in BAND_NAMES:
        reg[f"H_{k.upper().replace('.', '')}_PCT"] = bands[k]
    ll = reg.geometry.representative_point().to_crs(4326)
    reg["LON"], reg["LAT"] = ll.x.round(5), ll.y.round(5)
    print(reg.drop(columns="geometry").head(40).to_string())

    def kind_summary(k):
        r = reg[reg.KIND == k]
        return {"regions": int(len(r)), "ha": round(float(r.CITY_HA.sum()), 1),
                "canopy_pct_area_weighted": round(float((r.CANOPY_PCT * r.CITY_HA).sum() / r.CITY_HA.sum()), 1) if len(r) else None,
                "by_overture_main_class": r.groupby("OV_MAIN_CLASS").CITY_HA.agg(["size", "sum"]).round(1).to_dict(orient="index"),
                "largest": r.head(10).drop(columns="geometry").to_dict(orient="records")}

    summ = {"overture_release": "2026-10-21.0", "lidar": PROD, "method_check": check,
            "thresholds": {"canopy_m": CANOPY_M, "block_m": BLOCK * grid.transform.a, "block_min_observed": BLOCK_MIN_OBS,
                           "forest_block": FOREST_BLOCK, "low_canopy": LOW_CANOPY, "dense_canopy": DENSE_CANOPY, "min_ha": MIN_HA},
            "land_cover_features_all_tiers": lc_all.to_dict(orient="records"),
            "land_cover_sources": srcs.to_dict(orient="records"),
            "land_cover_overlap_within_tier_ha": overlap_ha, "land_cover_class_overlaps_ha": overlaps,
            "land_cover_geometry": detail,
            "land_cover_by_class": lc_table, "forest_vs_lidar": vs,
            "land_use_sources": sorted(set(lu.source_datasets)),
            "land_use_by_class": dict(sorted(lu_table.items(), key=lambda kv: -kv[1]["city_ha"])),
            "land_use_tree_related_features": sorted(lu_named, key=lambda d: -d["city_ha"]),
            "disagreement": {"FOREST_LOW_CANOPY": kind_summary("FOREST_LOW_CANOPY"),
                             "DENSE_CANOPY_NOT_FOREST": kind_summary("DENSE_CANOPY_NOT_FOREST"),
                             "blocks_counted": int(ok.sum()),
                             "blocks_forest": int((ok & (ff >= FOREST_BLOCK)).sum()),
                             "blocks_forest_low_canopy": int((kind == 1).sum()),
                             "blocks_dense_canopy": int((ok & (cf >= DENSE_CANOPY)).sum()),
                             "blocks_dense_canopy_not_forest": int((kind == 2).sum())}}
    with open(os.path.join(OUT, "summary.json"), "w", encoding="utf-8") as f:
        json.dump(summ, f, indent=1, default=str, ensure_ascii=False)

    gpkg = os.path.join(OUT, "landcover_vs_lidar.gpkg")
    if os.path.exists(gpkg):
        os.remove(gpkg)
    reg.to_file(gpkg, layer="disagreement", driver="GPKG")
    lcw = lc.copy()
    lcw["CANOPY_PCT_WHOLE"] = [row(grid.counts([g]), cell_m2)["canopy_pct_of_observed"] for g in lcw.geometry]
    lcw.to_file(gpkg, layer="overture_land_cover", driver="GPKG")
    print("done")


if __name__ == "__main__":
    main()
