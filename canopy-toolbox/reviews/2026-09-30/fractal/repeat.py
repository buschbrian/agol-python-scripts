"""Repeat FRACTAL inference on a colorized LAS; save votes as model opinions.

Run with the Myria3D environment's Python. Requires no SSD or ArcGIS license
when the colorized input already exists. Outputs must be new directories.
"""
import argparse
from contextlib import ExitStack
import hashlib
import itertools
import json
import os
from pathlib import Path
import site
import subprocess
import sys
import time

import numpy as np


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def votes(predictions):
    """Plurality class, agreement share, tie flag and strict-majority flag.

    Zero denotes an unresolved tie. Agreement is repeat agreement, never
    calibrated confidence or accuracy. A unique plurality need not exceed 50%.
    """
    predictions = np.asarray(predictions)
    if predictions.ndim != 2 or not 3 <= len(predictions) <= 5:
        raise ValueError("Expected three to five aligned prediction arrays")
    if not np.issubdtype(predictions.dtype, np.integer) or np.any(predictions < 1) or np.any(predictions > 255):
        raise ValueError("Predicted classes must be integer LAS codes 1..255")
    classes = np.unique(predictions)
    counts = np.stack([(predictions == code).sum(axis=0) for code in classes])
    maximum = counts.max(axis=0)
    tied = (counts == maximum).sum(axis=0) > 1
    majority = classes[counts.argmax(axis=0)].astype(np.uint8)
    majority[tied] = 0
    return majority, maximum / len(predictions), tied, maximum > len(predictions) / 2


