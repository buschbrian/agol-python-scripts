r"""Calibration sample for the treetop review evidence: a blind, stratified, seeded draw of city treetops to label.

    python reviews/2026-10-15/calibration_sample.py draw PACKET_DIR [--seed 20261015] [--evidence DIR] [--prefix C1]
                                                                                            plain or Pro Python
    python reviews/2026-10-15/calibration_sample.py build-gdb PACKET_DIR                     Pro Python
    python reviews/2026-10-15/calibration_sample.py export-labels PACKET_DIR [--replace]     Pro Python
    python reviews/2026-10-15/calibration_sample.py import-page PACKET_DIR [--apply] [--replace]   plain or Pro Python
    python reviews/2026-10-15/calibration_sample.py score PACKET_DIR [--out score.json]      plain or Pro Python

draw         assigns every treetop in the evidence CSV to one stratum by priority (WIRE_HINT > WALL_HINT > FLAT_TOP >
             ROOF_HEIGHT, then POLE_ONLY, then UNFLAGGED), removes treetops the evaluation frame forbids (25 m + the 1 m
             top radius from every reference unit and census plot; the 12TVL3302 and 12TVL2203 tiles with halos) and
             those within 3 m of a training unit a person has already seen, then draws each stratum at random without
             replacement, keeping drawn treetops at least 2.5 m apart. All drawn units are shuffled together, so the first
             k in review order are a random subsample of every stratum. Writes units.csv (blind: no flags, no stratum,
             no TREE_ID) and sample.json (strata, populations, seed, digests). Refuses an existing packet.
             --evidence is the evidence run to draw from (default October 15's); --prefix starts each UNIT_ID.
             Seen training units are every labelled unit of SEEN_PACKETS plus the audit 2 units, as of the draw.
build-gdb    writes the blind point layer (LABEL has a coded domain of training_review.LABELS) and a LAS dataset of the
             ORIGINAL delivery LAS (classes 1/2/7/18 only, so no baseline class can bias the reviewer) on the SSD, in
             calibration-PACKET beside the evidence CSV the sample was drawn from.
export-labels  copies LABEL/REVIEWER/REVIEW_DATE/NOTE from that layer to PACKET_DIR/labels.csv, for the repo.
import-page    copies the label page's answers (reviews/2026-10-20/label-page, calibration mode) into labels.csv;
             a preview unless --apply. Both refuse to change or blank a label already in labels.csv unless --replace.
score        joins labels.csv to sample.json. TREE is a real treetop; every other definite class is not; MIXED and
             UNSURE are reported apart and left out of the share. A stratum is MEASURED only with at least 30 definite
             labels. Two-sided 95% Clopper-Pearson intervals. Partial packets are scored.

Once labelled, these units are used up as a test: if any treetop_evidence rule is changed after looking at them,
they cannot measure the changed rule (the audit 1 rule).
"""
import argparse
import csv
import datetime
import hashlib
import json
from pathlib import Path
import sys

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
from canopy import training_review as tr  # noqa: E402
from canopy.lidar_root import lidar_root  # noqa: E402

VALLEY = lidar_root()/"2023-salt-lake-valley"
EVIDENCE = VALLEY/"runs"/"treetop-evidence-20261015"
TRAINING_REVIEW = VALLEY/"runs"/"pilot-2026-09-29"/"training-review"
TRAINING_PACKET = TRAINING_REVIEW/"packet-20260929"/"packet.json"
TRAINING_LABELS = HERE.parent/"2026-09-29"/"packets"/"training-labels"/"labels-progress.csv"
# (packet, repo label backup) for every packet a person labels; the first gives the evaluation frame.
SEEN_PACKETS = (
    (TRAINING_PACKET, TRAINING_LABELS),
    (TRAINING_REVIEW/"packet-20261020-refined"/"packet.json",
     HERE.parent/"2026-09-29"/"packets"/"training-labels-refined"/"labels-progress.csv"),
    (TRAINING_REVIEW/"packet-20261020-rare"/"packet.json",
     HERE.parent/"2026-09-29"/"packets"/"training-labels-rare"/"labels-progress.csv"),
)
AUDIT2_UNITS = HERE.parent/"2026-09-30"/"audit-2"/"audit-units.txt"
DELIVERY_LAS = VALLEY/"las"

