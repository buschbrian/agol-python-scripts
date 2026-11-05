r"""Roof attributes per roof plane and per building from roofer's CityJSON (October 24, 2026).

    python reviews/2026-10-23/lod2-check/roof_attributes.py CITYJSON OUT_DIR

Standard library and numpy only. Read-only on CITYJSON (one file with the LoD 2.2 solids, as roofer_city_stages.collect_city
writes it). Writes OUT_DIR\roof_planes.csv (one row per roof face) and OUT_DIR\building_roofs.csv (one row per building) and
OUT_DIR\roof-attributes.json (counts, definitions).
Per roof plane (a RoofSurface face of the LoD 2.2 solid): plan area, true (sloped) area, slope (degrees from horizontal),
azimuth (compass bearing of the downslope direction, 0 = north, clockwise; empty for a flat plane), lowest and highest z, height
above the building's ground, the roof-height percentiles roofer attached to the face.
Per building: plane count (planes of 1 m2 and more in plan are "main"), roof plan and true area, area-weighted mean slope, the
largest plane's slope and azimuth, ridge (highest roof z) and eave (lowest roof z) height above ground, building height (ridge
above ground), flat area (planes under 5 degrees), and the roof area facing south (135 to 225 degrees), east (45 to 135), west
(225 to 315) and north (315 to 45) on planes of 5 to 70 degrees. These are geometry from the lidar roof; they are not a solar
production estimate (no shading, no panel layout, no weather).
Heights above ground use roofer's own ground elevation for the building (rf_h_ground). The snag counts (TINY_FACES under 0.5 m2 in
plan, SLIVER_FACES narrower than 0.4 m, STEEP_FACES steeper than 75 degrees) are for quality screening, as roofer_sweep.py counts them.
"""
import csv
import json
from pathlib import Path
import sys

import numpy as np

FLAT_DEG = 5.0
STEEP_DEG = 70.0
MAIN_PLAN_M2 = 1.0


def faces(city):
    scale, translate = np.array(city["transform"]["scale"]), np.array(city["transform"]["translate"])
    verts = np.array(city["vertices"], float)*scale+translate
    for key, obj in city["CityObjects"].items():
        if obj["type"] != "BuildingPart":
            continue
        fid = int(key.split("-")[0])
        for g in obj["geometry"]:
            if g["lod"] != "2.2" or g["type"] != "Solid":
                continue
            surfaces = g["semantics"]["surfaces"]
            for shell, labels in zip(g["boundaries"], g["semantics"]["values"]):
                for n, (face, label) in enumerate(zip(shell, labels)):
                    if surfaces[label]["type"] == "RoofSurface":
                        yield fid, key, n, surfaces[label], verts[face[0]], [verts[h] for h in face[1:]]


def shoelace(ring):
    x, y = ring[:, 0], ring[:, 1]
    return 0.5*(np.dot(x, np.roll(y, -1))-np.dot(y, np.roll(x, -1)))


def true_area(ring):
    """Area of a planar 3D polygon by the vector area (sum of cross products from the first vertex)."""
    c = np.zeros(3)
    for a, b in zip(ring[1:-1], ring[2:]):
        c += np.cross(a-ring[0], b-ring[0])
    return 0.5*np.linalg.norm(c), 0.5*c


def plane_row(fid, part, n, surface, ring, holes):
    area3, vec = true_area(ring)
    for h in holes:
        a, v = true_area(h)
        area3 -= a
    plan = abs(shoelace(ring))-sum(abs(shoelace(h)) for h in holes)
    norm = np.linalg.norm(vec)
    nz = abs(vec[2])/norm if norm > 0 else 1.0
    slope = float(np.degrees(np.arccos(min(1.0, nz))))
    normal = vec/norm if norm > 0 else np.array([0, 0, 1.0])
    if normal[2] < 0:
        normal = -normal
    azimuth = None
    if slope >= 0.5:
        azimuth = float((np.degrees(np.arctan2(normal[0], normal[1]))+360) % 360)   # downslope: the horizontal part of the normal
    perimeter = float(np.linalg.norm(np.diff(np.vstack([ring, ring[:1]]), axis=0), axis=1).sum())
    return {"FP_ID": fid, "PART": part, "FACE": n, "PLAN_M2": round(plan, 3), "AREA_M2": round(area3, 3), "PERIM_M": round(perimeter, 2),
            "SLOPE_DEG": round(slope, 1), "AZIMUTH_DEG": None if azimuth is None else round(azimuth, 1),
            "Z_MIN": round(float(ring[:, 2].min()), 3), "Z_MAX": round(float(ring[:, 2].max()), 3),
            "RF_H_ROOF_50P": surface.get("rf_h_roof_50p"), "RF_H_ROOF_70P": surface.get("rf_h_roof_70p"),
            "RF_H_ROOF_MAX": surface.get("rf_h_roof_max"), "RF_H_ROOF_MIN": surface.get("rf_h_roof_min")}


def facing(azimuth, lo, hi):
    return azimuth is not None and (lo <= azimuth < hi if lo < hi else (azimuth >= lo or azimuth < hi))