def consensus(source, predictions, output, chunk_size=200_000):
    """Check all original dimensions by index, then write a new source copy."""
    import laspy

    if not 3 <= len(predictions) <= 5:
        raise ValueError("Expected three to five repeats")
    output = Path(output)
    partial = output.with_name(output.stem + ".partial.las")
    if output.exists() or partial.exists():
        raise FileExistsError(output)
    summary = {"points": 0, "unanimous_points": 0, "tie_points": 0,
               "strict_majority_points": 0, "class_counts": {}, "pairwise": []}
    pairs = list(itertools.combinations(range(len(predictions)), 2))
    same = np.zeros(len(pairs), dtype=np.int64)
    with ExitStack() as stack:
        original = stack.enter_context(laspy.open(source))
        readers = [stack.enter_context(laspy.open(p)) for p in predictions]
        dimensions = list(original.header.point_format.dimension_names)
        for reader in readers:
            if reader.header.point_count != original.header.point_count:
                raise ValueError("Prediction point count differs from input")
            if "PredictedClassification" not in reader.header.point_format.dimension_names:
                raise ValueError("Missing PredictedClassification")
        header = original.header.copy()
        for name, dtype in (("MajorityClassification", np.uint8), ("RepeatAgreement", np.float32),
                            ("RepeatTie", np.uint8), ("StrictMajority", np.uint8)):
            header.add_extra_dim(laspy.ExtraBytesParams(name=name, type=dtype))
        writer = stack.enter_context(laspy.open(partial, mode="w", header=header))
        for block in original.chunk_iterator(chunk_size):
            predicted = [reader.read_points(len(block)) for reader in readers]
            for cloud in predicted:
                for name in dimensions:
                    # Compare physical coordinates: PDAL may rewrite scale/offset.
                    field = name.lower() if name in ("X", "Y", "Z") else name
                    if not np.array_equal(np.asarray(block[field]), np.asarray(cloud[field])):
                        raise ValueError(f"Prediction changed point order or source dimension {name}")
            codes = np.stack([np.asarray(cloud["PredictedClassification"]) for cloud in predicted])
            majority, agreement, tied, strict = votes(codes)
            new = laspy.ScaleAwarePointRecord.zeros(len(block), header=header)
            for name in dimensions:
                new[name] = block[name]
            new["MajorityClassification"] = majority
            new["RepeatAgreement"] = agreement
            new["RepeatTie"] = tied.astype(np.uint8)
            new["StrictMajority"] = strict.astype(np.uint8)
            writer.write_points(new)
            summary["points"] += len(block)
            summary["unanimous_points"] += int((agreement == 1).sum())
            summary["tie_points"] += int(tied.sum())
            summary["strict_majority_points"] += int(strict.sum())
            classes, counts = np.unique(majority, return_counts=True)
            for code, count in zip(classes, counts):
                key = str(int(code))
                summary["class_counts"][key] = summary["class_counts"].get(key, 0) + int(count)
            for index, (a, b) in enumerate(pairs):
                same[index] += int((codes[a] == codes[b]).sum())
    if not summary["points"]:
        raise ValueError("Empty input")
    summary["pairwise"] = [{"runs": [a + 1, b + 1], "agreement": int(count) / summary["points"]}
                           for (a, b), count in zip(pairs, same)]
    partial.rename(output)
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--tools", type=Path, default=Path(os.environ.get("FRACTAL_TOOLS", str(Path.home() / "tools"))))
    parser.add_argument("--repeats", type=int, choices=(3, 4, 5), default=3)
    parser.add_argument("--batch", type=int, default=10)
    args = parser.parse_args(argv)
    if site.ENABLE_USER_SITE:
        raise RuntimeError("Set PYTHONNOUSERSITE=1 before starting Python")
    import torch
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA GPU required for this runner")
    if args.batch < 1:
        raise ValueError("Batch must be positive")
    source, output, tools = args.source.resolve(), args.output.resolve(), args.tools.resolve()
    checkout = tools / "myria3d"
    checkpoint = checkout / "trained_model_assets" / "FRACTAL-LidarHD_7cl_randlanet.ckpt"
    import laspy
    with laspy.open(source) as reader:
        if reader.header.point_format.id != 8 or not reader.header.point_count:
            raise ValueError("Expected a nonempty colorize_las.py point-format-8 input")
        crs = reader.header.parse_crs()
        horizontal = crs.sub_crs_list[0] if crs and crs.is_compound else crs
        if horizontal is None or horizontal.to_epsg() != 6341:
            raise ValueError("Input must use EPSG:6341")
        for block in reader.chunk_iterator(200_000):
            if np.any(np.asarray(block.classification) != 1):
                raise ValueError("Input classifications must be reset to 1 by colorize_las.py")
            if any(np.any(np.asarray(block[name]) > 255 * 256) for name in ("red", "green", "blue", "nir")):
                raise ValueError("Input colors exceed the FRACTAL 255*256 range")
    source_hash, model_hash = sha256(source), sha256(checkpoint)
    output.mkdir(parents=True, exist_ok=False)
    env = dict(os.environ, PYTHONNOUSERSITE="1")
    env["PATH"] = os.pathsep.join([str(Path(sys.prefix) / "Library" / "bin"), env.get("PATH", "")])
    manifest = {"status": "running", "source": str(source), "source_sha256_before": source_hash,
                "model_sha256": model_hash, "runner_sha256": sha256(__file__), "python": sys.executable,
                "model_code_sha256": {str(p.relative_to(checkout)): sha256(p) for p in
                                      (checkout / "run.py", checkout / "myria3d/predict.py",
                                       checkout / "myria3d/pctl/datamodule/hdf5.py",
                                       checkpoint.with_name("FRACTAL-LidarHD_7cl_randlanet-inference-Myria3DV3.8.yaml"))},
                "torch": torch.__version__, "gpu": torch.cuda.get_device_name(0), "repeats": args.repeats,
                "batch": args.batch, "started": time.time(), "rows": [],
                "interpretation": "Model opinions; repeat agreement is not confidence or accuracy. No labels modified."}

    def save():
        (output / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    save()
    try:
        predicted = []
        for number in range(1, args.repeats + 1):
            row_dir = output / f"repeat-{number}"
            command = [sys.executable, str(checkout / "run.py"), "task.task_name=predict",
                       f"predict.src_las={source.as_posix()}", f"predict.output_dir={row_dir.as_posix()}",
                       "predict.gpus=[0]", "datamodule.epsg=6341", f"datamodule.batch_size={args.batch}",
                       "datamodule.num_workers=0", "datamodule.prefetch_factor=null", "model.num_workers=0",
                       "predict.interpolator.probas_to_save=all", f"hydra.run.dir={(row_dir / 'hydra').as_posix()}"]
            row = {"repeat": number, "command": command, "started": time.time()}
            manifest["rows"].append(row)
            save()
            print(f"Repeat {number}/{args.repeats} on {manifest['gpu']}", flush=True)
            with open(output / f"repeat-{number}.log", "w", encoding="utf-8") as log:
                result = subprocess.run(command, cwd=checkout, env=env, stdout=log, stderr=subprocess.STDOUT)
            row.update(exit_code=result.returncode, seconds=time.time() - row["started"])
            row["source_sha256_after"] = sha256(source)
            if row["source_sha256_after"] != source_hash:
                raise ValueError("SOURCE CHANGED")
            prediction = row_dir / source.name
            if result.returncode or not prediction.is_file():
                raise RuntimeError(f"Repeat {number} failed; see repeat-{number}.log")
            row["output_sha256"] = sha256(prediction)
            predicted.append(prediction)
            save()
        manifest["consensus"] = consensus(source, predicted, output / "consensus.las")
        manifest["source_sha256_after"] = sha256(source)
        if manifest["source_sha256_after"] != source_hash:
            raise ValueError("SOURCE CHANGED")
        manifest["consensus_sha256"] = sha256(output / "consensus.las")
        manifest["status"] = "complete; source dimensions and order verified"
    except Exception as exc:
        manifest.update(status="failed", error=str(exc))
        raise
    finally:
        manifest["finished"] = time.time()
        save()
    print(json.dumps(manifest["consensus"], indent=2), flush=True)


if __name__ == "__main__":
    main()
