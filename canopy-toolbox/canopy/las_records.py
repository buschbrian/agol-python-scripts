"""Uncompressed LAS 1.1-1.4 layouts and masks. No ArcPy.

Layout: ASPRS LAS 1.4 specification; opaque Extra Bytes retain their record stride.
"""
from pathlib import Path
import struct
import numpy as np

def header(path):
    path = Path(path)
    with path.open("rb") as handle:
        data = handle.read(375)
        if data[:4] != b"LASF":
            raise ValueError(f"Not a LAS file: {path}")
        if len(data) < 227:
            raise ValueError("Truncated LAS header")
        major, minor = data[24], data[25]
        minimum = {1:227, 2:227, 3:235, 4:375}.get(minor)
        if major != 1 or minimum is None:
            raise ValueError("Supported LAS versions are 1.1 through 1.4")
        header_size = struct.unpack_from('<H', data, 94)[0]
        if len(data) < minimum or header_size < minimum:
            raise ValueError("Truncated LAS version header")
        fmt = data[104] & 63
        if data[104] & 128:
            raise ValueError("Compressed LAS needs extraction before direct point inspection")
        count = struct.unpack_from("<I", data, 107)[0]
        if (major, minor) >= (1, 4):
            count = struct.unpack_from("<Q", data, 247)[0] or count
        bounds = struct.unpack_from("<6d", data, 179)
        result = {
            "path": str(path.resolve()), "bytes": path.stat().st_size, "mtime_ns": path.stat().st_mtime_ns,
            "version": f"{major}.{minor}", "format": fmt, "points": count,
            "offset": struct.unpack_from("<I", data, 96)[0],
            "record_length": struct.unpack_from("<H", data, 105)[0],
            "extent": [bounds[1], bounds[3], bounds[0], bounds[2]],
            "z_min": bounds[5], "z_max": bounds[4],
            "file_creation_year": struct.unpack_from("<H", data, 92)[0],
            "file_creation_day": struct.unpack_from("<H", data, 90)[0],
        }
        lengths = (20,28,26,34,57,63,30,36,38,59,67)
        if fmt > 10 or (fmt >= 6 and minor < 4):
            raise ValueError("Unsupported LAS point format for version")
        if result['record_length'] < lengths[fmt]:
            raise ValueError("LAS point record is shorter than its format")
        if result['offset'] < header_size or result['offset']+count*result['record_length'] > result['bytes']:
            raise ValueError("Truncated LAS point records or invalid point offset")
        scale=np.array(struct.unpack_from('<3d',data,131))
        offset=np.array(struct.unpack_from('<3d',data,155))
        if not np.isfinite(scale).all() or not (scale > 0).all() or not np.isfinite(offset).all():
            raise ValueError("LAS scales and offsets must be finite; scales must be positive")
        # File creation date is not necessarily the flight date.
        handle.seek(struct.unpack_from("<H", data, 94)[0])
        for _ in range(struct.unpack_from("<I", data, 100)[0]):
            vlr = handle.read(54)
            if len(vlr) != 54 or handle.tell() > result['offset']:
                raise ValueError("Truncated LAS variable-length record")
            size = struct.unpack_from("<H", vlr, 20)[0]
            if handle.tell()+size > result['offset']:
                raise ValueError("LAS variable-length record overlaps points")
            content = handle.read(size)
            if struct.unpack_from("<H", vlr, 18)[0] == 2112:
                result["wkt"] = content.decode("utf-8", "replace").rstrip("\0")
    return result


def records(path, mode='r'):
    """Structured mapped records, scale, offset, modern-layout flag and header."""
    info=header(path)
    with open(path,'rb') as handle:
        head=handle.read(227)
    scale=np.array(struct.unpack_from('<3d',head,131))
    offset=np.array(struct.unpack_from('<3d',head,155))
    modern=info['format'] >= 6
    dtype=np.dtype({'names':['x','y','z','returns','flags','classification'],
                    'formats':['<i4','<i4','<i4','u1','u1','u1'],
                    'offsets':[0,4,8,14,15,16 if modern else 15],
                    'itemsize':info['record_length']})
    points=(np.memmap(path,dtype=dtype,offset=info['offset'],shape=(info['points'],),mode=mode)
            if info['points'] else np.empty(0,dtype=dtype))
    return points,scale,offset,modern,info


def return_masks(return_byte, modern):
    number=return_byte & (15 if modern else 7)
    count=(return_byte >> 4) if modern else ((return_byte >> 3) & 7)
    return number == 1, (number == 1) & (count == 1)


def clean_flags(flag_byte, modern):
    return (flag_byte & (13 if modern else 160)) == 0


def decode(block, scale, offset, modern):
    classes=block['classification'] if modern else block['classification'] & 31
    first,_=return_masks(block['returns'],modern)
    xyz=[block[axis]*scale[i]+offset[i] for i,axis in enumerate('xyz')]
    return *xyz,classes,first,~clean_flags(block['flags'],modern)


def class_counts(path, sample=False):
    info = header(path)
    counts = np.zeros(256, dtype=np.int64)
    flags = {"withheld": 0, "overlap": 0, "synthetic": 0}
    returns = np.zeros(16, dtype=np.int64)
    with open(path, "rb") as handle:
        if sample:
            blocks = [(int(start), min(512, info["points"])) for start in
                      np.linspace(0, max(0, info["points"]-512), 16, dtype=np.int64)]
        else:
            blocks = ((start, min(1_000_000, info["points"]-start)) for start in
                      range(0, info["points"], 1_000_000))
        for start, count in blocks:
            handle.seek(info["offset"]+start*info["record_length"])
            data = np.frombuffer(handle.read(count*info["record_length"]), dtype=np.uint8)
            if data.size != count*info["record_length"]:
                raise ValueError(f"Truncated LAS point records: {path}")
            data = data.reshape(-1, info["record_length"])
            modern = info["format"] >= 6
            classes = data[:, 16] if modern else data[:, 15] & 31
            counts += np.bincount(classes, minlength=256)
            returns += np.bincount(data[:, 14] & (15 if modern else 7), minlength=16)
            flag = data[:, 15]
            flags["withheld"] += int(np.count_nonzero(flag & (4 if modern else 128)))
            flags["synthetic"] += int(np.count_nonzero(flag & (1 if modern else 32)))
            flags["overlap"] += int(np.count_nonzero(flag & 8)) if modern else 0
    return {
        "mode": "sample" if sample else "complete", "evaluated_points": int(counts.sum()),
        "classes": {str(i): int(n) for i, n in enumerate(counts) if n},
        "returns": {str(i): int(n) for i, n in enumerate(returns) if n}, "flags": flags,
    }


