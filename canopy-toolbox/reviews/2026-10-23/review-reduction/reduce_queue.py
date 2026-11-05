r"""Making the footprint review queue smaller (October 23, 2026): size the four ideas on the real data, draw the
pre-registered sample for the attached candidates, and later evaluate the proposed rule on Brian's answers.

    python -I reviews/2026-10-23/review-reduction/reduce_queue.py size        comparison figures -> size.json
    python -I reviews/2026-10-23/review-reduction/reduce_queue.py sample      draw the sample once -> sample.csv, eyes.csv
    python -I reviews/2026-10-23/review-reduction/reduce_queue.py evaluate    after Brian answers: the rule's verdict

ArcGIS Pro env millcreek-py3, PYTHONNOUSERSITE=1. Read-only on the candidates, the county footprints, the alignment
classes and the review data; writes only beside this file. No rule is applied to any data here: `evaluate` reports
whether the pre-registered rule passes, and Brian decides. The protocol is PROTOCOL.md beside this file, committed
before any sample answer exists.
"""
import argparse
import json
import math
from pathlib import Path
import sys

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2]))
from canopy.lidar_root import lidar_root  # noqa: E402

RUNS = lidar_root()/"2023-salt-lake-valley"/"runs"
LIB = RUNS/"millcreek-products-20261022"
CAND = RUNS/"footprint-candidates-lidar-20261023"
ALIGN = RUNS/"county-alignment-20261023"
REVIEW = RUNS/"footprint-review-20261023"/"data"
SEED = 20261023
# Seconds per answer, from Brian's label-page pace (median 4 s, about 6 s with pauses) plus a second to load
PACE = {"attached": 5, "pairs": 10, "parcel": 10, "swap": 6, "sample": 6}
# Strata of the attached candidates the rule may settle, with sample sizes (about 300 in all)
STRATA = [  # (name, group(s), min m2, max m2, n)
    ("S1 corner of a county roof", ("attached_same_roof",), 0, 15, 50),
    ("S2 lower roof, under 20 m2", ("attached_lower",), 0, 20, 50),
    ("S3 lower roof, 20-40 m2", ("attached_lower",), 20, 40, 40),
    ("S4 other, under 20 m2", ("attached",), 0, 20, 50),
    ("S5 other, 20-40 m2", ("attached",), 20, 40, 50),
    ("S6 lower or other, 40-80 m2", ("attached", "attached_lower"), 40, 80, 60),
]
EYES_MIN_M2 = 80   # attached pieces this big always get a look


def load():
    import geopandas as gpd
    import pandas as pd
    idx = json.loads((REVIEW/"index.json").read_text(encoding="utf-8"))
    items = pd.DataFrame(idx["items"])
    cand = gpd.read_file(CAND/"candidates.gdb", layer="candidates")
    cand["GROUP"] = cand.CAND_ID.map(dict(zip(items.id, items.group)))
    cls = pd.read_csv(ALIGN/"classes.csv", dtype={"SOURCE_ID": str}).set_index("SOURCE_ID")
    cand["F_CLASS"] = cand.NEAR_FP_SOURCE_ID.map(cls.CLASS)
    cand["F_CANOPY"] = cand.NEAR_FP_SOURCE_ID.map(cls.CANOPY)
    cand["F_BEST"] = cand.NEAR_FP_SOURCE_ID.map(cls.ROOF_BEST)
    return items, cand, cls


def risky(df):
    """The county building next to the piece can't be trusted as the thing to merge into: rebuilt or gone, trees over
    30% or more of it, or under 80% roof under any shift."""
    return (df.F_CLASS == "REBUILT_OR_GONE") | (df.F_CANOPY >= 0.3) | (df.F_BEST < 0.8)


def attached(cand):
    return cand[cand.GROUP.isin(["attached", "attached_lower", "attached_same_roof"])].copy()


def stratum_of(r):
    for name, groups, lo, hi, _ in STRATA:
        if r.GROUP in groups and lo <= r.FOOTPRINT_M2 < hi:
            return name
    return None


