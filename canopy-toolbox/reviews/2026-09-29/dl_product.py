"""Assemble a documented PRODUCT copy from verified binary model outputs.

This is not a raw model output and must never enter dl_compare. Raw outputs are
only read; their SHA-256 is checked against the inference manifests before and
after. Class policy, applied per point in this order:

  1. baseline noise 7/18 is kept (the tool excluded it);
  2. baseline ground 2 is restored (EDIT_ALL may have replaced it) for the DTM;
  3. tree prediction 5 -> class 5 and, with --building, building prediction 6 -> class 6;
  4. points both models claim (tree 5 AND building 6) follow --policy:
       tree-wins      -> 5 (the September 29 product; default)
       building-wins  -> 6
       conflict-class -> --conflict-class (user-definable 64-255, default 65). canopy run
                         reads neither as vegetation (3;4;5), non-canopy (2;6;9;...;0) nor
                         building (6): such points add no canopy height, no building
                         occlusion and no observation, so a cell holding only conflict
                         first/single returns stays NoData (unknown), not zero canopy;
  5. everything else -> class 0, which is verified model background.

Every other record byte comes from the tree output, which the comparator has
already shown to be byte-identical to the baseline outside classification.
Manifests may be single-file dl_run manifests or the per-file manifests of a
multi-file row; the compare file may be a single or a multi-file (--row-manifest)
comparison. No ArcPy.

  python dl_product.py --baseline B.las --tree-manifest T.json --tree-compare T.json
      [--building-manifest M.json --building-compare C.json]
      [--policy tree-wins|building-wins|conflict-class [--conflict-class 65]] --out NEW.las
"""
import argparse
import json
from pathlib import Path
import shutil
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from canopy.las_records import header
from canopy.run_safeguards import fingerprint, verify_fingerprint

CHUNK = 4_000_000
NOISE = (7, 18)
POLICIES = ('tree-wins', 'building-wins', 'conflict-class')
DEFAULT_CONFLICT_CLASS = 65


def _same(a, b):
    try:
        return Path(a).resolve() == Path(b).resolve()
    except (OSError, TypeError):
        return False


def _compare_entry(compare, job, manifest_path):
    """The comparison entry for this manifest: the job entry, or its file in a multi-file row."""
    entry = compare.get(job, {})
    if 'files' not in entry:
        return entry
    if entry.get('status') != 'verified_inference':
        return {}
    matches = [e for e in entry['files'].values() if _same(e.get('inference_manifest', ''), manifest_path)]
    return matches[0] if len(matches) == 1 else {}


def _verified(manifest_path, compare_path, job, baseline):
    manifest = json.loads(Path(manifest_path).read_text(encoding='utf-8'))
    compare = json.loads(Path(compare_path).read_text(encoding='utf-8'))
    entry = _compare_entry(compare, job, manifest_path)
    if manifest.get('status') != 'complete' or entry.get('status') != 'verified_inference':
        raise ValueError(f"{job} output lacks a complete manifest and verified binary integrity")
    if manifest.get('boundary') is not None and entry.get('processed_extent') != manifest['boundary']:
        raise ValueError(f"{job} comparison does not describe the manifest boundary")
    verify_fingerprint(manifest['source'], baseline)
    verify_fingerprint(manifest['output'], manifest['output']['path'])
    return manifest


def _classes(path, info):
    return np.memmap(path, dtype=np.uint8, mode='r', offset=info['offset'],
                     shape=(info['points'], info['record_length']))[:, 16]


