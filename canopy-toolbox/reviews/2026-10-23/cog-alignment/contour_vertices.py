r"""Contour vertices from the hosted contours layer, for the COG alignment test (October 23, 2026).

    python reviews/2026-10-23/cog-alignment/contour_vertices.py OUT_JSON [--proxy URL] [--per-tile 80]

ArcGIS Pro Python (as run; it imports no arcpy, so the repo .venv with numpy should also do), with serve.py running (the layer is private; the proxy adds the token). For the level 16 tile holding
each check cell in web/cells.json, the tile is fetched from the hosted Vector Tile Service through the proxy and decoded
with the vector tile datum check's reader; a seeded sample of the vertices inside it is written in Web Mercator. The tiles
carry no attributes, but every line is a 2 m contour, so the terrain under a vertex should be a multiple of 2 m.
"""
import argparse
import gzip
import json
from pathlib import Path
import sys
import urllib.request

import numpy as np

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[2]/"2026-10-22"/"hosting"/"vector-tiles"))
from datum_check import ORIGIN, WORLD, tile_vertices  # noqa: E402

LEVEL = 16  # the package's deepest level here; clients overzoom past it


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("out", type=Path)
    p.add_argument("--proxy", default="http://127.0.0.1:8793/proxy/contours/VectorTileServer")
    p.add_argument("--per-tile", type=int, default=80)
    args = p.parse_args(argv)
    cells = json.loads((HERE.parent/"web"/"cells.json").read_text())["cells"]
    size = WORLD/2**LEVEL
    rng = np.random.default_rng(20261023)
    tiles, vertices = [], []
    for i, c in enumerate(cells):
        x, y = c["itrf08"]
        row, col = int((-ORIGIN-y)//size), int((x-ORIGIN)//size)
        url = f"{args.proxy}/tile/{LEVEL}/{row}/{col}.pbf"
        with urllib.request.urlopen(url, timeout=60) as r:
            raw = r.read()
        tile = gzip.decompress(raw) if raw[:2] == b"\x1f\x8b" else raw
        pts = tile_vertices(tile, row, col, size)
        pick = pts[rng.choice(len(pts), size=min(args.per_tile, len(pts)), replace=False)]
        tiles.append({"cell": i, "level": LEVEL, "row": row, "col": col, "bytes": len(raw), "vertices": len(pts)})
        vertices += [{"cell": i, "x": float(px), "y": float(py)} for px, py in pick]
    args.out.write_text(json.dumps({
        "source": args.proxy, "note": "vertices of the hosted 2 m contours, Web Mercator, decoded from the tiles",
        "tiles": tiles, "vertices": vertices}, indent=1))
    print(f"{len(vertices)} vertices from {len(tiles)} tiles")


if __name__ == "__main__":
    main()