SCHEMA = "treetop-calibration/1"
PRIORITY = ("WIRE_HINT", "WALL_HINT", "FLAT_TOP", "ROOF_HEIGHT")
STRATA = ("WIRE", "WALL", "FLAT_TOP", "ROOF_HEIGHT", "POLE_ONLY", "UNFLAGGED")
SIZES = {"WIRE": 50, "WALL": 50, "FLAT_TOP": 50, "ROOF_HEIGHT": 100, "POLE_ONLY": 50, "UNFLAGGED": 50}
SUSPECT_STRATA = STRATA[:4]
TOP_RADIUS_M = 1.0          # the flags describe the top within 1 m of the peak
SEEN_RADIUS_M = 3.0         # treetops this close to a training unit a person has seen are left out
MIN_SPACING_M = 2.5
MEASURED_MIN = 30
NOT_SCORED = ("MIXED", "UNSURE")
UNIT_COLUMNS = ["UNIT_ID", "ORDER", "X", "Y", "HEIGHT_M", "LABEL", "REVIEWER", "REVIEW_DATE", "NOTE"]
LABEL_COLUMNS = ["UNIT_ID", "LABEL", "REVIEWER", "REVIEW_DATE", "NOTE"]
NOTE = ("Calibration labels for canopy/treetop_evidence rules. Never evaluation answers, never training labels, never in "
        "reference.gdb. Label blind: do not open sample.json or the treetop_evidence layer until every unit is labelled. "
        "Once these labels have been looked at, a rule changed in response cannot be tested on them.")


# ---------------------------------------------------------------- pure helpers
def stratum(row):
    """The one stratum of an evidence row (dict of '0'/'1' flag strings)."""
    for flag, name in zip(PRIORITY, SUSPECT_STRATA):
        if row[flag] == "1":
            return name
    return "POLE_ONLY" if row["POLE_HINT"] == "1" else "UNFLAGGED"


def ids_digest(ids):
    return hashlib.sha256("\n".join(sorted(ids)).encode()).hexdigest()


def excluded_reason(x, y, frame, seen_xy):
    """Per treetop: '' when it may be sampled, else why not."""
    tr.check_frame(frame)
    x, y = np.asarray(x, float), np.asarray(y, float)
    reason = np.full(x.shape, "", dtype=object)
    for tile, row in frame["excluded_tiles"].items():
        reason[(reason == "") & (tr._rect_distance(x, y, row["extent"]) < TOP_RADIUS_M)] = f"excluded tile {tile}"
    open_ = reason == ""
    close = np.zeros(x.shape, bool)
    close[open_] = tr.evaluation_distance(x[open_], y[open_], frame) < frame["buffer_m"]+TOP_RADIUS_M
    reason[close] = "evaluation buffer"
    if len(seen_xy):
        from scipy.spatial import cKDTree
        d, _ = cKDTree(np.asarray(seen_xy, float)).query(np.c_[x, y])
        reason[(reason == "") & (d < SEEN_RADIUS_M)] = "near a seen training unit"
    return reason


def draw_stratum(ids, xy, n, rng, taken_xy):
    """n ids drawn without replacement in a seeded random order, skipping any within MIN_SPACING_M of one taken."""
    chosen = []
    for i in rng.permutation(len(ids)):
        if len(chosen) == n:
            break
        p = xy[i]
        if taken_xy and np.min(np.hypot(*(np.asarray(taken_xy)-p).T)) < MIN_SPACING_M:
            continue
        chosen.append(i)
        taken_xy.append(tuple(p))
    return chosen


def clopper_pearson(k, n, alpha=.05):
    """Two-sided exact interval for k successes in n."""
    from scipy.stats import beta
    if n == 0:
        return (0.0, 1.0)
    lo = 0.0 if k == 0 else float(beta.ppf(alpha/2, k, n-k+1))
    hi = 1.0 if k == n else float(beta.ppf(1-alpha/2, k+1, n-k))
    return (lo, hi)


