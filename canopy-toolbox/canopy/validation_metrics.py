"""Sampling design and accuracy metrics for the validation harness. No arcpy.

Reference labels describe what is on the ground at a location (a baseline treetop,
a CHM cell centre) or whether a baseline crown outline is right. Strata are fixed
from the BASELINE run when the sample is drawn. Any other run is scored by asking
what it says at the same locations, so every variant is compared on the same labels.

All estimates are stratified: each labelled unit in stratum h stands for
N_h / n_h population units, where n_h counts usable (labelled, not UNSURE) units.
Units are reviewed in a random order, so any labelled prefix is a random subsample
of each stratum. Confidence intervals are Wilson intervals within a stratum and
stratified percentile bootstrap intervals for weighted totals and ratios.
"""
from __future__ import annotations

import hashlib
import math

import numpy as np
from .matching import match_candidates

CANOPY_M = 2.0          # lowest detection band; the proposed tree definition
Z95 = 1.959963984540054

POINT_LABELS = ("TREE", "ROOF_OR_BUILDING", "OTHER_STRUCTURE", "SHRUB_UNDER_2M",
                "GROUND_OR_OPEN", "UNSURE")
CROWN_LABELS = ("CORRECT", "MERGED", "SPLIT", "NOT_A_TREE", "UNSURE")
YES_NO = ("YES", "NO", "UNSURE")

# Treetop candidates (baseline trees_review). SEAM takes precedence; the building
# context is kept on every unit as CONTEXT for domain summaries.
ROOF_LEVEL_M = 0.5      # candidate no more than this above the local roof
OVERHANG_M = 2.0        # candidate more than this above the local roof
NEAR_BUILDING_M = 1.0   # a class-6 point within this horizontal distance
SMALL_CROWN_M2 = 3.0
TREETOP_TARGETS = {"ROOF_LEVEL": 40, "ROOF_MID": 20, "ABOVE_ROOF": 40,
                   "SMALL_CROWN": 40, "NORMAL": 40, "SEAM": 30}
# Baseline non-canopy cells (omission search).
OMISSION_TARGETS = {"OM_ROOF": 20, "OM_NEAR_BLDG": 25, "OM_DENSE": 20,
                    "OM_EDGE": 15, "OM_OPEN": 10, "OM_NODATA": 10}
CELL_NEAR_M = 3.0       # "near building" for cells: within 3 m of a class-6 cell
DENSE_RADIUS_M = 5.0
DENSE_SHARE = 0.5
EDGE_M = 3.0
# Observed CHM cells for cell-level canopy error.
CELL_TARGETS = {"CANOPY_NEAR": 30, "CANOPY_FAR": 30, "NONCAN_NEAR": 30, "NONCAN_FAR": 30}
# Baseline crown polygons.
CROWN_BLDG_M2 = 1.0     # crown overlaps building cells (dilated 1 m) by at least this
CROWN_TARGETS = {"CR_BLDG": 15, "CR_SMALL": 15, "CR_MEDIUM": 15, "CR_LARGE": 15}
CROWN_SMALL_MAX_M2, CROWN_LARGE_MIN_M2 = 10.0, 50.0

MATCH_RADIUS_M = 1.5    # a baseline candidate survives in a variant if a variant
                        # candidate lies within this distance
CROWN_SAME_IOU = 0.8    # a variant crown inherits a baseline crown label at this IoU
MIN_STRATUM_N = 5       # fewer usable units than this is flagged as unstable


# ---------------------------------------------------------------- stratification

def treetop_context(building_distance, height, roof_height):
    """Building context of one candidate; roof_height is None when unknown."""
    if building_distance is None or not building_distance <= NEAR_BUILDING_M:
        return "AWAY"
    if roof_height is None or not math.isfinite(roof_height):
        return "ROOF_MID"
    above = height - roof_height
    if above <= ROOF_LEVEL_M:
        return "ROOF_LEVEL"
    return "ABOVE_ROOF" if above > OVERHANG_M else "ROOF_MID"


def treetop_stratum(seam, context, crown_area):
    if seam:
        return "SEAM"
    if context != "AWAY":
        return context
    return "SMALL_CROWN" if crown_area < SMALL_CROWN_M2 else "NORMAL"


