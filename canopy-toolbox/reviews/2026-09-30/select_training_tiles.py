"""Seeded, documented draw of three additional TRAINING tiles (September 30, 2026).

Run with ArcGIS Pro Python (arcpy reads the evaluation frame in reference.gdb, read-only):
    set PYTHONNOUSERSITE=1
    python reviews/2026-09-30/select_training_tiles.py [--out reviews/2026-09-30/training-tiles.json]

Universe: the 61 USGS tiles that touch Millcreek (acquisitions/2023-salt-lake-valley/usgs-laz-millcreek.csv).
A tile is a candidate when
  1. its LAZ and the converted LAS the September 29 pilot prepared from exist, for the core AND all eight
     1 km grid neighbours (so a prepared 50 m halo is complete on every side), with LAS header point
     counts equal to the published manifest's;
  2. it is not 12TVL2804 (already the training tile);
  3. its core and its prepared extent (core + 50 m) do not intersect the prepared extent of 12TVL3302
     (prospective holdout, canopy.evaluation_design.HOLDOUT_EXTENT) or of 12TVL2203 (external transfer,
     core + 50 m, as enforced by the training-review packet);
  4. no evaluation feature (reference.gdb treetop/omission/cell/crown samples, independent census plots)
     has a bounding box intersecting its prepared extent (TRAINING_REVIEW.md: a training tile must carry
     no evaluation units).
Draw: random.Random(20260930).sample(sorted(candidates), 3).
Stratification was considered and rejected: the delivered classes are only 1/2/7/18 (no class 6), and the
acquisition facts carry no land-use or building-density field, so there is no usable pre-processing proxy.
The sampled class-2 share from the LAS inventory is recorded per candidate as description only.
"""
import argparse
import csv
import datetime
import hashlib
import json
from pathlib import Path
import random
import sys

TOOLBOX = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(TOOLBOX))
from canopy import evaluation_design as ed  # noqa: E402

SEED = 20260930
DRAW = 3
BUFFER = 50.0
CSV = TOOLBOX / "acquisitions" / "2023-salt-lake-valley" / "usgs-laz-millcreek.csv"
from canopy.lidar_root import lidar_root  # noqa: E402
LAZ = lidar_root() / "2023-salt-lake-valley" / "laz"
LAS = Path(r"D:\lidar\2023-salt-lake-valley\las")
PILOT = lidar_root() / "2023-salt-lake-valley" / "runs" / "pilot-2026-09-29"
INVENTORY = PILOT / "las-inventory.json"
REFERENCE_GDB = PILOT / "validation" / "reference.gdb"
REFERENCE_SAMPLES = ("treetop_sample", "omission_sample", "cell_sample", "crown_sample")
PLOTS_JSON = TOOLBOX / "reviews" / "2026-09-29" / "packets" / "independent-plot-census-v2" / "plots.esri.json"
TRAINING_TILE = "12TVL2804"
EXTERNAL_TILE = "12TVL2203"
EXCLUSIONS = {
    "12TVL3302 prospective holdout + prepared 50 m halo": tuple(ed.HOLDOUT_EXTENT),
    "12TVL2203 external transfer + prepared 50 m halo": (ed.TILES[EXTERNAL_TILE][0] - BUFFER,
                                                          ed.TILES[EXTERNAL_TILE][1] - BUFFER,
                                                          ed.TILES[EXTERNAL_TILE][2] + BUFFER,
                                                          ed.TILES[EXTERNAL_TILE][3] + BUFFER),
}


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def intersects(a, b):
    """Open-rectangle overlap (shared edges do not count)."""
    return a[0] < b[2] and a[2] > b[0] and a[1] < b[3] and a[3] > b[1]


def neighbours(tile):
    e, n = int(tile[5:7]), int(tile[7:9])
    return [f"12TVL{e + de:02d}{n + dn:02d}" for de in (-1, 0, 1) for dn in (-1, 0, 1) if de or dn]


