
import arcpy
from collections import defaultdict

# Input paths
polygon_layer = r'path_to_your_polygon_layer'
neighbor_table = r'path_to_your_polygon_neighbors_table'

# Step 1: Create adjacency dictionary
adjacency = defaultdict(set)

with arcpy.da.SearchCursor(neighbor_table, ['src_OBJECTID', 'nbr_OBJECTID']) as cursor:
    for src, nbr in cursor:
        if src == nbr:
            continue
        adjacency[src].add(nbr)
        adjacency[nbr].add(src)

# Step 2: Assign colors ensuring no neighbors share the same color
colors = {}
available_colors = range(1, 10)  # Adjust number of colors as needed

sorted_polygons = sorted(adjacency, key=lambda x: len(adjacency[x]), reverse=True)

for polygon in sorted_polygons:
    used_colors = set(colors[nbr] for nbr in adjacency[polygon] if nbr in colors)
    for color in available_colors:
        if color not in used_colors:
            colors[polygon] = color
            break
    else:
        raise RuntimeError(f'No available color for polygon {polygon}; increase the palette before editing features')

# Step 3: Add and populate a color field
color_field = 'Color_ID'

existing_fields = [f.name for f in arcpy.ListFields(polygon_layer)]
if color_field not in existing_fields:
    arcpy.AddField_management(polygon_layer, color_field, 'SHORT')

with arcpy.da.UpdateCursor(polygon_layer, ['OID@', color_field]) as cursor:
    for oid, _ in cursor:
        cursor.updateRow([oid, colors.get(oid, 1)])  # Default to color 1 if missing

print('Color assignment complete!')
