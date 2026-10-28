"""Citywide treetop count on the rebuilt canopy, exactly as the October 8 count ran (October 22, 2026).

    python reviews/2026-10-22/canopy-rebuild/count_rebuilt.py REBUILD_ROOT NEW_RUN

Run with ArcGIS Pro Python (arcpy for the boundary, parcels and output feature class; PYTHONNOUSERSITE=1, CANOPY_LIDAR_ROOT
set) after canopy_rebuild.py. Read-only on every input; writes a NEW run folder. Brian said go ahead on October 22.

1. Canonical CHM: the October 8 count detected on one canonical CHM of the city plus a 20 m margin (canonical-chm.bin, the
   October 19 grid; NaN where unobserved and outside its planned 950 m raster cores). Both rebuild versions are assembled the
   same way from canopy_rebuild.py's working arrays with October 19's terrain_context.tif, masked to those cores. The native one must equal October 8's canonical-chm.bin exactly (values and
   NaN cells); the detector, bands, ownership and raster code are unchanged since October 8 (their SHA-256 are checked
   against count.json), so equal input reproduces the 607,972 treetops.
2. On the combined canonical CHM: count_peaks.detect with the default bands (2-6 m: 1 m; 6-12: 1.5; 12-20: 2; 20+: 2.5;
   smoothing one cell), peaks clipped to the municipal boundary, parcel ownership from the same parcel snapshot, all by the
   October 8 code (run_city_count.py lines 142-216, repeated here because that script also rasterizes from LAS).
3. Comparison with October 8: treetops at the same cell, removed and added, and the ownership totals.
Writes NEW_RUN/count.json, city-treetops.csv, tree-count.gdb/city_treetops, owner-classification-review.csv,
treetop-changes.csv (removed and added cells) and canonical-chm-combined.bin.

No crowns: crown delineation is bounded to 4,000,000 cells (AGENTS.md) and the October 8 count produced none either.
"""
import argparse
import collections
import csv
import hashlib
import json
from pathlib import Path
import sys
import time
import uuid

import numpy as np

HERE = Path(__file__).resolve()
TOOLBOX = HERE.parents[3]
sys.path.insert(0, str(TOOLBOX))
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(TOOLBOX/"reviews"/"2026-10-21"/"roof-consensus"))
import canopy_rebuild as rb  # noqa: E402
import consensus_roofs as cr  # noqa: E402

OCT8 = cr.RUNS/"city-count-20261008"
CODE = {"run_city_count.py": TOOLBOX/"reviews"/"2026-10-08"/"run_city_count.py", "count_peaks.py": TOOLBOX/"canopy"/"count_peaks.py",
        "parcel_ownership.py": TOOLBOX/"canopy"/"parcel_ownership.py", "rasters.py": TOOLBOX/"canopy"/"rasters.py",
        "bands.py": TOOLBOX/"canopy"/"bands.py"}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_work(root, g):
    size = g["rows"]*g["cols"]
    arrays = {}
    for version in rb.VERSIONS:
        arrays[version] = {key: np.load(root/"work"/f"{version}_{key}.npy", mmap_mode="r") for key in ("veg", "bld", "non")}
        for a in arrays[version].values():
            if a.shape != (size,):
                raise ValueError("Working arrays do not match the grid")
    return arrays


def core_mask(city, inputs, g):
    """Cells the October 8 count rasterized: its planned 950 m cores (run_city_count.py: tiles of the 20 m-buffered extent
    whose core touches the city buffered by 20 m). Outside them its canonical CHM is NaN although points exist there."""
    import shapely
    from canopy.tiling import Extent, snap_extent, tile_grid
    extent = snap_extent(Extent(*inputs["extent"]).buffered(20), .5)
    if abs(extent.xmin-g["x0"]) > 1e-6 or abs(extent.ymax-g["y0"]) > 1e-6:
        raise ValueError("The October 8 extent does not start at the grid origin")
    context = shapely.buffer(city, 20)
    mask = np.zeros((g["rows"], g["cols"]), bool)
    planned = [t for t in tile_grid(extent, 950, 20, .5) if shapely.intersects(context, shapely.box(*t.core))]
    for t in planned:
        r0, c0 = round((extent.ymax-t.core.ymax)/.5), round((t.core.xmin-extent.xmin)/.5)
        mask[r0:r0+round(t.core.height/.5), c0:c0+round(t.core.width/.5)] = True
    return mask, len(planned)


