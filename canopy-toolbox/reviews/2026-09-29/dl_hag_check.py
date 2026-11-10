"""Verify that a height-above-ground (z-mode) LAS differs from its absolute baseline only in Z.

Read-only. Compares every point record byte except the 4-byte Z integer (record
bytes 8-11 in every LAS point format) and every header/VLR byte before the point
offset except the Z offset and max/min Z fields, which the HAG writer declares it
rewrites. Anything after the point records (EVLRs) must be identical too. A HAG
row's model predictions are compared index-by-index with the HAG baseline only;
this check establishes that its point order and all other attributes equal the
absolute baseline, so the two rows' predictions can be paired by index.

  python dl_hag_check.py --absolute ABS.las --hag HAG.las --out CHECK.json
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from canopy.las_records import header

CHUNK = 4_000_000
Z_BYTES = slice(8, 12)
# Header windows (LAS 1.1-1.4): Z offset at 171, max Z at 211, min Z at 219.
HEADER_Z_FIELDS = {"z_offset": (171, 179), "max_z": (211, 219), "min_z": (219, 227)}


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def check(absolute, hag):
    a_info, h_info = header(absolute), header(hag)
    result = {"absolute": {"path": a_info['path'], "bytes": a_info['bytes'], "sha256": _sha256(absolute)},
              "hag": {"path": h_info['path'], "bytes": h_info['bytes'], "sha256": _sha256(hag)},
              "status": "rejected"}
    for key in ('format', 'record_length', 'points', 'offset', 'bytes'):
        if a_info[key] != h_info[key]:
            result['error'] = f"{key} differs: {a_info[key]} vs {h_info[key]}"
            return result
    with open(absolute, 'rb') as fa, open(hag, 'rb') as fh:
        head_a, head_h = fa.read(a_info['offset']), fh.read(h_info['offset'])
    allowed = np.zeros(len(head_a), dtype=bool)
    for start, stop in HEADER_Z_FIELDS.values():
        allowed[start:stop] = True
    differs = np.frombuffer(head_a, np.uint8) != np.frombuffer(head_h, np.uint8)
    if np.any(differs & ~allowed):
        result['error'] = f"Header/VLR bytes differ outside the Z fields at {np.nonzero(differs & ~allowed)[0][:20].tolist()}"
        return result
    result['header_z_fields'] = {name: {"absolute": struct.unpack('<d', head_a[s:e])[0],
                                        "hag": struct.unpack('<d', head_h[s:e])[0]}
                                 for name, (s, e) in HEADER_Z_FIELDS.items()}
    n, length, offset = a_info['points'], a_info['record_length'], a_info['offset']
    a = np.memmap(absolute, np.uint8, 'r', offset=offset, shape=(n, length)) if n else np.zeros((0, length), np.uint8)
    h = np.memmap(hag, np.uint8, 'r', offset=offset, shape=(n, length)) if n else np.zeros((0, length), np.uint8)
    z_changed = 0
    for start in range(0, n, CHUNK):
        stop = min(n, start + CHUNK)
        x, y = np.asarray(a[start:stop]), np.asarray(h[start:stop])
        if not (np.array_equal(x[:, :8], y[:, :8]) and np.array_equal(x[:, 12:], y[:, 12:])):
            result['error'] = f"Non-Z point bytes differ in records {start}:{stop}"
            return result
        z_changed += int(np.any(x[:, Z_BYTES] != y[:, Z_BYTES], axis=1).sum())
    del a, h
    tail = offset + n * length
    with open(absolute, 'rb') as fa, open(hag, 'rb') as fh:
        fa.seek(tail), fh.seek(tail)
        if fa.read() != fh.read():
            result['error'] = "Bytes after the point records (EVLRs) differ"
            return result
    result.update(status="non_z_bytes_identical", points=n, records_with_changed_z=z_changed,
                  compared="all header/VLR bytes except Z offset and max/min Z; all record bytes except Z; "
                           "all bytes after the records")
    return result


def paired_predictions(absolute_output, hag_output, target):
    """Index-paired class table of two verified raw outputs whose baselines passed check().

    Returns {absolute_class: {hag_class: count}} and the target-class agreement.
    Only meaningful after check() showed the two baselines share point order.
    """
    a_info, h_info = header(absolute_output), header(hag_output)
    if any(a_info[k] != h_info[k] for k in ('format', 'record_length', 'points', 'offset')):
        raise ValueError("Outputs do not share a record layout")
    n, length, offset = a_info['points'], a_info['record_length'], a_info['offset']
    cls = 16 if a_info['format'] >= 6 else 15
    a = np.memmap(absolute_output, np.uint8, 'r', offset=offset, shape=(n, length))
    h = np.memmap(hag_output, np.uint8, 'r', offset=offset, shape=(n, length))
    table = np.zeros((256, 256), dtype=np.int64)
    for start in range(0, n, CHUNK):
        stop = min(n, start + CHUNK)
        x, y = np.asarray(a[start:stop, cls]).astype(np.int64), np.asarray(h[start:stop, cls]).astype(np.int64)
        if cls == 15:
            x, y = x & 31, y & 31
        table += np.bincount(x * 256 + y, minlength=65536).reshape(256, 256)
    del a, h
    both = int(table[target, target])
    only_abs = int(table[target].sum() - both)
    only_hag = int(table[:, target].sum() - both)
    return {"crosstab_absolute_by_hag": {int(i): {int(j): int(table[i, j]) for j in np.nonzero(table[i])[0]}
                                         for i in np.nonzero(table.sum(1))[0]},
            "target_class": target, "target_both": both, "target_absolute_only": only_abs,
            "target_hag_only": only_hag, "points": n,
            "identical_predictions": bool(only_abs == 0 and only_hag == 0 and
                                          int(np.trace(table)) == n)}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--absolute', type=Path, required=True)
    parser.add_argument('--hag', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--pair', nargs=3, action='append', metavar=('JOB', 'ABS_OUTPUT', 'HAG_OUTPUT'),
                        help='Also pair two verified raw outputs by point index (JOB tree or building)')
    args = parser.parse_args()
    result = check(args.absolute, args.hag)
    if result['status'] == 'non_z_bytes_identical':
        for job, abs_output, hag_output in args.pair or []:
            result.setdefault('paired_predictions', {})[job] = paired_predictions(
                abs_output, hag_output, {'tree': 5, 'building': 6}[job])
    args.out.write_text(json.dumps(result, indent=1), encoding='utf-8')
    shown = ('status', 'error', 'points', 'records_with_changed_z', 'header_z_fields')
    print(json.dumps({k: v for k, v in result.items() if k in shown}, indent=1))
    for job, pair in result.get('paired_predictions', {}).items():
        print(job, {k: v for k, v in pair.items() if k != 'crosstab_absolute_by_hag'})
    if result['status'] != 'non_z_bytes_identical':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