def score(sample, labels):
    """Per-stratum label mix, not-tree share with its interval, and a projection onto the citywide suspect strata."""
    by_unit = {u["UNIT_ID"]: u for u in sample["units"]}
    unknown = sorted(set(labels)-set(by_unit))
    if unknown:
        raise ValueError(f"labels.csv has units not in the sample: {unknown[:5]}")
    bad = sorted({v for v in labels.values() if v and v not in tr.LABELS})
    if bad:
        raise ValueError(f"Unknown labels: {bad}")
    out = {"schema": SCHEMA, "labelled": sum(1 for v in labels.values() if v), "units": len(by_unit), "strata": {}}
    for s in STRATA:
        units = [u for u in sample["units"] if u["STRATUM"] == s]
        got = [labels.get(u["UNIT_ID"], "") for u in units]
        mix = {k: got.count(k) for k in tr.LABELS if got.count(k)}
        definite = sum(v for k, v in mix.items() if k not in NOT_SCORED)
        not_tree = definite-mix.get("TREE", 0)
        lo, hi = clopper_pearson(not_tree, definite)
        out["strata"][s] = {"drawn": len(units), "labelled": sum(1 for g in got if g), "label_mix": mix,
                            "mixed_or_unsure": sum(mix.get(k, 0) for k in NOT_SCORED), "definite": definite,
                            "not_tree": not_tree,
                            "not_tree_share": round(not_tree/definite, 4) if definite else None,
                            "ci95": [round(lo, 4), round(hi, 4)], "measured": definite >= MEASURED_MIN,
                            "population_citywide": sample["populations"]["citywide"][s]}
    if all(out["strata"][s]["measured"] for s in SUSPECT_STRATA):
        est = sum(out["strata"][s]["not_tree_share"]*out["strata"][s]["population_citywide"] for s in SUSPECT_STRATA)
        low = sum(out["strata"][s]["ci95"][0]*out["strata"][s]["population_citywide"] for s in SUSPECT_STRATA)
        high = sum(out["strata"][s]["ci95"][1]*out["strata"][s]["population_citywide"] for s in SUSPECT_STRATA)
        out["suspect_not_tree_projection"] = {
            "estimate": round(est), "bounds": [round(low), round(high)],
            "method": "sum over suspect strata of citywide population x not-tree share; bounds sum the per-stratum "
                      "95% limits (conservative, not a joint interval). Assumes the eligible area represents the city."}
    else:
        out["suspect_not_tree_projection"] = None
    return out


# ---------------------------------------------------------------- io
def read_csv(path):
    with open(path, newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def write_csv(path, columns, rows):
    with open(path, "w", newline="", encoding="utf-8") as handle:
        w = csv.DictWriter(handle, columns)
        w.writeheader()
        w.writerows(rows)


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 24), b""):
            h.update(block)
    return h.hexdigest()


def seen_training_units():
    """The evaluation frame, the seen (packet, UNIT_ID) pairs and their XY, over every packet in SEEN_PACKETS."""
    audit = {line.strip() for line in AUDIT2_UNITS.read_text().splitlines() if line.strip()}
    frame, seen, xy = None, set(), []
    for packet_path, labels_path in SEEN_PACKETS:
        packet = json.loads(packet_path.read_text(encoding="utf-8"))
        if frame is None:
            frame = packet["frame"]
        elif packet["frame"]["digest"] != frame["digest"]:
            raise ValueError(f"{packet_path} has a different evaluation frame")
        ids = {r["UNIT_ID"] for r in read_csv(labels_path) if r["LABEL"].strip()}
        if packet_path == TRAINING_PACKET:
            ids |= audit
        seen |= {(packet_path.parent.name, i) for i in ids}
        xy += [(u["X"], u["Y"]) for u in packet["units"] if u["UNIT_ID"] in ids]
    return frame, seen, xy