def canonical(arrays, version, g, path, cores):
    """The canonical CHM (NaN where unobserved or outside the October 8 cores) with the margin terrain, disk-backed."""
    out = np.memmap(path, mode="w+", dtype="float32", shape=(g["rows"], g["cols"]))
    terrain = cr.OCT19/"terrain_context.tif"
    for r0 in range(0, g["rows"], 512):
        r1 = min(r0+512, g["rows"])
        chm, _, _, _ = rb.rasters(arrays, version, g, r0, r1, terrain=terrain)
        chm[~cores[r0:r1]] = np.nan
        out[r0:r1] = chm
    out.flush()
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("rebuild", type=Path)
    parser.add_argument("out", type=Path)
    args = parser.parse_args(argv)
    if args.out.exists():
        raise FileExistsError(args.out)
    import arcpy
    import shapely
    from shapely.strtree import STRtree
    from canopy import bands, common, count_peaks, parcel_ownership
    oct8 = json.loads((OCT8/"count.json").read_text(encoding="utf-8"))
    changed = [n for n, p in CODE.items() if sha(p) != oct8["code_sha256"][n]]
    if changed:
        raise ValueError(f"Code changed since October 8: {changed}")
    g = cr.grid()
    if [g["rows"], g["cols"]] != oct8["shape"] or abs(oct8["extent"][0]-g["x0"]) > 1e-6 or abs(oct8["extent"][3]-g["y0"]) > 1e-6:
        raise ValueError("The October 8 canonical grid differs from the October 19 grid")
    args.out.mkdir(parents=True)
    state = {"status": "canonical CHM", "started": time.time(), "rebuild": str(args.rebuild), "october8": str(OCT8),
             "interpretation": "Estimated treetops >=2 m, not a field-verified stem census", "parameters": oct8["parameters"]}
    manifest = args.out/"count.json"

    def save():
        common.write_json(manifest, state)

    save()
    try:
        inputs = json.loads((OCT8/"inputs.json").read_text(encoding="utf-8"))
        city = shapely.union_all([shapely.from_wkb(bytes(w)) for w, in arcpy.da.SearchCursor(inputs["boundary"], ["SHAPE@WKB"])])
        if not shapely.is_valid(city):
            raise ValueError("City boundary geometry is invalid")
        cores, planned = core_mask(city, inputs, g)
        if planned != oct8.get("raster_tiles_planned", planned):
            raise ValueError(f"{planned} cores planned, October 8 planned {oct8['raster_tiles_planned']}")
        state["october8_cores"] = planned
        arrays = load_work(args.rebuild, g)
        native = canonical(arrays, "native", g, args.out/"canonical-chm-native.bin", cores)
        reference = np.memmap(OCT8/"canonical-chm.bin", mode="r", dtype="float32", shape=(g["rows"], g["cols"]))
        mismatch = 0
        for r0 in range(0, g["rows"], 1024):
            a, b = np.asarray(native[r0:r0+1024]), np.asarray(reference[r0:r0+1024])
            mismatch += int(((np.isnan(a) != np.isnan(b)) | (np.abs(np.nan_to_num(a)-np.nan_to_num(b)) > 0)).sum())
        state["native_equals_october8_canonical"] = mismatch == 0
        state["native_canonical_mismatched_cells"] = mismatch
        save()
        if mismatch:
            raise ValueError(f"The native canonical CHM differs from October 8's in {mismatch} cells")
        del native, reference              # canonical-chm-native.bin stays (Windows keeps a mapped file open); delete it later
        array = canonical(arrays, "combined", g, args.out/"canonical-chm-combined.bin", cores)
        state["status"] = "detecting globally reconciled peaks"
        save()
        x0, y0 = g["x0"], g["y0"]
        peaks = count_peaks.detect(array, bands.DEFAULT_BANDS, .5, args.out/"peak-work")
        xy = np.array([(x0+(c+.5)*.5, y0-(r+.5)*.5) for r, c, h in peaks]).reshape(-1, 2)
        shapely.prepare(city)
        inside = shapely.intersects_xy(city, xy[:, 0], xy[:, 1])
        state["peaks_before_city_clip"] = len(peaks)
        peaks = [p for p, k in zip(peaks, inside) if k]
        xy = xy[inside]
        state.update(status="assigning parcel ownership", city_treetops=len(peaks))
        save()
        # Ownership exactly as run_city_count.py.
        geometries, categories, groups_, public = [], [], [], collections.Counter()
        for oid, owner, wkb in arcpy.da.SearchCursor(inputs["parcels"], ["OID@", "own_name", "SHAPE@WKB"]):
            if wkb is None:
                raise ValueError(f"Parcel {oid} has no geometry")
            geom = shapely.from_wkb(bytes(wkb))
            if not shapely.is_valid(geom):
                raise ValueError(f"Parcel {oid} geometry is invalid")
            category, group = parcel_ownership.classify(owner)
            geometries.append(geom), categories.append(category), groups_.append(group)
            if category != "PRIVATE":
                public[(str(owner), category, group)] += 1
        with open(args.out/"owner-classification-review.csv", "w", encoding="utf-8", newline="") as handle:
            w = csv.writer(handle)
            w.writerow(["OWNER_OF_RECORD", "CATEGORY", "BASIS", "PARCELS"])
            w.writerows((*k, n) for k, n in sorted(public.items()))
        tree = STRtree(geometries)
        assigned = []
        for offset in range(0, len(xy), 10000):
            batch = xy[offset:offset+10000]
            hits = collections.defaultdict(list)
            for point, parcel in zip(*tree.query(shapely.points(batch), predicate="intersects")):
                hits[int(point)].append(int(parcel))
            for i in range(len(batch)):
                ids = hits[i]
                category = parcel_ownership.resolve(categories[j] for j in ids)
                gs = sorted(set(groups_[j] for j in ids))
                group = gs[0] if len(gs) == 1 else ("MULTIPLE_PUBLIC_PARCELS" if category == "PUBLIC_GOVERNMENT" else "")
                assigned.append((category, group, len(ids)))
        totals = collections.Counter(a[0] for a in assigned)
        if sum(totals.values()) != len(peaks):
            raise RuntimeError("Ownership totals do not sum to unique city peaks")
        source_id = "canopy-rebuild-20261022 combined classification"
        gdb = str(args.out/"tree-count.gdb")
        arcpy.management.CreateFileGDB(str(args.out), "tree-count.gdb")
        tops = common.create_points(gdb, "city_treetops", arcpy.SpatialReference(6341))
        common.add_fields(tops, [("OWNERSHIP", "TEXT", 32), ("OWNER_GROUP", "TEXT", 80), ("PARCEL_MATCHES", "LONG", None),
                                 ("OCT8", "TEXT", 12)])
        old = {}
        with open(OCT8/"city-treetops.csv", encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                old[(round(float(row["X"]), 2), round(float(row["Y"]), 2))] = row
        new_keys = set()
        fields = ["SHAPE@XY", "TREE_ID", "HEIGHT_M", "MIN_HEIGHT", "SMOOTH", "SOURCE_ID", "REVIEW_STATUS",
                  "OWNERSHIP", "OWNER_GROUP", "PARCEL_MATCHES", "OCT8"]
        with arcpy.da.InsertCursor(tops, fields) as cursor, \
                open(args.out/"city-treetops.csv", "w", encoding="utf-8", newline="") as handle:
            w = csv.writer(handle)
            w.writerow(["TREE_ID", "X", "Y", "HEIGHT_M", "OWNERSHIP", "OWNER_GROUP", "PARCEL_MATCHES", "OCT8"])
            for (r, c, h), (x, y), (category, group, matches) in zip(peaks, xy, assigned):
                key = (round(float(x), 2), round(float(y), 2))
                new_keys.add(key)
                same = "SAME_CELL" if key in old else "NEW"
                tree_id = old[key]["TREE_ID"] if key in old else str(uuid.uuid5(uuid.NAMESPACE_URL, f"{source_id}|6341|{x:.6f}|{y:.6f}"))
                cursor.insertRow([(x, y), tree_id, h, 2., 1, source_id, "UNVERIFIED", category, group, matches, same])
                w.writerow([tree_id, x, y, h, category, group, matches, same])
        common.metadata(tops, "Citywide count-only detection on the canopy rebuilt from the combined classification "
                        "(October 22, 2026), by the October 8 method. Ownership uses the detected apex location and the "
                        "October 8 parcel snapshot. OCT8: SAME_CELL where October 8 had a treetop at the same cell, else NEW.")
        removed = [row for key, row in old.items() if key not in new_keys]
        with open(args.out/"treetop-changes.csv", "w", encoding="utf-8", newline="") as handle:
            w = csv.writer(handle)
            w.writerow(["CHANGE", "TREE_ID", "X", "Y", "HEIGHT_M", "OWNERSHIP"])
            for row in removed:
                w.writerow(["REMOVED", row["TREE_ID"], row["X"], row["Y"], row["HEIGHT_M"], row["OWNERSHIP"]])
            with open(args.out/"city-treetops.csv", encoding="utf-8", newline="") as new_csv:
                for row in csv.DictReader(new_csv):
                    if row["OCT8"] == "NEW":
                        w.writerow(["ADDED", row["TREE_ID"], row["X"], row["Y"], row["HEIGHT_M"], row["OWNERSHIP"]])
        same_cell = len(new_keys & set(old))
        state.update(status="complete", finished=time.time(), ownership_totals=dict(totals),
                     public_breakdown=dict(collections.Counter(g_ for c_, g_, n in assigned if c_ == "PUBLIC_GOVERNMENT")),
                     comparison={"october8_treetops": len(old), "rebuilt_treetops": len(peaks), "same_cell": same_cell,
                                 "removed": len(old)-same_cell, "added": len(peaks)-same_cell,
                                 "october8_ownership": oct8.get("ownership_totals")},
                     outputs={"treetops": tops, "csv": str(args.out/"city-treetops.csv")},
                     quality_status="PRELIMINARY_UNVALIDATED; provisional model-assisted classification")
        state["seconds"] = state["finished"]-state["started"]
        save()
        print(json.dumps({k: state[k] for k in ("native_equals_october8_canonical", "city_treetops", "ownership_totals",
                                                 "comparison", "seconds")}, indent=1), flush=True)
    except BaseException as exc:
        state.update(status="failed", error=repr(exc), finished=time.time())
        save()
        raise


if __name__ == "__main__":
    main()
