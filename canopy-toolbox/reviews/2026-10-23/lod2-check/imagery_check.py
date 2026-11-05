r"""An independent look at roofer's roofs on aerial imagery (October 24, 2026).

    python reviews/2026-10-23/lod2-check/imagery_check.py CITYJSON ROOFER_CITY_DIR OUT [--n 96] [--seed 20261024]

ArcGIS Pro Python or the deep-learning clone (arcpy, pyproj, numpy, Pillow; PYTHONNOUSERSITE=1). Read-only on its inputs; the only
network use is Esri World Imagery's public export service (one request per building, a 40 to 120 m window around it, sent as a
bounding box in Web Mercator); nothing of ours is uploaded. Imagery is for review only and stays under OUT.
- The scoring so far compares models to the lidar both were fed. This puts the roofs next to something else: the roof planes of a
  seeded random sample of the three-way hybrid, drawn on the imagery.
- Sample: stratified by inferred roof type among buildings the three-way hybrid takes from roofer (60 to 1,500 m2), plus the
  buildings that fell back to Esri LOD2.0 because roofer was broken or worse, to see whether the fallback was right.
- Overlay: each roof plane's outline, filled by the compass direction it faces (flat planes grey), the county footprint dashed
  white. Imagery is not true ortho and has its own position error, so the overlay is shifted by up to 5 m to where the plane edges
  sit on the strongest image edges; the shift used is printed on each cell, and a weak fit is marked "?".
- Output: OUT\\sample.csv, OUT\\sheets\\sheet_NN.png (8 buildings each: imagery alone, then with the overlay), OUT\\imagery\\<FP_ID>.jpg,
  OUT\\imagery-review.csv (one row per building, rating columns empty for the reviewer).
"""
import argparse
import colorsys
import csv
import io
import json
from pathlib import Path
import random
import sys
import urllib.request

import numpy as np

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parent))
import roof_attributes as ra  # noqa: E402

PX = 340
FOOTPRINTS = Path(r"H:\lidar\2023-salt-lake-valley\runs\massing-filled-20261023\massing.gdb\footprints")
TRANSFORM = "WGS_1984_(ITRF08)_To_NAD_1983_2011"
URL = ("https://services.arcgisonline.com/arcgis/rest/services/World_Imagery/MapServer/export?bbox={bbox}&bboxSR=3857&imageSR=3857"
       "&size={size},{size}&format=jpg&f=image")
STRATA = {"pitched": 34, "steep-pitched": 28, "flat": 10, "flat-parapet": 4, "multi-level": 4, "other": 4}
FALLBACK_N = 12


def sample(three_way_csv, check_csv, n, seed):
    rows = {int(r["FP_ID"]): r for r in csv.DictReader(open(check_csv, encoding="utf-8"))}
    level = {int(r["FP_ID"]): r for r in csv.DictReader(open(three_way_csv, encoding="utf-8"))}
    rng = random.Random(seed)
    chosen = []
    for kind, count in STRATA.items():
        pool = [i for i, r in rows.items() if level[i]["LEVEL"] == "roofer LoD2.2" and r["ROOF_TYPE"] == kind
                and 60 <= float(r["FOOTPRINT_M2"]) <= 1500]
        k = max(1, round(count*n/sum(STRATA.values())))
        chosen += [(i, "roofer") for i in rng.sample(sorted(pool), min(k, len(pool)))]
    fall = [i for i, r in level.items() if r["LEVEL"] == "Esri LOD2.0" and r["ROOFER_VERDICT"] in ("broken", "worse")
            and 60 <= float(rows[i]["FOOTPRINT_M2"]) <= 1500]
    chosen += [(i, "fallback") for i in rng.sample(sorted(fall), min(FALLBACK_N, len(fall)))]
    rng.shuffle(chosen)
    return [{"FP_ID": i, "GROUP": g, "ROOF_TYPE": rows[i]["ROOF_TYPE"], "FOOTPRINT_M2": round(float(rows[i]["FOOTPRINT_M2"])),
             "LEVEL": level[i]["LEVEL"], "ROOFER_VERDICT": level[i]["ROOFER_VERDICT"], "ESRI_VERDICT": level[i]["ESRI_VERDICT"]}
            for i, g in chosen]