def draw(packet_dir, seed, evidence=EVIDENCE, prefix="C1"):
    packet_dir = Path(packet_dir).resolve()
    if packet_dir.exists():
        raise FileExistsError(f"Use a new packet folder: {packet_dir}")
    evidence = Path(evidence)
    evidence_csv = evidence/"treetop-evidence.csv"
    frame, seen, seen_xy = seen_training_units()
    tr.check_frame(frame)
    rows = read_csv(evidence_csv)
    x = np.array([float(r["X"]) for r in rows])
    y = np.array([float(r["Y"]) for r in rows])
    strata = np.array([stratum(r) for r in rows])
    reason = excluded_reason(x, y, frame, seen_xy)
    eligible = reason == ""
    rng = np.random.default_rng(seed)
    taken, units = [], []
    pools = {}
    for s in STRATA:
        idx = np.flatnonzero(eligible & (strata == s))
        idx = idx[np.argsort([rows[i]["TREE_ID"] for i in idx])]          # sorted pool: reproducible draw
        pools[s] = {"eligible": len(idx), "digest": ids_digest(rows[i]["TREE_ID"] for i in idx)}
        if len(idx) < SIZES[s]:
            raise ValueError(f"Stratum {s} has only {len(idx)} eligible treetops")
        for j in draw_stratum([rows[i]["TREE_ID"] for i in idx], np.c_[x[idx], y[idx]], SIZES[s], rng, taken):
            units.append({"TREE_ID": rows[idx[j]]["TREE_ID"], "STRATUM": s, "row": int(idx[j])})
    for order, k in enumerate(rng.permutation(len(units)), 1):
        units[k]["ORDER"] = order
        units[k]["UNIT_ID"] = f"{prefix}-{order:04d}"
    units.sort(key=lambda u: u["ORDER"])
    packet_dir.mkdir(parents=True)
    write_csv(packet_dir/"units.csv", UNIT_COLUMNS,
              [{"UNIT_ID": u["UNIT_ID"], "ORDER": u["ORDER"], "X": rows[u["row"]]["X"], "Y": rows[u["row"]]["Y"],
                "HEIGHT_M": rows[u["row"]]["HEIGHT_M"], "LABEL": "", "REVIEWER": "", "REVIEW_DATE": "", "NOTE": ""}
               for u in units])
    excluded = {}
    for r, s in zip(reason, strata):
        if r:
            excluded.setdefault(r, {}).setdefault(str(s), 0)
            excluded[r][str(s)] += 1
    sample = {
        "schema": SCHEMA, "created": datetime.datetime.now().isoformat(timespec="seconds"), "seed": seed,
        "method": "per stratum in STRATA order: numpy default_rng(seed).permutation over the TREE_ID-sorted eligible "
                  "pool, taking units at least MIN_SPACING_M from every unit already taken; then one shared "
                  "permutation gives the review order",
        "priority": list(PRIORITY), "strata": list(STRATA), "sizes": SIZES, "min_spacing_m": MIN_SPACING_M,
        "evidence_csv": str(evidence_csv), "evidence_csv_sha256": sha256(evidence_csv),
        "evidence_rules_version": json.loads((evidence/"manifest.json").read_text())["rules_version"],
        "frame_source": str(TRAINING_PACKET), "frame_digest": frame["digest"], "frame_buffer_m": frame["buffer_m"],
        "top_radius_m": TOP_RADIUS_M, "seen_training_units": len(seen), "seen_radius_m": SEEN_RADIUS_M,
        "seen_packets": [str(p) for p, _ in SEEN_PACKETS],
        "populations": {"citywide": {s: int(np.count_nonzero(strata == s)) for s in STRATA},
                        "eligible": {s: pools[s]["eligible"] for s in STRATA}},
        "pool_digests": {s: pools[s]["digest"] for s in STRATA}, "excluded": excluded,
        "units": [{k: u[k] for k in ("UNIT_ID", "ORDER", "TREE_ID", "STRATUM")} for u in units],
        "note": NOTE,
    }
    (packet_dir/"sample.json").write_text(json.dumps(sample, indent=1))
    spacing = min(np.hypot(*(np.array(a)-np.array(b))) for i, a in enumerate(taken) for b in taken[i+1:])
    print(json.dumps({"units": len(units), "populations": sample["populations"], "excluded": excluded,
                      "min_spacing_m": round(float(spacing), 2)}, indent=1))


def calibration_dir(packet_dir):
    """The packet's folder on the SSD, beside the evidence it was drawn from (by run name, so any drive letter works)."""
    sample = json.loads((packet_dir/"sample.json").read_text())
    run = Path(sample["evidence_csv"].replace("\\", "/")).parent.name
    return VALLEY/"runs"/run/f"calibration-{packet_dir.name}"