def evaluation_features():
    import arcpy
    features = []
    for fc in REFERENCE_SAMPLES:
        path = str(REFERENCE_GDB / fc)
        if arcpy.Describe(path).spatialReference.factoryCode != 6341:
            raise ValueError(f"{fc} must be EPSG:6341")
        with arcpy.da.SearchCursor(path, ["SHAPE@", "SAMPLE_ID", "TILE"]) as cursor:
            for shape, sample_id, tile in cursor:
                e = shape.extent
                features.append({"source": fc, "id": sample_id, "tile": tile,
                                 "bbox": (e.XMin, e.YMin, e.XMax, e.YMax)})
    doc = json.loads(PLOTS_JSON.read_text(encoding="utf-8"))
    if doc.get("spatialReference", {}).get("wkid") != 6341:
        raise ValueError("plots.esri.json must be EPSG:6341")
    for f in doc["features"]:
        xs = [p[0] for ring in f["geometry"]["rings"] for p in ring]
        ys = [p[1] for ring in f["geometry"]["rings"] for p in ring]
        features.append({"source": "census_plots", "id": f["attributes"]["PLOT_ID"],
                         "tile": f["attributes"]["TILE"], "bbox": (min(xs), min(ys), max(xs), max(ys))})
    return features


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, default=Path(__file__).with_name("training-tiles.json"))
    args = parser.parse_args()

    with open(CSV, newline="", encoding="utf-8") as f:
        manifest = {r["tile"]: r for r in csv.DictReader(f)}
    inventory = {Path(f["path"]).stem: f for f in json.loads(INVENTORY.read_text())["files"]}
    laz_present = {p.name.rsplit("_", 1)[-1][:-4] for p in LAZ.glob("*.laz")}
    las_present = {p.stem for p in LAS.glob("*.las")}
    features = evaluation_features()
    per_tile_features = {}
    for feat in features:
        per_tile_features[feat["tile"]] = per_tile_features.get(feat["tile"], 0) + 1

    def available(t):
        return (t in manifest and t in laz_present and t in las_present and t in inventory
                and int(inventory[t]["points"]) == int(manifest[t]["points"]))

    universe, candidates = [], []
    for tile in sorted(manifest):
        inv = inventory.get(tile)
        core = tuple(inv["extent"]) if inv else None
        record = {"tile": tile, "in_city_copy": manifest[tile]["in_city_copy"], "reasons_excluded": []}
        if core:
            core = (core[0], core[1], round(core[2]), round(core[3]))
            prepared = (core[0] - BUFFER, core[1] - BUFFER, core[2] + BUFFER, core[3] + BUFFER)
            record.update(core_extent=core, prepared_extent=prepared)
            sample = inv.get("classification", {})
            total = sum(sample.get("classes", {}).values())
            record["sampled_class2_share"] = round(sample.get("classes", {}).get("2", 0) / total, 4) if total else None
        if not available(tile):
            record["reasons_excluded"].append("core LAZ/LAS missing or LAS point count differs from manifest")
        missing = [n for n in neighbours(tile) if not available(n)]
        if missing:
            record["reasons_excluded"].append(f"neighbour LAZ/LAS missing: {', '.join(missing)}")
        if tile == TRAINING_TILE:
            record["reasons_excluded"].append("already the training tile")
        if core:
            for label, box in EXCLUSIONS.items():
                if intersects(core, box) or intersects(prepared, box):
                    record["reasons_excluded"].append(f"overlaps {label}")
            hits = [f for f in features if intersects(prepared, f["bbox"])]
            if hits:
                counts = {}
                for f in hits:
                    counts[f"{f['source']}:{f['tile']}"] = counts.get(f"{f['source']}:{f['tile']}", 0) + 1
                record["reasons_excluded"].append(f"evaluation features within prepared extent: {counts}")
        universe.append(record)
        if not record["reasons_excluded"]:
            candidates.append(tile)

    rng = random.Random(SEED)
    drawn = rng.sample(sorted(candidates), DRAW)
    result = {
        "created": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        "purpose": "Additional TRAINING-domain tiles for fine-tuning point-cloud models. Never holdout or transfer.",
        "seed": SEED, "draw": f"random.Random({SEED}).sample(sorted(candidates), {DRAW})",
        "draw_order": drawn, "selected": sorted(drawn),
        "stratification": ("Not used. Delivered classes are 1/2/7/18 only (no class 6), and acquisition-facts.md "
                           "carries no land-use or building-density field, so no usable pre-processing proxy "
                           "exists; simple random sampling from the eligible candidates. sampled_class2_share "
                           "(8,192-point inventory sample) is descriptive only."),
        "rules": {
            "universe": f"{len(manifest)} tiles in {CSV.relative_to(TOOLBOX).as_posix()} (all touch Millcreek)",
            "availability": f"LAZ in {LAZ} and converted LAS in {LAS} (the pilot's prepare source) for the core "
                            "and all 8 neighbours, LAS header point count equal to the USGS manifest",
            "prepared_extent": f"core header extent (max rounded as the pilot driver does) +/- {BUFFER} m",
            "exclusions": {k: list(v) for k, v in EXCLUSIONS.items()},
            "not_training_tile": TRAINING_TILE,
            "evaluation_frame": {"reference_gdb": str(REFERENCE_GDB), "feature_classes": list(REFERENCE_SAMPLES),
                                 "plots_json": str(PLOTS_JSON), "plots_json_sha256": sha256(PLOTS_JSON),
                                 "features": len(features), "features_by_tile": per_tile_features,
                                 "rule": "no feature bounding box may intersect the candidate's prepared extent"},
            "holdout_guard": "canopy.evaluation_design.assert_training_extents on every selected prepared extent",
        },
        "candidates": candidates,
        "universe": universe,
    }
    for tile in drawn:
        rec = next(r for r in universe if r["tile"] == tile)
        ed.assert_training_extents([rec["prepared_extent"], rec["core_extent"]])
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=1), encoding="utf-8")
    print(json.dumps({"candidates": candidates, "draw_order": drawn}, indent=1))


if __name__ == "__main__":
    main()
