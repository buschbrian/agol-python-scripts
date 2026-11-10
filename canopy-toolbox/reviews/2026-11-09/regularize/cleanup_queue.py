"""Switch the 550 joined outlines to the LiDAR, and add a "cleanup" queue of regularized outlines that LoD2.2 flagged.

    cleanup_queue.py DATA RUN     (millcreek-py3, PYTHONNOUSERSITE=1)

DATA is the review page's data folder, RUN is runs\\lidar-footprints-20261109. Appends bundles k0001... and backs up index.json
first; other items and all answers stay as they are. RUN/decisions.csv is a new file, the October file is not changed.
"""

import collections
import csv
import datetime
import json
import os
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[2] / "2026-10-26" / "lidar-footprints"))
import add_outline_queue as aoq  # noqa: E402

brd, amq = aoq.brd, aoq.amq
CITY2 = brd.RUNS / "lidar-footprints-20261026" / "city2"
QUEUE, PREFIX = "cleanup", "K"
PIECES = {"PART_OF_BUILDING", "VEHICLE"}
RULE = "rule_joins_county"


def switch_joins(run):
    with open(CITY2 / "decisions.csv", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        fields, rows = reader.fieldnames, list(reader)
    changed = 0
    for row in rows:
        if row["REVIEW_GROUP"] == RULE and row["BY"] == "rule":
            row.update(DECISION="LIDAR_RIGHT", BY="rule-20261109",
                       NOTE="Brian, November 9: LiDAR outer shape; county lines only as unit divisions inside it")
            changed += 1
    with open(run / "decisions.csv", "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    return rows, changed


def select(run, decisions):
    by_lidar = {lb: r for r in decisions for lb in r["LIDAR_IDS"].split(";") if lb}
    with open(run / "roofer" / "lod22-flags.csv", encoding="utf-8", newline="") as f:
        flagged = [r for r in csv.DictReader(f) if r["FLAG"] != "OK"]
    def group(r):
        if by_lidar.get(r["LB_ID"], {}).get("DECISION") in PIECES:
            return "cleanup_piece"
        return "cleanup_no_model" if r["FLAG"] == "NO_MODEL" else "cleanup_roof_fit"
    rank = {"cleanup_no_model": 0, "cleanup_roof_fit": 1, "cleanup_piece": 2}
    rows = sorted(flagged, key=lambda r: (rank[group(r)], -float(r["RMSE_MAX_M"] or 0), r["LB_ID"]))
    return [(group(r), r, by_lidar.get(r["LB_ID"], {})) for r in rows]


def main(data, run):
    import geopandas as gpd
    import shapely
    decisions, changed = switch_joins(run)
    picks = select(run, decisions)
    print(f"joins switched: {changed}; queue:", dict(collections.Counter(g for g, _, _ in picks)), flush=True)
    built = json.loads((data / "index.json").read_text(encoding="utf-8"))
    if any(it["queue"] == QUEUE for it in built["items"]):
        raise SystemExit(f"The {QUEUE} queue is already in this data")
    if any(it["id"].startswith(PREFIX) and it["id"][1:].startswith("B") for it in built["items"]):
        raise SystemExit("id prefix collision")
    shutil.copy2(data / "index.json", data / "index.before-cleanup-20261109.json")
    index = list(built["items"])
    county = gpd.read_file(brd.LIB / "buildings.gdb", layer="building_heights")
    county_web = gpd.read_file(brd.COUNTY_WEB, layer="buildings").set_index("SOURCE_ID")
    lidar = gpd.read_file(run / "regularized.gdb", layer="buildings")
    lidar["geometry"] = [aoq.polygons(g) for g in shapely.make_valid(lidar.geometry.values)]
    web = amq.Web(county, county_web)
    print("ITRF08:", web.check, flush=True)
    chips = brd.Chips()
    by_id = {r.LB_ID: r for r in lidar.itertuples()}
    county_tree, lidar_tree = shapely.STRtree(list(county.geometry)), shapely.STRtree(list(lidar.geometry))
    county_ids, lidar_ids = list(county.SOURCE_ID), list(lidar.LB_ID)
    details, order = {}, []
    for group, flag, decision in picks:
        row = by_id[flag["LB_ID"]]
        chip, uri = chips.render(row.geometry.bounds)
        box = shapely.box(chip["left"], chip["top"] - chip["n"] * brd.CELL, chip["left"] + chip["n"] * brd.CELL, chip["top"])
        red = brd.rings_of(row.geometry)
        context = {"county_px": [], "county_ll": [], "cand_px": [], "cand_ll": []}
        for j in county_tree.query(box, "intersects"):
            context["county_px"] += brd.Chips.px(brd.rings_of(county.geometry.iloc[j]), chip)
            if county_ids[j] in county_web.index:
                context["county_ll"] += brd.merc_to_ll(brd.rings_of(county_web.loc[county_ids[j]].geometry))
        for j in lidar_tree.query(box, "intersects"):
            if lidar_ids[j] != flag["LB_ID"]:
                rings = brd.rings_of(lidar.geometry.iloc[j])
                context["cand_px"] += brd.Chips.px(rings, chip)
                context["cand_ll"] += web.ll(rings)
        rmse = f"{float(flag['RMSE_MAX_M']):.2f} m ({float(flag['RMSE_MAX_M']) / 0.3048:.1f} ft)" if flag["RMSE_MAX_M"] else "—"
        facts = {"LiDAR outline": flag["LB_ID"], "LoD2.2 check": flag["FLAG"], "Roof fit error (worst part)": rmse,
                 "Parts with a model": f"{flag['MODELS']} of {flag['PARTS']}", "Outline area": f"{row.REG_AREA_M2:,.0f} m² ({row.REG_AREA_M2 / 0.3048**2:,.0f} sq ft)",
                 "Roof height (median)": f"{row.ROOF_H50_M:.1f} m ({row.ROOF_H50_M / 0.3048:.0f} ft)", "Regularize": row.REG_STATUS,
                 "Compared with county": decision.get("CLASS") or "MATCH", "Current decision": decision.get("DECISION") or "—"}
        item_id = PREFIX + flag["LB_ID"]
        details[item_id] = {"id": item_id, "queue": QUEUE, "group": group, "facts": facts, "outline_ll": web.ll(red), "outline_px": brd.Chips.px(red, chip),
                            "hint_ll": None, "hint_px": None, "focus_ll": None, "focus_px": None, "related": [], "profile": None,
                            "chip": {"uri": uri, "size": chip["n"], "metres": chip["n"] * brd.CELL}, **context}
        order.append(item_id)
    for k in range(0, len(order), brd.BUNDLE):
        ids = order[k:k + brd.BUNDLE]
        name = f"{PREFIX.lower()}{k // brd.BUNDLE + 1:04d}.json"
        path = data / "bundles" / name
        if path.exists():
            raise SystemExit(f"{path} exists")
        path.write_text(json.dumps({i: details[i] for i in ids}, separators=(",", ":"), allow_nan=False), encoding="utf-8")
        for i in ids:
            index.append({"id": i, "queue": QUEUE, "group": details[i]["group"], "order": len(index) + 1, "bundle": name})
    counts = {}
    for it in index:
        counts.setdefault(it["queue"], {}).setdefault(it["group"], 0)
        counts[it["queue"]][it["group"]] += 1
    built.update(counts=counts, items=index)
    built[f"{QUEUE}_added"] = datetime.datetime.now().isoformat(timespec="seconds")
    built[f"{QUEUE}_sources"] = {"outlines": str(run / "regularized.gdb"), "flags": str(run / "roofer" / "lod22-flags.csv")}
    partial = data / "index.partial"
    partial.write_text(json.dumps(built, separators=(",", ":")), encoding="utf-8")
    os.replace(partial, data / "index.json")
    print(f"added {len(order)} items:", json.dumps(counts[QUEUE]))


if __name__ == "__main__":
    main(Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve())
