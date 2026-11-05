"""Whole-pulse random thinning of a LAS 1.4 (PDRF 6-10) baseline into a NEW file.

The density experiment's thinned file is its own baseline: inference output is
compared with this exact file, never index-by-index with the full-density input.
A pulse is the set of records sharing GPS time, point source ID and scanner
channel. Pulses are kept or dropped whole, so Number of Returns and return
numbers stay consistent with the retained records. Every retained record is
copied byte-for-byte in original order; only header count, returns-by-number
and bounds change. No ArcPy.

  python dl_thin.py SOURCE.las OUT.las --density 3 --seed 20260929 --extent XMIN YMIN XMAX YMAX
"""
import argparse
import json
from pathlib import Path
import struct
import sys
import time

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from canopy.las_records import header
from canopy.run_safeguards import fingerprint, valid_extent

CHUNK = 4_000_000
BLOCK = 50.0
NOISE = (7, 18)


def _raw(path, info, mode='r'):
    return np.memmap(path, dtype=np.uint8, mode=mode, offset=info['offset'],
                     shape=(info['points'], info['record_length']))


def _fields(raw):
    """Pulse and return fields from PDRF 6-10 record bytes."""
    returns = raw[:, 14]
    return {"return_number": returns & 15, "number_of_returns": returns >> 4,
            "channel": (raw[:, 15] >> 4) & 3, "classification": np.array(raw[:, 16]),
            "point_source_id": raw[:, 20:22].copy().view('<u2').ravel(),
            "gps_time": raw[:, 22:30].copy().view('<f8').ravel()}


