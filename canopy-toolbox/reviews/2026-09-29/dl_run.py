"""Pretrained inference on exact pilot COPIES with verifiable provenance.

Use the configured ArcGIS Pro deep-learning environment. This driver does not
change Pro's environment. Failed runs are recorded and never count as evidence.

One row may hold several files (a tile core plus its halo files): repeat
--source/--copy in matching order. All copies go into one LAS dataset and one
tool call. A single-file row keeps the original manifest layout
(work/run-JOB.json with source/input/output). A multi-file row writes a row
manifest work/run-JOB.json listing its files, plus one schema-1 manifest per
file, work/run-JOB-STEM.json, which dl_compare and dl_product read unchanged.
"""
import argparse
import importlib.metadata
import importlib.util
import json
import os
from pathlib import Path
import site
import subprocess
import sys
import threading
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from canopy.run_safeguards import fingerprint, valid_extent

from canopy.lidar_root import lidar_root  # noqa: E402
ROOT = lidar_root() / "2023-salt-lake-valley" / "runs" / "pilot-2026-09-29" / "deep-learning" / "12TVL2804"
MODELS = lidar_root() / "models"
SOURCE = ROOT.parents[1] / "12TVL2804" / "prepared" / "points" / "12TVL2804.las"
JOBS = {"building": ("building_point_classification.dlpk", 6), "tree": ("Tree_point_classification.dlpk", 5)}
PACKAGES = ('torch', 'arcgis', 'numpy', 'scipy')


def _under(path, prefix):
    try:
        return Path(path).resolve().is_relative_to(Path(prefix).resolve())
    except (OSError, TypeError, ValueError):
        return False


def runtime_isolation(allow_user_site=False):
    """Record whether per-user site-packages could shadow the environment's own packages.

    Pro's Python 3.13 environments read the per-user Python313 site-packages under
    APPDATA unless PYTHONNOUSERSITE is set; a stray numpy there replaced the clone's own.
    """
    return {"PYTHONNOUSERSITE": os.environ.get('PYTHONNOUSERSITE'),
            "site_ENABLE_USER_SITE": bool(site.ENABLE_USER_SITE),
            "user_site": site.getusersitepackages() if site.ENABLE_USER_SITE else None,
            "sys_prefix": sys.prefix, "allow_user_site_override": bool(allow_user_site),
            "scope": "calling interpreter; the tool's own worker processes are not inspected"}


def package_provenance(names=PACKAGES):
    """Version and file location of each package without importing it here."""
    result = {}
    for name in names:
        entry = {"version": None, "module_version": None, "file": None, "loaded": name in sys.modules,
                 "distribution_location": None}
        try:
            entry['version'] = importlib.metadata.version(name)
            entry['distribution_location'] = str(importlib.metadata.distribution(name).locate_file(''))
        except importlib.metadata.PackageNotFoundError:
            pass
        module = sys.modules.get(name)
        if module is not None:
            entry['file'] = getattr(module, '__file__', None)
            entry['module_version'] = getattr(module, '__version__', None)
        else:
            try:
                spec = importlib.util.find_spec(name)
            except (ImportError, ValueError):
                spec = None
            entry['file'] = spec.origin if spec is not None else None
        entry['under_sys_prefix'] = _under(entry['file'], sys.prefix) if entry['file'] else None
        result[name] = entry
    return result


