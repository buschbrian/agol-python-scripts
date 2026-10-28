"""Blind audit of the triage AUTO candidates: draw a random sample to label, then score the result.

    python reviews/2026-09-30/audit_sample.py draw NEW_AUDIT_DIR [--n 40] [--seed 20260930]
    python reviews/2026-09-30/audit_sample.py score AUDIT_DIR [--labels labels-progress.csv] [--out score.json]

draw   picks n units at random (seeded, without replacement) from the AUTO candidates in triage/triage-proposals.csv,
       leaving out every unit a person had already labelled (those were seen while the rules were corrected, so they
       cannot test them). It writes audit-units.txt (unit IDs only, so the labeller does not see a proposal),
       audit-select.txt (a Select By Attributes expression for Pro) and audit-sample.json (seed, pool size, SHA-256 of
       the pool's sorted IDs, class mix), so the draw can be reproduced and cannot be quietly redrawn.
score  joins the human labels (the repo backup written by training_labels.bat backup) to the proposals for the audited
       units and reports how many agree, the disagreements, and the one-sided 95% Clopper-Pearson lower bound on the
       share of AUTO candidates that are right. MIXED and UNSURE count as NOT confirmed, which is the cautious reading.
       It refuses to score while any audited unit is unlabelled.

Label the audited units without opening triage/triage-proposals.csv; the proposals are only read by `score`.
"""
import argparse
import csv
import hashlib
import json
from math import comb
from pathlib import Path
import sys

import numpy as np

HERE = Path(__file__).resolve().parent
TRIAGE = HERE/"triage"/"triage-proposals.csv"
LABELS = HERE.parent/"2026-09-29"/"packets"/"training-labels"/"labels-progress.csv"
NOT_CONFIRMED = ("MIXED", "UNSURE")


def read_csv(path):
    with open(path, encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def pool_ids(proposals, labelled):
    """Sorted IDs of AUTO candidates that no person had labelled."""
    return sorted(r["UNIT_ID"] for r in proposals
                  if r["TIER"] == "AUTO_CANDIDATE" and not r["HUMAN_LABEL"] and r["UNIT_ID"] not in labelled)


def digest(ids):
    return hashlib.sha256("\n".join(ids).encode("utf-8")).hexdigest()


def draw(proposals, labelled, n, seed):
    pool = pool_ids(proposals, labelled)
    if n > len(pool):
        raise ValueError(f"Asked for {n} units but only {len(pool)} AUTO candidates are available")
    rng = np.random.default_rng(seed)
    chosen = sorted(rng.choice(pool, size=n, replace=False).tolist())
    by_id = {r["UNIT_ID"]: r for r in proposals}
    mix = {}
    for unit in chosen:
        mix[by_id[unit]["PROPOSED"]] = mix.get(by_id[unit]["PROPOSED"], 0)+1
    return {"seed": seed, "n": n, "pool_size": len(pool), "pool_sha256": digest(pool), "method":
            "numpy.random.default_rng(seed).choice(sorted pool, n, replace=False), then sorted",
            "excluded_already_labelled": sorted(labelled), "class_mix": dict(sorted(mix.items())), "units": chosen}


def lower_bound(n, correct, alpha=0.05):
    """One-sided (1 - alpha) Clopper-Pearson lower bound on a proportion with `correct` successes in n."""
    if correct <= 0:
        return 0.0
    lo, hi = 0.0, 1.0
    for _ in range(100):
        mid = (lo+hi)/2
        tail = sum(comb(n, i)*mid**i*(1-mid)**(n-i) for i in range(correct, n+1))   # P(X >= correct | p = mid)
        if tail > alpha:
            hi = mid
        else:
            lo = mid
    return hi


def score(sample, proposals, labels):
    by_proposal = {r["UNIT_ID"]: r for r in proposals}
    by_label = {r["UNIT_ID"]: r for r in labels if r.get("LABEL")}
    missing = [u for u in sample["units"] if u not in by_label]
    if missing:
        raise ValueError(f"{len(missing)} of {sample['n']} audited units are not labelled yet, e.g. {missing[:5]}")
    rows, per_class = [], {}
    for unit in sample["units"]:
        proposed, human = by_proposal[unit]["PROPOSED"], by_label[unit]["LABEL"]
        agree = proposed == human
        rows.append({"unit": unit, "proposed": proposed, "human": human, "agree": agree,
                     "not_confirmed": human in NOT_CONFIRMED})
        entry = per_class.setdefault(proposed, {"audited": 0, "agree": 0})
        entry["audited"] += 1
        entry["agree"] += int(agree)
    correct = sum(r["agree"] for r in rows)
    n = len(rows)
    return {"audited": n, "agree": correct, "disagree": n-correct,
            "agreement": round(correct/n, 4), "lower_bound_95": round(lower_bound(n, correct), 4),
            "by_class": dict(sorted(per_class.items())),
            "disagreements": [r for r in rows if not r["agree"]],
            "reading": "MIXED and UNSURE are counted as not confirmed. The bound is about the AUTO candidates as a "
                       "whole; per-class numbers are too small to bound on their own."}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    d = sub.add_parser("draw"); d.add_argument("out", type=Path)
    d.add_argument("--n", type=int, default=40); d.add_argument("--seed", type=int, default=20260930)
    d.add_argument("--triage", type=Path, default=TRIAGE); d.add_argument("--labels", type=Path, default=LABELS)
    s = sub.add_parser("score"); s.add_argument("audit", type=Path)
    s.add_argument("--triage", type=Path, default=TRIAGE); s.add_argument("--labels", type=Path, default=LABELS)
    s.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    if args.command == "draw":
        if args.out.exists():
            raise FileExistsError(f"Choose a new audit folder: {args.out}")
        proposals = read_csv(args.triage)
        labelled = {r["UNIT_ID"] for r in read_csv(args.labels) if r.get("LABEL")} if args.labels.is_file() else set()
        sample = draw(proposals, labelled, args.n, args.seed)
        args.out.mkdir(parents=True)
        (args.out/"audit-units.txt").write_text("\n".join(sample["units"])+"\n", encoding="utf-8")
        quoted = ",".join(f"'{u}'" for u in sample["units"])
        (args.out/"audit-select.txt").write_text(f"UNIT_ID IN ({quoted})\n", encoding="utf-8")
        (args.out/"audit-sample.json").write_text(json.dumps(sample, indent=1), encoding="utf-8")
        print(f"Drew {sample['n']} of {sample['pool_size']} candidates (seed {sample['seed']}); class mix {sample['class_mix']}")
        print(f"Wrote {args.out}. Label those units WITHOUT opening {args.triage.name}.")
    else:
        sample = json.loads((args.audit/"audit-sample.json").read_text(encoding="utf-8"))
        result = score(sample, read_csv(args.triage), read_csv(args.labels))
        text = json.dumps(result, indent=1)
        if args.out:
            args.out.write_text(text, encoding="utf-8")
        print(text)


if __name__ == "__main__":
    main()