def pulses(fields):
    """Group index per record (sorted by key) and per-pulse structure diagnostics."""
    order = np.lexsort((fields['channel'], fields['point_source_id'], fields['gps_time']))
    g, s, c = fields['gps_time'][order], fields['point_source_id'][order], fields['channel'][order]
    start = np.ones(len(order), dtype=bool)
    start[1:] = (g[1:] != g[:-1]) | (s[1:] != s[:-1]) | (c[1:] != c[:-1])
    group_sorted = np.cumsum(start) - 1
    group = np.empty(len(order), dtype=np.int64)
    group[order] = group_sorted
    count = int(group_sorted[-1]) + 1 if len(order) else 0
    size = np.bincount(group, minlength=count)
    nor = fields['number_of_returns'].astype(np.int64)
    nor_min = np.full(count, 255, dtype=np.int64)
    nor_max = np.zeros(count, dtype=np.int64)
    np.minimum.at(nor_min, group, nor)
    np.maximum.at(nor_max, group, nor)
    pairs = np.unique(group * 16 + fields['return_number'].astype(np.int64))
    distinct_returns = np.bincount(pairs // 16, minlength=count)
    consistent = nor_min == nor_max
    return group, {
        "pulses": count, "points": int(len(order)),
        "pulses_with_inconsistent_number_of_returns": int((~consistent).sum()),
        "pulses_with_duplicate_return_numbers": int((distinct_returns < size).sum()),
        "pulses_with_more_records_than_number_of_returns": int((size > nor_max).sum()),
        "complete_pulses": int((consistent & (size == nor_max) & (distinct_returns == size)).sum()),
        "incomplete_pulses_note": "records absent from the source (for example returns clipped at the tile edge) "
                                  "are not repaired; such pulses are kept or dropped whole like any other",
    }


def block_density(x, y, classification, extent, block=BLOCK):
    """Points per square metre in tile-aligned blocks, all points and non-noise."""
    x0, y0, x1, y1 = extent
    nx, ny = int(round((x1-x0)/block)), int(round((y1-y0)/block))
    inside = (x >= x0) & (x < x1) & (y >= y0) & (y < y1)
    ix = np.floor((x[inside]-x0)/block).astype(np.int64)
    iy = np.floor((y[inside]-y0)/block).astype(np.int64)
    cell = iy*nx + ix
    keep = ~np.isin(classification[inside], NOISE)

    def stats(counts):
        d = counts / (block*block)
        q = np.percentile(d, [0, 5, 25, 50, 75, 95, 100])
        return {"min": round(float(q[0]), 4), "p05": round(float(q[1]), 4), "p25": round(float(q[2]), 4),
                "median": round(float(q[3]), 4), "mean": round(float(d.mean()), 4), "p75": round(float(q[4]), 4),
                "p95": round(float(q[5]), 4), "max": round(float(q[6]), 4)}
    return {"block_m": block, "blocks": nx*ny, "extent": [x0, y0, x1, y1],
            "points_outside_extent": int((~inside).sum()),
            "all_points_per_m2": stats(np.bincount(cell, minlength=nx*ny)),
            "non_noise_points_per_m2": stats(np.bincount(cell[keep], minlength=nx*ny))}


def thin(source, out, density, seed, extent):
    source, out = Path(source).resolve(), Path(out).resolve()
    if out.exists() or out == source:
        raise ValueError(f"Output must be a new file: {out}")
    info = header(source)
    if info['format'] < 6 or info['version'] != '1.4':
        raise ValueError("Whole-pulse thinning here supports LAS 1.4 point formats 6-10 only")
    with source.open('rb') as handle:
        head = bytearray(handle.read(info['offset']))
    evlr_start, evlr_count = struct.unpack_from('<QI', head, 235)
    if evlr_count or evlr_start or struct.unpack_from('<I', head, 107)[0]:
        raise ValueError("Source with EVLRs or a legacy point count is not supported")
    scale = np.array(struct.unpack_from('<3d', head, 131))
    offset = np.array(struct.unpack_from('<3d', head, 155))
    area = (extent[2]-extent[0]) * (extent[3]-extent[1])
    before = fingerprint(source)
    raw = _raw(source, info)
    fields = _fields(raw)
    group, structure = pulses(fields)
    probability = density * area / info['points']
    if not 0 < probability <= 1:
        raise ValueError(f"Target density {density} needs keep probability {probability}")
    keep_pulse = np.random.default_rng(seed).random(structure['pulses']) < probability
    keep = keep_pulse[group]
    del group
    kept = int(keep.sum())
    xyz = np.stack([raw[keep, 0:4].copy().view('<i4').ravel(), raw[keep, 4:8].copy().view('<i4').ravel(),
                    raw[keep, 8:12].copy().view('<i4').ravel()], axis=1) * scale + offset
    by_return = np.bincount(fields['return_number'][keep], minlength=16)[1:16]
    struct.pack_into('<6d', head, 179, xyz[:, 0].max(), xyz[:, 0].min(), xyz[:, 1].max(), xyz[:, 1].min(),
                     xyz[:, 2].max(), xyz[:, 2].min())
    struct.pack_into('<Q', head, 247, kept)
    struct.pack_into('<15Q', head, 255, *[int(v) for v in by_return])
    temp = out.with_suffix('.las.partial')
    with temp.open('wb') as handle:
        handle.write(head)
        for start in range(0, info['points'], CHUNK):
            stop = min(info['points'], start+CHUNK)
            handle.write(np.ascontiguousarray(raw[start:stop][keep[start:stop]]).tobytes())
    # Read back and byte-compare every retained record with the source subset.
    written = header(temp)
    if written['points'] != kept or written['format'] != info['format'] or \
            written['record_length'] != info['record_length']:
        raise ValueError("Thinned header does not describe the written records")
    copy = _raw(temp, written)
    position = 0
    for start in range(0, info['points'], CHUNK):
        stop = min(info['points'], start+CHUNK)
        subset = raw[start:stop][keep[start:stop]]
        if not np.array_equal(subset, copy[position:position+len(subset)]):
            raise ValueError(f"Retained records differ from the source near records {start}:{stop}")
        position += len(subset)
    thinned_fields = _fields(copy)
    _, thinned_structure = pulses(thinned_fields)
    classes = thinned_fields['classification']
    density_after = block_density(xyz[:, 0], xyz[:, 1], classes, extent)
    del copy, thinned_fields
    temp.replace(out)
    x = raw[:, 0:4].copy().view('<i4').ravel()*scale[0]+offset[0]
    y = raw[:, 4:8].copy().view('<i4').ravel()*scale[1]+offset[1]
    density_before = block_density(x, y, fields['classification'], extent)
    after_source = fingerprint(source)
    if after_source != before:
        raise RuntimeError("Source changed while thinning")
    unique, counts = np.unique(classes, return_counts=True)
    return {
        "method": "whole-pulse Bernoulli selection: pulse key (GPS time, point source ID, scanner channel); "
                  "each pulse kept independently with probability p = target_density * area / source_points",
        "point_versus_pulse_policy": "pulses kept or dropped whole; Number of Returns and return numbers unchanged",
        "retained_attributes": "every byte of each retained record (XYZ, intensity, return/number of returns, "
                               "classification flags, scanner channel, scan direction/edge, classification, "
                               "user data, scan angle, point source ID, GPS time) in original order",
        "header_changes": "point count (1.4 field), points by return, XYZ bounds; VLRs and other fields copied",
        "rng": "numpy.random.default_rng(seed).random(pulse_count) over pulses in sorted key order",
        "seed": seed, "target_points_per_m2": density, "area_m2": area, "keep_probability": probability,
        "source": before, "source_after": after_source, "source_points": info['points'],
        "source_pulse_structure": structure, "source_block_density": density_before,
        "thinned_points": kept, "kept_pulses": int(keep_pulse.sum()),
        "thinned_pulse_structure": thinned_structure, "thinned_block_density": density_after,
        "thinned_class_counts": {int(k): int(v) for k, v in zip(unique, counts)},
        "records_byte_identical_to_source_subset": True, "output": fingerprint(out),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('source', type=Path)
    parser.add_argument('out', type=Path)
    parser.add_argument('--density', type=float, default=3.0)
    parser.add_argument('--seed', type=int, default=20260929)
    parser.add_argument('--extent', type=float, nargs=4, required=True)
    parser.add_argument('--record', type=Path, help='JSON record; defaults to OUT.thinning.json')
    args = parser.parse_args()
    started = time.monotonic()
    record = thin(args.source, args.out, args.density, args.seed, valid_extent(args.extent))
    record['elapsed_seconds'] = round(time.monotonic()-started, 1)
    target = args.record or args.out.with_suffix('.thinning.json')
    target.write_text(json.dumps(record, indent=1), encoding='utf-8')
    print(json.dumps({k: record[k] for k in ('thinned_points', 'keep_probability', 'output')}, indent=1))


if __name__ == '__main__':
    main()