def pair_files(job, root, sources, copies):
    """Resolve (source, copy) pairs; every copy is a dedicated file under ROOT/JOB."""
    if len(sources) != len(copies):
        raise ValueError("Give one --copy for each --source, in the same order")
    pairs = [(Path(s).resolve(), Path(c).resolve()) for s, c in zip(sources, copies)]
    resolved_sources = {s for s, _ in pairs}
    names = [c.stem.lower() for _, c in pairs]
    if len(set(names)) != len(names) or len({c for _, c in pairs}) != len(pairs):
        raise ValueError("Copies must have distinct file names")
    if len(resolved_sources) != len(pairs):
        raise ValueError("Each source may appear only once in a row")
    for _, las in pairs:
        if root not in las.parents or las.parent.name != job or las in resolved_sources:
            raise ValueError("Inference must operate on the dedicated copy")
        # The tool edits in place and only fails when it opens the file for writing, after inference.
        if las.exists() and not os.access(las, os.W_OK):
            raise ValueError(f"Inference copy is read-only; the tool could not write predictions: {las}")
    return pairs


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("job", choices=list(JOBS))
    parser.add_argument("--boundary", nargs=4, type=float)
    parser.add_argument("--batch", type=int, default=1)
    parser.add_argument("--mode", choices=["EDIT_ALL"], default="EDIT_ALL")
    parser.add_argument('--source',type=Path,action='append',
                        help='Unchanged baseline file; repeat for a multi-file row (default: the 12TVL2804 core)')
    parser.add_argument('--copy',type=Path,action='append',
                        help='Exact copy under OUTPUT_ROOT/JOB, one per --source in the same order; '
                             'defaults to 12TVL2804.las for a single source')
    parser.add_argument('--output-root',type=Path,default=ROOT,help='Dedicated experiment root containing JOB/SOURCE_NAME')
    parser.add_argument('--lasd', help='Name of the row LAS dataset under OUTPUT_ROOT/JOB (multi-file rows; '
                                       'default JOB.lasd)')
    parser.add_argument('--label', help='Data-use label recorded in every manifest, e.g. '
                                        '"prospective holdout - inference only, never training"')
    parser.add_argument('--reference-height',type=Path,help='Ground elevation raster for the paired HAG experiment')
    parser.add_argument('--allow-user-site', action='store_true',
                        help='Run even though per-user site-packages are enabled (recorded in the manifest)')
    args = parser.parse_args()
    isolation = runtime_isolation(args.allow_user_site)
    if isolation['site_ENABLE_USER_SITE'] and not args.allow_user_site:
        # Refuse before any manifest is written, so an earlier record is preserved.
        parser.error(f"per-user site-packages are enabled ({isolation['user_site']}) and may shadow this "
                     "environment's numpy/scipy; set PYTHONNOUSERSITE=1 or pass --allow-user-site")
    extent = valid_extent(args.boundary)
    if args.batch < 1:
        parser.error("--batch must be positive")
    root = args.output_root.resolve()
    sources = args.source or [SOURCE]
    if args.copy:
        copies = args.copy
    elif len(sources) == 1:
        copies = [root / args.job / '12TVL2804.las']
    else:
        parser.error("A multi-file row needs one --copy per --source")
    pairs = pair_files(args.job, root, sources, copies)
    multi = len(pairs) > 1
    las = pairs[0][1]
    model_name, target = JOBS[args.job]
    model = MODELS / model_name
    work = root / "work"
    work.mkdir(exist_ok=True)
    manifest = work / f"run-{args.job}.json"
    info = {"schema_version": 1, "status": "running", "job": args.job,
            "started_utc": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
            "class_mode": args.mode, "output_classes": [0, target], "excluded_class_codes": [7, 18],
            "boundary": extent, "boundary_inclusion": "inclusive rectangle", "epsg": 6341,
            "batch_size": args.batch, "python": sys.executable, "runtime_isolation": isolation}
    if args.label:
        info['data_use_label'] = args.label
    file_manifests = {c: work / f"run-{args.job}-{c.stem}.json" for _, c in pairs} if multi else {}

    def write(path, record):
        temp = path.with_suffix('.json.tmp')
        temp.write_text(json.dumps(record, indent=2), encoding='utf-8')
        temp.replace(path)

    def save():
        if not multi:
            write(manifest, info)
            return
        # Per-file manifests carry the single-file schema that the comparator and product reader check.
        common = {k: v for k, v in info.items() if k != 'files'}
        for entry in info['files']:
            record = dict(common, source=entry['source'], input=entry['input'], row_manifest=str(manifest),
                          row_files=len(info['files']))
            if 'output' in entry:
                record['output'] = entry['output']
            write(Path(entry['manifest']), record)
        write(manifest, info)

    samples, stop = [], threading.Event()

    def sample_gpu():
        while not stop.is_set():
            try:
                output = subprocess.run(['nvidia-smi', '--query-gpu=memory.used', '--format=csv,noheader,nounits'],
                                        capture_output=True, text=True, timeout=10)
                samples.append(int(output.stdout.splitlines()[0]))
            except (OSError, ValueError, IndexError, subprocess.TimeoutExpired):
                pass
            stop.wait(1)

    thread = None
    arcpy = None
    checked_out = False
    started = time.monotonic()
    # Preserve earlier success if the caller tries to reuse already-classified input.
    files = [{"source": fingerprint(s), "input": fingerprint(c)} for s, c in pairs]
    for entry in files:
        if any(entry['source'][k] != entry['input'][k] for k in ('sha256', 'bytes')):
            raise ValueError("Inference copy differs from baseline; restore a fresh copy before rerunning")
    info['model'] = fingerprint(model)
    if multi:
        for entry, (_, c) in zip(files, pairs):
            entry['manifest'] = str(file_manifests[c])
        info['files'] = files
    else:
        info.update(source=files[0]['source'], input=files[0]['input'])
    if args.reference_height:
        info['reference_height']=fingerprint(args.reference_height)
    save()
    try:
        import arcpy as runtime
        arcpy = runtime
        info['arcgis'] = arcpy.GetInstallInfo()
        info['package_provenance'] = package_provenance()
        info['packages'] = {name: entry['version'] for name, entry in info['package_provenance'].items()}
        checkout = arcpy.CheckOutExtension('3D')
        checked_out = checkout == 'CheckedOut'
        if not checked_out:
            raise RuntimeError(f"3D Analyst checkout failed: {checkout}")
        arcpy.env.overwriteOutput = True
        lasd = (las.parent / (args.lasd or f'{args.job}.lasd')) if multi else las.with_suffix('.lasd')
        # Recreate even an existing dataset so it cannot reference original LAS
        # files or a different experiment through stale dataset membership.
        members = [str(c) for _, c in pairs] if multi else str(las)
        arcpy.management.CreateLasDataset(members, str(lasd), compute_stats='COMPUTE_STATS',
                                          spatial_reference=arcpy.SpatialReference(6341))
        info['lasd'] = str(lasd)
        kwargs = dict(in_point_cloud=str(lasd), in_trained_model=str(model), output_classes=[0, target],
            in_class_mode=args.mode, compute_stats='COMPUTE_STATS', update_pyramid='UPDATE_PYRAMID',
            excluded_class_codes=[7, 18], batch_size=args.batch)
        if args.reference_height:
            kwargs['reference_height']=str(args.reference_height.resolve())
        if extent:
            x0, y0, x1, y1 = extent
            polygon = arcpy.Polygon(arcpy.Array([arcpy.Point(*p) for p in
                [(x0, y0), (x0, y1), (x1, y1), (x1, y0), (x0, y0)]]), arcpy.SpatialReference(6341))
            boundary = work / f'boundary-{args.job}.shp'
            arcpy.management.CopyFeatures([polygon], str(boundary))
            kwargs['boundary'] = str(boundary)
        thread = threading.Thread(target=sample_gpu, daemon=True)
        thread.start()
        arcpy.ddd.ClassifyPointCloudUsingTrainedModel(**kwargs)
        outputs = [fingerprint(c) for _, c in pairs]
        if multi:
            for entry, output in zip(info['files'], outputs):
                entry['output'] = output
        else:
            info['output'] = outputs[0]
        protected=[(model,info['model'],'model')]
        protected += [(s, entry['source'], f'source {s.name}') for (s, _), entry in zip(pairs, files)]
        if args.reference_height: protected.append((args.reference_height,info['reference_height'],'reference_height'))
        for path, record, key in protected:
            if fingerprint(path) != record:
                raise RuntimeError(f"{key} changed while inference ran")
        info['status'] = 'complete'
    except Exception as exc:
        info.update(status='failed', error=str(exc))
        raise
    finally:
        stop.set()
        if thread:
            thread.join(timeout=12)
        info['package_provenance_after'] = package_provenance()
        info.update(elapsed_seconds=round(time.monotonic()-started, 1),
                    gpu_used_mib_first_sample=samples[0] if samples else None,
                    gpu_used_mib_peak=max(samples, default=None))
        if arcpy:
            info['messages'] = arcpy.GetMessages()
        save()
        if checked_out:
            arcpy.CheckInExtension('3D')
        print(json.dumps(info, indent=2), flush=True)


if __name__ == '__main__':
    main()
