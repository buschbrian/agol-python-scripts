r"""How far the county footprint layer is misaligned against the 2023 LiDAR roofs, and which shifts are shared by a
neighbourhood (registration) rather than one building (a real offset or a rebuild). October 23, 2026.

    python -I reviews/2026-10-23/county-alignment/align_county.py fit OUT [--pilot]    per-footprint best shift
    python -I reviews/2026-10-23/county-alignment/align_county.py field OUT            local shift field, structure
    python -I reviews/2026-10-23/county-alignment/align_county.py classify OUT         classes, aligned layer, queues

ArcGIS Pro env millcreek-py3 (rasterio, geopandas, scipy), PYTHONNOUSERSITE=1. Read-only on the library, the LiDAR
candidates and the review data; writes only under OUT. The County's data is never edited: the shifted outlines are a
derived layer. Everything is compared in EPSG 6341, where both the LiDAR and the library's county copy
(buildings.gdb/building_heights) live; nothing goes through WGS84 here.
- fit: for every county footprint, the shift (dx, dy) within +-3 m, at 0.25 m steps, that puts the most consensus roof
  cells (roof_height_m.tif has a value) inside the outline; where several shifts tie (roofs overhang their footprints),
  the centre of the tied plateau. The outline is rasterized at 0.25 m cell centres and the
  0.5 m roof is read at 0.25 m; an FFT cross-correlation gives every shift's roof share at once. Recorded per footprint:
  the roof share unshifted and at the best shift, the shift, how sharp the peak is (best minus the mean 0.5-0.75 m away),
  the margin over the best shift at least 1 m away (a second peak means the fit is ambiguous), whether the best shift
  is on the search edge, and the share of the outline under canopy of 2 m or more without roof (trees hide roofs).
- field: reliable fits (rules below) are smoothed into a local shift: the median dx and dy of reliable neighbours within
  150 m (at least 5). Reports how well neighbours agree, and the shift by the county layer's own attributes.
- classify: ALIGNED, SYSTEMATIC, REAL_OFFSET, REBUILT_OR_GONE or UNCERTAIN for each footprint (rules in classify());
  the derived layer of footprints moved by their local shift; and the review queues re-derived against it.
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
REVIEW = RUNS/"footprint-review-20261023"/"data"
FINE = 0.25            # metres per fine cell
MAX_SHIFT = 3.0        # metres
K = int(round(MAX_SHIFT / FINE))
PILOT = [(428000.0, 4504000.0, 429000.0, 4505000.0),      # 12TVL2804, the labelled tile
         (426000.0, 4503000.0, 427000.0, 4504000.0)]      # 12TVL2603
# A fit is reliable enough to describe the neighbourhood when the building is big enough to have a shape, its roof is
# well seen at the best shift, the peak is sharp and single, it is not on the search edge, and trees don't hide it.
RELIABLE = {"min_m2": 40, "min_best": 0.85, "min_sharp": 0.02, "min_margin": 0.02, "max_canopy": 0.2}
NEIGHBOUR_M = 150
MIN_NEIGHBOURS = 5
COLUMNS = ["SOURCE_ID", "AREA_M2", "ROOF0", "ROOF_BEST", "DX", "DY", "SHIFT_M", "PLATEAU_M", "SHARP", "MARGIN", "EDGE",
           "CANOPY"]
PLATEAU = 0.01         # shifts within 1% of the best roof share count as tied


class Grid:
    """The roof and canopy rasters in memory as masks, read at 0.25 m around any outline."""

    def __init__(self):
        import rasterio
        with rasterio.open(LIB/"roof_height_m.tif") as r, rasterio.open(LIB/"chm_m.tif") as c:
            assert r.transform == c.transform and r.shape == c.shape and r.crs.to_epsg() == 6341
            self.t = r.transform
            a = r.read(1)
            self.roof = (a != r.nodata) & np.isfinite(a)
            del a
            h = c.read(1)
            self.canopy = np.isfinite(h) & (h != c.nodata) & (h >= 2)
            del h
        self.cell = self.t.a

    def window(self, bounds):
        """Fine (0.25 m) roof and canopy masks covering bounds plus the search margin, and the window's origin."""
        x0, y0, x1, y1 = bounds
        pad = MAX_SHIFT + 1.0
        c0 = int(math.floor((x0 - pad - self.t.c) / self.cell))
        c1 = int(math.ceil((x1 + pad - self.t.c) / self.cell))
        r0 = int(math.floor((self.t.f - (y1 + pad)) / self.cell))
        r1 = int(math.ceil((self.t.f - (y0 - pad)) / self.cell))
        rows, cols = self.roof.shape
        out = []
        for mask in (self.roof, self.canopy):
            w = np.zeros((r1 - r0, c1 - c0), bool)
            rr0, cc0 = max(r0, 0), max(c0, 0)
            rr1, cc1 = min(r1, rows), min(c1, cols)
            if rr1 > rr0 and cc1 > cc0:
                w[rr0 - r0:rr1 - r0, cc0 - c0:cc1 - c0] = mask[rr0:rr1, cc0:cc1]
            out.append(np.repeat(np.repeat(w, 2, 0), 2, 1))
        return out[0], out[1], (self.t.c + c0 * self.cell, self.t.f - r0 * self.cell)


