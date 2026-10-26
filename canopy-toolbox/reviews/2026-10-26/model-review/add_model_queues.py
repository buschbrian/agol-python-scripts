"""Append the 3D-building and CFTree review queues to the footprint review page's data (October 26, 2026).

Reads the queues written by queues.py and adds four queues to an existing page data folder, the way `add-pairs` did on
October 23: new bundle files (m0001...), the index appended, every existing item, chip and answer left as it is.

- models: county footprints whose 3D building has no roofer LoD2.2 roof (no model, LOD1.2 block, LOD2.0 roof), except
  those already in the "county footprints with no 2023 roof" queue.
- trees: a stratified random sample first, then models with several October 22 treetops inside (merged?), then models
  whose inferred trunk is inside a county footprint.
- tree_seams: one item per cross-tile overlap pair.
- tree_rejects: the 75 candidates CFTree could not model.

Tree items carry a side-view image: the model's own LiDAR points, the other model's (seams), other vegetation nearby,
the crown mesh silhouette and the inferred trunk, from the CFTree run's segmentation.xyz and CityJSON.

Map outlines go to WGS84 through Web Mercator on the ITRF08 datum. ArcPy's WGS_1984_(ITRF08)_To_NAD_1983_2011 is
sampled on a grid and fitted as a plane on top of pyproj's datum-free projection (residual about 1.6 m, varying by
millimetres across the city); the fit is checked against the county footprints' ArcPy-projected web copies.

    python add_model_queues.py QUEUES DATA [--pilot] [--sample 300] [--seed 20261026]

--pilot writes a separate pilot folder DATA (it must not exist) holding only 5 items per queue and an empty answers
folder, for `serve_footprint_review.py --data DATA`.
"""
import argparse
import collections
import csv
import datetime
import gzip
import json
import math
import os
from pathlib import Path
import random
import sqlite3
import sys

import numpy as np

HERE = Path(__file__).resolve()
PAGE = HERE.parents[1].parent/"2026-10-23"/"footprint-review"
sys.path.insert(0, str(PAGE))
sys.path.insert(0, str(HERE.parents[3]))
import build_review_data as brd  # noqa: E402

CFTREE = Path(r"C:\Users\Brian\Documents\Codex\2026-10-24\go-x20\work\cftree-city-20261025")
EXCEPTIONS = Path(r"C:\Users\Brian\Documents\Codex\2026-10-24\go-x20\outputs\cftree-city-review-exceptions.csv")
TRANSFORM = "WGS_1984_(ITRF08)_To_NAD_1983_2011"
FEET = brd.FEET
BUNDLE = brd.BUNDLE
MERGED_BINS = ((3, 5), (6, 10), (11, 10**9))   # October 22 treetops inside one model's outline ("merged?" group)
GROUP_CAP = 300         # items per tree group beyond the sample (largest cue first)
CONTEXT_M = 6           # vegetation points within this distance of the window shown grey in the side views