def build_gdb(packet_dir):
    import arcpy
    packet_dir = Path(packet_dir).resolve()
    sample = json.loads((packet_dir/"sample.json").read_text())
    out = calibration_dir(packet_dir)
    if out.exists():
        raise FileExistsError(out)
    out.mkdir()
    las = sorted(DELIVERY_LAS.glob("*.las"))
    before = {str(p): (p.stat().st_size, p.stat().st_mtime_ns) for p in las}
    gdb = out/"calibration.gdb"
    arcpy.management.CreateFileGDB(str(out), gdb.name)
    arcpy.management.CreateDomain(str(gdb), "LABEL", "Calibration label", "TEXT", "CODED")
    for code, (meaning, _) in tr.LABELS.items():
        arcpy.management.AddCodedValueToDomain(str(gdb), "LABEL", code, f"{code}: {meaning}"[:250])
    fc = str(gdb/"calibration_units")
    arcpy.management.XYTableToPoint(str(packet_dir/"units.csv"), fc, "X", "Y",
                                    coordinate_system=arcpy.SpatialReference(6341))
    keep = {c.lower() for c in UNIT_COLUMNS}
    extra = [f.name for f in arcpy.ListFields(fc) if f.type not in ("OID", "Geometry") and f.name.lower() not in keep]
    if extra:
        arcpy.management.DeleteField(fc, extra)
    for name in ("LABEL", "REVIEWER", "REVIEW_DATE", "NOTE"):     # empty CSV columns may arrive as non-text fields
        if [f for f in arcpy.ListFields(fc, name) if f.type != "String"]:
            arcpy.management.DeleteField(fc, name)
        if not arcpy.ListFields(fc, name):
            arcpy.management.AddField(fc, name, "TEXT", field_length=254 if name == "NOTE" else 40)
    arcpy.management.AssignDomainToField(fc, "LABEL", "LABEL")
    # ORDER is reserved in a file geodatabase, so the review order is carried as REVIEW_ORDER (= the UNIT_ID number).
    arcpy.management.AddField(fc, "REVIEW_ORDER", "LONG")
    with arcpy.da.UpdateCursor(fc, ["UNIT_ID", "REVIEW_ORDER"]) as cursor:
        for unit_id, _ in cursor:
            cursor.updateRow([unit_id, int(unit_id.split("-")[1])])
    md = arcpy.metadata.Metadata(fc)
    md.title, md.summary = "Treetop calibration units (blind)", NOTE
    md.save()
    lasd = str(out/"delivery.lasd")
    arcpy.management.CreateLasDataset([str(p) for p in las], lasd, compute_stats="NO_COMPUTE_STATS",
                                      relative_paths="ABSOLUTE_PATHS")
    after = {str(p): (p.stat().st_size, p.stat().st_mtime_ns) for p in las}
    record = {"feature_class": fc, "features": int(arcpy.management.GetCount(fc)[0]), "lasd": lasd,
              "las_files": len(las), "las_unchanged": before == after, "units_expected": len(sample["units"])}
    (out/"build.json").write_text(json.dumps(record, indent=1))
    print(json.dumps(record, indent=1))
    if record["features"] != record["units_expected"] or not record["las_unchanged"]:
        raise SystemExit("Build check failed")


def merge_labels(existing, incoming, replace=False):
    """Merge incoming label rows into existing ones (both {UNIT_ID: row}). A unit's label is never changed or blanked
    unless replace is set; such units are returned as conflicts and left as they were."""
    out = {uid: dict(r) for uid, r in existing.items()}
    report = {"new": 0, "unchanged": 0, "replaced": 0, "conflicts": []}
    for uid, row in incoming.items():
        old = (existing.get(uid, {}).get("LABEL") or "").strip()
        new = (row.get("LABEL") or "").strip()
        if old == new:
            report["unchanged"] += 1
            if new:
                out[uid] = {**out[uid], **row}
        elif not old:
            out[uid] = dict(row)
            report["new"] += 1
        elif replace:
            out[uid] = dict(row)
            report["replaced"] += 1
        else:
            report["conflicts"].append({"UNIT_ID": uid, "labels.csv": old, "incoming": new or "(blank)"})
    return out, report


def write_labels(packet_dir, merged):
    """labels.csv with one row per unit of units.csv, in review order."""
    rows = []
    for u in read_csv(packet_dir/"units.csv"):
        r = merged.get(u["UNIT_ID"], {})
        rows.append({k: (r.get(k) or "") if k != "UNIT_ID" else u["UNIT_ID"] for k in LABEL_COLUMNS})
    write_csv(packet_dir/"labels.csv", LABEL_COLUMNS, rows)
    return rows


