"""Export a feet-first companion table from the released building feature class; never edits source data."""
import argparse
from collections import Counter
import csv
import hashlib
import json
import math
from pathlib import Path

METERS_PER_FOOT = 0.3048
IDENTITY = ['FP_ID', 'SOURCE_ID', 'PARCEL_ID', 'LEVEL', 'FALLBACK_REASON', 'HEIGHT_STATUS', 'ROOF_COV_PCT']
LENGTHS = ['HEIGHT_P50_M', 'HEIGHT_P95_M', 'RIDGE_HT_M', 'EAVE_HT_M', 'BLDG_HT_M',
           'ROOF_Z50_M', 'GROUND_Z50_M']
AREAS = ['FOOTPRINT_M2', 'ROOF_PLAN_M2', 'ROOF_AREA_M2', 'FLAT_AREA_M2',
         'SOUTH_AREA_M2', 'EAST_AREA_M2', 'WEST_AREA_M2', 'NORTH_AREA_M2']
OTHER = ['ROOF_PLANES', 'ROOF_SLOPE_MEAN', 'ROOF_SLOPE_MAIN', 'ROOF_AZIMUTH_MAIN']
FIELDS = IDENTITY + LENGTHS + AREAS + OTHER


def convert(value, dimension):
    if value is None:
        return None
    if not math.isfinite(value):
        raise ValueError('Non-finite source measurement')
    return value / METERS_PER_FOOT ** dimension


def column(field):
    return field[:-3] + '_SQFT' if field in AREAS else field[:-2] + '_FT' if field in LENGTHS else field


def export(source, output):
    import arcpy
    rows = list(arcpy.da.SearchCursor(source, FIELDS))
    rows.sort(key=lambda row: row[0])
    ids = [row[0] for row in rows]
    if len(ids) != 21561 or len(set(ids)) != 21561 or sum(ids) != 237493394:
        raise ValueError('Source does not match the released hybrid')
    levels = Counter(row[FIELDS.index('LEVEL')] for row in rows)
    null_roofs = sum(row[FIELDS.index('ROOF_AREA_M2')] is None for row in rows)
    if null_roofs != 831:
        raise ValueError('Unexpected missing roof measurement count')
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('w', newline='', encoding='utf-8') as stream:
        writer = csv.writer(stream)
        writer.writerow([column(field) for field in FIELDS])
        for row in rows:
            writer.writerow([round(convert(v, 2 if f in AREAS else 1), 6)
                             if v is not None and f in LENGTHS + AREAS else v
                             for f, v in zip(FIELDS, row)])
    with output.open(newline='', encoding='utf-8') as stream:
        back = list(csv.DictReader(stream))
    for row, exported in zip(rows, back):
        for f, value in zip(FIELDS, row):
            got = exported[column(f)]
            if value is None:
                assert got == '', (f, got)
            elif f in LENGTHS + AREAS:
                assert math.isclose(float(got) * METERS_PER_FOOT ** (2 if f in AREAS else 1),
                                    value, rel_tol=0, abs_tol=0.000001), (row[0], f)
    audit = dict(rows=len(rows), unique_fp_ids=len(set(ids)), fp_id_sum=sum(ids), model_counts=dict(levels),
                 blank_roof_measurements=null_roofs, converted_columns={f: column(f) for f in LENGTHS + AREAS},
                 meters_per_international_foot=METERS_PER_FOOT, every_value_roundtrip_checked=True,
                 sha256=hashlib.sha256(output.read_bytes()).hexdigest(), bytes=output.stat().st_size,
                 units_note='FT is international feet; SQFT is square feet. Blank is unavailable, not zero. '
                            'Z50 fields are elevations; other height fields are above ground. Angles remain degrees. '
                            'Source metric coordinate geometry is unchanged; this file has no geometry.')
    output.with_suffix('.audit.json').write_text(json.dumps(audit, indent=2) + '\n')
    print(json.dumps(audit, indent=2))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('source')
    p.add_argument('output', type=Path)
    args = p.parse_args()
    export(args.source, args.output)