def fit_one(geom, grid):
    from rasterio.features import geometry_mask
    from rasterio.transform import from_origin
    from scipy.signal import fftconvolve
    roof, canopy, (left, top) = grid.window(geom.bounds)
    fp = ~geometry_mask([geom], out_shape=roof.shape, transform=from_origin(left, top, FINE, FINE))
    n = int(fp.sum())
    if n == 0:
        return None
    corr = fftconvolve(roof.astype(np.float32), fp[::-1, ::-1].astype(np.float32), mode="full")
    h, w = fp.shape
    scores = corr[h - 1 - K:h + K, w - 1 - K:w + K] / n          # scores[K + dr, K + dc]: outline moved dr rows, dc cols
    scores = np.round(scores, 6)
    dr, dc = np.mgrid[-K:K + 1, -K:K + 1]
    best = scores.max()
    # Roofs overhang their footprints, so many shifts can tie for the most roof: take the centre of that plateau
    # (every shift within 1% of the best), which centres the outline under the roof.
    plateau = scores >= best - PLATEAU
    pr, pc = dr[plateau].mean(), dc[plateau].mean()
    width = float(np.hypot(dr[plateau] - pr, dc[plateau] - pc).max() * FINE)
    d_from = np.hypot(dr - pr, dc - pc) * FINE
    ring = scores[(d_from >= width + 0.5) & (d_from <= width + 0.75)]
    far = scores[d_from >= width + 1.0]
    dx, dy = pc * FINE, -pr * FINE
    under_trees = canopy & ~roof & fp
    return {"AREA_M2": geom.area, "ROOF0": float(scores[K, K]), "ROOF_BEST": float(best), "DX": float(dx), "DY": float(dy),
            "SHIFT_M": float(math.hypot(dx, dy)), "PLATEAU_M": width,
            "SHARP": float(best - ring.mean()) if ring.size else 0.0, "MARGIN": float(best - far.max()) if far.size else 0.0,
            "EDGE": int(bool((np.abs(dr[plateau]) == K).any() or (np.abs(dc[plateau]) == K).any())),
            "CANOPY": float(under_trees.sum() / n)}


def reliable(df):
    r = RELIABLE
    return ((df.AREA_M2 >= r["min_m2"]) & (df.ROOF_BEST >= r["min_best"]) & (df.SHARP >= r["min_sharp"])
            & (df.MARGIN >= r["min_margin"]) & (df.EDGE == 0) & (df.CANOPY <= r["max_canopy"]))