def apply_merge(packet_dir, incoming, replace, apply, source):
    path = packet_dir/"labels.csv"
    existing = {r["UNIT_ID"]: r for r in read_csv(path)} if path.exists() else {}
    units = {u["UNIT_ID"] for u in read_csv(packet_dir/"units.csv")}
    unknown = sorted(set(incoming)-units)
    if unknown:
        raise ValueError(f"{source} has units not in this packet: {unknown[:5]}")
    bad = sorted({r["LABEL"] for r in incoming.values() if r["LABEL"] and r["LABEL"] not in tr.LABELS})
    if bad:
        raise ValueError(f"Unknown labels in {source}: {bad}")
    merged, report = merge_labels(existing, incoming, replace)
    print(json.dumps({k: v for k, v in report.items() if k != "conflicts"} | {"conflicts": len(report["conflicts"])}))
    for c in report["conflicts"][:20]:
        print(f"  conflict {c['UNIT_ID']}: labels.csv {c['labels.csv']}, {source} {c['incoming']}")
    if report["conflicts"] and not replace:
        raise SystemExit("Nothing written: add --replace to let these answers overwrite labels.csv")
    if not apply:
        print("Preview only: add --apply to write labels.csv")
        return
    rows = write_labels(packet_dir, merged)
    print(f"{sum(1 for r in rows if r['LABEL'])} of {len(rows)} labelled -> {path}")


def export_labels(packet_dir, replace=False):
    import arcpy
    packet_dir = Path(packet_dir).resolve()
    fc = str(calibration_dir(packet_dir)/"calibration.gdb"/"calibration_units")
    rows = {r[0]: {"UNIT_ID": r[0], "LABEL": r[1] or "", "REVIEWER": r[2] or "", "REVIEW_DATE": r[3] or "",
                   "NOTE": r[4] or ""} for r in arcpy.da.SearchCursor(fc, LABEL_COLUMNS)}
    apply_merge(packet_dir, rows, replace, True, "the Pro layer")


def import_page(packet_dir, replace=False, apply=False):
    """Copy the label page's answers (serve_label_page.py --calibration) into labels.csv; preview unless apply."""
    packet_dir = Path(packet_dir).resolve()
    path = calibration_dir(packet_dir)/"label-page"/"answers"/"calibration-answers.csv"
    rows = {r["UNIT_ID"]: {k: r.get(k, "") for k in LABEL_COLUMNS} for r in read_csv(path)}
    print(f"{len(rows)} answers on the page ({path})")
    apply_merge(packet_dir, rows, replace, apply, "the page")


def score_command(packet_dir, out=None):
    packet_dir = Path(packet_dir).resolve()
    sample = json.loads((packet_dir/"sample.json").read_text())
    path = packet_dir/"labels.csv"
    labels = {r["UNIT_ID"]: r["LABEL"].strip() for r in read_csv(path)} if path.exists() else {}
    result = score(sample, labels)
    text = json.dumps(result, indent=1)
    if out:
        Path(out).write_text(text)
    print(text)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("step", choices=("draw", "build-gdb", "export-labels", "import-page", "score"))
    p.add_argument("packet", type=Path)
    p.add_argument("--seed", type=int, default=20261015)
    p.add_argument("--out", type=Path)
    p.add_argument("--evidence", type=Path, default=EVIDENCE, help="evidence run folder to draw from")
    p.add_argument("--prefix", default="C1", help="UNIT_ID prefix")
    p.add_argument("--apply", action="store_true", help="import-page: write labels.csv (default: preview)")
    p.add_argument("--replace", action="store_true", help="export-labels, import-page: let answers change a label")
    a = p.parse_args(argv)
    {"draw": lambda: draw(a.packet, a.seed, a.evidence, a.prefix), "build-gdb": lambda: build_gdb(a.packet),
     "export-labels": lambda: export_labels(a.packet, a.replace),
     "import-page": lambda: import_page(a.packet, a.replace, a.apply),
     "score": lambda: score_command(a.packet, a.out)}[a.step]()


if __name__ == "__main__":
    main()