class Web:
    """EPSG 6341 -> WGS84 latitude/longitude through EPSG 3857 on the ITRF08 datum."""

    def __init__(self, county, county_web):
        import arcpy
        import pyproj
        self.tr = pyproj.Transformer.from_crs(6341, 3857, always_xy=True)
        x0, y0, x1, y1 = county.total_bounds
        sr0, sr1 = arcpy.SpatialReference(6341), arcpy.SpatialReference(3857)
        rows = []
        for x in np.linspace(x0, x1, 6):
            for y in np.linspace(y0, y1, 6):
                g = arcpy.PointGeometry(arcpy.Point(x, y), sr0).projectAs(sr1, TRANSFORM).firstPoint
                px, py = self.tr.transform(x, y)
                rows.append((x, y, g.X - px, g.Y - py))
        a = np.asarray(rows)
        design = np.c_[np.ones(len(a)), a[:, 0] - x0, a[:, 1] - y0]
        self.origin = (x0, y0)
        self.cx = np.linalg.lstsq(design, a[:, 2], rcond=None)[0]
        self.cy = np.linalg.lstsq(design, a[:, 3], rcond=None)[0]
        fit = np.abs(np.c_[design @ self.cx - a[:, 2], design @ self.cy - a[:, 3]]).max()
        assert fit < 0.002, fit
        # Against the county footprints' own ArcPy-projected copies: first vertex of 200 footprints.
        worst = 0.0
        sample = county[county.SOURCE_ID.isin(county_web.index)].sample(200, random_state=1)
        for r in sample.itertuples():
            ex = list(r.geometry.exterior.coords) if r.geometry.geom_type == "Polygon" else list(r.geometry.geoms[0].exterior.coords)
            wg = county_web.loc[r.SOURCE_ID].geometry
            wx = list(wg.exterior.coords) if wg.geom_type == "Polygon" else list(wg.geoms[0].exterior.coords)
            mx, my = self.merc(*ex[0])
            worst = max(worst, math.hypot(mx - wx[0][0], my - wx[0][1]))
        assert worst < 0.01, f"ITRF08 fit is {worst:.3f} m from the county web copies"
        self.check = {"plane_fit_m": round(float(fit), 5), "vs_county_web_m": round(worst, 5), "transform": TRANSFORM}

    def merc(self, x, y):
        px, py = self.tr.transform(x, y)
        dx, dy = x - self.origin[0], y - self.origin[1]
        return px + self.cx[0] + self.cx[1] * dx + self.cx[2] * dy, py + self.cy[0] + self.cy[1] * dx + self.cy[2] * dy

    def ll(self, rings):
        return brd.merc_to_ll([[self.merc(x, y) for x, y in ring] for ring in rings])


def dot(x, y, r=0.6, n=12):
    """A small ring standing for a point (the trunk, or a rejected segment's top) on the map and the chip."""
    return [[(x + r * math.cos(2 * math.pi * k / n), y + r * math.sin(2 * math.pi * k / n)) for k in range(n + 1)]]


def indices(boundaries):
    if isinstance(boundaries, int):
        yield boundaries
    else:
        for value in boundaries:
            yield from indices(value)


def mesh_vertices(run, tile, shard, model_id):
    """Crown and trunk vertices (EPSG 6341, metres) of one model from its CityJSON shard."""
    key = (tile, shard)
    if key not in mesh_vertices.cache:
        mesh_vertices.cache.clear()
        with gzip.open(run/"tiles"/tile/shard, "rt", encoding="utf-8") as f:
            mesh_vertices.cache[key] = json.load(f)
    d = mesh_vertices.cache[key]
    v = np.asarray(d["vertices"], dtype=np.float64) * d["transform"]["scale"] + d["transform"]["translate"]
    obj = d["CityObjects"]["T_" + model_id]
    crown = v[np.unique(list(indices(obj["geometry"][0]["boundaries"])))]
    trunk = v[np.unique(list(indices(obj["geometry"][1]["boundaries"])))]
    return crown, trunk, obj["attributes"]


mesh_vertices.cache = {}


def load_segmentation(path):
    import pandas as pd
    t = pd.read_csv(path, sep=" ", header=None, names=["seg", "x", "y", "z"],
                    dtype={"seg": np.int32, "x": np.float64, "y": np.float64, "z": np.float64}, engine="c")
    return t["seg"].to_numpy(), t[["x", "y", "z"]].to_numpy()


class Ground:
    """The October 22 terrain (0.5 m) at any points, so the side views show height above the real ground."""

    def __init__(self, chips):
        self.ds, self.t = chips.ds["dtm"], chips.t

    def __call__(self, x, y):
        from rasterio.windows import Window
        c = np.floor((np.asarray(x, float) - self.t.c) / brd.CELL).astype(int)
        r = np.floor((self.t.f - np.asarray(y, float)) / brd.CELL).astype(int)
        c0, r0 = int(c.min()), int(r.min())
        a = self.ds.read(1, window=Window(c0, r0, int(c.max()) - c0 + 1, int(r.max()) - r0 + 1), boundless=True,
                         fill_value=self.ds.nodata).astype(np.float64)
        a[(a == self.ds.nodata) | ~np.isfinite(a)] = np.nan
        return a[r - r0, c - c0]


