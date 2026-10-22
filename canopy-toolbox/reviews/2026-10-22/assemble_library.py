"""Assemble the October 22 Millcreek product library: the current version of every product, in one folder.

    python reviews/2026-10-22/assemble_library.py NEW_FOLDER

Any Python 3. Read-only on every source; copies into a NEW folder and writes library.json with each product's source path
and SHA-256 (checked again after the copy). The October 19 library and the October 8 count stay where they are, untouched;
see PRODUCTS.md beside this script for what changed and why.
"""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import shutil

RUNS = Path(r"D:\lidar\2023-salt-lake-valley\runs")
REBUILD = RUNS/"canopy-rebuild-20261022"
ROOFS = RUNS/"roof-consensus-20261021"
COUNT = RUNS/"city-count-20261022"
COVER = RUNS/"cover-20261022"
OCT19 = RUNS/"millcreek-products-20261019"
PRODUCTS = {   # library name: (source, what it is)
    "chm_m.tif": (REBUILD/"chm_m.tif", "canopy height (m) from the combined classification; NoData = unknown or outside the city"),
    "observed.tif": (REBUILD/"observed.tif", "1 observed, 0 unknown, 3 outside the city"),
    "vegetation_support.tif": (REBUILD/"vegetation_support.tif", "1 where a vegetation return supports the cell"),
    "building_occlusion.tif": (REBUILD/"building_occlusion.tif", "1 where a consensus roof occludes lower vegetation"),
    "terrain_m.tif": (OCT19/"terrain_m.tif", "bare-earth elevation (m), October 19 (ground was not reclassified)"),
    "roof_elevation_m.tif": (ROOFS/"roof_elevation_consensus_m.tif", "consensus roof elevation (m), 2 of 3 sources"),
    "roof_height_m.tif": (ROOFS/"roof_height_consensus_m.tif", "consensus roof height above terrain (m); negatives kept"),
    "building_sources.tif": (ROOFS/"building_sources.tif", "which sources saw roof: 1 native + 2 FRACTAL + 4 Esri"),
    "buildings.gdb": (ROOFS/"buildings"/"buildings.gdb", "building_heights: county footprints with consensus roof heights"),
    "building-heights.csv": (ROOFS/"buildings"/"building-heights.csv", "the same attributes by SOURCE_ID"),
    "tree-count.gdb": (COUNT/"tree-count.gdb", "city_treetops: 527,140 treetops >= 2 m with ownership; OCT8 field"),
    "city-treetops.csv": (COUNT/"city-treetops.csv", "the same treetops as CSV"),
    "crowns.gdb": (RUNS/"crowns-20261022"/"crowns.gdb", "crowns (400,063) and trees_review, tiled crown method"),
    "cover.gdb": (COVER/"cover.gdb", "zones, cover_rebuilt and cover_oct19 (canopy.cover.summarize)"),
    "cover-comparison.csv": (COVER/"cover-comparison.csv", "cover by zone, October 19 against rebuilt"),
    "review/canopy_change.tif": (REBUILD/"canopy_change.tif", "canopy >= 2 m: 1 both, 2 lost, 3 gained since October 19"),
    "review/treetop-changes.csv": (COUNT/"treetop-changes.csv", "treetops removed and added since October 8"),
    "review/height-changes.csv": (ROOFS/"buildings"/"height-changes.csv", "footprints whose height or support changed"),
}


def digest(path):
    path = Path(path)
    h = hashlib.sha256()
    files = sorted(p for p in path.rglob("*") if p.is_file()) if path.is_dir() else [path]
    for f in files:
        if path.is_dir():
            h.update(str(f.relative_to(path)).replace("\\", "/").encode())
        with open(f, "rb") as handle:
            for block in iter(lambda: handle.read(8 << 20), b""):
                h.update(block)
    return h.hexdigest()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("out", type=Path)
    args = parser.parse_args(argv)
    if args.out.exists():
        raise FileExistsError(args.out)
    missing = [str(src) for src, _ in PRODUCTS.values() if not Path(src).exists()]
    if missing:
        raise FileNotFoundError(missing)
    args.out.mkdir(parents=True)
    record = {"created": datetime.datetime.now().isoformat(timespec="seconds"),
              "status": "PRELIMINARY_UNVALIDATED planning estimates; see PRODUCTS.md", "products": {}}
    for name, (src, meaning) in PRODUCTS.items():
        target = args.out/name
        target.parent.mkdir(parents=True, exist_ok=True)
        before = digest(src)
        if Path(src).is_dir():
            shutil.copytree(src, target, ignore=shutil.ignore_patterns("*.lock"))
        else:
            shutil.copy2(src, target)
            for sidecar in (".tfw", ".tif.aux.xml", ".tif.xml"):
                extra = Path(str(src)[:-4]+sidecar) if sidecar == ".tfw" else Path(str(src)+sidecar[4:])
                if extra.exists():
                    shutil.copy2(extra, Path(str(target)[:-4]+sidecar) if sidecar == ".tfw" else Path(str(target)+sidecar[4:]))
        if Path(src).is_file() and digest(target) != before:
            raise RuntimeError(f"{name}: copy differs from its source")
        record["products"][name] = {"source": str(src), "sha256": before, "meaning": meaning}
        print(f"{name}: {meaning}", flush=True)
    (args.out/"library.json").write_text(json.dumps(record, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