def crown_stratum(area, building_overlap):
    if building_overlap >= CROWN_BLDG_M2:
        return "CR_BLDG"
    if area < CROWN_SMALL_MAX_M2:
        return "CR_SMALL"
    return "CR_LARGE" if area >= CROWN_LARGE_MIN_M2 else "CR_MEDIUM"


def cell_strata(chm, building_cells, cell):
    """Return (omission_code, cell_code, building_distance, canopy_distance) arrays.

    Codes are stratum names or '' for cells outside that frame. building_cells marks
    CHM cells holding at least one class-6 return.
    """
    from scipy import ndimage
    observed = np.isfinite(chm)
    canopy = observed & (chm >= CANOPY_M)
    bdist = ndimage.distance_transform_edt(~building_cells) * cell
    cdist = ndimage.distance_transform_edt(~canopy) * cell
    radius = int(round(DENSE_RADIUS_M / cell))
    yy, xx = np.ogrid[-radius:radius+1, -radius:radius+1]
    disk = (xx*xx + yy*yy <= radius*radius).astype(float)
    share = ndimage.convolve(canopy.astype(float), disk, mode="constant") / disk.sum()
    near = bdist <= CELL_NEAR_M
    omission = np.full(chm.shape, "", dtype=object)
    frame = observed & ~canopy
    omission[~observed] = "OM_NODATA"
    omission[frame & (cdist > EDGE_M)] = "OM_OPEN"
    omission[frame & (cdist <= EDGE_M)] = "OM_EDGE"
    omission[frame & (share >= DENSE_SHARE)] = "OM_DENSE"
    omission[frame & near] = "OM_NEAR_BLDG"
    omission[frame & building_cells] = "OM_ROOF"
    cells = np.full(chm.shape, "", dtype=object)
    cells[canopy & near] = "CANOPY_NEAR"
    cells[canopy & ~near] = "CANOPY_FAR"
    cells[frame & near] = "NONCAN_NEAR"
    cells[frame & ~near] = "NONCAN_FAR"
    return omission, cells, bdist, cdist


# ---------------------------------------------------------------- reproducible draws

def seed_for(seed, *parts):
    """Stable 63-bit seed for one (sample, tile, stratum)."""
    text = "|".join([str(seed), *map(str, parts)])
    return int.from_bytes(hashlib.sha256(text.encode()).digest()[:8], "little") >> 1


def draw(keys, n, seed):
    """Simple random sample without replacement, independent of input order.

    Returns the chosen keys in a random order.
    """
    keys = np.sort(np.asarray(keys))
    if len(np.unique(keys)) != len(keys):
        raise ValueError("Sampling keys must be unique")
    n = min(int(n), len(keys))
    if n <= 0:
        return []
    chosen = np.random.default_rng(seed).choice(len(keys), size=n, replace=False)
    return keys[chosen].tolist()


def review_order(units, seed):
    """Assign BATCH and a blind REVIEW_ORDER to units = [(key, stratum_key), ...].

    Each stratum's first ceil(n/2) units (in draw order) form batch 1. All batch-1
    units come first in a random interleaving, then batch 2. Any prefix of the order
    is a random subsample within every stratum. Returns {key: (order, batch)}.
    """
    rank = {}
    for key, stratum in units:
        rank.setdefault(stratum, []).append(key)
    batches = {1: [], 2: []}
    for stratum, keys in rank.items():
        half = math.ceil(len(keys) / 2)
        for i, key in enumerate(keys):
            batches[1 if i < half else 2].append(key)
    rng = np.random.default_rng(seed)
    result, order = {}, 0
    for batch in (1, 2):
        keys = sorted(batches[batch], key=str)
        for i in rng.permutation(len(keys)):
            order += 1
            result[keys[i]] = (order, batch)
    return result


# ---------------------------------------------------------------- intervals

def wilson(k, n, z=Z95):
    """Wilson score interval for k successes in n trials: (p, low, high)."""
    if n <= 0:
        return (None, None, None)
    p = k / n
    denominator = 1 + z*z/n
    centre = (p + z*z/(2*n)) / denominator
    half = z*math.sqrt(p*(1-p)/n + z*z/(4*n*n)) / denominator
    return (p, max(0.0, centre-half), min(1.0, centre+half))