def fit(out, pilot):
    import geopandas as gpd
    import pandas as pd
    import shapely
    county = gpd.read_file(LIB/"buildings.gdb", layer="building_heights")
    if pilot:
        box = shapely.union_all([shapely.box(*b) for b in PILOT])
        county = county[county.geometry.within(box)]
    grid = Grid()
    rows = []
    started = datetime.datetime.now()
    for k, r in enumerate(county.itertuples(), 1):
        res = fit_one(r.geometry, grid)
        if res:
            rows.append({"SOURCE_ID": r.SOURCE_ID, **res})
        if k % 2000 == 0:
            print(f"  {k}/{len(county)}", flush=True)
    df = pd.DataFrame(rows, columns=COLUMNS)
    df["RELIABLE"] = reliable(df).astype(int)
    name = "fit-pilot.csv" if pilot else "fit.csv"
    out.mkdir(parents=True, exist_ok=True)
    df.to_csv(out/name, index=False)
    summary = {"footprints": len(county), "fitted": len(df), "reliable_fits": int(df.RELIABLE.sum()),
               "seconds": round((datetime.datetime.now() - started).total_seconds()), "rules": RELIABLE,
               "search": {"max_m": MAX_SHIFT, "step_m": FINE}}
    rel = df[df.RELIABLE == 1]
    for key, d in (("all", df), ("reliable", rel)):
        summary[key] = {"median_dx": round(float(d.DX.median()), 3), "median_dy": round(float(d.DY.median()), 3),
                        "shift_p50": round(float(d.SHIFT_M.median()), 3), "shift_p90": round(float(d.SHIFT_M.quantile(.9)), 3),
                        "roof0_p50": round(float(d.ROOF0.median()), 3), "roof_best_p50": round(float(d.ROOF_BEST.median()), 3)}
    (out/(name.replace(".csv", ".json"))).write_text(json.dumps(summary, indent=1), encoding="utf-8")
    print(json.dumps(summary, indent=1))


def load_fits(out):
    import geopandas as gpd
    import pandas as pd
    df = pd.read_csv(out/"fit.csv", dtype={"SOURCE_ID": str})
    county = gpd.read_file(LIB/"buildings.gdb", layer="building_heights")
    g = county.merge(df, on="SOURCE_ID", how="inner", validate="one_to_one")
    g["X"], g["Y"] = g.geometry.centroid.x, g.geometry.centroid.y
    return g


def local_field(g):
    """For every footprint: the median shift of the reliable fits within NEIGHBOUR_M (itself left out), their count and
    spread (median distance of their shifts from that median)."""
    from scipy.spatial import cKDTree
    rel = g[g.RELIABLE == 1]
    tree = cKDTree(rel[["X", "Y"]].values)
    rx, ry, rid = rel.DX.values, rel.DY.values, rel.SOURCE_ID.values
    lx, ly, ln, lmad = [], [], [], []
    for sid, x, y in zip(g.SOURCE_ID.values, g.X.values, g.Y.values):
        nb = [j for j in tree.query_ball_point((x, y), NEIGHBOUR_M) if rid[j] != sid]
        if len(nb) >= MIN_NEIGHBOURS:
            mx, my = float(np.median(rx[nb])), float(np.median(ry[nb]))
            lx.append(mx), ly.append(my), ln.append(len(nb))
            lmad.append(float(np.median(np.hypot(rx[nb] - mx, ry[nb] - my))))
        else:
            lx.append(np.nan), ly.append(np.nan), ln.append(len(nb)), lmad.append(np.nan)
    g = g.copy()
    g["LOCAL_DX"], g["LOCAL_DY"], g["LOCAL_N"], g["LOCAL_SPREAD"] = lx, ly, ln, lmad
    g["LOCAL_M"] = np.hypot(g.LOCAL_DX, g.LOCAL_DY)
    g["RESID_M"] = np.hypot(g.DX - g.LOCAL_DX, g.DY - g.LOCAL_DY)
    return g


