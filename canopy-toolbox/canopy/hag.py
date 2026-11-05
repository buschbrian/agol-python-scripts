"""Height above ground (HAG) from a prepared dataset's class-2 ground. The core does not import ArcPy.

Ground surface: the pipeline DTM (rasters.DTM_INTERPOLATION) of class-2 points, withheld, overlap
and synthetic points excluded, from every file of the prepared dataset, in 0.5 m cells.
raster_builder() makes it with ArcGIS Pro and is the only function here that imports ArcPy.

A point's ground is the value of the cell that contains it; a point on the raster's east or south
edge uses the edge cell. This is the pipeline's CHM arithmetic (DSM cell minus DTM cell) applied
per point. Nothing is interpolated: a point whose cell is NoData or outside the raster is
uncovered. HAG = Z - ground, signed and never clamped. About half of all ground points lie a few
centimetres below their cell value, so negative HAG is counted by class, not treated as an error.

Outputs in a NEW folder (existing folders are refused):

- z mode, points/<file>.las: a new baseline whose Z is HAG. It changes protected bytes, so it has
  its own fingerprint. Z scale is kept, Z offset becomes 0, header max/min Z are those of the
  stored values. Every other byte (other header fields, VLRs, other record bytes, EVLRs) is
  identical to the source and verified. A file with any uncovered point is refused (not written);
  its uncovered point indices go to uncovered/<file>.npz.
- extrabytes mode, points-extrabytes/<file>.las: each record keeps all its bytes, original Z
  included, and gains a 4-byte signed integer "HeightAboveGround" described by an Extra Bytes VLR
  (LASF_Spec 4, LAS 1.4 R15 layout; scale = the file's Z scale, offset 0). Uncovered points hold
  the declared no_data value. Only LAS 1.4 files are written: PDAL ignores an Extra Bytes VLR in
  LAS 1.2, so legacy-version files are skipped, as are files that already carry extra bytes.

Quality: EXPERIMENTAL_UNVALIDATED. HAG depends on the ground classification of the preparation.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import platform
import stat
import struct
import time

import numpy as np

from . import las_records

CELL_M = .5
CHUNK = 2_000_000
MODES = ("z", "extrabytes", "both")
Z_FOLDER, EB_FOLDER = "points", "points-extrabytes"
STANDARD_LENGTH = (20, 28, 26, 34, 57, 63, 30, 36, 38, 59, 67)
# Header byte windows the Z copy rewrites; the offsets are the same in LAS 1.1-1.4.
Z_SCALE_AT, Z_OFFSET_AT, MAX_Z_AT, MIN_Z_AT = 147, 171, 211, 219
Z_WINDOWS = ((Z_OFFSET_AT, Z_OFFSET_AT+8), (MAX_Z_AT, MIN_Z_AT+8))
INT32 = (-2**31, 2**31-1)
EB_NAME = b"HeightAboveGround"
EB_DESCRIPTION = b"Z minus 0.5 m ground cell (m)"
EB_TYPE = 6                  # signed 32-bit integer, scaled
EB_OPTIONS = 1 | 8 | 16      # no_data, scale and offset are set
EB_NO_DATA = INT32[0]
QUALITY = "EXPERIMENTAL_UNVALIDATED"
DEFINITION = {
    "ground": "class 2, withheld/overlap/synthetic excluded, all prepared files, LasDatasetToRaster "
              "TRIANGULATION NATURAL_NEIGHBOR WINDOW_SIZE MINIMUM 1 (the pipeline DTM)",
    "sampling": "value of the raster cell containing the point (east/south edge points use the edge cell); "
                "no interpolation between cells; NoData or outside = uncovered",
    "hag": "Z - ground, metres, signed (negative kept, never clamped)",
    "z_mode": "Z replaced by round(HAG / Z scale); Z scale kept; Z offset 0; header max/min Z from stored "
              "values; files with any uncovered point are refused",
    "extrabytes_mode": "4-byte signed int HeightAboveGround = round(HAG / Z scale), scale = Z scale, offset 0; "
                       f"uncovered = no_data {EB_NO_DATA}; original record bytes unchanged",
    "vertical_reference_note": "The WKT VLR is copied unchanged, so z-mode files still declare the source "
                               "vertical datum although Z is height above ground (metres).",
}


class GroundSurface:
    """Ground elevation cells (float32, NaN = NoData), north-up, square cells."""

    def __init__(self, values, xmin, ymax, cell, record=None):
        self.values = np.asarray(values, dtype=np.float32)
        if self.values.ndim != 2 or not self.values.size:
            raise ValueError("Ground values must be a non-empty 2-D array")
        cell = float(cell)
        if not math.isfinite(cell) or cell <= 0 or not math.isfinite(xmin) or not math.isfinite(ymax):
            raise ValueError("Ground origin and cell size must be finite; the cell size positive")
        self.xmin, self.ymax, self.cell = float(xmin), float(ymax), cell
        self.rows, self.cols = self.values.shape
        self.xmax, self.ymin = self.xmin+self.cols*cell, self.ymax-self.rows*cell
        self.record = dict(record or {})

    @property
    def extent(self):
        return [self.xmin, self.ymin, self.xmax, self.ymax]

    def sample(self, x, y):
        """Ground of the containing cell (float64); NaN where uncovered."""
        x, y = np.asarray(x, dtype=float), np.asarray(y, dtype=float)
        col = np.floor((x-self.xmin)/self.cell).astype(np.int64)
        row = np.floor((self.ymax-y)/self.cell).astype(np.int64)
        col[(col == self.cols) & (x <= self.xmax)] = self.cols-1
        row[(row == self.rows) & (y >= self.ymin)] = self.rows-1
        inside = (col >= 0) & (col < self.cols) & (row >= 0) & (row < self.rows)
        ground = np.full(x.shape, np.nan)
        ground[inside] = self.values[row[inside], col[inside]]
        return ground

    def heights(self, x, y, z):
        return np.asarray(z, dtype=float)-self.sample(x, y)


def snap_out(extent, cell=CELL_M):
    x0, y0, x1, y1 = (float(v) for v in extent)
    return [math.floor(x0/cell)*cell, math.floor(y0/cell)*cell, math.ceil(x1/cell)*cell, math.ceil(y1/cell)*cell]


def digests(path, block=8*1024*1024):
    """SHA-256 and MD5 of a file in one read, with size and modification time."""
    path = Path(path).resolve()
    sha, md5 = hashlib.sha256(), hashlib.md5()
    with path.open("rb") as handle:
        for piece in iter(lambda: handle.read(block), b""):
            sha.update(piece); md5.update(piece)
    info = path.stat()
    return {"path": str(path), "bytes": info.st_size, "mtime_ns": info.st_mtime_ns,
            "sha256": sha.hexdigest(), "md5": md5.hexdigest()}


def _vlr_end(head):
    """Byte after the last VLR (points may start later, after padding)."""
    at = struct.unpack_from("<H", head, 94)[0]
    for _ in range(struct.unpack_from("<I", head, 100)[0]):
        at += 54+struct.unpack_from("<H", head, at+20)[0]
    return at


def _vlr_ids(head):
    at, found = struct.unpack_from("<H", head, 94)[0], []
    for _ in range(struct.unpack_from("<I", head, 100)[0]):
        found.append((head[at+2:at+18].rstrip(b"\0").decode("ascii", "replace"), struct.unpack_from("<H", head, at+18)[0]))
        at += 54+struct.unpack_from("<H", head, at+20)[0]
    return found


def _open(path):
    info = las_records.header(path)
    n, length, start = info["points"], info["record_length"], info["offset"]
    with open(path, "rb") as handle:
        head = handle.read(start)
    raw = (np.memmap(path, dtype=np.uint8, mode="r", offset=start, shape=(n, length)) if n
           else np.zeros((0, length), np.uint8))
    return info, head, raw, start+n*length


def _copy_tail(path, tail_start, out, block=8*1024*1024):
    with open(path, "rb") as handle:
        handle.seek(tail_start)
        for piece in iter(lambda: handle.read(block), b""):
            out.write(piece)


def _block_heights(ground, points, scale, offset, modern, start, stop):
    block = points[start:stop]
    x, y, z, classes, _, _ = las_records.decode(block, scale, offset, modern)
    return ground.heights(x, y, z), np.asarray(classes, dtype=np.uint8)


def _quantize(hag, zscale, reserve_min=False):
    q = np.round(hag/zscale)
    low = INT32[0]+(1 if reserve_min else 0)
    if len(q) and (q.min() < low or q.max() > INT32[1]):
        raise ValueError("Height above ground does not fit a 32-bit integer at the file's Z scale")
    return q.astype("<i4")


def _stats(q, classes, zscale):
    negative = q < 0
    return {"negative": int(negative.sum()),
            "negative_by_class": np.bincount(classes[negative], minlength=256).astype(np.int64),
            "below_minus_1m": int((q < -round(1/zscale)).sum()),
            "points_by_class": np.bincount(classes, minlength=256).astype(np.int64)}


def _merge(total, part):
    for key, value in part.items():
        total[key] = total.get(key, 0)+value


def _classes(counts):
    return {str(i): int(v) for i, v in enumerate(counts) if v}


def write_z(source, target, ground, uncovered_log=None, chunk=CHUNK):
    """New LAS copy of source whose Z is HAG. Returns a record; refused files are not written."""
    source, target = Path(source), Path(target)
    if target.exists():
        raise FileExistsError(f"Output already exists: {target}")
    started = time.perf_counter()
    info, head, raw, tail_start = _open(source)
    head = bytearray(head)
    zscale = struct.unpack_from("<d", head, Z_SCALE_AT)[0]
    points, scale, offset, modern, _ = las_records.records(source, "r")
    n = info["points"]
    partial = target.with_name(target.name+".partial")
    uncovered, totals, qmin, qmax = [], {}, None, None
    try:
        with open(partial, "wb") as out:
            out.write(head)
            for start in range(0, n, chunk):
                stop = min(n, start+chunk)
                hag, classes = _block_heights(ground, points, scale, offset, modern, start, stop)
                bad = ~np.isfinite(hag)
                if bad.any():
                    uncovered.append(np.flatnonzero(bad)+start)
                if uncovered:
                    continue   # keep counting uncovered points; nothing more is written
                q = _quantize(hag, zscale)
                record = np.array(raw[start:stop])
                record[:, 8:12] = q.view(np.uint8).reshape(-1, 4)
                out.write(record.tobytes())
                _merge(totals, _stats(q, classes, zscale))
                if len(q):
                    qmin = int(q.min()) if qmin is None else min(qmin, int(q.min()))
                    qmax = int(q.max()) if qmax is None else max(qmax, int(q.max()))
            if not uncovered:
                _copy_tail(source, tail_start, out)
    finally:
        del points, raw
    row = {"source": str(source.resolve()), "points": n, "format": info["format"], "version": info["version"],
           "z_scale": zscale}
    if uncovered:
        partial.unlink()
        indices = np.concatenate(uncovered).astype(np.int64)
        if uncovered_log is not None:
            Path(uncovered_log).parent.mkdir(parents=True, exist_ok=True)
            np.savez_compressed(uncovered_log, point_index=indices)
        row.update(status="refused", uncovered=int(len(indices)),
                   reason="points without ground coverage; Z mode never invents a ground value",
                   uncovered_log=str(uncovered_log) if uncovered_log is not None else None)
        return row
    zmax = qmax*zscale if qmax is not None else 0.
    zmin = qmin*zscale if qmin is not None else 0.
    decimals = max(0, round(-math.log10(zscale)))
    struct.pack_into("<d", head, Z_OFFSET_AT, 0.)
    struct.pack_into("<2d", head, MAX_Z_AT, zmax, zmin)
    with open(partial, "r+b") as out:
        out.write(head)
    os.replace(partial, target)
    row.update(status="written", path=str(target.resolve()), uncovered=0, z_offset=0.,
               hag_max_m=round(zmax, decimals), hag_min_m=round(zmin, decimals), negative=totals.get("negative", 0),
               negative_by_class=_classes(totals.get("negative_by_class", [])),
               below_minus_1m=totals.get("below_minus_1m", 0),
               points_by_class=_classes(totals.get("points_by_class", [])),
               seconds=round(time.perf_counter()-started, 1))
    return row


def verify_z(source, target, ground, chunk=CHUNK):
    """Binary check of a Z copy: only Z offset, max/min Z and record Z bytes may differ, Z = HAG."""
    s_info, s_head, s_raw, s_tail = _open(source)
    t_info, t_head, t_raw, t_tail = _open(target)
    mask = np.ones(len(s_head), bool)
    for lo, hi in Z_WINDOWS:
        mask[lo:hi] = False
    zscale = struct.unpack_from("<d", s_head, Z_SCALE_AT)[0]
    same_layout = (len(s_head) == len(t_head) and s_info["points"] == t_info["points"] and
                   s_info["record_length"] == t_info["record_length"] and
                   Path(source).stat().st_size == Path(target).stat().st_size)
    result = {"same_layout_and_size": same_layout}
    if not same_layout:
        result["all_pass"] = False
        return result
    a, b = np.frombuffer(s_head, np.uint8), np.frombuffer(t_head, np.uint8)
    result["header_and_vlrs_identical_outside_z_fields"] = bool((a[mask] == b[mask]).all())
    points, scale, offset, modern, _ = las_records.records(source, "r")
    other, wrong, qmin, qmax = 0, 0, None, None
    for start in range(0, s_info["points"], chunk):
        stop = min(s_info["points"], start+chunk)
        x, y = np.array(s_raw[start:stop]), np.array(t_raw[start:stop])
        differ = x != y
        differ[:, 8:12] = False
        other += int(differ.sum())
        hag, _ = _block_heights(ground, points, scale, offset, modern, start, stop)
        stored = y[:, 8:12].copy().view("<i4").ravel()
        wrong += int((~np.isfinite(hag) | (stored != np.round(hag/zscale))).sum())
        if len(stored):
            qmin = int(stored.min()) if qmin is None else min(qmin, int(stored.min()))
            qmax = int(stored.max()) if qmax is None else max(qmax, int(stored.max()))
    del points, s_raw, t_raw
    with open(source, "rb") as f1, open(target, "rb") as f2:
        f1.seek(s_tail); f2.seek(t_tail)
        result["trailing_bytes_identical"] = f1.read() == f2.read()
    offset_z = struct.unpack_from("<d", t_head, Z_OFFSET_AT)[0]
    zmax, zmin = struct.unpack_from("<2d", t_head, MAX_Z_AT)
    result.update(
        non_z_record_bytes_differing=other, z_values_not_equal_to_hag=wrong,
        z_scale_kept=struct.unpack_from("<d", t_head, Z_SCALE_AT)[0] == zscale, z_offset_zero=offset_z == 0.,
        header_max_min_z_match_stored=(qmax is None or (zmax == qmax*zscale and zmin == qmin*zscale)))
    result["all_pass"] = bool(all(v for k, v in result.items() if isinstance(v, bool)) and other == 0 and wrong == 0)
    return result


def descriptor(scale):
    """192-byte Extra Bytes descriptor (LAS 1.4 R15) for the scaled integer HAG attribute."""
    d = bytearray(192)
    d[2], d[3] = EB_TYPE, EB_OPTIONS
    d[4:4+len(EB_NAME)] = EB_NAME
    struct.pack_into("<q", d, 40, EB_NO_DATA)
    struct.pack_into("<d", d, 112, scale)
    struct.pack_into("<d", d, 136, 0.)
    d[160:160+len(EB_DESCRIPTION)] = EB_DESCRIPTION
    return bytes(d)


def extrabytes_feasible(info, head):
    """None when an Extra Bytes attribute can be appended, else the reason it cannot."""
    if head[24:26] != bytes([1, 4]):
        return ("Extra Bytes VLRs are a LAS 1.4 construct; PDAL 3.5 ignores one in a LAS 1.2 file (checked), "
                "so the attribute would be invisible. Use z mode for this file.")
    if info["record_length"] != STANDARD_LENGTH[info["format"]]:
        return "record already carries extra bytes; appending would need their descriptors"
    if ("LASF_Spec", 4) in _vlr_ids(head):
        return "file already has an Extra Bytes VLR"
    if info["record_length"]+4 > 65535 or struct.unpack_from("<H", head, 94)[0] > len(head):
        return "record or header too long"
    return None


def write_extrabytes(source, target, ground, chunk=CHUNK):
    """New LAS copy of source with a HeightAboveGround Extra Bytes attribute; Z untouched."""
    source, target = Path(source), Path(target)
    if target.exists():
        raise FileExistsError(f"Output already exists: {target}")
    started = time.perf_counter()
    info, head, raw, tail_start = _open(source)
    row = {"source": str(source.resolve()), "points": info["points"], "format": info["format"],
           "version": info["version"]}
    reason = extrabytes_feasible(info, head)
    if reason:
        del raw
        row.update(status="skipped", reason=reason)
        return row
    zscale = struct.unpack_from("<d", head, Z_SCALE_AT)[0]
    n, length = info["points"], info["record_length"]
    vlr = struct.pack("<H16sHH32s", 0, b"LASF_Spec", 4, 192, b"Height above ground") + descriptor(zscale)
    end = _vlr_end(head)
    new = bytearray(head[:end])+vlr+head[end:]
    grow = len(vlr)+4*n
    struct.pack_into("<I", new, 96, len(new))
    struct.pack_into("<I", new, 100, struct.unpack_from("<I", head, 100)[0]+1)
    struct.pack_into("<H", new, 105, length+4)
    minor = head[25]
    shifted = []
    for at, used in ((227, minor >= 3), (235, minor >= 4)):
        if used and struct.unpack_from("<Q", head, at)[0]:
            struct.pack_into("<Q", new, at, struct.unpack_from("<Q", head, at)[0]+grow)
            shifted.append(at)
    points, scale, offset, modern, _ = las_records.records(source, "r")
    partial = target.with_name(target.name+".partial")
    totals, uncovered = {}, 0
    try:
        with open(partial, "wb") as out:
            out.write(new)
            for start in range(0, n, chunk):
                stop = min(n, start+chunk)
                hag, classes = _block_heights(ground, points, scale, offset, modern, start, stop)
                bad = ~np.isfinite(hag)
                uncovered += int(bad.sum())
                q = _quantize(np.where(bad, 0., hag), zscale, reserve_min=True)
                q[bad] = EB_NO_DATA
                record = np.empty((stop-start, length+4), np.uint8)
                record[:, :length] = raw[start:stop]
                record[:, length:] = q.view(np.uint8).reshape(-1, 4)
                out.write(record.tobytes())
                _merge(totals, _stats(q[~bad], classes[~bad], zscale))
            _copy_tail(source, tail_start, out)
    finally:
        del points, raw
    os.replace(partial, target)
    row.update(status="written", path=str(target.resolve()), uncovered_no_data=uncovered,
               attribute={"name": EB_NAME.decode(), "data_type": "int32 (Extra Bytes type 6)", "scale": zscale,
                          "offset": 0., "no_data": EB_NO_DATA},
               header_fields_changed=["offset_to_point_data", "number_of_vlrs", "point_record_length"] +
               [{227: "start_of_waveform_data", 235: "start_of_first_evlr"}[at] for at in shifted],
               negative=totals.get("negative", 0),
               negative_by_class=_classes(totals.get("negative_by_class", [])),
               seconds=round(time.perf_counter()-started, 1))
    return row


def verify_extrabytes(source, target, ground, chunk=CHUNK):
    """Binary check: original records, header (outside the layout fields) and VLRs unchanged."""
    s_info, s_head, s_raw, s_tail = _open(source)
    t_info, t_head, t_raw, t_tail = _open(target)
    end = _vlr_end(s_head)
    zscale = struct.unpack_from("<d", s_head, Z_SCALE_AT)[0]
    vlr = struct.pack("<H16sHH32s", 0, b"LASF_Spec", 4, 192, b"Height above ground") + descriptor(zscale)
    expected_head = bytearray(s_head[:end])+vlr+s_head[end:]
    fields = [(96, 100), (100, 104), (105, 107)] + ([(227, 235)] if s_head[25] >= 3 else []) + \
             ([(235, 243)] if s_head[25] >= 4 else [])
    mask = np.ones(len(expected_head), bool)
    for lo, hi in fields:
        mask[lo:hi] = False
    a = np.frombuffer(bytes(expected_head), np.uint8)
    b = np.frombuffer(t_head, np.uint8)
    result = {"layout": len(a) == len(b) and t_info["points"] == s_info["points"] and
              t_info["record_length"] == s_info["record_length"]+4}
    if not result["layout"]:
        result["all_pass"] = False
        return result
    result["header_and_vlrs_identical_outside_layout_fields"] = bool((a[mask] == b[mask]).all())
    result["extra_bytes_vlr_present"] = ("LASF_Spec", 4) in _vlr_ids(t_head)
    points, scale, offset, modern, _ = las_records.records(source, "r")
    length, other, wrong = s_info["record_length"], 0, 0
    for start in range(0, s_info["points"], chunk):
        stop = min(s_info["points"], start+chunk)
        x, y = np.array(s_raw[start:stop]), np.array(t_raw[start:stop])
        other += int((x != y[:, :length]).sum())
        hag, _ = _block_heights(ground, points, scale, offset, modern, start, stop)
        stored = y[:, length:].copy().view("<i4").ravel()
        expected = np.where(np.isfinite(hag), np.round(np.where(np.isfinite(hag), hag, 0)/zscale), EB_NO_DATA)
        wrong += int((stored != expected).sum())
    del points, s_raw, t_raw
    with open(source, "rb") as f1, open(target, "rb") as f2:
        f1.seek(s_tail); f2.seek(t_tail)
        result["trailing_bytes_identical"] = f1.read() == f2.read()
    result.update(original_record_bytes_differing=other, hag_values_wrong=wrong)
    result["all_pass"] = bool(all(v for k, v in result.items() if isinstance(v, bool)) and other == 0 and wrong == 0)
    return result


def _write_json(path, value):
    path = Path(path)
    pending = path.with_name(path.name+".pending")
    pending.write_text(json.dumps(value, indent=2, default=str), encoding="utf-8")
    os.replace(pending, path)


def _peak_memory_gb():
    try:
        import psutil
        info = psutil.Process().memory_info()
        return round(getattr(info, "peak_wset", info.rss)/1e9, 2)
    except Exception:  # reported when available; never blocks processing
        return None


def _check_input(prepared_lasd, output_folder):
    root = Path(prepared_lasd).resolve().parent
    manifest = root/"preparation.json"
    if not manifest.is_file():
        raise ValueError("Use a prepared working-copy LAS dataset with preparation.json")
    previous = json.loads(manifest.read_text(encoding="utf-8"))
    if previous.get("status") != "complete" or Path(previous["working_lasd"]).resolve() != Path(prepared_lasd).resolve():
        raise ValueError("Preparation manifest does not match a completed LAS dataset")
    destination = Path(output_folder).resolve()
    if destination == root or root in destination.parents:
        raise ValueError("Choose a new HAG folder outside the input preparation")
    if destination.exists():
        raise FileExistsError("HAG output already exists")
    files = sorted((root/"points").glob("*.las"))
    if not files:
        raise ValueError("Prepared point files were not found")
    return manifest, previous, destination, files


def _side_files(prepared_lasd, files):
    rows = []
    for path in [Path(prepared_lasd)]+[p.with_suffix(".lasx") for p in files]:
        if path.is_file():
            info = path.stat()
            rows.append({"path": str(path.resolve()), "bytes": info.st_size, "mtime_ns": info.st_mtime_ns})
    return rows


def core_index(headers, previous):
    """Index of the core file: of the files whose header extent contains the centre of the prepared
    extent (a tile plus its halo), the one with the smallest extent; None without a prepared extent."""
    extent = previous.get("extent")
    if not extent:
        return None
    cx, cy = (extent[0]+extent[2])/2, (extent[1]+extent[3])/2
    found = [((h["extent"][2]-h["extent"][0])*(h["extent"][3]-h["extent"][1]), i) for i, h in enumerate(headers)
             if h["extent"][0] <= cx <= h["extent"][2] and h["extent"][1] <= cy <= h["extent"][3]]
    return min(found)[1] if found else None


def run(prepared_lasd, output_folder, ground, extent=None, mode="z", cell=CELL_M, label=None, chunk=CHUNK):
    """HAG copies of a prepared dataset's point files in a NEW folder; manifest.json is written last.

    status is "complete" when every written file passed binary verification and, in z or both
    mode, the core file (see core_index) was written; refused halo files are listed in refused_z. A
    refused core gives status "refused" (outputs kept for inspection), an exception "failed".

    ground(folder, extent, cell) returns a GroundSurface of the whole preparation (raster_builder()
    in ArcGIS Pro). extent, when given, selects the files to write (those it intersects); the
    ground always comes from every prepared file.
    """
    started = time.perf_counter()
    if mode not in MODES:
        raise ValueError(f"Mode must be one of {', '.join(MODES)}")
    if not math.isfinite(cell) or cell <= 0:
        raise ValueError("Cell size must be finite and positive")
    manifest_path, previous, destination, files = _check_input(prepared_lasd, output_folder)
    headers = [las_records.header(path) for path in files]
    if extent is not None:
        extent = [float(v) for v in extent]
        if len(extent) != 4 or not all(map(math.isfinite, extent)) or extent[0] >= extent[2] or extent[1] >= extent[3]:
            raise ValueError("Extent must be xmin ymin xmax ymax")
        chosen = [i for i, h in enumerate(headers) if h["extent"][0] <= extent[2] and h["extent"][2] >= extent[0]
                  and h["extent"][1] <= extent[3] and h["extent"][3] >= extent[1]]
        if not chosen:
            raise ValueError("No prepared file intersects the extent")
    else:
        chosen = list(range(len(files)))
    union = [min(h["extent"][0] for h in headers), min(h["extent"][1] for h in headers),
             max(h["extent"][2] for h in headers), max(h["extent"][3] for h in headers)]
    ground_extent = snap_out(union, cell)
    destination.mkdir(parents=True)
    manifest = destination/"manifest.json"
    state = {"status": "running", "tool": "python -m canopy hag", "label": label, "mode": mode,
             "quality_status": QUALITY, "input_preparation": str(manifest_path),
             "prepared_lasd": str(Path(prepared_lasd).resolve()), "prepared_extent": previous.get("extent"),
             "selection_extent": extent, "ground_extent": ground_extent, "cell_m": cell, "definition": DEFINITION,
             "roles": "core = the smallest file containing the centre of the prepared extent; halo = the others",
             "outputs": {"z": Z_FOLDER if mode in ("z", "both") else None,
                         "extrabytes": EB_FOLDER if mode in ("extrabytes", "both") else None},
             "runtime": {"python": platform.python_version(), "numpy": np.__version__}, "seconds": {}}
    _write_json(manifest, state)
    try:
        clock = time.perf_counter()
        sources = [digests(path) for path in files]
        sides = _side_files(prepared_lasd, files)
        state["sources"] = sources
        state["seconds"]["fingerprint_sources"] = round(time.perf_counter()-clock, 1); clock = time.perf_counter()
        surface = ground(destination/"ground", ground_extent, cell)
        missing = ~np.isfinite(surface.values)
        state["ground"] = {**surface.record, "extent": surface.extent, "cell_m": surface.cell,
                           "shape": [surface.rows, surface.cols], "nodata_cells": int(missing.sum()),
                           "z_min": float(np.nanmin(surface.values)) if (~missing).any() else None,
                           "z_max": float(np.nanmax(surface.values)) if (~missing).any() else None}
        state["seconds"]["ground"] = round(time.perf_counter()-clock, 1)
        _write_json(manifest, state)
        state["files"] = {}
        totals = {"points": 0, "uncovered": 0, "negative": 0, "written_z": [], "refused_z": [],
                  "written_extrabytes": [], "skipped_extrabytes": []}
        core = core_index(headers, previous)
        for number in chosen:
            path = files[number]
            role = None if core is None else "core" if number == core else "halo"
            row = state["files"][path.name] = {"source": sources[number], "role": role}
            totals["points"] += headers[number]["points"]
            if mode in ("z", "both"):
                clock = time.perf_counter()
                target = destination/Z_FOLDER/path.name
                target.parent.mkdir(exist_ok=True)
                z = write_z(path, target, surface, destination/"uncovered"/(path.stem+".npz"), chunk)
                if z["status"] == "written":
                    z["verification"] = verify_z(path, target, surface, chunk)
                    if not z["verification"]["all_pass"]:
                        raise RuntimeError(f"Z copy failed binary verification: {path.name}")
                    z["output"] = digests(target)
                    os.chmod(target, stat.S_IREAD)
                    totals["written_z"].append(path.name); totals["negative"] += z["negative"]
                else:
                    totals["refused_z"].append(path.name)
                totals["uncovered"] += z["uncovered"]
                z["seconds_total"] = round(time.perf_counter()-clock, 1)
                row["z"] = z
            if mode in ("extrabytes", "both"):
                clock = time.perf_counter()
                target = destination/EB_FOLDER/path.name
                target.parent.mkdir(exist_ok=True)
                eb = write_extrabytes(path, target, surface, chunk)
                if eb["status"] == "written":
                    eb["verification"] = verify_extrabytes(path, target, surface, chunk)
                    if not eb["verification"]["all_pass"]:
                        raise RuntimeError(f"Extra Bytes copy failed binary verification: {path.name}")
                    eb["output"] = digests(target)
                    os.chmod(target, stat.S_IREAD)
                    totals["written_extrabytes"].append(path.name)
                    if mode == "extrabytes":
                        totals["uncovered"] += eb["uncovered_no_data"]
                else:
                    totals["skipped_extrabytes"].append(path.name)
                eb["seconds_total"] = round(time.perf_counter()-clock, 1)
                row["extrabytes"] = eb
            _write_json(manifest, state)
        state["totals"] = totals
        state["refused_z"] = totals["refused_z"]
        cores = [name for name, row in state["files"].items() if row["role"] == "core"]
        refused_core = [name for name in cores if "z" in state["files"][name] and
                        state["files"][name]["z"]["status"] != "written"]
        state["core_z_written"] = (None if mode == "extrabytes" or not cores else not refused_core)
        clock = time.perf_counter()
        raster = surface.record.get("raster")
        if raster:
            now = digests(raster["path"])
            if now["sha256"] != raster["sha256"]:
                raise RuntimeError("Ground raster changed during the run")
            state["ground_raster_unchanged"] = True
        after = [digests(path) for path in files]
        changed = [a["path"] for a, b in zip(sources, after) if (a["sha256"], a["bytes"], a["mtime_ns"]) !=
                   (b["sha256"], b["bytes"], b["mtime_ns"])]
        changed += [row["path"] for row in sides if (Path(row["path"]).stat().st_size, Path(row["path"]).stat().st_mtime_ns)
                    != (row["bytes"], row["mtime_ns"])]
        if changed:
            raise RuntimeError("Prepared inputs changed during the HAG run: "+", ".join(changed))
        state["sources_unchanged"] = {"point_files_sha256": True, "lasd_and_lasx_size_mtime": True,
                                      "checked": len(after)+len(sides)}
        state["seconds"]["recheck"] = round(time.perf_counter()-clock, 1)
        state["seconds"]["total"] = round(time.perf_counter()-started, 1)
        state["peak_memory_gb"] = _peak_memory_gb()
        if refused_core:
            # Halo refusals are compatible with a complete dataset; a missing core copy is not.
            state["status"] = "refused"
            state["error"] = ("Core file refused in z mode (points without ground coverage): " +
                              ", ".join(f"{n} ({state['files'][n]['z']['uncovered']:,} uncovered)" for n in refused_core))
        else:
            state["status"] = "complete"
    except Exception as exc:
        state["status"] = "failed"; state["error"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        _write_json(manifest, state)
    return state


def raster_builder(prepared_lasd, epsg=None):
    """ArcGIS Pro: return ground(folder, extent, cell) building the pipeline DTM of class-2 ground.

    Reads prepared_lasd through a LAS dataset layer (the same way `canopy run` does); the raster is
    written to NEW folder/ground.tif, set read-only and fingerprinted.
    """
    import arcpy
    from . import common
    sr = arcpy.Describe(str(prepared_lasd)).spatialReference
    common.metric_reference(sr)
    if epsg is not None and sr.factoryCode != int(epsg):
        raise ValueError(f"Expected EPSG:{epsg}, found {sr.factoryCode} ({sr.name})")
    vcs = getattr(sr, "VCS", None)
    reference = {"name": sr.name, "factory_code": sr.factoryCode, "linear_unit": sr.linearUnitName,
                 "vertical": getattr(vcs, "name", None), "vertical_unit": getattr(vcs, "linearUnitName", None)}

    def build(folder, extent, cell=CELL_M):
        from .rasters import DTM_INTERPOLATION, GROUND_CLASSES
        from .run_safeguards import fingerprint
        folder = Path(folder)
        folder.mkdir(parents=True)
        tif = folder/"ground.tif"
        name = f"hag_ground_{os.getpid()}_{time.monotonic_ns()}"
        started = time.perf_counter()
        layer = arcpy.management.MakeLasDatasetLayer(str(prepared_lasd), name, class_code=GROUND_CLASSES,
                                                     withheld="EXCLUDE_WITHHELD", overlap="EXCLUDE_OVERLAP",
                                                     synthetic="EXCLUDE_SYNTHETIC")[0]
        try:
            with arcpy.EnvManager(extent=arcpy.Extent(*extent), outputCoordinateSystem=sr, snapRaster=None,
                                  pyramid="NONE"):
                arcpy.conversion.LasDatasetToRaster(layer, str(tif), "ELEVATION", DTM_INTERPOLATION, "FLOAT",
                                                    "CELLSIZE", cell, 1)
        finally:
            arcpy.management.Delete(name)
        arcpy.management.CalculateStatistics(str(tif))
        raster = arcpy.Raster(str(tif))
        e = raster.extent
        values = arcpy.RasterToNumPyArray(raster, nodata_to_value=np.nan).astype(np.float32)
        width, height, code = raster.meanCellWidth, raster.meanCellHeight, raster.spatialReference.factoryCode
        del raster
        if not (math.isclose(width, cell) and math.isclose(height, cell)):
            raise ValueError(f"Ground raster cells are {width} x {height}, not {cell}")
        actual = [e.XMin, e.YMin, e.XMax, e.YMax]
        if any(abs(a-b) > 1e-6 for a, b in zip(actual, extent)):
            raise ValueError(f"Ground raster extent {actual} differs from the requested {list(extent)}")
        os.chmod(tif, stat.S_IREAD)
        record = {"method": "LasDatasetToRaster "+DTM_INTERPOLATION, "classes": GROUND_CLASSES,
                  "excluded_flags": "withheld, overlap, synthetic", "source_lasd": str(Path(prepared_lasd).resolve()),
                  "spatial_reference": reference, "raster_spatial_reference": code, "requested_extent": list(extent),
                  "raster": fingerprint(tif), "read_only": True,
                  "build_seconds": round(time.perf_counter()-started, 1)}
        return GroundSurface(values, e.XMin, e.YMax, width, record)
    return build