class Design:
    """One stratified sample: per-unit stratum keys, stratum populations, and
    per-unit quantities (only usable units; unusable ones are dropped here)."""

    def __init__(self, strata, population, values):
        self.strata = np.asarray(strata, dtype=object)
        self.population = dict(population)
        if any(not math.isfinite(float(n)) or int(n) != n or n < 0 for n in self.population.values()):
            raise ValueError("Stratum populations must be nonnegative integers")
        self.values = {k: np.asarray(v, dtype=float) for k, v in values.items()}
        for name, array in self.values.items():
            if array.shape != self.strata.shape:
                raise ValueError(f"{name} does not have one value per unit")
            if not np.isfinite(array).all():
                raise ValueError(f"{name} has missing values; drop unusable units first")
        unknown = set(self.strata) - set(self.population)
        if unknown:
            raise ValueError(f"Units in strata without a population: {sorted(unknown)}")
        self.groups = {h: np.flatnonzero(self.strata == h) for h in self.population}
        if any(len(idx) > self.population[h] for h, idx in self.groups.items()):
            raise ValueError("Usable sample count exceeds its stratum population")

    def covered(self):
        return [h for h, idx in self.groups.items() if len(idx) and self.population[h] > 0]

    def missing(self):
        return sorted(h for h, idx in self.groups.items() if not len(idx) and self.population[h] > 0)

    def coverage(self):
        total = sum(self.population.values())
        return sum(self.population[h] for h in self.covered()) / total if total else 0.0

    def totals(self, index=None):
        """Estimated population totals of every value, over covered strata."""
        result = dict.fromkeys(self.values, 0.0)
        for h in self.covered():
            idx = self.groups[h] if index is None else index[h]
            for name, array in self.values.items():
                result[name] += self.population[h] * float(array[idx].mean())
        return result

    def resample(self, rng):
        return {h: self.groups[h] if len(self.groups[h]) == self.population[h] else
                rng.choice(self.groups[h], size=len(self.groups[h]), replace=True)
                for h in self.covered()}


def estimate(designs, statistic, replicates=2000, seed=0, alpha=0.05):
    """Point estimate and stratified bootstrap interval of statistic(totals).

    designs: {name: Design}; statistic receives {name: totals} and returns a dict
    of named scalars (None when undefined). Each design is resampled independently
    within its strata.
    """
    if replicates < 2 or not 0 < alpha < 1:
        raise ValueError("Require at least two replicates and alpha between zero and one")
    point = statistic({k: d.totals() for k, d in designs.items()})
    census = all(not d.missing() and all(len(d.groups[h]) == d.population[h]
                 for h in d.covered()) for d in designs.values())
    # An empirical bootstrap cannot learn the unobserved category in a homogeneous
    # non-census stratum. Suppress headline intervals rather than claim certainty.
    homogeneous = any(len(idx) < d.population[h] and all(
        np.all(v[idx] == v[idx[0]]) for v in d.values.values())
        for d in designs.values() for h in d.covered() for idx in [d.groups[h]])
    rng = np.random.default_rng(seed)
    draws = {k: [] for k in point}
    for _ in range(replicates):
        value = statistic({k: d.totals(d.resample(rng)) for k, d in designs.items()})
        for key in point:
            if value.get(key) is not None and math.isfinite(value[key]):
                draws[key].append(value[key])
    result = {}
    for key, value in point.items():
        sample = draws[key]
        if value is None or not math.isfinite(value) or len(sample) < replicates/2:
            result[key] = {"estimate": value, "low": None, "high": None,
                           "interval_status": "UNDEFINED_OR_INSUFFICIENT_DRAWS"}
        elif census:
            result[key] = {"estimate": value, "low": value, "high": value,
                           "interval_status": "CENSUS"}
        else:
            low, high = np.quantile(sample, [alpha/2, 1-alpha/2])
            suppressed = homogeneous or low == high
            result[key] = {"estimate": value,
                           "low": None if suppressed else float(low),
                           "high": None if suppressed else float(high),
                           "interval_status": "HOMOGENEOUS_OR_DEGENERATE_SAMPLE" if suppressed else "BOOTSTRAP"}
    return result


