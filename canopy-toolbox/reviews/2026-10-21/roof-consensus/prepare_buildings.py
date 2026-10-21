"""Set up footprint roof-height statistics from the consensus roofs with the unchanged October 19 summary script.

    python reviews/2026-10-21/roof-consensus/prepare_buildings.py ROOT
    <ArcGIS Pro python> reviews/2026-10-19/summarize_city_buildings.py ROOT/buildings

ROOT is a complete consensus_roofs.py output. This writes ROOT/buildings/products.json and ROOT/buildings/footprints/
footprints.json, the two inputs summarize_city_buildings.py reads: the October 19 manifests with one change, the roof elevation
raster, which becomes ROOT/roof_elevation_consensus_m.tif. Terrain, city boundary and the county footprint snapshot
(22,042 footprints, five repaired copies) are October 19's own, so the two building layers differ only in their roofs.
"""
import argparse
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[3]))
sys.path.insert(0, str(HERE.parent))
import consensus_roofs as cr  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("root", type=Path)
    args = parser.parse_args(argv)
    root = args.root.resolve()
    if json.loads((root/"manifest.json").read_text(encoding="utf-8")).get("status") != "complete":
        raise ValueError("The consensus run is not complete")
    roof = root/"roof_elevation_consensus_m.tif"
    if not roof.is_file():
        raise FileNotFoundError(roof)
    target = root/"buildings"
    if target.exists():
        raise FileExistsError(target)
    products = json.loads((cr.OCT19/"products.json").read_text(encoding="utf-8"))
    footprints = json.loads((cr.OCT19/"footprints"/"footprints.json").read_text(encoding="utf-8"))
    if products["status"] != "complete" or footprints["status"] != "complete":
        raise ValueError("The October 19 inputs are not complete")
    products = {"status": "complete", "boundary": products["boundary"],
                "outputs": {"terrain": products["outputs"]["terrain"], "roof_elevation": str(roof)},
                "derived_from": str(cr.OCT19/"products.json"),
                "change": "roof_elevation is the 2-of-3 consensus (native, FRACTAL majority, Esri), October 21, 2026"}
    (target/"footprints").mkdir(parents=True)
    (target/"products.json").write_text(json.dumps(products, indent=1), encoding="utf-8")
    (target/"footprints"/"footprints.json").write_text(json.dumps(footprints, indent=1), encoding="utf-8")
    print(f"wrote {target}; now run summarize_city_buildings.py {target} with ArcGIS Pro Python")


if __name__ == "__main__":
    main()
