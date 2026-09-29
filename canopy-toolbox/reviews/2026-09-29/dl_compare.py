"""Compare Esri pretrained point-cloud model output with the canopy pipeline classes.

Reads LAS point records with numpy (memory-mapped) and never writes. The original
prepared tile is the baseline; the building/ and tree/ copies were classified in
place by Classify Point Cloud Using Trained Model. Point order is preserved, so the
arrays are compared index by index.

Usage: python dl_compare.py [--extent xmin ymin xmax ymax] [--out dl-12TVL2804.json]
Requires successful run manifests from dl_run.py with matching file fingerprints.
The processed boundary is applied automatically; --extent may restrict it further.
Class agreement with a pretrained model is not independently labelled accuracy.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import struct
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from canopy.run_safeguards import prediction_extent, valid_extent

ORIGINAL = Path(r"H:\lidar\2023-salt-lake-valley\runs\pilot-2026-09-29\12TVL2804\prepared\points\12TVL2804.las")
ROOT = Path(r"H:\lidar\2023-salt-lake-valley\runs\pilot-2026-09-29\deep-learning\12TVL2804")
COPIES = {"building": ROOT / "building" / "12TVL2804.las", "tree": ROOT / "tree" / "12TVL2804.las"}
CHUNK = 4_000_000
NAMES = {0: "0 never classified", 1: "1 unclassified", 2: "2 ground", 3: "3 low veg", 4: "4 medium veg",
         5: "5 high veg", 6: "6 building", 7: "7 low noise", 18: "18 high noise"}


def validate_point_edits(original, copy, modern=True, processed_mask_fn=None, target=None):
    """Read every point byte; only eligible classification bits may differ.

    The processing mask covers the inference boundary, independently of any
    smaller reporting extent. Opaque Extra Bytes are preserved as well.
    """
    if len(original) != len(copy) or original.dtype != copy.dtype:
        raise ValueError('Point count or record layout differs from the original')
    cls_byte = 16 if modern else 15
    if (original.dtype.itemsize < (30 if modern else 20) or
            original.dtype.fields['classification'][1] != cls_byte):
        raise ValueError('Point record layout does not match the classification encoding')
    for start in range(0, len(original), CHUNK):
        stop = min(len(original), start + CHUNK)
        a = original[start:stop].view('u1').reshape(stop-start, -1)
        b = copy[start:stop].view('u1').reshape(stop-start, -1)
        if not (np.array_equal(a[:, :cls_byte], b[:, :cls_byte]) and
                np.array_equal(a[:, cls_byte+1:], b[:, cls_byte+1:])):
            raise ValueError(f'Non-classification point bytes differ in records {start}:{stop}')
        ca, cb = a[:, cls_byte], b[:, cls_byte]
        if not modern:
            if not np.array_equal(ca & 224, cb & 224):
                raise ValueError(f'Legacy classification flags changed in records {start}:{stop}')
            ca, cb = ca & 31, cb & 31
        noise = np.isin(ca, [7, 18])
        if np.any(ca[noise] != cb[noise]):
            raise ValueError('Excluded noise classes were modified')
        inside = np.ones(stop-start, dtype=bool) if processed_mask_fn is None else processed_mask_fn(original, start, stop)
        if np.any(ca[~inside] != cb[~inside]):
            raise ValueError('Classification changed outside the processed boundary')
        if target is not None:
            unexpected = np.unique(cb[inside & ~noise & ~np.isin(cb, [0, target])])
            if len(unexpected):
                raise ValueError(f'Processed non-noise points retain unexpected classes: {unexpected.tolist()}')


def crosstab(original, copy, mask_fn, modern=True):
    """Return {orig_class: {pred_class: count}} using a chunked bincount over pairs."""
    table = np.zeros((256, 256), dtype=np.int64)
    n = len(original)
    for start in range(0, n, CHUNK):
        stop = min(n, start + CHUNK)
        a = np.asarray(original["classification"][start:stop])
        b = np.asarray(copy["classification"][start:stop])
        if not modern:
            a, b = a & 31, b & 31
        if mask_fn is not None:
            keep = mask_fn(original, start, stop)
            a, b = a[keep], b[keep]
        table += np.bincount(a.astype(np.int64)*256 + b, minlength=65536).reshape(256, 256)
    return {int(i): {int(j): int(table[i, j]) for j in np.nonzero(table[i])[0]} for i in np.nonzero(table.sum(1))[0]}


def summarize(table, positive):
    """Collapse to our-class x (positive / other) counts for the target class."""
    rows = {}
    for cls, preds in table.items():
        pos = int(preds.get(positive, 0))
        total = int(sum(preds.values()))
        rows[cls] = {"points": total, "model_target": pos, "model_background_or_other": total-pos,
                     "share_model_target": round(pos/total, 5) if total else None}
    return rows


def main():
    from canopy.roofs import _records
    from canopy.preparation import header
    ap = argparse.ArgumentParser()
    ap.add_argument("--extent", nargs=4, type=float, metavar=("XMIN", "YMIN", "XMAX", "YMAX"))
    ap.add_argument("--out", default=str(Path(__file__).with_name("dl-12TVL2804.json")))
    args = ap.parse_args()
    valid_extent(args.extent)

    original_info = header(ORIGINAL)
    original, scale, offset, modern = _records(ORIGINAL, "r")
    result = {"original": str(ORIGINAL), "points": int(len(original)), "extent": args.extent}

    def extent_mask(bounds):
        if bounds is None:
            return None
        def inside(records, start, stop):
            x = np.asarray(records["x"][start:stop])*scale[0]+offset[0]
            y = np.asarray(records["y"][start:stop])*scale[1]+offset[1]
            return (x >= bounds[0]) & (x <= bounds[2]) & (y >= bounds[1]) & (y <= bounds[3])
        return inside

    for name, path in COPIES.items():
        entry = {"path": str(path), "status": "rejected"}
        manifest_path = ROOT / "work" / f"run-{name}.json"
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            extent = prediction_extent(manifest, name, ORIGINAL, path, args.extent)
            processed = valid_extent(manifest.get('boundary'))
        except (OSError, ValueError, KeyError) as exc:
            entry["error"] = f"Inference provenance rejected: {exc}"
            result[name] = entry
            continue
        positive = 6 if name == "building" else 5
        try:
            copy_info = header(path)
            if any(copy_info[k] != original_info[k] for k in ('format', 'record_length', 'points')):
                raise ValueError('Point format, record length or count differs from the original')
            copy, scale_c, offset_c, modern_c = _records(path, "r")
            if modern_c != modern or not (np.array_equal(scale, scale_c) and np.array_equal(offset, offset_c)):
                raise ValueError('Point scale or offset differs from the original')
            validate_point_edits(original, copy, modern, extent_mask(processed), target=positive)
            table = crosstab(original, copy, extent_mask(extent), modern)
        except (OSError, ValueError, struct.error, IndexError) as exc:
            entry['error'] = f'Point integrity rejected: {exc}'
            result[name] = entry
            continue
        entry.update(status="verified_inference", points=int(len(copy)),
                     coordinates_identical=True, nonclassification_bytes_identical=True,
                     outside_boundary_classes_identical=True,
                     processed_extent=processed, comparison_extent=extent,
                     inference_manifest=str(manifest_path), model=manifest["model"])
        entry["target_class"] = positive
        entry["crosstab_our_class_by_prediction"] = table
        entry["by_our_class"] = summarize(table, positive)
        result[name] = entry
        del copy

    b = result.get("building", {}).get("crosstab_our_class_by_prediction")
    t = result.get("tree", {}).get("crosstab_our_class_by_prediction")
    key = {}
    if b:
        veg = {c: b.get(c, {}).get(6, 0) for c in (3, 4, 5)}
        key["our_3_4_5_called_building_by_building_model"] = {**{str(c): v for c, v in veg.items()}, "total": sum(veg.values())}
        c6 = b.get(6, {})
        key["our_6_called_background_by_building_model"] = {"background": sum(v for k, v in c6.items() if k != 6),
                                                            "of": sum(c6.values())}
    if t:
        c5 = t.get(5, {})
        key["our_5_called_background_by_tree_model"] = {"background": sum(v for k, v in c5.items() if k != 5),
                                                        "of": sum(c5.values())}
        c6 = t.get(6, {})
        key["our_6_called_tree_by_tree_model"] = {"tree": int(c6.get(5, 0)), "of": sum(c6.values())}
    result["key_numbers"] = key
    result["status"] = "verified_inference" if all(result[n].get("status") == "verified_inference"
                                                  for n in COPIES) else "rejected_or_partial"
    result["interpretation"] = "Class disagreement with pretrained models; not independently labelled accuracy."

    Path(args.out).write_text(json.dumps(result, indent=1))
    print(json.dumps(key, indent=1))
    for name in ("building", "tree"):
        if "error" in result.get(name, {}):
            print(name, result[name]["error"])
        if name in result and "by_our_class" in result[name]:
            print(name)
            for cls, row in sorted(result[name]["by_our_class"].items()):
                print("  ", NAMES.get(cls, cls), row)
    if result["status"] != "verified_inference":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