def field(out):
    """The local shift field and whether misalignment is shared by neighbourhoods or by the county layer's attributes."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import pandas as pd
    g = local_field(load_fits(out))
    rel = g[g.RELIABLE == 1]
    has = rel.LOCAL_N >= MIN_NEIGHBOURS

    def q(s):
        s = pd.Series(s).dropna()
        return {"n": int(len(s)), "p50": round(float(s.median()), 3), "p90": round(float(s.quantile(.9)), 3)}
    # A footprint is "explained by a shared local shift" when the local shift is big enough to matter (0.5 m or more)
    # and its own shift is within 0.5 m of it.
    shared = has & (rel.LOCAL_M >= 0.5) & (rel.RESID_M <= 0.5)
    summary = {
        "reliable_fits": int(len(rel)), "with_neighbours": int(has.sum()),
        "own_shift_m": q(rel.SHIFT_M), "local_median_shift_m": q(rel.loc[has, "LOCAL_M"]),
        "residual_from_local_m": q(rel.loc[has, "RESID_M"]), "neighbour_spread_m": q(rel.loc[has, "LOCAL_SPREAD"]),
        "local_shift_at_least_0.5m": int((has & (rel.LOCAL_M >= 0.5)).sum()),
        "explained_by_shared_local_shift": int(shared.sum()),
        "share_explained": round(float(shared.sum() / max(has.sum(), 1)), 4),
        "citywide_median_shift": {"dx": round(float(rel.DX.median()), 3), "dy": round(float(rel.DY.median()), 3)},
        "datum_reference": "the HARN path would move footprints by (-0.17, +0.36) m here; the stored chained path is a "
                           "null shift (checked October 23)",
    }
    # Coarse cells: does any part of the city drift as a block?
    for size in (250, 500):
        cells = rel.assign(CX=(rel.X // size) * size, CY=(rel.Y // size) * size).groupby(["CX", "CY"]).agg(
            DX=("DX", "median"), DY=("DY", "median"), N=("DX", "size")).reset_index()
        cells = cells[cells.N >= 10]
        mag = np.hypot(cells.DX, cells.DY)
        summary[f"cells_{size}m"] = {"cells": int(len(cells)), "median_shift_m": q(mag),
                                     "cells_at_least_0.5m": int((mag >= 0.5).sum()), "max_m": round(float(mag.max()), 3)}
        cells.to_csv(out/f"field-{size}m.csv", index=False)
    # By the county layer's own attributes
    attrs = {}
    rel2 = rel.assign(EDIT_YEAR=pd.to_datetime(rel.EditDate, errors="coerce").dt.year,
                      CREATE_YEAR=pd.to_datetime(rel.CreationDate, errors="coerce").dt.year,
                      BUILT_DECADE=(rel.BuiltYear // 10) * 10)
    for col in ("SOURCE", "BuildType", "Creator", "Editor", "CREATE_YEAR", "EDIT_YEAR", "BUILT_DECADE", "JURISDICTION"):
        if col not in rel2:
            continue
        t = rel2.groupby(rel2[col].fillna("(none)").astype(str)).agg(N=("DX", "size"), DX=("DX", "median"),
                                                                       DY=("DY", "median"), SHIFT_P50=("SHIFT_M", "median"))
        t = t[t.N >= 30].round(3)
        attrs[col] = t.sort_values("N", ascending=False).head(12).to_dict(orient="index")
    summary["by_attribute"] = attrs
    g[["SOURCE_ID", "X", "Y", "DX", "DY", "SHIFT_M", "RELIABLE", "LOCAL_DX", "LOCAL_DY", "LOCAL_N", "LOCAL_SPREAD",
       "LOCAL_M", "RESID_M"]].to_csv(out/"field.csv", index=False)
    (out/"field.json").write_text(json.dumps(summary, indent=1, default=str), encoding="utf-8")
    # Maps
    fig, axes = plt.subplots(1, 2, figsize=(22, 8), gridspec_kw={"width_ratios": [2.2, 1]})
    c = pd.read_csv(out/"field-250m.csv")
    ax = axes[0]
    ax.scatter(g.X, g.Y, s=0.3, c="#ccc")
    qv = ax.quiver(c.CX + 125, c.CY + 125, c.DX, c.DY, np.hypot(c.DX, c.DY), angles="xy", scale_units="xy", scale=1 / 1000,
                   width=0.0018, cmap="viridis", clim=(0, 0.6))
    fig.colorbar(qv, ax=ax, label="median shift in the 250 m cell (m)")
    ax.set_aspect("equal")
    ax.set_title("County footprints against the 2023 LiDAR: median shift per 250 m cell (arrows x1000)")
    ax = axes[1]
    ax.hist(rel.SHIFT_M, bins=np.arange(0, 3.01, 0.125), alpha=0.6, label="each footprint's own shift")
    ax.hist(rel.loc[has, "LOCAL_M"], bins=np.arange(0, 3.01, 0.125), alpha=0.6, label="local median within 150 m")
    ax.set_xlabel("metres")
    ax.set_ylabel("reliable footprints")
    ax.legend()
    ax.set_title("Own shift vs shared local shift")
    fig.savefig(out/"shift-field.png", dpi=90, bbox_inches="tight")
    print(json.dumps({k: v for k, v in summary.items() if k != "by_attribute"}, indent=1))
    print(json.dumps(attrs, indent=1, default=str)[:3000])


def score_at(geom, grid, dx, dy):
    """Roof share of the outline moved by (dx, dy), rounded to the 0.25 m search grid."""
    from rasterio.features import geometry_mask
    from rasterio.transform import from_origin
    roof, _, (left, top) = grid.window(geom.bounds)
    fp = ~geometry_mask([geom], out_shape=roof.shape, transform=from_origin(left, top, FINE, FINE))
    n = fp.sum()
    if not n:
        return np.nan
    dr, dc = int(round(-dy / FINE)), int(round(dx / FINE))
    return float((np.roll(np.roll(fp, dr, 0), dc, 1) & roof).sum() / n)


def classes(g):
    """ALIGNED: well roofed where it is and no shift gains much. SYSTEMATIC: well roofed once the neighbourhood's shift
    is applied, and that gains. REAL_OFFSET: a trustworthy fit of its own, 0.5 m or more away from the neighbourhood's
    shift, that brings it onto its roof. REBUILT_OR_GONE: weak roof under any shift, not hidden by trees. UNCERTAIN:
    the rest (trees over the roof, part roofed under any shift, ambiguous or edge fits, small buildings)."""
    trust = (g.SHARP >= RELIABLE["min_sharp"]) & (g.MARGIN >= RELIABLE["min_margin"]) & (g.EDGE == 0)
    out = np.full(len(g), "UNCERTAIN", dtype=object)
    gone = (g.ROOF_BEST < 0.5) & (g.CANOPY < 0.3)
    aligned = (g.ROOF0 >= 0.85) & (g.ROOF_BEST - g.ROOF0 < 0.05)
    systematic = ~aligned & (g.ROOF_LOCAL >= 0.85) & (g.ROOF_LOCAL - g.ROOF0 >= 0.05) & (g.LOCAL_M >= 0.25)
    offset = (~aligned & ~systematic & trust & (g.ROOF_BEST >= 0.85) & (g.ROOF_BEST - g.ROOF0 >= 0.05)
              & (g.SHIFT_M >= 0.5) & (g.RESID_M.fillna(g.SHIFT_M) >= 0.5))
    out[gone.values] = "REBUILT_OR_GONE"
    out[aligned.values] = "ALIGNED"
    out[systematic.values] = "SYSTEMATIC"
    out[offset.values] = "REAL_OFFSET"
    return out


def near_mask(geoms, shape, transform):
    """Cells whose centre is on or within 1.5 m of an outline's cells, as the candidate detection excluded them."""
    from rasterio.features import rasterize
    from scipy import ndimage
    cm = rasterize(((g, 1) for g in geoms), out_shape=shape, transform=transform, fill=0, dtype="uint8",
                   all_touched=False).astype(bool)
    return ndimage.distance_transform_edt(~cm) * transform.a <= 1.5


