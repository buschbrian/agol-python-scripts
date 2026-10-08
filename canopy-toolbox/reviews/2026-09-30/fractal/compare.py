"""Inspect verified FRACTAL consensus or compare it with TRAINING patch labels.

Run with Myria3D Python and PYTHONNOUSERSITE=1. No ArcPy or label writes.
  python compare.py --run naip2024=RUN --out NEW_DIRECTORY
  python compare.py --run naip2021=RUN1 --run naip2024=RUN2 --packet PACKET
                   --labels labels-progress.csv --triage triage-proposals.csv --out NEW_DIRECTORY
The protocol is fixed in canopy/fractal_compare.py; this is not evaluation scoring.
"""
import argparse
import csv
import hashlib
import itertools
import json
from pathlib import Path
import site
import sys

import numpy as np

TOOLBOX = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(TOOLBOX))
from canopy import fractal_compare as fc, training_review as tr  # noqa: E402
from canopy.lidar_root import live  # noqa: E402


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_csv(path):
    with open(path, encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def load_answers(packet_path, labels_path, triage_path=None):
    packet = json.loads((Path(packet_path) / "packet.json").read_text(encoding="utf-8"))
    if packet.get("schema") != tr.SCHEMA:
        raise ValueError("Expected a TRAINING review packet, never an evaluation worksheet")
    tr.check_frame(packet["frame"])
    if tr.units_digest(packet["units"]) != packet["units_digest"]:
        raise ValueError("Training packet units were altered")
    units = {u["UNIT_ID"]: u for u in packet["units"]}
    answers, seen = [], set()
    for row in read_csv(labels_path):
        uid = row.get("UNIT_ID")
        if uid in seen or uid not in units:
            raise ValueError("Duplicate or foreign training label")
        seen.add(uid)
        unit = units[uid]
        if row.get("UNIT_TOKEN") != tr.unit_token(packet["frame"]["digest"], unit):
            raise ValueError(f"{uid}: training label token differs")
        if row.get("LABEL"):
            if row.get("CHECK", "OK") != "OK":
                raise ValueError(f"{uid}: label backup has a failed check")
            answers.append({**unit, **tr.normalize_answer(unit, row, packet["frame"])})
    proposals = {}
    if triage_path:
        for row in read_csv(triage_path):
            uid = row.get("UNIT_ID")
            if uid not in units or uid in proposals or row.get("PROPOSED", "") not in ("", *tr.LABELS):
                raise ValueError("Duplicate, foreign or invalid triage proposal")
            proposals[uid] = row
    return answers, proposals


def load_run(folder):
    import laspy
    folder = Path(folder)
    manifest_path = folder / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("status") != "complete; source dimensions and order verified":
        raise ValueError("FRACTAL repeat run is not verified complete")
    repeats = manifest["repeats"]
    source_path = live(manifest["source"])
    if not source_path.is_absolute():
        source_path = folder / source_path
    output_path = folder / "consensus.las"
    source_hash, output_hash = sha256(source_path), sha256(output_path)
    if source_hash != manifest["source_sha256_before"] or source_hash != manifest["source_sha256_after"]:
        raise ValueError("Inference input hash differs from the verified run")
    if output_hash != manifest["consensus_sha256"]:
        raise ValueError("Consensus hash differs from the verified run")
    source, output = laspy.read(source_path), laspy.read(output_path)
    if len(source.points) != len(output.points):
        raise ValueError("Consensus point count differs")
    for dimension in source.point_format.dimension_names:
        field = dimension.lower() if dimension in ("X", "Y", "Z") else dimension
        if not np.array_equal(np.asarray(source[field]), np.asarray(output[field])):
            raise ValueError(f"Consensus changed source dimension {dimension}")
    codes = np.asarray(output.MajorityClassification)
    agreement = np.asarray(output.RepeatAgreement)
    tied, strict = np.asarray(output.RepeatTie), np.asarray(output.StrictMajority)
    fc.validate_consensus(codes, agreement, tied, strict, repeats)
    clean = ~(np.asarray(output.withheld, bool) | np.asarray(output.synthetic, bool) | np.asarray(output.overlap, bool))
    data = {"x": np.asarray(output.x)[clean], "y": np.asarray(output.y)[clean], "z": np.asarray(output.z)[clean],
            "codes": codes[clean], "agreement": agreement[clean], "tied": tied[clean], "strict": strict[clean],
            "bounds": [float(output.header.mins[0]), float(output.header.mins[1]),
                       float(output.header.maxs[0]), float(output.header.maxs[1])]}
    info = {"points": len(output.points), "eligible_points": int(clean.sum()), "flagged_points_excluded": int((~clean).sum()),
            "mean_repeat_agreement": float(agreement[clean].mean()) if clean.any() else None,
            "ties": int(tied[clean].sum()), "repeats": repeats,
            "consensus_sha256": output_hash, "manifest_sha256": sha256(manifest_path), "source_sha256": source_hash,
            "counts": {str(int(code)): int(count) for code, count in zip(*np.unique(codes[clean], return_counts=True))}}
    return data, info


def run(runs, output, packet=None, labels=None, triage=None):
    if bool(packet) != bool(labels) or triage and not packet:
        raise ValueError("Supply both --packet and --labels; triage requires them")
    output = Path(output)
    if output.exists():
        raise FileExistsError(output)
    if not runs or len({name for name, _ in runs}) != len(runs):
        raise ValueError("Variant names must be nonempty and unique")
    answers, proposals = load_answers(packet, labels, triage) if packet else ([], {})
    report = {"protocol": fc.PROTOCOL, "mode": "training_diagnostic" if packet else "inspection_only",
              "label_mapping": fc.LABEL_FAMILIES, "model_mapping": fc.MODEL_FAMILIES,
              "minimum_patch_points": fc.MIN_PATCH_POINTS, "variants": {}, "paired": [],
              "interpretation": "Model opinions and training-patch diagnostics; no labels modified and no independent accuracy claim."}
    if packet:
        report["inputs_sha256"] = {"packet": sha256(Path(packet) / "packet.json"), "labels": sha256(labels)}
        if triage:
            report["inputs_sha256"]["triage"] = sha256(triage)
    rows, xyz, by_variant = [], None, {}
    for name, folder in runs:
        data, info = load_run(folder)
        if xyz is None:
            xyz = tuple(data[k] for k in ("x", "y", "z"))
        elif any(not np.array_equal(a, data[k]) for a, k in zip(xyz, ("x", "y", "z"))):
            raise ValueError("Paired variants do not contain identical eligible points in the same order")
        current = []
        for unit in answers:
            row = fc.patch_comparison(unit, **data)
            proposal = proposals.get(unit["UNIT_ID"], {})
            row.update(VARIANT=name, TRIAGE_PROPOSED=proposal.get("PROPOSED", ""), TRIAGE_TIER=proposal.get("TIER", ""))
            row["TRIAGE_EXACT_AGREE"] = row["TRIAGE_PROPOSED"] == row["LABEL"] if row["TRIAGE_PROPOSED"] else None
            current.append(row)
        report["variants"][name] = {"inspection": info, "comparison": fc.summarize(current) if packet else None}
        by_variant[name] = {row["UNIT_ID"]: row for row in current}
        rows.extend(current)
    for a, b in itertools.combinations(by_variant, 2):
        common = [uid for uid in by_variant[a] if by_variant[a][uid]["AGREE"] is not None and by_variant[b][uid]["AGREE"] is not None]
        report["paired"].append({"variants": [a, b], "common_comparable_units": len(common),
                                 "model_family_changed": sum(by_variant[a][u]["MODEL_FAMILY"] != by_variant[b][u]["MODEL_FAMILY"] for u in common),
                                 "agreement_delta": float(np.mean([int(by_variant[b][u]["AGREE"]) - int(by_variant[a][u]["AGREE"]) for u in common])) if common else None})
    # Protect the input evidence before publishing any report.
    if packet and any(sha256(path) != report["inputs_sha256"][name] for name, path in
                      [("packet", Path(packet) / "packet.json"), ("labels", labels)] + ([("triage", triage)] if triage else [])):
        raise ValueError("Comparison input changed while reading")
    output.mkdir(parents=True, exist_ok=False)
    (output / "summary.json").write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    if rows:
        with open(output / "patches.csv", "w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
            writer.writeheader()
            writer.writerows([{**row, "FAMILY_COUNTS": json.dumps(row["FAMILY_COUNTS"], sort_keys=True)} for row in rows])
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--run", action="append", required=True, metavar="NAME=DIRECTORY")
    parser.add_argument("--packet", type=Path)
    parser.add_argument("--labels", type=Path)
    parser.add_argument("--triage", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    if site.ENABLE_USER_SITE:
        raise RuntimeError("Set PYTHONNOUSERSITE=1 before starting Python")
    runs = []
    for item in args.run:
        name, separator, folder = item.partition("=")
        if not separator or not name or not folder:
            raise ValueError("Use --run NAME=DIRECTORY")
        runs.append((name, Path(folder)))
    print(json.dumps(run(runs, args.out, args.packet, args.labels, args.triage), indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
