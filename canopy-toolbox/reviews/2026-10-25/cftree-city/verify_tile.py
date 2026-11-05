"""Check a completed tile's exported structure and feet attributes; no field-accuracy claim."""
import argparse
from collections import Counter
import csv
import gzip
import hashlib
import json
import math
from pathlib import Path


def verify(tile, report, measurements):
    status = json.loads((tile / 'status.json').read_text())
    if status['state'] not in {'complete', 'complete_with_rejections'}:
        raise ValueError('Tile is not complete')
    files = sorted(tile.glob('trees_*.city.json.gz'))
    assert len(files) == status['cityjson_shards']
    ids = set(); rows = []; degenerate_faces = 0; faces = 0
    for path in files:
        city = json.loads(gzip.decompress(path.read_bytes()))
        assert (city['type'], city['version']) == ('CityJSON', '2.0')
        assert city['metadata']['referenceSystem'].endswith('/6341')
        transform = city['transform']
        assert len(transform['scale']) == len(transform['translate']) == 3
        assert all(math.isfinite(v) for k in ['scale', 'translate'] for v in transform[k])
        vertices = [tuple(v[i] * transform['scale'][i] + transform['translate'][i] for i in range(3))
                    for v in city['vertices']]
        assert all(math.isfinite(x) for v in vertices for x in v)
        for ident, obj in city['CityObjects'].items():
            assert ident not in ids; ids.add(ident)
            assert obj['type'] == 'SolitaryVegetationObject' and len(obj['geometry']) == 2
            attrs = obj['attributes']
            assert attrs['tile_id'] == tile.name and attrs['source_points'] >= 50
            for metric, feet in [('crown_width_m', 'crown_width_ft'), ('trunk_DBH_m', 'modelled_trunk_diameter_ft')]:
                assert abs(attrs[metric] - attrs[feet] * .3048) < 1e-8
            for geom in obj['geometry']:
                assert (geom['type'], geom['lod']) == ('Solid', '3')
                edges = Counter()
                for shell in geom['boundaries']:
                    for face in shell:
                        assert len(face) == 1
                        ring = face[0]; assert len(ring) == 3
                        assert all(isinstance(v, int) and 0 <= v < len(vertices) for v in ring)
                        for i in range(3): edges[tuple(sorted((ring[i], ring[(i+1) % 3])))] += 1
                        a, b, c = (vertices[i] for i in ring)
                        u = [b[i] - a[i] for i in range(3)]; v = [c[i] - a[i] for i in range(3)]
                        cross = [u[1]*v[2]-u[2]*v[1], u[2]*v[0]-u[0]*v[2], u[0]*v[1]-u[1]*v[0]]
                        degenerate_faces += sum(x*x for x in cross) < 1e-18
                        faces += 1
                assert edges and all(count == 2 for count in edges.values()), (ident, 'open exported surface')
            rows.append({k: attrs[k] for k in ['gtid', 'tile_id', 'height_ft', 'crown_width_ft',
                'modelled_trunk_diameter_ft', 'source_points', 'edge_review', 'validation', 'trunk_method']})
    assert len(ids) == status['models']
    result = dict(tile=tile.name, models=len(ids), rejected=status['rejected'], shards=len(files),
        faces=faces, quantized_zero_area_faces=degenerate_faces, finite_coordinates=True,
        valid_vertex_indices=True, closed_edge_incidence=True, feet_conversion_tolerance_m=1e-8,
        boundary_review_models=sum(row['edge_review'] for row in rows),
        checks='Export structure and conversions; not full schema, solid topology, seam or field validation',
        files={p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in files})
    report.write_text(json.dumps(result, indent=2) + '\n')
    with measurements.open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)
    print(json.dumps({k: v for k, v in result.items() if k != 'files'}, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('tile', type=Path)
    parser.add_argument('report', type=Path)
    parser.add_argument('measurements', type=Path)
    args = parser.parse_args()
    verify(args.tile, args.report, args.measurements)