class Mapper:
    """UTM 12N NAD83(2011) to Web Mercator with the ITRF08 transformation the packages use (one offset per building)."""
    def __init__(self):
        import arcpy
        import pyproj
        self.arcpy = arcpy
        self.fast = pyproj.Transformer.from_crs(6341, 3857, always_xy=True)

    def offset(self, x, y):
        a = self.arcpy
        g = a.PointGeometry(a.Point(x, y), a.SpatialReference(6341)).projectAs(a.SpatialReference(4326), TRANSFORM) \
            .projectAs(a.SpatialReference(3857))
        fx, fy = self.fast.transform(x, y)
        return g.firstPoint.X-fx, g.firstPoint.Y-fy

    def __call__(self, xy, offset):
        fx, fy = self.fast.transform(xy[:, 0], xy[:, 1])
        return np.column_stack([fx+offset[0], fy+offset[1]])


def fetch(box, size):
    url = URL.format(bbox=",".join(f"{v:.3f}" for v in box), size=size)
    req = urllib.request.Request(url, headers={"User-Agent": "millcreek-review/1.0"})
    from PIL import Image
    return Image.open(io.BytesIO(urllib.request.urlopen(req, timeout=60).read())).convert("RGB")


def best_shift(gray, edge_px, reach=40, step=2):
    """The shift (dx, dy in pixels) putting the overlay's edge pixels on the strongest image edges, and how much better it is."""
    from PIL import ImageFilter
    g = np.asarray(gray.filter(ImageFilter.GaussianBlur(1.2)), float)
    gy, gx = np.gradient(g)
    mag = np.hypot(gx, gy)
    ys, xs = edge_px
    best, scores = (0, 0, -1.0), []
    for dy in range(-reach, reach+1, step):
        for dx in range(-reach, reach+1, step):
            yy, xx = ys+dy, xs+dx
            ok = (yy >= 0) & (yy < mag.shape[0]) & (xx >= 0) & (xx < mag.shape[1])
            if ok.sum() < 0.8*len(ys):
                continue
            s = float(mag[yy[ok], xx[ok]].mean())
            scores.append(s)
            if s > best[2]:
                best = (dx, dy, s)
    return best, (best[2]/np.median(scores) if scores else 1.0)


def azimuth_color(az, slope):
    if az is None or slope < 5:
        return (150, 150, 150)
    r, g, b = colorsys.hsv_to_rgb(az/360.0, 0.85, 0.95)
    return (int(r*255), int(g*255), int(b*255))


def draw(img, polys, footprint, shift, scale_px):
    from PIL import ImageDraw
    over = img.copy().convert("RGBA")
    layer = ImageDraw.Draw(over, "RGBA")
    for pts, color in polys:
        xy = [(x+shift[0], y+shift[1]) for x, y in pts]
        layer.polygon(xy, fill=color+(70,))
        layer.line(xy+[xy[0]], fill=(255, 255, 255, 230), width=1)
    fp = [(x+shift[0], y+shift[1]) for x, y in footprint]
    for a, b in zip(fp, fp[1:]+fp[:1]):
        d = np.hypot(b[0]-a[0], b[1]-a[1])
        for t in np.arange(0, d, 8):
            p0 = (a[0]+(b[0]-a[0])*t/d, a[1]+(b[1]-a[1])*t/d)
            p1 = (a[0]+(b[0]-a[0])*min(t+4, d)/d, a[1]+(b[1]-a[1])*min(t+4, d)/d)
            layer.line([p0, p1], fill=(255, 235, 0, 255), width=1)
    return over.convert("RGB")


