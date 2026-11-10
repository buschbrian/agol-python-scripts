r"""Split a multi-object OBJ (cjio's export) into one OBJ file per object (October 24, 2026).

    python reviews/2026-10-23/lod2-check/split_obj.py IN.obj OUT_DIR

Plain Python. Each `o <id>` block becomes OUT_DIR\<id>.obj holding only the vertices that object's faces use (renumbered from
1), with coordinates copied as written. Import 3D Files then makes one multipatch per file, named by the file.
"""
from pathlib import Path
import sys


def split(src, out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)
    vertices, objects, current = [], {}, None
    for line in Path(src).read_text(encoding="utf-8").splitlines():
        if line.startswith("v "):
            vertices.append(line)
        elif line.startswith("o "):
            current = line[2:].strip()
            objects[current] = []
        elif line.startswith("f ") and current is not None:
            objects[current].append([int(t.split("/")[0]) for t in line.split()[1:]])
    for name, faces in objects.items():
        used = sorted({i for f in faces for i in f})
        remap = {old: new for new, old in enumerate(used, 1)}
        lines = [f"o {name}"] + [vertices[i-1] for i in used] + \
                ["f " + " ".join(str(remap[i]) for i in f) for f in faces]
        (out/f"{name}.obj").write_text("\n".join(lines)+"\n", encoding="utf-8")
    return {"objects": len(objects), "vertices": len(vertices), "faces": sum(len(f) for f in objects.values())}


if __name__ == "__main__":
    print(split(sys.argv[1], sys.argv[2]))