SHRUB_M = 2.0           # the tree threshold drawn in the side views (CFTree and the canopy products use 2 m)


def profile_png(own, other, context, crown, trunk, base_z, ground=None):
    """Two side views (looking north: x-z; looking west: y-z), equal scales, as a PNG data URI. With ground, points
    under 2 m above the terrain are drawn in a lighter colour, and the terrain and the 2 m line are drawn."""
    import base64
    import io
    from PIL import Image, ImageDraw
    from shapely import MultiPoint
    pts = [p for p in (own, other) if p is not None and len(p)]
    allp = np.vstack(pts + ([crown] if crown is not None else []))
    cx, cy = (allp[:, 0].min() + allp[:, 0].max()) / 2, (allp[:, 1].min() + allp[:, 1].max()) / 2
    zhi = allp[:, 2].max() + 1.5
    half = max(8.0, 0.6 * max(np.ptp(allp[:, 0]), np.ptp(allp[:, 1])) + 2)
    along = np.arange(-half, half + 0.25, 0.5)
    lines = {}
    if ground is not None:
        lines = {0: ground(cx + along, np.full_like(along, cy)), 1: ground(np.full_like(along, cx), cy + along)}
    lows = [allp[:, 2].min()] + ([base_z] if base_z is not None else []) + \
        [float(np.nanmin(v)) for v in lines.values() if np.isfinite(v).any()]
    zlo = min(lows) - 1
    half = max(half, 0.5 * (zhi - zlo))
    along = np.arange(-half, half + 0.25, 0.5)
    if ground is not None:
        lines = {0: ground(cx + along, np.full_like(along, cy)), 1: ground(np.full_like(along, cx), cy + along)}

    def low(arr):
        if ground is None or arr is None or not len(arr):
            return np.zeros(0 if arr is None else len(arr), bool)
        return (arr[:, 2] - ground(arr[:, 0], arr[:, 1])) < SHRUB_M
    W = H = 330
    s = W / (2 * half)                           # the view stands on the ground: zlo at the bottom, 2 * half tall
    img = Image.new("RGB", (2 * W + 10, H), "white")
    d = ImageDraw.Draw(img)

    def view(axis, ox):
        c = cx if axis == 0 else cy
        flip = 1 if axis == 0 else -1           # looking west, north is to the right

        def u(v):
            return ox + W / 2 + flip * (v - c) * s

        def xy(p):
            return u(p[axis]), H - (p[2] - zlo) * s
        if context is not None and len(context):
            keep = np.abs(context[:, 1 - axis] - (cy if axis == 0 else cx)) < half
            for p in context[keep][::max(1, int(keep.sum() // 6000) or 1)]:
                x, y = xy(p)
                d.point((x, y), fill=(184, 184, 176))
        if axis in lines:
            g = lines[axis]
            for k in range(len(along) - 1):
                if np.isfinite(g[k]) and np.isfinite(g[k + 1]):
                    a0, a1 = c + along[k], c + along[k + 1]
                    d.line([(u(a0), H - (g[k] - zlo) * s), (u(a1), H - (g[k + 1] - zlo) * s)], fill=(140, 110, 70), width=2)
                    if k % 2 == 0:                             # dashed: the 2 m tree line
                        d.line([(u(a0), H - (g[k] + SHRUB_M - zlo) * s), (u(a1), H - (g[k + 1] + SHRUB_M - zlo) * s)],
                               fill=(40, 140, 60), width=1)
        for arr, col, pale in ((other, (255, 61, 245), (245, 175, 240)), (own, (255, 42, 42), (235, 160, 40))):
            if arr is None:
                continue
            step = max(1, len(arr) // 5000)
            under = low(arr)
            for p, is_low in zip(arr[::step], under[::step] if len(under) else [False] * len(arr[::step])):
                x, y = xy(p)
                d.rectangle((x - 0.6, y - 0.6, x + 0.6, y + 0.6), fill=pale if is_low else col)
        if crown is not None and len(crown) >= 3:
            hull = MultiPoint([(p[axis], p[2]) for p in crown]).convex_hull
            if hull.geom_type == "Polygon":
                d.line([(u(h), H - (z - zlo) * s) for h, z in hull.exterior.coords], fill=(30, 30, 30), width=2)
        if trunk is not None and len(trunk):
            a, b = sorted((u(trunk[:, axis].min()), u(trunk[:, axis].max())))
            d.rectangle((a, H - (trunk[:, 2].max() - zlo) * s, b, H - (trunk[:, 2].min() - zlo) * s),
                        outline=(120, 70, 20), width=2)
        if base_z is not None and axis not in lines:
            d.line([(ox, H - (base_z - zlo) * s), (ox + W, H - (base_z - zlo) * s)], fill=(140, 110, 70), width=1)
        for m in range(0, int(2 * half) + 1, 5):              # 5 m ticks along the bottom
            d.line([(ox + m * s, H - 1), (ox + m * s, H - 6)], fill=(90, 90, 90))
        d.text((ox + 4, 4), "looking north" if axis == 0 else "looking west", fill=(60, 60, 60))
    view(0, 0)
    view(1, W + 10)
    d.text((W - 60, H - 18), f"ticks 5 m ({5 * FEET:.0f} ft)", fill=(90, 90, 90))
    if lines:
        d.text((W + 14, H - 18), f"dashed green: {SHRUB_M:.0f} m ({SHRUB_M * FEET:.1f} ft) above ground", fill=(40, 140, 60))
    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=True)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def feet(m):
    return f"{m:.1f} m ({m * FEET:.0f} ft)"


def select(qdir, sample_n, seed, pilot):
    """The rows each queue gets, in page order."""
    with (qdir/"roof-queue.csv").open(encoding="utf-8") as f:
        roofs = [r for r in csv.DictReader(f) if r["IN_COUNTY_QUEUE"] == "0"]
    level_group = {"No hybrid model": "no_model", "Esri LOD1.2": "lod12", "Esri LOD2.0": "lod20"}
    for r in roofs:
        r["GROUP"] = level_group[r["LEVEL"]]
    roofs.sort(key=lambda r: (list(level_group.values()).index(r["GROUP"]), float(r["ROOF_COV_PCT"] or -1), r["SOURCE_ID"]))
    with (qdir/"tree-cues.csv").open(encoding="utf-8") as f:
        trees = list(csv.DictReader(f))
    by_id = {t["MODEL_ID"]: t for t in trees}
    rng = random.Random(seed)
    # Sample: stratified by height (2-5, 5-8, 8-12, 12-20, 20+ m), equal shares, drawn before any cue is looked at.
    strata = collections.defaultdict(list)
    for t in trees:
        h = float(t["HEIGHT_FT"]) / FEET
        strata[next(k for k, top in enumerate((5, 8, 12, 20, 1e9)) if h < top)].append(t["MODEL_ID"])
    sample = []
    for k in sorted(strata):
        sample += rng.sample(sorted(strata[k]), min(len(strata[k]), sample_n // len(strata)))
    chosen = set(sample)
    # Merged? Half the models hold 3 or more October 22 treetops, so draw equally from 3-5, 6-10 and 11+: the answers
    # say whether CFTree merges crowns or the October 22 detector splits them, at each level.
    merged = []
    for lo, hi in MERGED_BINS:
        pool = sorted(t["MODEL_ID"] for t in trees if lo <= int(t["TREETOPS_INSIDE"]) <= hi and t["MODEL_ID"] not in chosen)
        merged += [by_id[m] for m in rng.sample(pool, min(len(pool), GROUP_CAP // len(MERGED_BINS)))]
    merged.sort(key=lambda t: (int(t["TREETOPS_INSIDE"]), t["MODEL_ID"]))
    chosen |= {t["MODEL_ID"] for t in merged}
    over = sorted((t for t in trees if t["TRUNK_IN_FOOTPRINT"] == "1" and t["MODEL_ID"] not in chosen),
                  key=lambda t: (-float(t["ROOF_OVERLAP_PCT"]), t["MODEL_ID"]))
    over_all = len(over)
    over = rng.sample(over, min(GROUP_CAP, len(over)))
    over.sort(key=lambda t: (-float(t["ROOF_OVERLAP_PCT"]), t["MODEL_ID"]))
    tree_items = ([("sample", by_id[m]) for m in sample] + [("merged", t) for t in merged] + [("over_roof", t) for t in over])
    seams, seen = [], set()
    for t in sorted(trees, key=lambda t: t["MODEL_ID"]):
        p = t["SEAM_PARTNER"]
        if p and frozenset((t["MODEL_ID"], p)) not in seen:
            seen.add(frozenset((t["MODEL_ID"], p)))
            seams.append(("seam", t, by_id[p]))
    with EXCEPTIONS.open(encoding="utf-8-sig") as f:
        rejects = [("no_terrain" if "terrain" in r["reason"] else "no_trunk", r) for r in csv.DictReader(f)]
    assert len(rejects) == 75
    if pilot:
        roofs = [r for g in level_group.values() for r in [x for x in roofs if x["GROUP"] == g][:2]][:5]
        tree_items = tree_items[:2] + [x for x in tree_items if x[0] == "merged"][:2] + [x for x in tree_items if x[0] == "over_roof"][:1]
        seams, rejects = seams[:5], rejects[:5]
    sizes = {"models": dict(collections.Counter(r["GROUP"] for r in roofs)),
             "trees": dict(collections.Counter(g for g, _ in tree_items)), "tree_seams": len(seams),
             "tree_rejects": dict(collections.Counter(g for g, _ in rejects)),
             "trunk_in_footprint_total": over_all, "sample_strata": {k: len(v) for k, v in sorted(strata.items())}}
    return roofs, tree_items, seams, rejects, sizes


def main(argv=None):
    import geopandas as gpd
    import shapely
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("queues", type=Path)
    p.add_argument("data", type=Path)
    p.add_argument("--cftree", type=Path, default=CFTREE)
    p.add_argument("--pilot", action="store_true")
    p.add_argument("--sample", type=int, default=300)
    p.add_argument("--seed", type=int, default=20261026)
    p.add_argument("--refresh-profiles", action="store_true",
                   help="redraw only the side views of the tree items already in DATA (atomically, bundle by bundle)")
    a = p.parse_args(argv)
    data, run = a.data.resolve(), a.cftree.resolve()
    roofs, tree_items, seams, rejects, sizes = select(a.queues, a.sample, a.seed, a.pilot)
    print("selected:", json.dumps(sizes), flush=True)
    refresh = {} if a.refresh_profiles else None   # item id -> new side view

    if refresh is not None:
        built = json.loads((data/"index.json").read_text(encoding="utf-8"))
        index, roofs = list(built["items"]), []
    elif a.pilot:
        (data/"bundles").mkdir(parents=True, exist_ok=False)
        (data/"answers").mkdir()
        built, index = {"schema": "footprint-review/1", "built": datetime.datetime.now().isoformat(timespec="seconds"),
                        "pilot": True, "groups": dict(brd.GROUPS), "items": []}, []
    else:
        built = json.loads((data/"index.json").read_text(encoding="utf-8"))
        if any(it["queue"] in ("models", "trees", "tree_seams", "tree_rejects") for it in built["items"]):
            raise ValueError("The model queues are already in this data")
        index = list(built["items"])
    start, prefix = len(index), "m"

    county = gpd.read_file(brd.LIB/"buildings.gdb", layer="building_heights")
    county_web = gpd.read_file(brd.COUNTY_WEB, layer="buildings").set_index("SOURCE_ID")
    web = Web(county, county_web)
    print("ITRF08:", web.check, flush=True)
    chips = brd.Chips()
    ground = Ground(chips)
    _, parcels = brd.load_parcels()
    brd.load_alignment()
    county_tree = shapely.STRtree(list(county.geometry))
    county_ids = list(county.SOURCE_ID)
    outlines = gpd.read_parquet(a.queues/"tree-outlines.parquet")
    hull_of = dict(zip(outlines.MODEL_ID, outlines.geometry))
    tree_index = shapely.STRtree(list(outlines.geometry))
    tree_ids = list(outlines.MODEL_ID)
    with (a.queues/"tree-cues.csv").open(encoding="utf-8") as f:
        cues = {t["MODEL_ID"]: t for t in csv.DictReader(f)}
    details = {}

    def context(chip, exclude_county=(), exclude_trees=(), trees=False):
        n = chip["n"] * brd.CELL
        box = shapely.box(chip["left"], chip["top"] - n, chip["left"] + n, chip["top"])
        out = {"county_px": [], "county_ll": [], "cand_px": [], "cand_ll": []}
        for j in county_tree.query(box, "intersects"):
            sid = county_ids[j]
            if sid in exclude_county:
                continue
            out["county_px"] += brd.Chips.px(brd.rings_of(county.geometry.iloc[j]), chip)
            if sid in county_web.index:
                out["county_ll"] += brd.merc_to_ll(brd.rings_of(county_web.loc[sid].geometry))
        if trees:
            for j in tree_index.query(box, "intersects"):
                if tree_ids[j] in exclude_trees:
                    continue
                rings = brd.rings_of(outlines.geometry.iloc[j])
                out["cand_px"] += brd.Chips.px(rings, chip)
                out["cand_ll"] += web.ll(rings)
        return out

    def item(item_id, queue, group, facts, rings, rings_ll, bounds, focus=None, related=None, profile=None,
             exclude_county=(), exclude_trees=(), trees=False, min_half=25.0):
        if refresh is not None:
            refresh[item_id] = profile
            return
        chip, uri = chips.render(bounds, min_half)
        details[item_id] = {"id": item_id, "queue": queue, "group": group, "facts": facts,
                            "outline_ll": rings_ll, "outline_px": brd.Chips.px(rings, chip),
                            "hint_ll": None, "hint_px": None,
                            "focus_ll": web.ll(focus) if focus else None,
                            "focus_px": brd.Chips.px(focus, chip) if focus else None,
                            "related": related or [], "profile": profile,
                            "chip": {"uri": uri, "size": chip["n"], "metres": chip["n"] * brd.CELL},
                            **context(chip, exclude_county, exclude_trees, trees)}

    # 3D buildings without a detailed roof
    fp = county.set_index("SOURCE_ID", drop=False)
    for r in roofs:
        sid = r["SOURCE_ID"]
        f = fp.loc[sid]
        facts = brd.county_facts(f, chips, parcels)
        facts = {"3D model": r["LEVEL"] + (f" (why: {r['FALLBACK_REASON']})" if r["FALLBACK_REASON"] else ""), **facts}
        facts["Height (median / P95)"] = ("—" if brd.missing(f.HEIGHT_P50_M) else
                                          f"{f.HEIGHT_P50_M:.1f} / {f.HEIGHT_P95_M:.1f} m "
                                          f"({f.HEIGHT_P50_M * FEET:.0f} / {f.HEIGHT_P95_M * FEET:.0f} ft)")
        rings = brd.rings_of(f.geometry)
        ll = brd.merc_to_ll(brd.rings_of(county_web.loc[sid].geometry)) if sid in county_web.index else web.ll(rings)
        item(f"MD{sid}", "models", r["GROUP"], facts, rings, ll, f.geometry.bounds, related=[f"PR{sid}"],
             exclude_county={sid})
    print(f"models: {len(roofs)} items", flush=True)

    # Tree items, tile by tile so each segmentation file is read once
    jobs = collections.defaultdict(list)            # tile -> [(item id, queue, group, own row, other row)]
    for g, t in tree_items:
        jobs[t["TILE_ID"]].append((f"TR{t['MODEL_ID'][:8]}", "trees", g, t, None))
    for g, t, o in seams:
        jobs[t["TILE_ID"]].append((f"TS{t['MODEL_ID'][:8]}", "tree_seams", g, t, o))
        jobs[o["TILE_ID"]]                            # make sure the partner's tile is read too
    for g, r in rejects:
        jobs[r["tile"]].append((f"TX{r['model_id'][:8]}", "tree_rejects", g, r, None))
    segment_of = {}
    for tile in jobs:
        with sqlite3.connect(f"{(run/'tiles'/tile/'models.sqlite').as_uri()}?mode=ro", uri=True) as db:
            segment_of.update({ident: (tile, int(s)) for ident, s in db.execute("SELECT id, segment FROM models")})
    # Points of seam partners live in the partner's tile: collect them first.
    partner_points = {}
    need = collections.defaultdict(set)
    for _, _, o in seams:
        need[o["TILE_ID"]].add(o["MODEL_ID"])
    for n, tile in enumerate(sorted(jobs), 1):
        seg, xyz = load_segmentation(run/"tiles"/tile/"segmentation.xyz")
        for mid in need.get(tile, ()):
            partner_points[mid] = xyz[seg == segment_of[mid][1]]
        for item_id, queue, group, t, o in jobs[tile]:
            if queue == "tree_rejects":
                s = int(t["segment_id"])
                own = xyz[seg == s]
                top = own[own[:, 2].argmax()]
                x0, y0 = own[:, 0].min(), own[:, 1].min()
                x1, y1 = own[:, 0].max(), own[:, 1].max()
                near = xyz[(np.abs(xyz[:, 0] - top[0]) < 15) & (np.abs(xyz[:, 1] - top[1]) < 15) & (seg != s)]
                prof = profile_png(own, None, near, None, None, None, ground)
                rings = dot(top[0], top[1], 0.8)
                facts = {"Candidate": t["model_id"], "Tile": tile, "Why CFTree stopped": t["reason"].split(": ", 1)[-1],
                         "LiDAR points in the segment": f"{len(own):,}",
                         "Top above the lowest point": feet(float(top[2] - own[:, 2].min())),
                         "Segment extent": f"{x1 - x0:.1f} × {y1 - y0:.1f} m",
                         "Point shown": "the segment's highest return; not a measured stem"}
                item(item_id, queue, group, facts, rings, web.ll(rings), (x0, y0, x1, y1), profile=prof, trees=True)
                continue
            crown, trunk, attrs = mesh_vertices(run, tile, t["SHARD"], t["MODEL_ID"])
            own = xyz[seg == segment_of[t["MODEL_ID"]][1]]
            hull = hull_of[t["MODEL_ID"]]
            tx, ty = float(t["TRUNK_X"]), float(t["TRUNK_Y"])
            rings = brd.rings_of(hull) + dot(tx, ty)
            x0, y0, x1, y1 = hull.bounds
            other = focus = None
            exclude = {t["MODEL_ID"]}
            if o is not None:
                other = partner_points.get(o["MODEL_ID"])
                focus = brd.rings_of(hull_of[o["MODEL_ID"]])
                exclude.add(o["MODEL_ID"])
                ox0, oy0, ox1, oy1 = hull_of[o["MODEL_ID"]].bounds
                x0, y0, x1, y1 = min(x0, ox0), min(y0, oy0), max(x1, ox1), max(y1, oy1)
            box = (x0 - CONTEXT_M, y0 - CONTEXT_M, x1 + CONTEXT_M, y1 + CONTEXT_M)
            sel = ((xyz[:, 0] > box[0]) & (xyz[:, 0] < box[2]) & (xyz[:, 1] > box[1]) & (xyz[:, 1] < box[3])
                   & (seg != segment_of[t["MODEL_ID"]][1]))
            prof = profile_png(own, other, xyz[sel], crown, trunk, attrs.get("trunk_base_height_m"), ground)
            facts = {"Model": t["MODEL_ID"], "Tile": tile,
                     "Height": feet(float(t["HEIGHT_FT"]) / FEET), "Crown width": feet(float(t["CROWN_WIDTH_FT"]) / FEET),
                     "Crown outline area": f"{float(t['CROWN_AREA_SQFT']):,.0f} ft²",
                     "Trunk diameter (inferred, not measured)": f"{float(t['TRUNK_DIAM_FT']):.1f} ft",
                     "LiDAR points in the model": f"{int(t['SOURCE_POINTS']):,}",
                     "October 22 treetops inside": t["TREETOPS_INSIDE"],
                     "Trunk inside a county footprint": "yes" if t["TRUNK_IN_FOOTPRINT"] == "1" else "no",
                     "Outline over county footprints": f"{float(t['ROOF_OVERLAP_PCT']):.0f}%",
                     "Near a tile edge": "yes" if t["EDGE_REVIEW"] == "True" else "no"}
            if o is not None:
                facts.update({"Other model": o["MODEL_ID"], "Other model's tile": o["TILE_ID"],
                              "Other model's height": feet(float(o["HEIGHT_FT"]) / FEET),
                              "Shared outline": f"{100 * float(t['SEAM_SHARE']):.0f}% of the smaller outline"})
            item(item_id, queue, group, facts, rings, web.ll(rings), (x0, y0, x1, y1), focus=focus, profile=prof,
                 exclude_trees=exclude, trees=True)
        print(f"  tile {tile} ({n}/{len(jobs)}): {len(details)} items", flush=True)
        del seg, xyz

    if refresh is not None:
        # Replace each tree item's side view in place, one bundle at a time (a partial file, then a rename); every
        # other field, the index and the answers stay as they are. A running page picks the new views up on reload.
        live = {it["id"]: it["bundle"] for it in index if it["queue"] in ("trees", "tree_seams", "tree_rejects")}
        assert set(refresh) == set(live), (len(refresh), len(live), sorted(set(refresh) ^ set(live))[:5])
        for name in sorted(set(live.values())):
            path = data/"bundles"/name
            bundle = json.loads(path.read_text(encoding="utf-8"))
            for i in bundle:
                if i in refresh:
                    bundle[i]["profile"] = refresh[i]
            partial = path.with_suffix(".partial")
            partial.write_text(json.dumps(bundle, separators=(",", ":"), allow_nan=False), encoding="utf-8")
            os.replace(partial, path)
        print(f"side views redrawn on {len(refresh)} items in {len(set(live.values()))} bundles")
        return
    order = ([f"MD{r['SOURCE_ID']}" for r in roofs] + [f"TR{t['MODEL_ID'][:8]}" for _, t in tree_items]
             + [f"TS{t['MODEL_ID'][:8]}" for _, t, _ in seams] + [f"TX{r['model_id'][:8]}" for _, r in rejects])
    assert len(order) == len(set(order)) == len(details), (len(order), len(set(order)), len(details))
    assert not set(order) & {it["id"] for it in index}
    for k in range(0, len(order), BUNDLE):
        ids = order[k:k + BUNDLE]
        name = f"{prefix}{k // BUNDLE + 1:04d}.json"
        path = data/"bundles"/name
        assert not path.exists(), path
        path.write_text(json.dumps({i: details[i] for i in ids}, separators=(",", ":"), allow_nan=False), encoding="utf-8")
        for i in ids:
            d = details[i]
            index.append({"id": i, "queue": d["queue"], "group": d["group"], "order": len(index) + 1, "bundle": name})
    counts = {}
    for it in index:
        counts.setdefault(it["queue"], {}).setdefault(it["group"], 0)
        counts[it["queue"]][it["group"]] += 1
    built.update(counts=counts, items=index, models_added=datetime.datetime.now().isoformat(timespec="seconds"),
                 models_sources={"queues": str(a.queues), "cftree": str(run), "itrf08": web.check, "selection": sizes,
                                 "seed": a.seed})
    partial = data/"index.partial"
    partial.write_text(json.dumps(built, separators=(",", ":")), encoding="utf-8")
    os.replace(partial, data/"index.json")
    print(f"added {len(index) - start} items:", json.dumps({q: counts[q] for q in
                                                           ("models", "trees", "tree_seams", "tree_rejects") if q in counts}))


if __name__ == "__main__":
    main()