def _ratio(numerator, denominator):
    return numerator/denominator if denominator else None


def _status(usable, design):
    if not usable:
        return "NO_LABELS"
    return "PARTIAL" if design.missing() else "OK"


def _stratum_rows(units, population, success, applicable=lambda u: True):
    """Unweighted per-stratum counts with a Wilson interval of success among usable."""
    rows = {}
    for h, size in sorted(population.items()):
        mine = [u for u in units if u["stratum"] == h]
        usable = [u for u in mine if u["usable"] and applicable(u)]
        k = sum(1 for u in usable if success(u))
        p, lo, hi = wilson(k, len(usable))
        rows[h] = {"population": size, "sampled": len(mine),
                   "labelled": sum(1 for u in mine if u["label"] is not None),
                   "unsure": sum(1 for u in mine if u["label"] == "UNSURE"),
                   "usable": len(usable), "successes": k,
                   "share": p, "low": lo, "high": hi,
                   "unstable": 0 < len(usable) < MIN_STRATUM_N}
    return rows


def _prepare(units, population, labels=POINT_LABELS):
    """Mark usability; a unit is usable when labelled and not UNSURE."""
    prepared = []
    for unit in units:
        label = unit.get("label")
        label = None if label in (None, "") else str(label)
        if label is not None and label not in labels:
            raise ValueError(f"Unknown reference label: {label}")
        prepared.append({**unit, "label": label,
                         "usable": label is not None and label != "UNSURE"})
    unknown = {u["stratum"] for u in prepared} - set(population)
    if unknown:
        raise ValueError(f"Units in strata without a population: {sorted(unknown)}")
    return prepared


def _envelope(status, design, usable_count, units):
    return {"status": status, "units": len(units),
            "labelled": sum(1 for u in units if u["label"] is not None),
            "usable": usable_count, "unsure": sum(1 for u in units if u["label"] == "UNSURE"),
            "population_coverage": design.coverage(), "strata_without_labels": design.missing(),
            "inference_assumption": "Usable labels must be a random subsample within each stratum; selective nonresponse/UNSURE may bias estimates.",
            "estimand_scope": "COVERED_REFERENCE_STRATA"}


# ---------------------------------------------------------------- treetops

def score_treetops(units, population, new_candidates=0, variant_candidates=None,
                   replicates=2000, seed=0):
    """Precision of candidates, and what a variant removed.

    units: dicts with stratum, label (POINT_LABELS or None) and retained (bool: the
    run still has a candidate within MATCH_RADIUS_M of this baseline candidate).
    population: {stratum: baseline candidate count}. new_candidates: run candidates
    with no baseline candidate within MATCH_RADIUS_M; they were never sampled, so
    precision is also given with them all counted as false or all as true.
    """
    units = _prepare(units, population)
    if int(new_candidates) != new_candidates or new_candidates < 0:
        raise ValueError("New candidate count must be a nonnegative integer")
    if variant_candidates is not None:
        if int(variant_candidates) != variant_candidates or variant_candidates < 0:
            raise ValueError("Variant candidate count must be a nonnegative integer")
        if sum(bool(u["retained"]) for u in units) + new_candidates > variant_candidates:
            raise ValueError("Observed retained plus new candidates exceeds exact variant count")
    usable = [u for u in units if u["usable"]]
    y = [1.0 if u["label"] == "TREE" else 0.0 for u in usable]
    r = [1.0 if u["retained"] else 0.0 for u in usable]
    y, r = np.array(y), np.array(r)
    design = Design([u["stratum"] for u in usable], population, {
        "kept": r, "kept_tree": y*r, "kept_false": (1-y)*r,
        "removed_tree": y*(1-r), "removed_false": (1-y)*(1-r), "tree": y})
    status = _status(usable, design)
    result = _envelope(status, design, len(usable), units)
    result["per_stratum"] = _stratum_rows(units, population, lambda u: u["label"] == "TREE",
                                          lambda u: u["retained"])
    result["retained_by_stratum"] = {
        h: sum(1 for u in units if u["stratum"] == h and u["retained"]) for h in population}
    result["new_candidates"] = int(new_candidates)
    result["matching_method"] = "ONE_TO_ONE_MAX_CARDINALITY_MIN_DISTANCE"
    result["estimand_scope"] = "MATCHED_BASELINE_CANDIDATES_IN_COVERED_STRATA"
    if variant_candidates is not None:
        result["variant_candidates"] = int(variant_candidates)
    if status == "NO_LABELS":
        return result

    def statistic(t):
        t = t["s"]
        kept = t["kept"]
        low = _ratio(t["kept_tree"], kept + new_candidates)
        high = _ratio(t["kept_tree"] + new_candidates, kept + new_candidates)
        return {"precision": _ratio(t["kept_tree"], kept),
                "precision_if_new_false": low, "precision_if_new_true": high,
                "baseline_precision": _ratio(t["tree"], sum(t[k] for k in ("kept", "removed_tree",
                                                                           "removed_false"))),
                "candidates_kept": kept, "true_kept": t["kept_tree"], "false_kept": t["kept_false"],
                "true_removed": t["removed_tree"], "false_removed": t["removed_false"],
                "share_of_false_removed": _ratio(t["removed_false"], t["removed_false"]+t["kept_false"]),
                "share_of_true_removed": _ratio(t["removed_tree"], t["removed_tree"]+t["kept_tree"])}
    result["estimates"] = estimate({"s": design}, statistic, replicates, seed)
    if variant_candidates is not None:
        result["variant_candidates"] = int(variant_candidates)
    return result