def compute(city_path, out):
    city = json.loads(Path(city_path).read_text(encoding="utf-8"))
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    ground = {int(k): o.get("attributes", {}).get("rf_h_ground") for k, o in city["CityObjects"].items() if o["type"] == "Building"}
    attrs = {int(k): o.get("attributes", {}) for k, o in city["CityObjects"].items() if o["type"] == "Building"}
    planes = [plane_row(*f) for f in faces(city)]
    with open(out/"roof_planes.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, list(planes[0]))
        w.writeheader()
        w.writerows(planes)
    by = {}
    for p in planes:
        by.setdefault(p["FP_ID"], []).append(p)
    rows = []
    for fid, ps in sorted(by.items()):
        g = ground.get(fid)
        main = [p for p in ps if p["PLAN_M2"] >= MAIN_PLAN_M2]
        use = main or ps
        a3 = sum(p["AREA_M2"] for p in use)
        big = max(use, key=lambda p: p["AREA_M2"])
        zmax, zmin = max(p["Z_MAX"] for p in ps), min(p["Z_MIN"] for p in ps)
        slope_mean = sum(p["SLOPE_DEG"]*p["AREA_M2"] for p in use)/a3 if a3 else None
        sloped = [p for p in use if FLAT_DEG <= p["SLOPE_DEG"] <= STEEP_DEG]
        row = {"FP_ID": fid, "ROOF_PLANES": len(main), "ROOF_PLANES_ALL": len(ps),
               "ROOF_PLAN_M2": round(sum(p["PLAN_M2"] for p in use), 1), "ROOF_AREA_M2": round(a3, 1),
               "ROOF_SLOPE_MEAN": None if slope_mean is None else round(slope_mean, 1),
               "ROOF_SLOPE_MAIN": big["SLOPE_DEG"], "ROOF_AZIMUTH_MAIN": big["AZIMUTH_DEG"],
               "RIDGE_HT_M": None if g is None else round(zmax-g, 2), "EAVE_HT_M": None if g is None else round(zmin-g, 2),
               "BLDG_HT_M": None if g is None else round(zmax-g, 2),
               "FLAT_AREA_M2": round(sum(p["AREA_M2"] for p in use if p["SLOPE_DEG"] < FLAT_DEG), 1),
               "SOUTH_AREA_M2": round(sum(p["AREA_M2"] for p in sloped if facing(p["AZIMUTH_DEG"], 135, 225)), 1),
               "EAST_AREA_M2": round(sum(p["AREA_M2"] for p in sloped if facing(p["AZIMUTH_DEG"], 45, 135)), 1),
               "WEST_AREA_M2": round(sum(p["AREA_M2"] for p in sloped if facing(p["AZIMUTH_DEG"], 225, 315)), 1),
               "NORTH_AREA_M2": round(sum(p["AREA_M2"] for p in sloped if facing(p["AZIMUTH_DEG"], 315, 45)), 1),
               "TINY_FACES": sum(1 for p in ps if p["PLAN_M2"] < 0.5),
               "SLIVER_FACES": sum(1 for p in ps if p["PERIM_M"] > 0 and 2*p["PLAN_M2"]/p["PERIM_M"] < 0.4),
               "STEEP_FACES": sum(1 for p in ps if p["SLOPE_DEG"] > 75),
               "RF_ROOF_TYPE": attrs.get(fid, {}).get("rf_roof_type"), "RF_VOLUME_M3": attrs.get(fid, {}).get("rf_volume_lod22")}
        rows.append(row)
    with open(out/"building_roofs.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    summary = {"roof_planes": len(planes), "buildings": len(rows),
               "planes_per_building_median": float(np.median([r["ROOF_PLANES"] for r in rows])),
               "roof_area_m2_total": round(sum(r["ROOF_AREA_M2"] for r in rows)), "flat_area_m2": round(sum(r["FLAT_AREA_M2"] for r in rows)),
               "south_area_m2": round(sum(r["SOUTH_AREA_M2"] for r in rows)), "east_area_m2": round(sum(r["EAST_AREA_M2"] for r in rows)),
               "west_area_m2": round(sum(r["WEST_AREA_M2"] for r in rows)), "north_area_m2": round(sum(r["NORTH_AREA_M2"] for r in rows)),
               "slope_deg_percentiles_by_area": None,
               "definitions": {"flat": f"under {FLAT_DEG} degrees", "usable": f"{FLAT_DEG} to {STEEP_DEG} degrees",
                               "main plane": f"plan area of {MAIN_PLAN_M2} m2 or more",
                               "azimuth": "compass bearing of the downslope direction, 0 north, clockwise"}}
    order = np.argsort([p["SLOPE_DEG"] for p in planes])
    cum = np.cumsum([planes[i]["AREA_M2"] for i in order])
    summary["slope_deg_percentiles_by_area"] = {str(q): planes[order[int(np.searchsorted(cum, cum[-1]*q/100))]]["SLOPE_DEG"]
                                                for q in (10, 25, 50, 75, 90)}
    (out/"roof-attributes.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    return summary


if __name__ == "__main__":
    print(json.dumps(compute(sys.argv[1], sys.argv[2]), indent=1))