def classify(out):
    import geopandas as gpd
    import pandas as pd
    import rasterio
    from shapely import affinity
    g = local_field(load_fits(out))
    grid = Grid()
    g["ROOF_LOCAL"] = [score_at(geom, grid, dx, dy) if not math.isnan(dx) else np.nan
                       for geom, dx, dy in zip(g.geometry, g.LOCAL_DX, g.LOCAL_DY)]
    del grid
    g["CLASS"] = classes(g)
    counts = g.CLASS.value_counts().to_dict()
    print("classes:", counts, flush=True)
    # Derived outlines: (a) every footprint moved by its neighbourhood's shift; (b) the best fit, i.e. SYSTEMATIC moved by
    # the neighbourhood's shift, REAL_OFFSET by its own, the rest where they are.
    def moved(r, how):
        if how == "local" or r.CLASS == "SYSTEMATIC":
            dx, dy = (0, 0) if math.isnan(r.LOCAL_DX) else (r.LOCAL_DX, r.LOCAL_DY)
        elif r.CLASS == "REAL_OFFSET":
            dx, dy = r.DX, r.DY
        else:
            dx, dy = 0, 0
        return affinity.translate(r.geometry, dx, dy)
    local = g.assign(geometry=[moved(r, "local") for r in g.itertuples()])
    best = g.assign(geometry=[moved(r, "best") for r in g.itertuples()])
    keep = ["SOURCE_ID", "PARCEL_ID", "AREA_M2", "ROOF0", "ROOF_BEST", "ROOF_LOCAL", "DX", "DY", "SHIFT_M", "PLATEAU_M",
            "SHARP", "MARGIN", "EDGE", "CANOPY", "RELIABLE", "LOCAL_DX", "LOCAL_DY", "LOCAL_N", "LOCAL_SPREAD", "LOCAL_M",
            "RESID_M", "CLASS", "geometry"]
    gpkg = out/"county-alignment.gpkg"
    if gpkg.exists():
        gpkg.unlink()
    g[keep].to_file(gpkg, layer="footprints_as_county", driver="GPKG")
    best[keep].to_file(gpkg, layer="footprints_best_fit", driver="GPKG")
    local[keep].to_file(gpkg, layer="footprints_local_shift", driver="GPKG")
    cells = pd.read_csv(out/"field-250m.csv")
    gpd.GeoDataFrame(cells, geometry=gpd.points_from_xy(cells.CX + 125, cells.CY + 125), crs=6341).to_file(
        gpkg, layer="shift_field_250m", driver="GPKG")
    # The two review queues against each set of outlines
    with rasterio.open(CAND/"clusters.tif") as src:
        labels, transform = src.read(1), src.transform
    total = np.bincount(labels.ravel())
    cand = gpd.read_file(CAND/"candidates.gdb", layer="candidates")
    number = cand.CAND_ID.str[2:].astype(int).values
    index = json.loads((REVIEW/"index.json").read_text(encoding="utf-8"))
    pairs = [it for it in index["items"] if it["queue"] == "pairs"]
    related = {}
    for path in sorted((REVIEW/"bundles").glob("p*.json")):
        for k, v in json.loads(path.read_text(encoding="utf-8")).items():
            related[k] = v["related"]
    by_sid = g.set_index("SOURCE_ID")
    queue_groups = {it["id"]: it["group"] for it in index["items"] if it["queue"] == "candidates"}
    result = {"classes": counts}
    explained_sets = {}
    for name, layer in (("local_shift", local), ("best_fit", best)):
        near = near_mask(layer.geometry, labels.shape, transform)
        inside = np.bincount(labels[near].ravel(), minlength=len(total))
        share = inside[number] / total[number]
        cand_ex = set(cand.CAND_ID[share >= 0.8])
        explained_sets[name] = cand_ex
        roof_after = by_sid.ROOF_LOCAL if name == "local_shift" else by_sid.ROOF_BEST.where(
            by_sid.CLASS.isin(["REAL_OFFSET"]), by_sid.ROOF_LOCAL.where(by_sid.CLASS == "SYSTEMATIC", by_sid.ROOF0))
        pair_ex = [p["id"] for p in pairs if roof_after.get(p["id"][2:], 0) >= 0.85
                   and all(c in cand_ex for c in related[p["id"]])]
        by_group = pd.Series([queue_groups[c] for c in cand_ex], dtype=object).value_counts().to_dict()
        result[name] = {"candidates_explained": len(cand_ex), "by_group": by_group, "pairs_explained": len(pair_ex),
                        "pairs_explained_ids": pair_ex}
        del near
        print(name, json.dumps({k: v for k, v in result[name].items() if k != "pairs_explained_ids"}), flush=True)
    pd.DataFrame({"CAND_ID": cand.CAND_ID, "GROUP": [queue_groups[c] for c in cand.CAND_ID],
                  "EXPLAINED_BY_LOCAL_SHIFT": cand.CAND_ID.isin(explained_sets["local_shift"]).astype(int),
                  "EXPLAINED_BY_BEST_FIT": cand.CAND_ID.isin(explained_sets["best_fit"]).astype(int)}).to_csv(
        out/"candidates-explained.csv", index=False)
    result["before"] = {"candidates": len(cand), "attached": sum(1 for v in queue_groups.values() if v.startswith("attached")),
                        "pairs": len(pairs)}
    g.drop(columns="geometry").to_csv(out/"classes.csv", index=False)
    (out/"classify.json").write_text(json.dumps(result, indent=1, default=str), encoding="utf-8")


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("step", choices=("fit", "field", "classify"))
    p.add_argument("out", type=Path)
    p.add_argument("--pilot", action="store_true")
    a = p.parse_args(argv)
    if a.step == "fit":
        fit(a.out.resolve(), a.pilot)
    elif a.step == "field":
        field(a.out.resolve())
    else:
        classify(a.out.resolve())


if __name__ == "__main__":
    main()