def assemble(baseline, tree_manifest, tree_compare, out, building_manifest=None, building_compare=None,
             policy='tree-wins', conflict_class=DEFAULT_CONFLICT_CLASS):
    baseline, out = Path(baseline).resolve(), Path(out).resolve()
    if out.exists():
        raise ValueError(f"Product must be a new file: {out}")
    if policy not in POLICIES:
        raise ValueError(f"Unknown conflict policy {policy!r}; use one of {', '.join(POLICIES)}")
    if policy != 'tree-wins' and not building_manifest:
        raise ValueError(f"Policy {policy} needs a building prediction")
    if policy == 'conflict-class' and not (isinstance(conflict_class, int) and 64 <= conflict_class <= 255):
        raise ValueError("The conflict class must be a user-definable LAS class code, 64 to 255")
    tree = _verified(tree_manifest, tree_compare, 'tree', baseline)
    building = _verified(building_manifest, building_compare, 'building', baseline) if building_manifest else None
    info = header(baseline)
    x0, y0, x1, y1 = info['extent']
    for manifest in [tree] + ([building] if building else []):
        bounds = manifest.get('boundary')
        if bounds is not None and not (bounds[0] <= x0 and bounds[1] <= y0 and bounds[2] >= x1 and bounds[3] >= y1):
            raise ValueError("Inference boundary must contain every baseline point so class 0 is entirely "
                             "model background")
    if info['format'] < 6:
        raise ValueError("Product assembly supports point formats 6-10")
    raw_tree = Path(tree['output']['path'])
    raws = [raw_tree] + ([Path(building['output']['path'])] if building else [])
    for path in raws:
        other = header(path)
        if any(other[k] != info[k] for k in ('format', 'points', 'record_length', 'offset')):
            raise ValueError(f"Raw output layout differs from the baseline: {path}")
    before = {str(p): fingerprint(p) for p in [baseline] + raws}
    temp = out.with_suffix('.las.partial')
    shutil.copyfile(raw_tree, temp)
    base = _classes(baseline, info)
    tree_cls = _classes(raw_tree, info)
    building_cls = _classes(raws[1], info) if building else None
    product = np.memmap(temp, dtype=np.uint8, mode='r+', offset=info['offset'],
                        shape=(info['points'], info['record_length']))
    keys = ['noise_kept', 'ground_restored', 'ground_restored_over_tree', 'ground_restored_over_building',
            'tree_5', 'building_6', 'conflict_tree5_building6', 'background_0']
    keys.append({'tree-wins': 'conflict_tree5_building6_resolved_to_tree',
                 'building-wins': 'conflict_tree5_building6_resolved_to_building',
                 'conflict-class': f'conflict_tree5_building6_to_class_{conflict_class}'}[policy])
    counts = {k: 0 for k in keys}
    for start in range(0, info['points'], CHUNK):
        stop = min(info['points'], start+CHUNK)
        b, t = np.asarray(base[start:stop]), np.asarray(tree_cls[start:stop])
        u = np.asarray(building_cls[start:stop]) if building else np.zeros_like(t)
        noise = np.isin(b, NOISE)
        ground = (b == 2) & ~noise
        tree5 = (t == 5) & ~noise & ~ground
        build6 = (u == 6) & ~noise & ~ground
        conflict = tree5 & build6
        result = np.zeros_like(b)
        result[noise] = b[noise]
        result[ground] = 2
        if policy == 'building-wins':
            result[tree5] = 5
            result[build6] = 6
        else:
            result[build6] = 6
            result[tree5] = 5
            if policy == 'conflict-class':
                result[conflict] = conflict_class
        product[start:stop, 16] = result
        counts['noise_kept'] += int(noise.sum())
        counts['ground_restored'] += int(ground.sum())
        counts['ground_restored_over_tree'] += int((ground & (t == 5)).sum())
        counts['ground_restored_over_building'] += int((ground & (u == 6)).sum())
        counts['tree_5'] += int((result == 5).sum())
        counts['building_6'] += int((result == 6).sum())
        counts['conflict_tree5_building6'] += int(conflict.sum())
        counts[keys[-1]] += int(conflict.sum())
        counts['background_0'] += int((result == 0).sum())
    product.flush()
    del product, base, tree_cls, building_cls
    temp.replace(out)
    after = {str(p): fingerprint(p) for p in [baseline] + raws}
    if after != before:
        raise RuntimeError("A baseline or raw model output changed during product assembly")
    conflict_rule = {
        'tree-wins': "points both models claim (tree 5 and building 6) -> 5",
        'building-wins': "points both models claim (tree 5 and building 6) -> 6",
        'conflict-class': f"points both models claim (tree 5 and building 6) -> {conflict_class} "
                          "(held out of canopy, building occlusion and observation by canopy run)"}[policy]
    return {
        "kind": "postprocessed product copy; NOT a raw model output; never use in dl_compare",
        "conflict_policy": policy,
        "conflict_class": conflict_class if policy == 'conflict-class' else None,
        "policy": ["baseline noise 7/18 kept", "baseline ground 2 restored",
                   "tree prediction 5 -> 5",
                   "building prediction 6 -> 6" if building else "no building prediction combined",
                   conflict_rule if building else "no conflicts possible without a building prediction",
                   "remaining points -> 0 (verified model background; full-file inference)"],
        "baseline": before[str(baseline)], "raw_outputs_before": [before[str(p)] for p in raws],
        "raw_outputs_after": [after[str(p)] for p in raws],
        "tree_manifest": str(Path(tree_manifest).resolve()),
        "building_manifest": str(Path(building_manifest).resolve()) if building else None,
        "counts": counts, "points": info['points'], "output": fingerprint(out),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--tree-manifest', type=Path, required=True)
    parser.add_argument('--tree-compare', type=Path, required=True)
    parser.add_argument('--building-manifest', type=Path)
    parser.add_argument('--building-compare', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--policy', choices=POLICIES, default='tree-wins',
                        help='Class for points both models claim (default tree-wins)')
    parser.add_argument('--conflict-class', type=int, default=DEFAULT_CONFLICT_CLASS,
                        help='User-definable class (64-255) for --policy conflict-class')
    args = parser.parse_args()
    if bool(args.building_manifest) != bool(args.building_compare):
        parser.error('--building-manifest and --building-compare go together')
    record = assemble(args.baseline, args.tree_manifest, args.tree_compare, args.out,
                      args.building_manifest, args.building_compare, args.policy, args.conflict_class)
    args.out.with_suffix('.product.json').write_text(json.dumps(record, indent=1), encoding='utf-8')
    print(json.dumps(record['counts'], indent=1))


if __name__ == '__main__':
    main()