# ---------------------------------------------------------------- CHM cells

def score_cells(units, population, cell_area, mapped_in_frame=None, replicates=2000, seed=0):
    """Cell-level canopy commission, omission and area bias.

    units: dicts with stratum, label and canopy (bool: the run's CHM >= 2 m at the
    cell). population: {stratum: cell count}. mapped_in_frame: the run's exact canopy
    cell count inside the sampled frame (for reporting beside the estimate).
    """
    units = _prepare(units, population)
    usable = [u for u in units if u["usable"]]
    y = np.array([1.0 if u["label"] == "TREE" else 0.0 for u in usable])
    c = np.array([1.0 if u["canopy"] else 0.0 for u in usable])
    design = Design([u["stratum"] for u in usable], population, {
        "mapped": c, "tree": y, "false_canopy": c*(1-y), "missed": y*(1-c), "hit": y*c})
    status = _status(usable, design)
    result = _envelope(status, design, len(usable), units)
    result["per_stratum"] = _stratum_rows(units, population, lambda u: u["label"] == "TREE")
    result["mapped_canopy_m2_in_frame"] = None if mapped_in_frame is None else mapped_in_frame*cell_area
    if status == "NO_LABELS":
        return result

    def statistic(t):
        t = t["s"]
        return {"commission": _ratio(t["false_canopy"], t["mapped"]),
                "omission": _ratio(t["missed"], t["tree"]),
                "true_canopy_m2": t["tree"]*cell_area,
                "mapped_canopy_m2": t["mapped"]*cell_area,
                "false_canopy_m2": t["false_canopy"]*cell_area,
                "missed_canopy_m2": t["missed"]*cell_area,
                "area_bias_m2": (t["false_canopy"]-t["missed"])*cell_area,
                "relative_bias": _ratio(t["false_canopy"]-t["missed"], t["tree"])}
    result["estimates"] = estimate({"s": design}, statistic, replicates, seed)
    return result


# ---------------------------------------------------------------- omission search