def main(argv=None):
    from PIL import Image, ImageDraw, ImageFont
    import arcpy
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("cityjson", type=Path)
    p.add_argument("city_dir", type=Path)
    p.add_argument("out", type=Path)
    p.add_argument("--n", type=int, default=96)
    p.add_argument("--seed", type=int, default=20261024)
    a = p.parse_args(argv)
    out = a.out
    (out/"imagery").mkdir(parents=True, exist_ok=True)
    (out/"sheets").mkdir(exist_ok=True)
    picks = sample(a.city_dir/"three-way.csv", a.city_dir/"check"/"lod2-check.csv", a.n, a.seed)
    want = {r["FP_ID"] for r in picks}
    city = json.loads(a.cityjson.read_text(encoding="utf-8"))
    planes = {}
    for fid, part, n, surface, ring, holes in ra.faces(city):
        if fid in want:
            planes.setdefault(fid, []).append((ring, ra.plane_row(fid, part, n, surface, ring, holes)))
    fps = {fid: [(pt.X, pt.Y) for pt in shape.getPart(0) if pt] for fid, shape in
           arcpy.da.SearchCursor(str(FOOTPRINTS), ["FP_ID", "SHAPE@"]) if fid in want}
    mapper = Mapper()
    font = ImageFont.load_default()
    cells, log = [], []
    for r in picks:
        fid = r["FP_ID"]
        fp = np.array(fps[fid])
        rings = planes.get(fid, [])
        allxy = np.vstack([fp]+[ring[:, :2] for ring, _ in rings])
        cx, cy = (allxy[:, 0].min()+allxy[:, 0].max())/2, (allxy[:, 1].min()+allxy[:, 1].max())/2
        half = max(20.0, 0.5*max(np.ptp(allxy[:, 0]), np.ptp(allxy[:, 1]))+8.0)
        off = mapper.offset(cx, cy)
        c3 = mapper(np.array([[cx, cy]]), off)[0]
        span3 = half*1.2992      # Web Mercator metres per ground metre at 40.7 degrees north
        try:
            img = fetch((c3[0]-span3, c3[1]-span3, c3[0]+span3, c3[1]+span3), PX*2).resize((PX, PX))
        except Exception as e:      # reported in the log, the cell is left blank
            log.append({"FP_ID": fid, "error": str(e)})
            continue
        img.save(out/"imagery"/f"{fid}.jpg", quality=90)

        def to_px(xy):
            m = mapper(np.asarray(xy)[:, :2], off)
            return [((x-(c3[0]-span3))/(2*span3)*PX, ((c3[1]+span3)-y)/(2*span3)*PX) for x, y in m]
        polys = [(to_px(ring), azimuth_color(row["AZIMUTH_DEG"], row["SLOPE_DEG"])) for ring, row in rings]
        fp_px = to_px(fp)
        mask = Image.new("L", (PX, PX), 0)
        md = ImageDraw.Draw(mask)
        for pts, _ in polys:
            md.line(pts+[pts[0]], fill=255, width=1)
        ys, xs = np.nonzero(np.asarray(mask))
        if len(ys) < 10:
            shift, ratio, (dx, dy) = (0, 0), 1.0, (0, 0)
        else:
            (dx, dy, _), ratio = best_shift(img.convert("L"), (ys, xs))
            shift = (dx, dy)
        mpp = 2*half/PX
        shift_m = float(np.hypot(dx, dy)*mpp)
        over = draw(img, polys, fp_px, shift, PX)
        tag = f"FP {fid} {r['ROOF_TYPE']} {r['FOOTPRINT_M2']} m2 | {r['LEVEL'].replace('roofer LoD2.2','roofer')} | shift {shift_m:.1f} m{' ?' if ratio < 1.25 else ''}"
        cell = Image.new("RGB", (PX*2+4, PX+18), (255, 255, 255))
        cell.paste(img, (0, 18))
        cell.paste(over, (PX+4, 18))
        ImageDraw.Draw(cell).text((3, 3), tag+f" | grp {r['GROUP']} | roofer {r['ROOFER_VERDICT']} Esri {r['ESRI_VERDICT']}", fill=(0, 0, 0), font=font)
        cells.append((fid, cell))
        r.update({"WINDOW_M": round(2*half, 1), "SHIFT_M": round(shift_m, 2), "REGISTRATION_RATIO": round(ratio, 2), "PLANES": len(rings)})
    for k in range(0, len(cells), 8):
        chunk = cells[k:k+8]
        w, h = chunk[0][1].size
        sheet = Image.new("RGB", (w*2+6, (h+4)*((len(chunk)+1)//2)), (255, 255, 255))
        for j, (_, cell) in enumerate(chunk):
            sheet.paste(cell, ((j % 2)*(w+6), (j//2)*(h+4)))
        sheet.save(out/"sheets"/f"sheet_{k//8+1:02d}.png")
    with open(out/"sample.csv", "w", newline="", encoding="utf-8") as f:
        names = list(dict.fromkeys(k for r in picks for k in r))
        wr = csv.DictWriter(f, names)
        wr.writeheader()
        wr.writerows(picks)
    with open(out/"imagery-review.csv", "w", newline="", encoding="utf-8") as f:
        wr = csv.writer(f)
        wr.writerow(["FP_ID", "SHEET", "ROOF_FORM_MATCHES", "GABLES_AND_RIDGES", "CHIMNEYS_DORMERS", "EDGES_CLEAN", "NOTE"])
        for j, (fid, _) in enumerate(cells):
            wr.writerow([fid, f"sheet_{j//8+1:02d}", "", "", "", "", ""])
    (out/"imagery-check.json").write_text(json.dumps({"sampled": len(picks), "drawn": len(cells), "errors": log,
                                                       "seed": a.seed, "strata": STRATA, "fallback_n": FALLBACK_N}, indent=1), encoding="utf-8")
    print(json.dumps({"sampled": len(picks), "drawn": len(cells), "errors": log}))


if __name__ == "__main__":
    main()
