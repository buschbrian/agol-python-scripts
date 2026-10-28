r"""Plan-view comparison of roofer configurations against the county footprint, on the pilot tile (October 24, 2026).

    python reviews/2026-10-23/lod2-check/roofer_inspect.py SWEEP_DIR OUT.png CONFIG [CONFIG ...] [--ids FP ...] [--n 8]

ArcGIS Pro Python or the deep-learning clone (arcpy, numpy, matplotlib; PYTHONNOUSERSITE=1). Read-only. For each building, one
panel per configuration: the LoD 2.2 roof faces filled by height, edges black, the county footprint dashed magenta. Without
--ids it picks the n buildings where the configurations' outlines differ most from the footprint (symmetric difference), so the
edge behaviour shows. Also prints, per configuration, the median and 90th percentile of the share of the footprint the model
outline does not cover, and the share of the model outline lying outside the footprint (both from 0.25 m masks).
"""
import argparse
import importlib.util
import json
from pathlib import Path
import sys

import numpy as np

HERE = Path(__file__).resolve()
PILOT = Path(r"H:\lidar\2023-salt-lake-valley\runs\roofer-20261024")


def _load(name):
    spec = importlib.util.spec_from_file_location(name, HERE.parent/f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def config_faces(sweep, name):
    """fid -> list of (ring Nx3, ground ring) for the config's LoD 2.2 solids."""
    ra, cc = _load("roof_attributes"), _load("collect_cityjson")
    tmp = sweep/name/"city.json"
    if not tmp.exists():
        cc.collect(sweep/name/"output", tmp)
    city = json.loads(tmp.read_text(encoding="utf-8"))
    roofs, grounds = {}, {}
    scale, translate = np.array(city["transform"]["scale"]), np.array(city["transform"]["translate"])
    verts = np.array(city["vertices"], float)*scale+translate
    for fid, part, n, surface, ring, holes in ra.faces(city):
        roofs.setdefault(fid, []).append(ring)
    for key, o in city["CityObjects"].items():
        if o["type"] != "BuildingPart":
            continue
        for g in o["geometry"]:
            if g["lod"] == "2.2" and g["type"] == "Solid":
                kinds = [s["type"] for s in g["semantics"]["surfaces"]]
                for shell, labels in zip(g["boundaries"], g["semantics"]["values"]):
                    for face, label in zip(shell, labels):
                        if kinds[label] == "GroundSurface":
                            grounds.setdefault(int(key.split("-")[0]), []).append(verts[face[0]])
    return roofs, grounds


def mask(rings, origin, size, cell=0.25):
    from PIL import Image, ImageDraw
    img = Image.new("L", size, 0)
    d = ImageDraw.Draw(img)
    for ring in rings:
        d.polygon([((x-origin[0])/cell, (origin[1]-y)/cell) for x, y in ring[:, :2]], fill=1)
    return np.asarray(img, bool)


def main(argv=None):
    import arcpy
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Polygon as MplPolygon
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("sweep", type=Path)
    p.add_argument("out", type=Path)
    p.add_argument("configs", nargs="+")
    p.add_argument("--ids", nargs="*", type=int)
    p.add_argument("--n", type=int, default=8)
    a = p.parse_args(argv)
    fps = {fid: np.array([(pt.X, pt.Y) for pt in s.getPart(0) if pt]) for fid, s in
           arcpy.da.SearchCursor(str(PILOT/"input"/"footprints.shp"), ["FP_ID", "SHAPE@"])}
    data = {c: config_faces(a.sweep, c) for c in a.configs}
    score = {c: {} for c in a.configs}
    for c, (roofs, grounds) in data.items():
        for fid, rings in grounds.items():
            fp = fps[fid]
            lo, hi = np.minimum(fp.min(0), np.min([r[:, :2].min(0) for r in rings], axis=0))-2, \
                np.maximum(fp.max(0), np.max([r[:, :2].max(0) for r in rings], axis=0))+2
            size = (int((hi[0]-lo[0])/0.25)+1, int((hi[1]-lo[1])/0.25)+1)
            origin = (lo[0], hi[1])
            m, f = mask(rings, origin, size), mask([fp], origin, size)
            score[c][fid] = (1-(m & f).sum()/max(1, f.sum()), (m & ~f).sum()/max(1, m.sum()))
    for c in a.configs:
        miss = np.array([v[0] for v in score[c].values()])
        out = np.array([v[1] for v in score[c].values()])
        print(f"{c:18s} footprint uncovered: median {np.median(miss)*100:.1f}% p90 {np.percentile(miss, 90)*100:.1f}% | "
              f"model outside footprint: median {np.median(out)*100:.1f}% p90 {np.percentile(out, 90)*100:.1f}%")
    ids = a.ids
    if not ids:
        common = set.intersection(*[set(score[c]) for c in a.configs])
        spread = {fid: max(score[c][fid][0] for c in a.configs)-min(score[c][fid][0] for c in a.configs) for fid in common}
        ids = sorted(spread, key=spread.get, reverse=True)[:a.n]
    fig, axes = plt.subplots(len(ids), len(a.configs), figsize=(3.6*len(a.configs), 3.4*len(ids)), squeeze=False)
    for i, fid in enumerate(ids):
        for j, c in enumerate(a.configs):
            ax = axes[i][j]
            rings = data[c][0].get(fid, [])
            zs = [r[:, 2].mean() for r in rings] or [0]
            lo, hi = min(zs), max(zs)
            for ring in rings:
                shade = 0.5 if hi == lo else (ring[:, 2].mean()-lo)/(hi-lo)
                ax.add_patch(MplPolygon(ring[:, :2], closed=True, facecolor=plt.cm.viridis(0.15+0.8*shade), edgecolor="k", lw=0.5))
            fp = fps[fid]
            ax.plot(*np.vstack([fp, fp[:1]]).T, color="magenta", ls="--", lw=1.1)
            ax.set_aspect("equal")
            ax.set_xticks([]); ax.set_yticks([])
            ax.autoscale_view()
            miss, outside = score[c].get(fid, (np.nan, np.nan))
            ax.set_title(f"FP {fid} | {c} | {len(rings)} faces | uncovered {miss*100:.0f}% outside {outside*100:.0f}%", fontsize=7)
    fig.tight_layout()
    fig.savefig(a.out, dpi=80)
    print("ids", ids)


if __name__ == "__main__":
    main()