def score_omission(units, population, cell_area, replicates=2000, seed=0):
    """Tree canopy hidden in baseline non-canopy cells, and whether a run recovers it.

    units: dicts with stratum, label, canopy (the run's CHM >= 2 m at the point) and
    candidate_near (the run has a candidate within 5 m). population: {stratum: cells}.
    """
    units = _prepare(units, population)
    usable = [u for u in units if u["usable"]]
    y = np.array([1.0 if u["label"] == "TREE" else 0.0 for u in usable])
    c = np.array([1.0 if u["canopy"] else 0.0 for u in usable])
    d = np.array([1.0 if u.get("candidate_near") else 0.0 for u in usable])
    design = Design([u["stratum"] for u in usable], population, {
        "tree": y, "still_missed": y*(1-c), "recovered": y*c, "added_false": (1-y)*c,
        "missed_no_candidate": y*(1-c)*(1-d), "cells": np.ones_like(y)})
    status = _status(usable, design)
    result = _envelope(status, design, len(usable), units)
    result["per_stratum"] = _stratum_rows(units, population, lambda u: u["label"] == "TREE")
    if status == "NO_LABELS":
        return result

    def statistic(t):
        t = t["s"]
        return {"tree_share_of_noncanopy": _ratio(t["tree"], t["cells"]),
                "baseline_missed_m2": t["tree"]*cell_area,
                "missed_m2": t["still_missed"]*cell_area,
                "recovered_m2": t["recovered"]*cell_area,
                "false_added_m2": t["added_false"]*cell_area,
                "missed_without_nearby_candidate_m2": t["missed_no_candidate"]*cell_area}
    result["estimates"] = estimate({"s": design}, statistic, replicates, seed)
    return result


def combined_omission_rate(cell_units, cell_population, omission_units, omission_population,
                           replicates=2000, seed=0):
    """Missed tree canopy / all tree canopy, using canopy strata of the cell sample
    for detected canopy and the omission sample for non-canopy. Both samples must be
    scored on the same run (canopy flags from that run)."""
    cell_units = [u for u in _prepare(cell_units, cell_population)
                  if u["usable"] and u["stratum"].split("|")[-1].startswith("CANOPY")]
    om_units = [u for u in _prepare(omission_units, omission_population) if u["usable"]]
    if not cell_units or not om_units:
        return {"status": "NO_LABELS"}
    cell_pop = {h: n for h, n in cell_population.items() if h.split("|")[-1].startswith("CANOPY")}
    a = Design([u["stratum"] for u in cell_units], cell_pop, {
        "hit": [1.0 if u["label"] == "TREE" and u["canopy"] else 0.0 for u in cell_units],
        "missed": [1.0 if u["label"] == "TREE" and not u["canopy"] else 0.0 for u in cell_units]})
    b = Design([u["stratum"] for u in om_units], omission_population, {
        "hit": [1.0 if u["label"] == "TREE" and u["canopy"] else 0.0 for u in om_units],
        "missed": [1.0 if u["label"] == "TREE" and not u["canopy"] else 0.0 for u in om_units]})

    def statistic(t):
        hit = t["a"]["hit"] + t["b"]["hit"]
        missed = t["a"]["missed"] + t["b"]["missed"]
        return {"omission_rate": _ratio(missed, hit + missed)}
    status = "PARTIAL" if a.missing() or b.missing() else "OK"
    return {"status": status, **estimate({"a": a, "b": b}, statistic, replicates, seed)}


# ---------------------------------------------------------------- crowns

def score_crowns(units, population, replicates=2000, seed=0):
    """Crown outline quality. units: stratum, label (CROWN_LABELS), roof (YES_NO) and
    same (bool: the run has a crown at IoU >= CROWN_SAME_IOU, so the label carries
    over). Crowns a run changed are counted, not scored."""
    units = _prepare(units, population, CROWN_LABELS)
    respondents = [u for u in units if u["usable"]]
    for unit in units:
        unit["changed"] = not unit.get("same", True)
        unit["usable"] = unit["usable"] and not unit["changed"]
    usable = [u for u in units if u["usable"]]
    values = {name: [1.0 if u["label"] == name and not u["changed"] else 0.0 for u in respondents]
              for name in CROWN_LABELS if name != "UNSURE"}
    values["roof"] = [1.0 if u.get("roof") == "YES" and not u["changed"] else 0.0 for u in respondents]
    values["roof_known"] = [0.0 if u.get("roof") in (None, "", "UNSURE") or u["changed"] else 1.0 for u in respondents]
    values["crowns"] = [0.0 if u["changed"] else 1.0 for u in respondents]
    design = Design([u["stratum"] for u in respondents], population, values)
    status = _status(usable, design)
    if status == "OK" and any(u["changed"] for u in units):
        status = "PARTIAL"
    result = _envelope(status, design, len(usable), units)
    result["estimand_scope"] = "UNCHANGED_MATCHED_BASELINE_CROWNS"
    result["changed_by_run"] = sum(1 for u in units if u["changed"])
    result["per_stratum"] = _stratum_rows(units, population, lambda u: u["label"] == "CORRECT")
    if status == "NO_LABELS":
        return result

    def statistic(t):
        t = t["s"]
        shares = {f"share_{name.lower()}": _ratio(t[name], t["crowns"])
                  for name in CROWN_LABELS if name != "UNSURE"}
        shares["share_includes_roof"] = _ratio(t["roof"], t["roof_known"])
        return shares
    result["estimates"] = estimate({"s": design}, statistic, replicates, seed)
    return result