def size():
    import geopandas as gpd
    import pandas as pd
    items, cand, cls = load()
    att = attached(cand)
    pairs = items[(items.queue == "pairs") & (items.group != "explained_by_alignment")]
    county = gpd.read_file(LIB/"buildings.gdb", layer="building_heights").set_index("SOURCE_ID")

    def pnorm(p):
        return None if p is None or isinstance(p, float) else "".join(ch for ch in str(p) if ch.isalnum())
    units = pd.concat([pd.DataFrame({"id": att.CAND_ID, "P": att.PARCEL_ID.map(pnorm)}),
                       pd.DataFrame({"id": pairs.id, "P": [pnorm(county.loc[i[2:]].PARCEL_ID) for i in pairs.id]})])
    per = units.dropna(subset=["P"]).groupby("P").size()
    touched = set(att.NEAR_FP_SOURCE_ID) | {i[2:] for i in pairs.id}
    t = cls.loc[[s for s in touched if s in cls.index]]
    t_risky = (t.CLASS == "REBUILT_OR_GONE") | (t.CANOPY >= 0.3) | (t.ROOF_BEST < 0.8)
    att["STRATUM"] = [stratum_of(r) for r in att.itertuples()]
    eyes = att[(att.FOOTPRINT_M2 >= EYES_MIN_M2) | risky(att)]
    settle = att[~att.CAND_ID.isin(eyes.CAND_ID) & att.STRATUM.notna()]
    n_sample = sum(s[4] for s in STRATA)
    hours = lambda n, k: round(n * PACE[k] / 3600, 1)  # noqa: E731
    baseline = len(att) * PACE["attached"] + len(pairs) * PACE["pairs"]
    out = {
        "baseline": {"attached": len(att), "pairs": len(pairs), "hours": round(baseline / 3600, 1)},
        "idea1_alignment": {"attached": len(att), "pairs": len(pairs), "hours": round(baseline / 3600, 1),
                            "note": "already measured: 6,213 -> 6,209 candidates and 458 -> 456 pairs"},
        "idea2_parcels": {"items": len(units), "parcels": int(len(per)), "parcels_with_one_item": int((per == 1).sum()),
                          "parcels_with_two": int((per == 2).sum()), "parcels_with_3_or_more": int((per >= 3).sum()),
                          "items_without_parcel": int(units.P.isna().sum()), "hours": hours(len(per), "parcel")},
        "idea3_sample": {"sample": n_sample, "settled_by_rule_if_all_strata_pass": len(settle),
                         "always_eyes": len(eyes), "eyes_80m2_or_more": int((eyes.FOOTPRINT_M2 >= EYES_MIN_M2).sum()),
                         "eyes_risky_county_building": int(risky(eyes).sum()),
                         "strata_sizes": settle.STRATUM.value_counts().sort_index().to_dict(),
                         "hours_best_case": round((n_sample * PACE["sample"] + len(eyes) * PACE["attached"]
                                                   + len(pairs) * PACE["pairs"]) / 3600, 1)},
        "idea4_swaps": {"county_buildings_touched": len(touched), "pieces_per_building_mean": round(
                            float(att.groupby("NEAR_FP_SOURCE_ID").size().mean()), 2),
                        "touched_risky": int(t_risky.sum()), "attached_on_safe_buildings": int((~risky(att)).sum()),
                        "attached_on_risky_buildings": int(risky(att).sum()),
                        "classes_of_touched": t.CLASS.value_counts().to_dict(),
                        "hours_if_each_swap_reviewed": hours(len(touched), "swap")},
        "pace_seconds": PACE,
    }
    (HERE/"size.json").write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")
    print(json.dumps(out, indent=1, default=str))


def sample():
    import pandas as pd
    if (HERE/"sample.csv").exists():
        raise FileExistsError("The sample is drawn once; delete sample.csv only if no answer has been given on it")
    items, cand, _ = load()
    att = attached(cand)
    att["STRATUM"] = [stratum_of(r) for r in att.itertuples()]
    eyes = att[(att.FOOTPRINT_M2 >= EYES_MIN_M2) | risky(att)]
    pool = att[~att.CAND_ID.isin(eyes.CAND_ID) & att.STRATUM.notna()]
    rng = np.random.default_rng(SEED)
    rows = []
    for name, *_, n in STRATA:
        part = pool[pool.STRATUM == name].sort_values("CAND_ID")
        pick = part.iloc[np.sort(rng.choice(len(part), size=min(n, len(part)), replace=False))]
        rows += [{"CAND_ID": c, "STRATUM": name, "STRATUM_SIZE": len(part)} for c in pick.CAND_ID]
    pd.DataFrame(rows).to_csv(HERE/"sample.csv", index=False)
    eyes.assign(REASON=np.where(eyes.FOOTPRINT_M2 >= EYES_MIN_M2, "80 m2 or more", "risky county building"))[
        ["CAND_ID", "GROUP", "FOOTPRINT_M2", "REASON"]].to_csv(HERE/"eyes.csv", index=False)
    print(f"sample {len(rows)} ({SEED=}), always-eyes {len(eyes)}")


def wilson_upper(k, n, z=1.96):
    if n == 0:
        return 1.0
    p = k / n
    return min(1.0, (p + z * z / (2 * n) + z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / (1 + z * z / n))


def evaluate():
    """The pre-registered decision (PROTOCOL.md), stratum by stratum, on the answers given so far."""
    import pandas as pd
    s = pd.read_csv(HERE/"sample.csv")
    ans = pd.read_csv(REVIEW/"answers"/"footprint-review-answers.csv")
    a = s.merge(ans[["ITEM_ID", "ANSWER"]], left_on="CAND_ID", right_on="ITEM_ID", how="left")
    out = {}
    for name, g in a.groupby("STRATUM"):
        done = g[g.ANSWER.notna() & (g.ANSWER != "UNSURE")]
        n, size_ = len(done), int(g.STRATUM_SIZE.iloc[0])
        accept = int((done.ANSWER == "ACCEPT").sum())
        not_part = int((done.ANSWER != "PART_OF_EXISTING").sum())
        up_a, up_m = wilson_upper(accept, n), wilson_upper(not_part, n)
        complete = len(g[g.ANSWER.notna()]) == len(g)
        out[name] = {
            "answered": int(g.ANSWER.notna().sum()), "of": len(g), "unsure": int((g.ANSWER == "UNSURE").sum()),
            "accept": accept, "not_part_of_existing": not_part, "answers": done.ANSWER.value_counts().to_dict(),
            "rule_A_no_separate_building": "pass" if complete and up_a <= 0.10 else ("fail" if complete else "waiting"),
            "rule_A_expected_wrong": round(size_ * accept / n) if n else None,
            "rule_A_upper_95": round(size_ * up_a),
            "rule_B_merge_into_county": "pass" if complete and up_m <= 0.15 else ("fail" if complete else "waiting"),
            "rule_B_expected_wrong": round(size_ * not_part / n) if n else None,
            "rule_B_upper_95": round(size_ * up_m), "stratum_size": size_}
    (HERE/"evaluation.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps(out, indent=1))


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("step", choices=("size", "sample", "evaluate"))
    a = p.parse_args(argv)
    {"size": size, "sample": sample, "evaluate": evaluate}[a.step]()


if __name__ == "__main__":
    main()
