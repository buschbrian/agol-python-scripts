"""Independently reconcile the finished CSV, feature class and count manifest."""
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import sys

import arcpy
import numpy as np
import shapely

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from canopy import common


def main(root):
    root = Path(root)
    state = json.loads((root / 'count.json').read_text())
    assert state['status'] == 'complete'
    inputs = json.loads((root / 'inputs.json').read_text())
    city = shapely.union_all([shapely.from_wkb(bytes(wkb)) for wkb, in
                             arcpy.da.SearchCursor(inputs['boundary'], ['SHAPE@WKB'])])
    shapely.prepare(city)
    totals, groups, csv_rows = Counter(), Counter(), {}
    with (root / 'city-treetops.csv').open(newline='', encoding='utf-8') as handle:
        for row in csv.DictReader(handle):
            tree_id = row['TREE_ID']
            assert tree_id not in csv_rows, f'Duplicate ID: {tree_id}'
            x, y, h = (float(row[key]) for key in ['X', 'Y', 'HEIGHT_M'])
            assert np.isfinite([x, y, h]).all() and h >= 2
            assert shapely.intersects_xy(city, x, y), 'Detection outside boundary'
            matches = int(row['PARCEL_MATCHES'])
            assert (matches == 0) == (row['OWNERSHIP'] == 'NO_PARCEL')
            totals[row['OWNERSHIP']] += 1
            if row['OWNERSHIP'] == 'PUBLIC_GOVERNMENT':
                groups[row['OWNER_GROUP']] += 1
            csv_rows[tree_id] = (x, y, h, row['OWNERSHIP'], row['OWNER_GROUP'], matches)
    assert dict(totals) == state['ownership_totals']
    assert dict(groups) == state['public_breakdown']
    assert sum(totals.values()) == state['city_treetops']
    fields = ['TREE_ID', 'SHAPE@XY', 'HEIGHT_M', 'OWNERSHIP', 'OWNER_GROUP',
              'PARCEL_MATCHES', 'REVIEW_STATUS', 'MIN_HEIGHT', 'SMOOTH', 'SOURCE_ID']
    seen = set()
    for tree_id, xy, h, category, group, matches, review, minimum, smooth, source in arcpy.da.SearchCursor(
            state['outputs']['treetops'], fields):
        assert tree_id not in seen
        seen.add(tree_id)
        x, y, csv_h, csv_category, csv_group, csv_matches = csv_rows[tree_id]
        assert np.allclose(xy, [x, y], rtol=0, atol=.001)
        assert (h, category, group or '', matches) == (csv_h, csv_category, csv_group, csv_matches)
        assert (review, minimum, smooth, source) == ('UNVERIFIED', 2, 1, state['source_id'])
    assert len(seen) == len(csv_rows)
    prep = json.loads((root / 'prepared/preparation.json').read_text())
    assert prep['status'] == 'complete'
    for tile, before in prep['before'].items():
        after = prep['after'][tile]
        for code in ('2', '7', '9', '17', '18', '20'):
            assert before['classes'].get(code, 0) == after['classes'].get(code, 0), (tile, code)
    for row in prep['sources'] + state['input_files']:
        stat = Path(row['path']).stat()
        assert (stat.st_size, stat.st_mtime_ns) == (row['bytes'], row['mtime_ns'])
    recovery = prep['height_recovery']
    assert len(recovery['height']) == len(state['input_files']) == 61
    assert all(row['protected_sha256_before'] == row['protected_sha256_after']
               for row in recovery['height'].values())
    assert len(state['tiles']) == state['raster_tiles_planned']
    obs = state['observation']
    assert obs['city_grid_cells'] == obs['observed_cells'] + obs['missing_cells']
    result = {'status': 'passed', 'unique_treetops': len(seen), 'ownership_totals': dict(totals),
              'public_breakdown': dict(groups), 'all_points_inside_city_and_ge_2m': True,
              'csv_and_feature_class_match': True, 'all_unverified': True,
              'source_and_working_fingerprints_unchanged': True,
              'protected_height_recovery_hashes_match': 61,
              'delivered_ground_and_noise_counts_unchanged': True,
              'all_raster_cores_complete': len(state['tiles']),
              'observation_counts_conserve': True,
              'csv_sha256': hashlib.sha256((root / 'city-treetops.csv').read_bytes()).hexdigest()}
    common.write_json(root / 'verification.json', result)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main(sys.argv[1])
