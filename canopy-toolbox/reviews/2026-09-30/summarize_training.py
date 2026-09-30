"""Collect the September 30 training-tile records into training-results.json (read-only on the run folders).

    python reviews/2026-09-30/summarize_training.py
Reads H:\\lidar\\2023-salt-lake-valley\\runs\\training-2026-09-30\\{TILE}\\cpu-record.json, training-timings.csv,
deep-learning\\gpu-status.json and each row's work\\row.json, run-JOB.json and compare-ROW.json.
Model agreement numbers are class disagreement with pretrained models, not accuracy.
"""
import csv
import json
from pathlib import Path

ROOT = Path(r"H:\lidar\2023-salt-lake-valley\runs\training-2026-09-30")
DL = ROOT / "deep-learning"
HERE = Path(__file__).resolve().parent
NAMES = {1: "unclassified", 2: "ground", 3: "low veg", 4: "medium veg", 5: "high veg", 6: "building",
         7: "low noise", 18: "high noise"}


def load(path):
    path = Path(path)
    return json.loads(path.read_text(encoding="utf-8-sig")) if path.exists() else None


def cpu(tile):
    rec = load(ROOT / tile / "cpu-record.json") or {}
    after = (rec.get("prepare_before_after") or {}).get("after") or {}
    core_after = after.get(f"{tile}.las", {}).get("classes", {})
    total = sum(core_after.values())
    return {"steps": rec.get("steps"), "prepare_status": rec.get("prepare_status"), "run_status": rec.get("run_status"),
            "prepare_parameters_equal_12TVL2804": rec.get("prepare_parameters_equal_12TVL2804"),
            "run_parameters_equal_12TVL2804_except_extent_source": rec.get(
                "run_parameters_equal_12TVL2804_except_extent_source"),
            "run_signature": rec.get("run_signature"), "run_signature_12TVL2804": rec.get("run_signature_12TVL2804"),
            "prepare_sources": rec.get("prepare_sources"), "prepare_extent": rec.get("prepare_extent"),
            "core_points_after_prepare": total,
            "core_class_share_after_prepare": {k: round(v / total, 4) for k, v in sorted(core_after.items(), key=lambda kv: int(kv[0]))} if total else None,
            "error": rec.get("error")}


def gpu_row(row):
    work = DL / row / "work"
    rec = load(work / "row.json")
    if rec is None:
        return None
    job = rec.get("job")
    run = load(work / f"run-{job}.json") or {}
    comp = load(work / f"compare-{row}.json") or {}
    j = comp.get(job, {})
    files = j.get("files", {})
    integrity = {name: {k: e.get(k) for k in ("status", "points", "coordinates_identical",
                                              "nonclassification_bytes_identical", "error")}
                 for name, e in files.items()}
    md5_ok = all(f.get("source_md5_before") == f.get("copy_md5") == f.get("source_md5_after") for f in rec.get("files", []))
    watch_ok = all(w.get("md5_before") == w.get("md5_after") for w in rec.get("watch", []))
    return {"row": row, "job": job, "status": rec.get("status"), "label": rec.get("label"),
            "files": len(rec.get("files", [])), "md5_source_copy_after_all_equal": md5_ok, "watch_unchanged": watch_ok,
            "dl_run_exit": rec.get("dl_run_exit"), "dl_run_wall_seconds": rec.get("dl_run_wall_seconds"),
            "tool_elapsed_seconds": run.get("elapsed_seconds"), "gpu_used_mib_peak": run.get("gpu_used_mib_peak"),
            "run_manifest": {k: run.get(k) for k in ("status", "class_mode", "excluded_class_codes", "batch_size",
                                                      "output_classes", "error")},
            "model_sha256": (run.get("model") or {}).get("sha256"),
            "runtime_isolation": run.get("runtime_isolation"),
            "dl_compare_exit": rec.get("dl_compare_exit"), "compare_status": comp.get("status"),
            "compare_points": j.get("points"), "integrity_by_file": integrity,
            "by_our_class": j.get("by_our_class"), "key_numbers": comp.get("key_numbers"),
            "interpretation": comp.get("interpretation")}


def main():
    selection = load(HERE / "training-tiles.json")
    tiles = selection["draw_order"]
    status = load(DL / "gpu-status.json")
    timings = []
    if (ROOT / "training-timings.csv").exists():
        with open(ROOT / "training-timings.csv", newline="", encoding="utf-8") as f:
            timings = list(csv.DictReader(f))
    result = {"selection": {k: selection[k] for k in ("seed", "draw", "draw_order", "candidates")},
              "timings": timings, "gpu_queue": status, "tiles": {}}
    for tile in tiles:
        result["tiles"][tile] = {"cpu": cpu(tile), "gpu": {job: gpu_row(f"{tile}-{job}") for job in ("tree", "building")}}
    (HERE / "training-results.json").write_text(json.dumps(result, indent=1, default=str), encoding="utf-8")
    for tile, t in result["tiles"].items():
        print(tile, t["cpu"]["prepare_status"], t["cpu"]["run_status"], t["cpu"]["prepare_parameters_equal_12TVL2804"],
              t["cpu"]["run_parameters_equal_12TVL2804_except_extent_source"], t["cpu"]["core_class_share_after_prepare"])
        for job, g in t["gpu"].items():
            if not g:
                print("  ", job, "not run")
                continue
            print("  ", job, g["status"], g["compare_status"], "md5", g["md5_source_copy_after_all_equal"],
                  "wall_s", g["dl_run_wall_seconds"], "gpu_peak", g["gpu_used_mib_peak"])
            for cls, row in sorted((g["by_our_class"] or {}).items(), key=lambda kv: int(kv[0])):
                print("     ", cls, NAMES.get(int(cls), cls), row)
            print("     key", json.dumps(g["key_numbers"]))


if __name__ == "__main__":
    main()
