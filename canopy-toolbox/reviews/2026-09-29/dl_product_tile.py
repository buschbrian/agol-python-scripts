"""Full-tile PRODUCT runs on the baseline run's grid, one per conflict policy.

For 12TVL2804: builds product copies (dl_product.assemble) of the core file from the
September 29 verified tree-full/building-abs outputs and of the seven halo files from
the September 30 verified halo rows, or (--halos baseline) exact copies of the
baseline halo files. Then builds a LAS dataset with statistics and runs
`python -m canopy run` with the baseline run's parameters read from its run.json,
so the output CHM grid equals the baseline grid and the validation harness can
score it. Run with ArcGIS Pro's default Python and PYTHONNOUSERSITE=1:

  python dl_product_tile.py --policy tree-wins building-wins conflict-class [--halos inferred|baseline]

Only `source_id` differs from the baseline parameters (it names the input points
and seeds TREE_IDs; the harness matches non-baseline candidates by location), plus
`classified_background_zero`, which the baseline did not use. Every product file
is new; baseline and raw outputs are hashed before and after.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

PILOT = Path(r"H:\lidar\2023-salt-lake-valley\runs\pilot-2026-09-29")
E29 = PILOT / "deep-learning" / "experiments-20260929"
E30 = PILOT / "deep-learning" / "experiments-20260930"
TOOLBOX = Path(__file__).resolve().parents[2]
PRO_PYTHON = r"C:\Program Files\ArcGIS\Pro\bin\Python\envs\arcgispro-py3\python.exe"
TILE = "12TVL2804"
CORE_ROWS = {"tree": (E29 / "tree-full" / "work" / "run-tree.json", E29 / "tree-full" / "work" / "compare-tree-full.json"),
             "building": (E29 / "building-abs" / "work" / "run-building.json",
                          E29 / "building-abs" / "work" / "compare-building-abs.json")}
HALO_ROWS = {"tree": E30 / f"{TILE}-halo-tree", "building": E30 / f"{TILE}-halo-building"}
# Keys of the baseline run.json that must match; source_id and classified_background_zero are declared differences.
MATCHED = ("extent", "tile_size", "overlap", "cell_size", "bands", "smoothing", "min_crown_area", "z_unit",
           "building_clearance")


def md5(path):
    digest = hashlib.md5()
    with open(path, 'rb') as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def baseline_parameters(run_json):
    state = json.loads(Path(run_json).read_text(encoding='utf-8'))
    if state.get('status') != 'complete':
        raise ValueError(f"Baseline run is not complete: {run_json}")
    return state['parameters']


def run_arguments(parameters, lasd, output, source_files, background_zero):
    """`canopy run` arguments reproducing the baseline parameters (source_id excepted)."""
    args = ["run", str(lasd), str(output), "--extent", *[repr(float(v)) for v in parameters['extent']],
            "--tile-size", repr(parameters['tile_size']), "--overlap", repr(float(parameters['overlap'])),
            "--cell-size", repr(float(parameters['cell_size'])), "--bands", parameters['bands'],
            "--smooth", str(int(parameters['smoothing'])), "--min-crown-area", repr(parameters['min_crown_area']),
            "--building-clearance", repr(float(parameters['building_clearance'])),
            "--source-files", *[str(p) for p in source_files]]
    if parameters.get('z_unit') == 'metres':
        args.append("--z-metres")
    elif parameters.get('z_unit') is not None:
        raise ValueError(f"Unexpected baseline z_unit {parameters['z_unit']!r}")
    if background_zero:
        args.append("--classified-background-zero")
    return args


def parameter_differences(baseline, product):
    """Every parameter that differs; MATCHED keys must not appear."""
    keys = sorted(set(baseline) | set(product))
    return {k: {"baseline": baseline.get(k), "product": product.get(k)} for k in keys
            if baseline.get(k) != product.get(k)}


def halo_names(tile_points, tile):
    return sorted(p.stem for p in Path(tile_points).glob('*.las') if p.stem != tile)


def assemble_files(policy, halos, out_points, conflict_class):
    import dl_product
    from canopy.las_records import class_counts
    prepared = PILOT / TILE / "prepared" / "points"
    out_points.mkdir(parents=True, exist_ok=False)
    records = {}
    building = CORE_ROWS['building']
    record = dl_product.assemble(prepared / f"{TILE}.las", *CORE_ROWS['tree'], out_points / f"{TILE}.las",
                                 *building, policy=policy, conflict_class=conflict_class)
    (out_points / f"{TILE}.product.json").write_text(json.dumps(record, indent=1), encoding='utf-8')
    records[TILE] = {"kind": "product", "counts": record['counts'], "output": record['output']}
    for name in halo_names(prepared, TILE):
        baseline = prepared / f"{name}.las"
        out = out_points / f"{name}.las"
        if halos == 'inferred':
            tree = (HALO_ROWS['tree'] / "work" / f"run-tree-{name}.json",
                    HALO_ROWS['tree'] / "work" / f"compare-{TILE}-halo-tree.json")
            build = (HALO_ROWS['building'] / "work" / f"run-building-{name}.json",
                     HALO_ROWS['building'] / "work" / f"compare-{TILE}-halo-building.json")
            record = dl_product.assemble(baseline, *tree, out, *build, policy=policy, conflict_class=conflict_class)
            out.with_suffix('.product.json').write_text(json.dumps(record, indent=1), encoding='utf-8')
            records[name] = {"kind": "product", "counts": record['counts'], "output": record['output']}
        else:
            before = md5(baseline)
            shutil.copyfile(baseline, out)
            if md5(out) != before:
                raise RuntimeError(f"Baseline halo copy differs: {out}")
            counts = class_counts(out)['classes']
            if '0' in counts:
                raise ValueError(f"Baseline halo {name} holds class 0; --classified-background-zero is not justified")
            records[name] = {"kind": "exact baseline copy", "md5": before, "classes": counts}
    return records


def build_dataset(points, lasd):
    import arcpy
    from canopy import rasters
    files = sorted(str(p) for p in Path(points).glob('*.las'))
    arcpy.management.CreateLasDataset(files, str(lasd), compute_stats='COMPUTE_STATS')
    audit = rasters.audit(str(lasd))
    if not audit['has_statistics'] or audit['statistics_stale'] or not audit['vertical_reference']:
        raise ValueError(f"Product dataset lacks fresh statistics or a vertical reference: {audit}")
    return files, audit


def grid_summary(chm, extent=None, band=15.0):
    """CHM cell counts, including NoData and the outer band of the tile."""
    import arcpy
    import numpy as np
    raster = arcpy.Raster(str(chm))
    array = arcpy.RasterToNumPyArray(raster, nodata_to_value=np.nan).astype('float64')
    cell = raster.meanCellWidth
    summary = {"shape": list(array.shape), "cell": cell, "xmin": raster.extent.XMin, "ymax": raster.extent.YMax,
               "nodata_cells": int(np.isnan(array).sum()), "canopy_cells_ge_2m": int((array >= 2).sum()),
               "zero_cells": int((array == 0).sum())}
    if extent:
        k = int(round(band / cell))
        edge = np.zeros(array.shape, dtype=bool)
        edge[:k], edge[-k:], edge[:, :k], edge[:, -k:] = True, True, True, True
        summary["edge_band_m"] = band
        summary["edge_nodata_cells"] = int(np.isnan(array[edge]).sum())
        summary["edge_canopy_cells_ge_2m"] = int((array[edge] >= 2).sum())
        summary["interior_canopy_cells_ge_2m"] = int((array[~edge] >= 2).sum())
    return summary


def outputs_summary(run, band=15.0):
    import arcpy
    state = json.loads((Path(run) / 'run.json').read_text(encoding='utf-8'))
    out = state['outputs']
    x0, y0, x1, y1 = state['parameters']['extent']
    near_edge = sum(1 for x, y in arcpy.da.SearchCursor(out['treetops'], ["SHAPE@X", "SHAPE@Y"])
                    if min(x - x0, x1 - x, y - y0, y1 - y) < band)
    return {"treetops": int(arcpy.management.GetCount(out['treetops'])[0]),
            f"treetops_within_{band:g}m_of_tile_edge": near_edge,
            "crowns": int(arcpy.management.GetCount(out['crowns'])[0]),
            "chm": grid_summary(out['chm'], state['parameters']['extent'], band)}


def chm_difference(run_a, run_b, bands=(15.0, 30.0, 50.0)):
    """Cell-by-cell CHM difference of two runs on the same grid, by distance from the tile edge."""
    import arcpy
    import numpy as np
    arrays = []
    for run in (run_a, run_b):
        chm = json.loads((Path(run) / 'run.json').read_text(encoding='utf-8'))['outputs']['chm']
        arrays.append(arcpy.RasterToNumPyArray(arcpy.Raster(chm), nodata_to_value=np.nan).astype('float64'))
    a, b = arrays
    if a.shape != b.shape:
        raise ValueError("Runs are not on the same grid")
    cell = arcpy.Raster(json.loads((Path(run_a) / 'run.json').read_text())['outputs']['chm']).meanCellWidth
    rows, cols = np.indices(a.shape)
    distance = np.minimum.reduce([rows, cols, a.shape[0]-1-rows, a.shape[1]-1-cols]) * cell
    result, lower = {}, 0.0
    for upper in list(bands) + [float('inf')]:
        zone = (distance >= lower) & (distance < upper)
        both = zone & ~np.isnan(a) & ~np.isnan(b)
        diff = np.abs(a[both] - b[both])
        result[f"{lower:g}-{upper:g} m"] = {
            "cells": int(zone.sum()), "nodata_changed": int((zone & (np.isnan(a) != np.isnan(b))).sum()),
            "value_changed_gt_0_1m": int((diff > 0.1).sum()),
            "canopy_ge_2m_a": int((zone & (a >= 2)).sum()), "canopy_ge_2m_b": int((zone & (b >= 2)).sum()),
            "mean_abs_diff_m": round(float(diff.mean()), 4) if diff.size else None}
        lower = upper
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--policy', nargs='+', choices=('tree-wins', 'building-wins', 'conflict-class'))
    parser.add_argument('--halos', choices=('inferred', 'baseline'), default='inferred')
    parser.add_argument('--conflict-class', type=int, default=65)
    parser.add_argument('--root', type=Path, default=E30)
    parser.add_argument('--python', default=PRO_PYTHON)
    parser.add_argument('--diff', nargs=2, type=Path, metavar=('RUN_A', 'RUN_B'),
                        help='Only report the CHM difference of two finished runs by distance from the tile edge')
    args = parser.parse_args()
    if os.environ.get('PYTHONNOUSERSITE') != '1':
        parser.error('Set PYTHONNOUSERSITE=1')
    if args.diff:
        print(json.dumps(chm_difference(*args.diff), indent=1))
        return
    if not args.policy:
        parser.error('--policy is required')
    base_run = PILOT / TILE / "run"
    parameters = baseline_parameters(base_run / "run.json")
    base_chm = json.loads((base_run / 'run.json').read_text(encoding='utf-8'))['outputs']['chm']
    prepared = PILOT / TILE / "prepared" / "points"
    watched = sorted(prepared.glob('*.las'))
    raws = [Path(json.loads(Path(m).read_text())['output']['path']) for m, _ in CORE_ROWS.values()]
    for job, row in HALO_ROWS.items():
        raws += [Path(f['output']['path']) for f in json.loads((row / 'work' / f'run-{job}.json').read_text())['files']]
    before = {str(p): md5(p) for p in watched + raws}
    summary = {"baseline_run": str(base_run), "baseline_parameters": parameters,
               "baseline_outputs": outputs_summary(base_run), "variants": {}}
    for policy in args.policy:
        name = f"product-{policy}" + ("" if args.halos == 'inferred' else "-baseline-halos")
        folder = args.root / name / TILE
        record = {"policy": policy, "halos": args.halos, "folder": str(folder), "timings_s": {}}
        t0 = time.monotonic()
        record['files'] = assemble_files(policy, args.halos, folder / "points", args.conflict_class)
        record['timings_s']['assemble'] = round(time.monotonic() - t0, 1)
        t0 = time.monotonic()
        files, record['lasd_audit'] = build_dataset(folder / "points", folder / "product.lasd")
        record['timings_s']['lasd_statistics'] = round(time.monotonic() - t0, 1)
        record['classified_background_zero'] = True
        record['classified_background_zero_justification'] = (
            "every product file comes from verified full-file inference; class 0 is verified model background"
            if args.halos == 'inferred' else
            "baseline halo copies hold no class 0 (checked); class 0 exists only in the inferred core, where it "
            "is verified model background. Halo classes are baseline classes, so this variant mixes semantics.")
        command = [args.python, "-m", "canopy", *run_arguments(parameters, folder / "product.lasd", folder / "run",
                                                                 files, True)]
        record['command'] = command
        t0 = time.monotonic()
        with open(folder / "canopy-run.log", "w", encoding="utf-8") as log:
            code = subprocess.call(command, cwd=TOOLBOX, stdout=log, stderr=subprocess.STDOUT,
                                   env=dict(os.environ, PYTHONNOUSERSITE='1'))
        record['timings_s']['canopy_run'] = round(time.monotonic() - t0, 1)
        record['canopy_run_exit'] = code
        if code == 0:
            product_parameters = json.loads((folder / "run" / "run.json").read_text(encoding='utf-8'))['parameters']
            record['parameter_differences'] = parameter_differences(parameters, product_parameters)
            unexpected = set(record['parameter_differences']) & set(MATCHED)
            record['parameters_match_baseline'] = not unexpected
            record['outputs'] = outputs_summary(folder / "run")
            base = summary['baseline_outputs']['chm']
            record['grid_equals_baseline'] = all(record['outputs']['chm'][k] == base[k]
                                                 for k in ('shape', 'cell', 'xmin', 'ymax'))
        summary['variants'][name] = record
        (args.root / f"{name}.json").write_text(json.dumps(record, indent=1), encoding='utf-8')
        print(json.dumps({k: record.get(k) for k in ('policy', 'halos', 'canopy_run_exit', 'timings_s',
                                                      'grid_equals_baseline', 'parameter_differences')},
                         indent=1), flush=True)
    after = {str(p): md5(p) for p in watched + raws}
    summary['protected_md5_unchanged'] = before == after
    summary['protected_md5'] = before
    summary['baseline_chm'] = base_chm
    out = args.root / f"product-tile-{args.halos}-{time.strftime('%Y%m%d-%H%M%S')}.json"
    out.write_text(json.dumps(summary, indent=1), encoding='utf-8')
    print(f"Summary: {out}")
    if before != after:
        raise SystemExit("A baseline or raw model output changed")


if __name__ == '__main__':
    main()
