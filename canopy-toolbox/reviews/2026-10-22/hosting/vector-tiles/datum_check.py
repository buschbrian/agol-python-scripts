r"""Which datum transformation the vector tile packages carry (October 23, 2026), read from the tiles themselves.

    python reviews/2026-10-22/hosting/vector-tiles/datum_check.py OUT_JSON

ArcGIS Pro Python (PYTHONNOUSERSITE=1). Read-only. The packages' maps record WGS_1984_(ITRF08)_To_NAD_1983_2011 as their
datum transformation, but Manage Tile Cache was found to ignore transformation settings (hosting/tiles), so the map setting
alone does not prove what Create Vector Tile Package did. For the four tiles nearest the middle of the city at each
package's deepest level, every vertex in the tile is turned into Web Mercator and matched to the nearest source vertex
projected two ways: with the transformation and with none. The transformation moves features by about 1.6 m in Web
Mercator (1.2 m on the ground); a tile unit is about 15 cm at level 16 and 7.5 cm at level 17, so the right choice gives
distances of a few centimetres and the wrong one up to about 1.6 m (less for dense polygon vertices on the 0.5 m grid,
where a shifted vertex often lands near another one; the treetops show the shift cleanly).
"""
import json
from pathlib import Path
import sys

import numpy as np

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[4]))
sys.path.insert(0, str(HERE.parent))
from canopy.lidar_root import lidar_root  # noqa: E402
from build_vector_tiles import _commands, _tiles, _varints  # noqa: E402

RUNS = lidar_root()/"2023-salt-lake-valley"/"runs"
TRANSFORM = "WGS_1984_(ITRF08)_To_NAD_1983_2011"
PACKAGES = {
    "slope_classes": (RUNS/"slope-tiles-20261022"/"millcreek_slope_classes.vtpk",
                      RUNS/"slope-tiles-20261022"/"slope_tiles.gdb"/"slope_classes"),
    "treetops": (RUNS/"vector-tiles-20261022"/"millcreek_treetops.vtpk",
                 RUNS/"millcreek-products-20261022"/"tree-count.gdb"/"city_treetops"),
    "crowns": (RUNS/"vector-tiles-20261022"/"millcreek_crowns.vtpk",
               RUNS/"millcreek-products-20261022"/"crowns.gdb"/"crowns"),
    "contours": (RUNS/"vector-tiles-20261022"/"millcreek_contours.vtpk",
                 RUNS/"terrain-city-20261022"/"terrain.gdb"/"contours"),
}
WORLD = 40075016.68557849  # level 0 is one 512-pixel tile across the Web Mercator world
ORIGIN = -WORLD/2
# The middle of the city (the vector tiles' pilot window), in Web Mercator.
CENTRE = (-12451000.0, 4966300.0)


def tile_vertices(tile, row, col, size):
    """Every vertex inside the tile's own extent, in Web Mercator."""
    out = []
    for field, _, layer in _varints(tile):
        if field != 3:
            continue
        extent, geoms = 4096, []
        for f, _, v in _varints(layer):
            if f == 5:
                extent = v
            elif f == 2:
                geoms.extend(g for gf, _, g in _varints(v) if gf == 4)
        for g in geoms:
            c, i, x, y = _commands(g), 0, 0, 0
            while i < len(c):
                cmd, count = c[i] & 7, c[i] >> 3
                i += 1
                if cmd == 7:
                    continue
                for _ in range(count):
                    dx, dy = c[i], c[i+1]
                    x += (dx >> 1) ^ -(dx & 1)
                    y += (dy >> 1) ^ -(dy & 1)
                    i += 2
                    if 0 <= x <= extent and 0 <= y <= extent:
                        out.append((ORIGIN + (col + x/extent)*size, -ORIGIN - (row + y/extent)*size))
    return np.array(out)


def source_vertices(arcpy, fc, bounds_merc):
    """Source vertices inside the tiles (plus 5 m), projected to Web Mercator with the transformation and with none."""
    merc, utm = arcpy.SpatialReference(3857), arcpy.SpatialReference(6341)
    x0, y0, x1, y1 = bounds_merc
    box = arcpy.Polygon(arcpy.Array([arcpy.Point(x0 - 5, y0 - 5), arcpy.Point(x0 - 5, y1 + 5),
                                     arcpy.Point(x1 + 5, y1 + 5), arcpy.Point(x1 + 5, y0 - 5)]), merc)
    box_utm = box.projectAs(utm, TRANSFORM)
    arcpy.env.geographicTransformations = None
    out = {}
    for name, transformation in (("transformed", TRANSFORM), ("untransformed", None)):
        # Exploded to vertices and projected by the cursor itself; the spatial filter returns whole polygons (the
        # under-10% slope class spans the city), so vertices are kept only inside the box.
        with arcpy.da.SearchCursor(str(fc), ["SHAPE@XY"], spatial_reference=merc, explode_to_points=True,
                                   datum_transformation=transformation, spatial_filter=box_utm) as cursor:
            xy = np.array([row[0] for row in cursor], float)
        keep = (xy[:, 0] >= x0 - 5) & (xy[:, 0] <= x1 + 5) & (xy[:, 1] >= y0 - 5) & (xy[:, 1] <= y1 + 5)
        out[name] = xy[keep]
    return out


def check(arcpy, vtpk, fc, n_tiles=4):
    """The n tiles nearest the centre at the package's deepest level (indexed packages stop shallower in sparse areas)."""
    from scipy.spatial import cKDTree
    tiles = [(lvl, r, c, t) for lvl, r, c, t in _tiles(vtpk)]
    level = max(lvl for lvl, _, _, _ in tiles)
    size = WORLD/2**level
    crow, ccol = (-ORIGIN - CENTRE[1])/size, (CENTRE[0] - ORIGIN)/size
    found = sorted(((r, c, t) for lvl, r, c, t in tiles if lvl == level),
                   key=lambda x: (x[0] + 0.5 - crow)**2 + (x[1] + 0.5 - ccol)**2)[:n_tiles]
    verts = np.vstack([tile_vertices(t, r, c, size) for r, c, t in found])
    rows, cols = [r for r, _, _ in found], [c for _, c, _ in found]
    bounds = (ORIGIN + min(cols)*size, -ORIGIN - (max(rows) + 1)*size, ORIGIN + (max(cols) + 1)*size,
              -ORIGIN - min(rows)*size)
    source = source_vertices(arcpy, fc, bounds)
    result = {"tiles": [[level, r, c] for r, c in zip(rows, cols)], "tile_vertices": len(verts),
              "source_vertices": len(source["transformed"])}
    for name, pts in source.items():
        d, _ = cKDTree(pts).query(verts)
        result[name] = {"median_m": round(float(np.median(d)), 3), "p90_m": round(float(np.percentile(d, 90)), 3)}
    result["carries"] = (TRANSFORM if result["transformed"]["median_m"] < result["untransformed"]["median_m"]
                         else "no transformation")
    return result


def main():
    import arcpy
    record = {"schema": "vector-tiles-datum/1", "tiles": "4 nearest the city centre at the deepest level", "transformation_tested": TRANSFORM, "packages": {}}
    for name, (vtpk, fc) in PACKAGES.items():
        record["packages"][name] = check(arcpy, vtpk, fc)
        print(name, json.dumps(record["packages"][name]), flush=True)
    Path(sys.argv[1]).write_text(json.dumps(record, indent=1) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
