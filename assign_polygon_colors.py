"""Assign non-adjacent colors to polygons from a neighbor table.

This script is designed for ArcGIS Pro / ArcPy workflows, but the core coloring
logic also works as a pure-Python utility for local development and testing.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from typing import Dict, Iterable, List, Mapping, MutableMapping, Set, Tuple

try:
    import arcpy  # type: ignore
except ImportError:  # pragma: no cover - optional dependency in non-ArcGIS environments
    arcpy = None


def build_adjacency(neighbor_rows: Iterable[Tuple[int, int]]) -> Dict[int, Set[int]]:
    """Create an adjacency map from a neighbor-table-style row iterator."""
    adjacency: MutableMapping[int, Set[int]] = defaultdict(set)
    for src, nbr in neighbor_rows:
        if src == nbr:
            continue
        adjacency[src].add(nbr)
        adjacency[nbr].add(src)
    return {polygon: set(neighbors) for polygon, neighbors in adjacency.items()}


def assign_polygon_colors(
    adjacency: Mapping[int, Iterable[int]],
    max_colors: int = 9,
) -> Dict[int, int]:
    """Return positive integer color IDs, preserving the original SHORT field contract."""
    if not 1 <= max_colors <= 32767:
        raise ValueError("max_colors must be between 1 and 32767 for a SHORT field.")
    normalized_adjacency = {polygon: set(neighbors) for polygon, neighbors in adjacency.items()}
    available_colors = range(1, max_colors + 1)

    ordered_polygons = sorted(normalized_adjacency, key=lambda polygon: len(normalized_adjacency[polygon]), reverse=True)
    colors: Dict[int, int] = {}

    for polygon in ordered_polygons:
        used_colors = {colors[nbr] for nbr in normalized_adjacency[polygon] if nbr in colors}
        for color in available_colors:
            if color not in used_colors:
                colors[polygon] = color
                break
        else:
            raise ValueError(
                f"Unable to assign a color with {max_colors} color IDs. "
                "Increase --max-colors."
            )

    return colors


def read_neighbor_rows(neighbor_table: str) -> List[Tuple[int, int]]:
    """Read neighbor rows from an ArcGIS table when ArcPy is available."""
    if arcpy is None:
        raise RuntimeError("ArcPy is required to read from a neighbor table.")

    with arcpy.da.SearchCursor(neighbor_table, ["src_OBJECTID", "nbr_OBJECTID"]) as cursor:
        return [(int(src), int(nbr)) for src, nbr in cursor]


def write_colors_to_layer(
    polygon_layer: str,
    colors: Mapping[int, int],
    color_field: str,
    id_field: str = "OID@",
) -> None:
    """Write the assigned color values to an ArcGIS feature class or table."""
    if arcpy is None:
        raise RuntimeError("ArcPy is required to write colors to the polygon layer.")

    existing_fields = {field.name.casefold(): field for field in arcpy.ListFields(polygon_layer)}
    existing = existing_fields.get(color_field.casefold())
    if existing is not None:
        if existing.type not in {"SmallInteger", "Integer", "BigInteger"}:
            raise ValueError(f"{color_field} must be an integer field; found {existing.type}.")
    else:
        arcpy.AddField_management(polygon_layer, color_field, "SHORT")

    with arcpy.da.UpdateCursor(polygon_layer, [id_field, color_field]) as cursor:
        for oid, _ in cursor:
            if int(oid) not in colors:
                raise ValueError(f"Missing color assignment for polygon {oid}.")
            cursor.updateRow([oid, colors[int(oid)]])


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments for the script."""
    parser = argparse.ArgumentParser(description="Assign integer color IDs to polygon neighbors")
    parser.add_argument("polygon_layer", help="Path to the polygon feature class or layer")
    parser.add_argument("neighbor_table", help="Path to the polygon neighbor table")
    parser.add_argument("--color-field", default="Color_ID", help="Integer field to store color IDs (default: Color_ID)")
    parser.add_argument("--id-field", default="OID@", help="ID field in the polygon layer (default: OID@, the ObjectID field whatever its name)")
    parser.add_argument("--max-colors", type=int, default=9, help="Maximum number of integer color IDs (1–32767; default: 9)")
    parser.add_argument("--dry-run", action="store_true", help="Build the color map without writing to the layer")
    return parser.parse_args()


def main() -> None:
    """Run the CLI workflow."""
    args = parse_args()

    if arcpy is None:
        raise RuntimeError("ArcPy is required to run this workflow. Install ArcGIS Pro or use the core functions directly.")

    neighbor_rows = read_neighbor_rows(args.neighbor_table)
    adjacency = build_adjacency(neighbor_rows)
    # Include isolated polygons before coloring so dry-run and writes agree.
    with arcpy.da.SearchCursor(args.polygon_layer, [args.id_field]) as cursor:
        for (polygon_id,) in cursor:
            adjacency.setdefault(int(polygon_id), set())
    colors = assign_polygon_colors(adjacency, max_colors=args.max_colors)

    if args.dry_run:
        print("Dry run complete. Color assignments:")
        for polygon_id, color in sorted(colors.items()):
            print(f"{polygon_id}: {color}")
        return

    write_colors_to_layer(args.polygon_layer, colors, args.color_field, args.id_field)
    print("Integer color ID assignment complete.")


if __name__ == "__main__":
    main()
