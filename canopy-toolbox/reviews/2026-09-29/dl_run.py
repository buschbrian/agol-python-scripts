"""Pretrained inference on an exact pilot COPY with verifiable provenance.

Use the configured ArcGIS Pro deep-learning environment. This driver does not
change Pro's environment. Failed runs are recorded and never count as evidence.
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import threading
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from canopy.run_safeguards import fingerprint, valid_extent

ROOT = Path(r"H:\lidar\2023-salt-lake-valley\runs\pilot-2026-09-29\deep-learning\12TVL2804")
MODELS = Path(r"H:\lidar\models")
SOURCE = ROOT.parents[1] / "12TVL2804" / "prepared" / "points" / "12TVL2804.las"
JOBS = {"building": ("building_point_classification.dlpk", 6), "tree": ("Tree_point_classification.dlpk", 5)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("job", choices=list(JOBS))
    parser.add_argument("--boundary", nargs=4, type=float)
    parser.add_argument("--batch", type=int, default=1)
    parser.add_argument("--mode", choices=["EDIT_ALL"], default="EDIT_ALL")
    args = parser.parse_args()
    extent = valid_extent(args.boundary)
    if args.batch < 1:
        parser.error("--batch must be positive")
    las = (ROOT / args.job / "12TVL2804.las").resolve()
    if ROOT.resolve() not in las.parents or las.parent.name != args.job or las == SOURCE.resolve():
        raise ValueError("Inference must operate on the dedicated copy")
    model_name, target = JOBS[args.job]
    model = MODELS / model_name
    work = ROOT / "work"
    work.mkdir(exist_ok=True)
    manifest = work / f"run-{args.job}.json"
    info = {"schema_version": 1, "status": "running", "job": args.job,
            "started_utc": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
            "class_mode": args.mode, "output_classes": [0, target], "excluded_class_codes": [7, 18],
            "boundary": extent, "boundary_inclusion": "inclusive rectangle", "epsg": 6341,
            "batch_size": args.batch, "python": sys.executable}

    def save():
        temp = manifest.with_suffix('.json.tmp')
        temp.write_text(json.dumps(info, indent=2), encoding='utf-8')
        temp.replace(manifest)

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
    info.update(source=fingerprint(SOURCE), input=fingerprint(las), model=fingerprint(model))
    if any(info['source'][k] != info['input'][k] for k in ('sha256', 'bytes')):
        raise ValueError("Inference copy differs from baseline; restore a fresh copy before rerunning")
    save()
    try:
        import arcpy as runtime
        arcpy = runtime
        info['arcgis'] = arcpy.GetInstallInfo()
        import importlib.metadata
        info['packages'] = {}
        for package in ('torch', 'arcgis', 'numpy', 'scipy'):
            try:
                info['packages'][package] = importlib.metadata.version(package)
            except importlib.metadata.PackageNotFoundError:
                info['packages'][package] = None
        checkout = arcpy.CheckOutExtension('3D')
        checked_out = checkout == 'CheckedOut'
        if not checked_out:
            raise RuntimeError(f"3D Analyst checkout failed: {checkout}")
        arcpy.env.overwriteOutput = True
        lasd = las.with_suffix('.lasd')
        # Recreate even an existing dataset so it cannot reference original LAS
        # files or a different experiment through stale dataset membership.
        arcpy.management.CreateLasDataset(str(las), str(lasd), compute_stats='COMPUTE_STATS',
                                          spatial_reference=arcpy.SpatialReference(6341))
        kwargs = dict(in_point_cloud=str(lasd), in_trained_model=str(model), output_classes=[0, target],
            in_class_mode=args.mode, compute_stats='COMPUTE_STATS', update_pyramid='UPDATE_PYRAMID',
            excluded_class_codes=[7, 18], batch_size=args.batch)
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
        info['output'] = fingerprint(las)
        for path, key in ((SOURCE, 'source'), (model, 'model')):
            if fingerprint(path) != info[key]:
                raise RuntimeError(f"{key} changed while inference ran")
        info['status'] = 'complete'
    except Exception as exc:
        info.update(status='failed', error=str(exc))
        raise
    finally:
        stop.set()
        if thread:
            thread.join(timeout=12)
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
