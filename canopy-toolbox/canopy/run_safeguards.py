"""Manifest and content checks for pilot/evaluation drivers. No ArcPy required."""
import hashlib
import json
import math
from pathlib import Path


def fingerprint(path):
    path = Path(path).resolve()
    digest = hashlib.sha256()
    with path.open('rb') as source:
        for chunk in iter(lambda: source.read(8 * 1024 * 1024), b''):
            digest.update(chunk)
    return {"path": str(path), "bytes": path.stat().st_size, "sha256": digest.hexdigest()}


def verify_fingerprint(record, path):
    actual = fingerprint(path)
    if any(record.get(key) != actual[key] for key in ("path", "bytes", "sha256")):
        raise ValueError(f"File does not match recorded content: {path}")


def valid_extent(extent):
    if extent is None:
        return None
    if len(extent) != 4 or not all(math.isfinite(float(v)) for v in extent):
        raise ValueError("Extent must contain four finite coordinates")
    x0, y0, x1, y1 = map(float, extent)
    if x0 >= x1 or y0 >= y1:
        raise ValueError("Extent minimum must precede maximum")
    return [x0, y0, x1, y1]


def prediction_extent(manifest, job, original, prediction, requested=None):
    """Require successful, reproducible binary inference and stay inside its boundary."""
    if manifest.get("schema_version") != 1 or manifest.get("status") != "complete":
        raise ValueError("No successful inference manifest; this copy is not model evidence")
    target = 6 if job == "building" else 5 if job == "tree" else None
    if target is None or manifest.get("job") != job or manifest.get("output_classes") != [0, target]:
        raise ValueError("Inference job or output classes do not match")
    if manifest.get("class_mode") != "EDIT_ALL" or manifest.get("excluded_class_codes") != [7, 18]:
        raise ValueError("Inference class/exclusion semantics do not match the comparator")
    verify_fingerprint(manifest.get("source", {}), original)
    verify_fingerprint(manifest.get("output", {}), prediction)
    verify_fingerprint(manifest.get("model", {}), manifest.get("model", {}).get("path", ""))
    if 'reference_height' in manifest:
        verify_fingerprint(manifest['reference_height'],manifest['reference_height'].get('path',''))
    source, before = manifest["source"], manifest.get("input", {})
    if any(source.get(k) != before.get(k) for k in ("bytes", "sha256")):
        raise ValueError("Inference did not begin from an exact copy of the baseline")
    processed = valid_extent(manifest.get("boundary"))
    requested = valid_extent(requested)
    if processed is not None and requested is not None:
        if any((requested[0] < processed[0], requested[1] < processed[1],
                requested[2] > processed[2], requested[3] > processed[3])):
            raise ValueError("Requested comparison extends outside the processed boundary")
    return requested if requested is not None else processed


def completed_preparation(folder, exists=None):
    """Incomplete preparations cannot be resumed: preserve them and choose a new folder."""
    folder = Path(folder)
    if not folder.exists():
        return False
    exists = exists or (lambda path: Path(path).is_file())
    manifest = folder / "preparation.json"
    if not manifest.is_file():
        raise ValueError(f"Existing preparation has no manifest; use a new output folder: {folder}")
    state = json.loads(manifest.read_text(encoding="utf-8"))
    lasd = state.get("working_lasd")
    points = list((folder / "points").glob("*.las"))
    if state.get("status") != "complete" or not lasd or not exists(lasd) or not points:
        raise ValueError(f"Preparation is incomplete or missing outputs; use a new output folder: {folder}")
    if set(state.get("after", {})) - {p.name for p in points}:
        raise ValueError(f"Preparation is missing recorded LAS files: {folder}")
    if Path(lasd).resolve() != (folder / "prepared.lasd").resolve():
        raise ValueError(f"Preparation manifest points outside the expected dataset: {folder}")
    return True


def run_resume_args(folder):
    """Always delegate reuse to the pipeline's signature and output checks."""
    folder = Path(folder)
    if not folder.exists():
        return []
    manifest = folder / "run.json"
    if not manifest.is_file():
        raise ValueError(f"Existing run has no manifest; use a new output folder: {folder}")
    state = json.loads(manifest.read_text(encoding="utf-8"))
    if not state.get("signature") or state.get("status") not in ("complete", "running", "failed"):
        raise ValueError(f"Run manifest cannot be resumed: {folder}")
    return ["--resume"]