# ---------------------------------------------------------------- comparison table

HEADLINE = [
    ("treetops", "precision", "Treetop precision among matched baseline candidates"),
    ("treetops", "precision_if_new_false", "Precision sensitivity: all new candidates false"),
    ("treetops", "precision_if_new_true", "Precision sensitivity: all new candidates true"),
    ("treetops", "false_removed", "False candidates removed vs baseline (est.)"),
    ("treetops", "true_removed", "True trees removed vs baseline (est.)"),
    ("treetops", "false_kept", "False candidates remaining (est.)"),
    ("cells", "commission", "CHM canopy-cell commission"),
    ("cells", "omission", "CHM canopy-cell omission"),
    ("cells", "area_bias_m2", "Canopy-area bias, m² (mapped - true)"),
    ("cells", "relative_bias", "Canopy-area bias, relative"),
    ("omission", "tree_share_of_noncanopy", "Omission search: tree share of non-canopy (baseline)"),
    ("omission", "missed_m2", "Omission search: tree canopy still missed, m²"),
    ("combined", "omission_rate", "Canopy omission rate (cell + omission samples)"),
    ("crowns", "share_correct", "Crowns correct"),
    ("crowns", "share_merged", "Crowns merged"),
    ("crowns", "share_split", "Crowns split"),
    ("crowns", "share_not_a_tree", "Crowns not a tree"),
    ("crowns", "share_includes_roof", "Crowns including roof"),
]


def _fmt(entry, key):
    value = entry.get("estimate")
    if value is None:
        return "n/a"
    percent = not key.endswith("m2") and key not in ("false_removed", "true_removed", "false_kept")
    def one(v):
        return f"{100*v:.1f}%" if percent else f"{v:,.0f}"
    if entry.get("low") is None:
        return one(value) + (" [interval unavailable]" if entry.get("interval_status") else "")
    return f"{one(value)} [{one(entry['low'])}, {one(entry['high'])}]"


def comparison_rows(scores):
    """scores: {(run, scope): {"treetops": ..., "cells": ..., ...}} -> table rows."""
    rows = []
    for (run, scope), score in scores.items():
        for group, key, title in HEADLINE:
            part = score.get(group) or {}
            status = part.get("status", "NOT_RUN")
            entry = (part.get("estimates") or part).get(key) if status != "NO_LABELS" else None
            if group == "crowns":
                title += " (unchanged matched baseline crowns only)"
            rows.append({"run": run, "scope": scope, "metric": title, "key": f"{group}.{key}",
                         "status": status,
                         "value": "no labels yet" if status == "NO_LABELS" else
                                  _fmt(entry, key) if isinstance(entry, dict) else "n/a"})
    return rows


def markdown_table(rows):
    runs = list(dict.fromkeys((r["run"], r["scope"]) for r in rows))
    metrics = list(dict.fromkeys(r["metric"] for r in rows))
    cell = {(r["metric"], r["run"], r["scope"]): r["value"] for r in rows}
    head = "| Metric | " + " | ".join(f"{run} ({scope})" for run, scope in runs) + " |"
    lines = [head, "|---|" + "---|"*len(runs)]
    for metric in metrics:
        lines.append(f"| {metric} | " + " | ".join(cell.get((metric, *k), "") for k in runs) + " |")
    return "\n".join(lines)
