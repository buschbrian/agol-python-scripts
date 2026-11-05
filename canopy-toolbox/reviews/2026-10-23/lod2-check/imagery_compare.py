r"""Is the roof that terrain clipping removes real? Two roofer configurations on aerial imagery (October 24, 2026).

    python reviews/2026-10-23/lod2-check/imagery_compare.py SWEEP_DIR OUT CONFIG_A CONFIG_B [--n 24] [--min-added 0.15] [--seed 1]

ArcGIS Pro Python or the deep-learning clone (arcpy, pyproj, numpy, Pillow; PYTHONNOUSERSITE=1). Same imagery source and shift as
imagery_check.py (Esri World Imagery's public export service, review only). On the pilot tile it picks buildings where
CONFIG_B covers at least --min-added more of the county footprint than CONFIG_A (what roofer's terrain clipping cuts away), seeded
random, and draws three cells: imagery, CONFIG_A's roof planes, CONFIG_B's, the footprint dashed yellow. The shift is found for
CONFIG_B's planes and used for both. Output: OUT\\compare_NN.png and OUT\\compare.csv (rating columns empty).
"""
import argparse
import csv
import importlib.util
import json
from pathlib import Path
import random
import sys

import numpy as np

HERE = Path(__file__).resolve()


def _load(name):
    spec = importlib.util.spec_from_file_location(name, HERE.parent/f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def main(argv=None):
    import arcpy
    from PIL import Image, ImageDraw, ImageFont
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("sweep", type=Path)
    p.add_argument("out", type=Path)
    p.add_argument("a")
    p.add_argument("b")
    p.add_argument("--n", type=int, default=24)
    p.add_argument("--min-added", type=float, default=0.15)
    p.add_argument("--seed", type=int, default=1)
    args = p.parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(HERE.parent))
    ic, ri, ra = _load("imagery_check"), _load("roofer_inspect"), _load("roof_attributes")
    fps = {fid: np.array([(pt.X, pt.Y) for pt in s.getPart(0) if pt]) for fid, s in
           arcpy.da.SearchCursor(str(ri.PILOT/"input"/"footprints.shp"), ["FP_ID", "SHAPE@"])}
    data = {c: ri.config_faces(args.sweep, c) for c in (args.a, args.b)}
    added = {}
    for fid, fp in fps.items():
        cover = {}
        for c in (args.a, args.b):
            rings = data[c][1].get(fid, [])
            if not rings:
                break
            lo, hi = fp.min(0)-1, fp.max(0)+1
            size = (int((hi[0]-lo[0])/0.25)+1, int((hi[1]-lo[1])/0.25)+1)
            f = ri.mask([fp], (lo[0], hi[1]), size)
            cover[c] = (ri.mask(rings, (lo[0], hi[1]), size) & f).sum()/max(1, f.sum())
        else:
            if cover[args.b]-cover[args.a] >= args.min_added:
                added[fid] = (cover[args.a], cover[args.b], float(arcpy.PointGeometry(arcpy.Point(*fp.mean(0))).area if False else 0))
    ids = sorted(added)
    random.Random(args.seed).shuffle(ids)
    ids = ids[:args.n]
    mapper = ic.Mapper()
    font = ImageFont.load_default()
    cells, rows = [], []
    for fid in ids:
        fp = fps[fid]
        pa = [ring for ring in data[args.a][0].get(fid, [])]
        pb = [ring for ring in data[args.b][0].get(fid, [])]
        allxy = np.vstack([fp]+[r[:, :2] for r in pb]+[r[:, :2] for r in pa])
        cx, cy = (allxy[:, 0].min()+allxy[:, 0].max())/2, (allxy[:, 1].min()+allxy[:, 1].max())/2
        half = max(20.0, 0.5*max(np.ptp(allxy[:, 0]), np.ptp(allxy[:, 1]))+8.0)
        off = mapper.offset(cx, cy)
        c3 = mapper(np.array([[cx, cy]]), off)[0]
        span = half*1.2992
        img = ic.fetch((c3[0]-span, c3[1]-span, c3[0]+span, c3[1]+span), ic.PX*2).resize((ic.PX, ic.PX))

        def px(xy):
            m = mapper(np.asarray(xy)[:, :2], off)
            return [((x-(c3[0]-span))/(2*span)*ic.PX, ((c3[1]+span)-y)/(2*span)*ic.PX) for x, y in m]
        pol_a = [(px(r), (0, 200, 255)) for r in pa]
        pol_b = [(px(r), (255, 80, 0)) for r in pb]
        mask = Image.new("L", (ic.PX, ic.PX), 0)
        md = ImageDraw.Draw(mask)
        for pts, _ in pol_b:
            md.line(pts+[pts[0]], fill=255, width=1)
        ys, xs = np.nonzero(np.asarray(mask))
        (dx, dy, _), ratio = ic.best_shift(img.convert("L"), (ys, xs)) if len(ys) > 10 else ((0, 0, 0), 1.0)
        fp_px = px(fp)
        oa, ob = ic.draw(img, pol_a, fp_px, (dx, dy), ic.PX), ic.draw(img, pol_b, fp_px, (dx, dy), ic.PX)
        cell = Image.new("RGB", (ic.PX*3+8, ic.PX+16), (255, 255, 255))
        for k, im in enumerate((img, oa, ob)):
            cell.paste(im, (k*(ic.PX+4), 16))
        ImageDraw.Draw(cell).text((3, 3), f"FP {fid} | imagery | {args.a} covers {added[fid][0]*100:.0f}% of footprint | {args.b} covers {added[fid][1]*100:.0f}% | shift {np.hypot(dx, dy)*2*half/ic.PX:.1f} m",
                                  fill=(0, 0, 0), font=font)
        cells.append(cell)
        rows.append({"FP_ID": fid, "COVER_A": round(added[fid][0], 2), "COVER_B": round(added[fid][1], 2), "ADDED_AREA_IS_ROOF": "", "NOTE": ""})
    per = 5
    for k in range(0, len(cells), per):
        chunk = cells[k:k+per]
        w, h = chunk[0].size
        sheet = Image.new("RGB", (w, (h+4)*len(chunk)), (255, 255, 255))
        for j, c in enumerate(chunk):
            sheet.paste(c, (0, j*(h+4)))
        sheet.save(args.out/f"compare_{k//per+1:02d}.png")
    with open(args.out/"compare.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(json.dumps({"buildings_where_B_adds_area": len(added), "drawn": len(cells)}))


if __name__ == "__main__":
    main()
