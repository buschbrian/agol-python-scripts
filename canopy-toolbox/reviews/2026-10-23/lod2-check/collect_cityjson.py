r"""Collect roofer's CityJSONSeq into one CityJSON file (October 24, 2026).

    python reviews/2026-10-23/lod2-check/collect_cityjson.py ROOFER_OUTPUT_DIR OUT.city.json

Plain Python (standard library only). Read-only on the input. Does what `cjseq collect` does: the first line of each
*.city.jsonl is the CityJSON header (version, transform, metadata); every following line is a CityJSONFeature with its own
vertex list, so its vertex indices are shifted by the number of vertices already collected. All features share the header's
transform (checked), so the integer vertices are copied as they are.
"""
import json
from pathlib import Path
import sys


def collect(folder, out):
    files = sorted(Path(folder).glob("*.city.jsonl"))
    if not files:
        raise SystemExit(f"no *.city.jsonl in {folder}")
    head = None
    objects, vertices = {}, []
    for path in files:
        lines = path.read_text(encoding="utf-8").splitlines()
        h = json.loads(lines[0])
        if head is None:
            head = h
        elif h["transform"] != head["transform"]:
            raise ValueError(f"{path.name}: another transform than the first file")
        for line in lines[1:]:
            feature = json.loads(line)
            shift = len(vertices)
            vertices.extend(feature["vertices"])
            for key, obj in feature["CityObjects"].items():
                if key in objects:
                    raise ValueError(f"duplicate CityObject id {key}")
                for geometry in obj.get("geometry", []):
                    geometry["boundaries"] = _shift(geometry["boundaries"], shift)
                objects[key] = obj
    city = {"type": "CityJSON", "version": head["version"], "transform": head["transform"],
            "metadata": head.get("metadata", {}), "CityObjects": objects, "vertices": vertices}
    Path(out).write_text(json.dumps(city), encoding="utf-8")
    return {"files": len(files), "city_objects": len(objects), "vertices": len(vertices)}


def _shift(boundaries, shift):
    if isinstance(boundaries, list):
        return [_shift(b, shift) for b in boundaries] if boundaries and isinstance(boundaries[0], list) else \
            [i+shift for i in boundaries]
    return boundaries


if __name__ == "__main__":
    print(json.dumps(collect(sys.argv[1], sys.argv[2])))
