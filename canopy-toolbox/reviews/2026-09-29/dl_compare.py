"""Compare Esri pretrained point-cloud model output with the canopy pipeline classes.

Reads LAS point records with numpy (memory-mapped) and never writes. The original
prepared tile is the baseline; the building/ and tree/ copies were classified in
place by Classify Point Cloud Using Trained Model. Point order is preserved, so the
arrays are compared index by index.

Usage: python dl_compare.py [--extent xmin ymin xmax ymax] [--out dl-12TVL2804.json]
       python dl_compare.py --original BASELINE.las --manifest tree=ROOT/work/run-tree.json --out OUT.json
       python dl_compare.py --row-manifest tree=ROOT/work/run-tree.json --out OUT.json   (multi-file row)
Requires successful run manifests from dl_run.py with matching file fingerprints.
A multi-file row compares every file with its own recorded baseline file, reports
each file separately and sums the tables only when every file passes.
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
         5: "5 high veg", 6: "6 building", 7: "7 low noise", 9: "9 water", 17: "17 bridge deck",
         18: "18 high noise", 20: "20 ignored ground"}


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


def _extent_mask(bounds, scale, offset):
    if bounds is None:
        return None
    def inside(records, start, stop):
        x = np.asarray(records["x"][start:stop])*scale[0]+offset[0]
        y = np.asarray(records["y"][start:stop])*scale[1]+offset[1]
        return (x >= bounds[0]) & (x <= bounds[2]) & (y >= bounds[1]) & (y <= bounds[3])
    return inside


def compare_job(name, manifest_path, original_path, requested=None, path=None):
    """Integrity-check one binary output against its own baseline file and tabulate classes.

    Returns the comparison entry; status is 'verified_inference' only after every
    record passed the byte-level gate.
    """
    from canopy.las_records import header, records
    manifest_path, original_path = Path(manifest_path), Path(original_path)
    entry = {"path": str(path), "status": "rejected", "original": str(original_path)}
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if path is None:
            path = Path(manifest.get('output', {}).get('path', ''))
            entry['path'] = str(path)
        extent = prediction_extent(manifest, name, original_path, path, requested)
        processed = valid_extent(manifest.get('boundary'))
    except (OSError, ValueError, KeyError) as exc:
        entry["error"] = f"Inference provenance rejected: {exc}"
        return entry
    if manifest.get('data_use_label'):
        entry['data_use_label'] = manifest['data_use_label']
    positive = 6 if name == "building" else 5
    try:
        original_info = header(original_path)
        original, scale, offset, modern = records(original_path, "r")[:4]
        copy_info = header(path)
        if any(copy_info[k] != original_info[k] for k in ('format', 'record_length', 'points')):
            raise ValueError('Point format, record length or count differs from the original')
        copy, scale_c, offset_c, modern_c = records(path, "r")[:4]
        if modern_c != modern or not (np.array_equal(scale, scale_c) and np.array_equal(offset, offset_c)):
            raise ValueError('Point scale or offset differs from the original')
        validate_point_edits(original, copy, modern, _extent_mask(processed, scale, offset), target=positive)
        table = crosstab(original, copy, _extent_mask(extent, scale, offset), modern)
    except (OSError, ValueError, struct.error, IndexError) as exc:
        entry['error'] = f'Point integrity rejected: {exc}'
        return entry
    entry.update(status="verified_inference", points=int(len(copy)),
                 coordinates_identical=True, nonclassification_bytes_identical=True,
                 outside_boundary_classes_identical=True,
                 processed_extent=processed, comparison_extent=extent,
                 inference_manifest=str(manifest_path), model=manifest["model"])
    entry["target_class"] = positive
    entry["crosstab_our_class_by_prediction"] = table
    entry["by_our_class"] = summarize(table, positive)
    del copy, original
    return entry


def add_tables(tables):
    total = {}
    for table in tables:
        for cls, preds in table.items():
            row = total.setdefault(int(cls), {})
            for pred, count in preds.items():
                row[int(pred)] = row.get(int(pred), 0) + int(count)
    return total


def compare_row(name, row_manifest_path, requested=None):
    """Compare every file of a multi-file row against its own recorded baseline file.

    Each file must pass on its own; the row is verified only if all of them are.
    """
    row_manifest_path = Path(row_manifest_path)
    entry = {"status": "rejected", "row_manifest": str(row_manifest_path), "files": {}}
    try:
        row = json.loads(row_manifest_path.read_text(encoding='utf-8'))
        if row.get('job') != name or not row.get('files'):
            raise ValueError('Row manifest has a different job or lists no files')
        if row.get('status') != 'complete':
            raise ValueError('Row inference did not complete; its outputs are not model evidence')
    except (OSError, ValueError, KeyError) as exc:
        entry['error'] = f"Inference provenance rejected: {exc}"
        return entry
    if row.get('data_use_label'):
        entry['data_use_label'] = row['data_use_label']
    for record in row['files']:
        source = Path(record['source']['path'])
        entry['files'][source.name] = compare_job(name, record['manifest'], source, requested)
    failed = [f for f, e in entry['files'].items() if e['status'] != 'verified_inference']
    if failed:
        entry['error'] = 'Point integrity rejected for ' + ', '.join(failed)
        return entry
    table = add_tables(e["crosstab_our_class_by_prediction"] for e in entry['files'].values())
    positive = 6 if name == "building" else 5
    entry.update(status="verified_inference", target_class=positive,
                 points=sum(e['points'] for e in entry['files'].values()),
                 crosstab_our_class_by_prediction=table, by_our_class=summarize(table, positive),
                 model=row['model'], processed_extent=valid_extent(row.get('boundary')),
                 comparison_extent=valid_extent(requested) or valid_extent(row.get('boundary')))
    return entry


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--extent", nargs=4, type=float, metavar=("XMIN", "YMIN", "XMAX", "YMAX"))
    ap.add_argument("--out", default=str(Path(__file__).with_name("dl-12TVL2804.json")))
    ap.add_argument('--original',type=Path,default=ORIGINAL)
    ap.add_argument('--manifest',action='append',help='JOB=manifest path; select paired or individual experiment jobs')
    ap.add_argument('--row-manifest', action='append',
                    help='JOB=row manifest of a multi-file dl_run row; each file is compared with its own baseline')
    args = ap.parse_args()
    valid_extent(args.extent)

    original_path=args.original
    manifests={name:ROOT/'work'/f'run-{name}.json' for name in COPIES}
    copies=dict(COPIES)
    rows = {}
    if args.manifest and args.row_manifest:
        ap.error('Use either --manifest or --row-manifest')
    if args.manifest or args.row_manifest:
        pairs=[p.split('=',1) for p in (args.manifest or args.row_manifest)]
        if any(len(p)!=2 or p[0] not in ('tree','building') for p in pairs) or len({p[0] for p in pairs})!=len(pairs):
            ap.error('Use one tree=manifest and/or building=manifest mapping')
        if args.row_manifest:
            rows = {name: Path(path) for name, path in pairs}
            copies = {}
        else:
            manifests={name:Path(path) for name,path in pairs}
            copies={name:None for name in manifests}
    if rows:
        result = {"mode": "multi-file row", "extent": args.extent}
        for name, path in rows.items():
            result[name] = compare_row(name, path, args.extent)
    else:
        from canopy.las_records import header
        result = {"original": str(original_path), "points": int(header(original_path)['points']),
                  "extent": args.extent}
        for name, path in copies.items():
            result[name] = compare_job(name, manifests[name], original_path, args.extent, path)
    jobs = list(rows or copies)

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
                                                  for n in jobs) else "rejected_or_partial"
    result["interpretation"] = "Class disagreement with pretrained models; not independently labelled accuracy."

    Path(args.out).write_text(json.dumps(result, indent=1))
    print(json.dumps(key, indent=1))
    for name in ("building", "tree"):
        if "error" in result.get(name, {}):
            print(name, result[name]["error"])
        for file_name, entry in result.get(name, {}).get("files", {}).items():
            if "error" in entry:
                print(name, file_name, entry["error"])
            else:
                print(name, file_name, entry["points"], "points;", {NAMES.get(c, c): r["model_target"]
                                                                     for c, r in sorted(entry["by_our_class"].items())})
        if name in result and "by_our_class" in result[name]:
            print(name, "total" if "files" in result[name] else "")
            for cls, row in sorted(result[name]["by_our_class"].items()):
                print("  ", NAMES.get(cls, cls), row)
    if result["status"] != "verified_inference":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
