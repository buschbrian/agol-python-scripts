"""Append an "outlines" queue to the footprint review page: every place where the LiDAR-first building outlines and the
county footprints disagree (October 26, 2026).

Brian decided the LiDAR is the truth for whole buildings and asked to bring the review queue back up "so I can go through
and we can fix out the rest and also go through how to split up any other decisions". One item per compare.csv group
that is not a MATCH: the LiDAR outline(s) in red, the county outline(s) in magenta, other county footprints white and
other LiDAR outlines dashed cyan. Each class starts with a random sample of 40 (seed 20261026) so that a whole class can
be decided from its sample; the rest of the class follows.

    python add_outline_queue.py DATA [--pilot]

Appends bundles o0001..., never touching other items or answers (as add_model_queues.py and add-pairs did). --pilot writes
a separate folder DATA with 3 items per class.
"""
import argparse
import collections
import csv
import datetime
import json
import os
from pathlib import Path
import random
import sys

HERE = Path(__file__).resolve()
MODEL_REVIEW = HERE.parents[1]/"model-review"
sys.path.insert(0, str(MODEL_REVIEW))
import add_model_queues as amq  # noqa: E402  (brings build_review_data as amq.brd, and the ITRF08 Web helper)

brd = amq.brd
CITY = brd.RUNS/"lidar-footprints-20261026"/"city"
CLASSES = ("RESHAPED", "LIDAR_JOINS", "LIDAR_SPLITS", "TANGLE", "COUNTY_ONLY", "LIDAR_ONLY")
SAMPLE = 40
SEED = 20261026


def select(pilot):
    with (CITY/"compare.csv").open(encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f) if r["CLASS"] in CLASSES]
    rng = random.Random(SEED)
    by_class = collections.defaultdict(list)
    for r in rows:
        by_class[r["CLASS"]].append(r)
    out = []
    for c in CLASSES:
        group = sorted(by_class[c], key=lambda r: r["GROUP"])
        sample = set(r["GROUP"] for r in rng.sample(group, min(SAMPLE, len(group))))
        first = [r for r in group if r["GROUP"] in sample]
        rest = [r for r in group if r["GROUP"] not in sample]
        if pilot:
            first, rest = first[:3], []
        out += [(f"sample_{c.lower()}", r) for r in first] + [(c.lower(), r) for r in rest]
    return out


def facts(r, county_by_id, lidar_by_id, parcels):
    cs = [county_by_id[s] for s in r["COUNTY_IDS"].split(";") if s]
    ls = [lidar_by_id[lb] for lb in r["LIDAR_IDS"].split(";") if lb]
    f = {"Class": r["CLASS"], "LiDAR outline(s)": f"{len(ls)}: " + (", ".join(lb.LB_ID for lb in ls) or "none"),
         "LiDAR area": "—" if not ls else f"{float(r['LIDAR_M2']):,.0f} m² ({float(r['LIDAR_M2']) / 0.3048**2:,.0f} sq ft)",
         "County outline(s)": f"{len(cs)}: " + (", ".join(c.SOURCE_ID for c in cs) or "none"),
         "County area": "—" if not cs else f"{float(r['COUNTY_M2']):,.0f} m² ({float(r['COUNTY_M2']) / 0.3048**2:,.0f} sq ft)",
         "Overlap (IoU, one each)": brd.txt(r["IOU"]),
         "County roof support (2023)": r["COUNTY_ROOF_COV_PCT"].replace(";", "%, ") + ("%" if r["COUNTY_ROOF_COV_PCT"] else "") or "—",
         "Canopy over the county outline": r["COUNTY_CANOPY_PCT"].replace(";", "%, ") + ("%" if r["COUNTY_CANOPY_PCT"] else "") or "—"}
    if ls:
        f["LiDAR roof height (median)"] = ", ".join(f"{lb.ROOF_H50_M:.1f} m ({lb.ROOF_H50_M / 0.3048:.0f} ft)" for lb in ls[:4])
    if cs:
        c = cs[0]
        use, assessor = brd.parcel_text(parcels.get(brd.pnorm(c.PARCEL_ID)))
        f.update({"Address (county)": brd.txt(c.ADDRESS), "Parcel": brd.txt(c.PARCEL_ID), "Parcel use": use,
                  "Assessor (main building)": assessor, "County type / year built": f"{brd.txt(c.BuildType)} / {brd.txt(c.BuiltYear, '{:.0f}')}"})
    return f


def main(argv=None):
    import geopandas as gpd
    import shapely
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("data", type=Path)
    p.add_argument("--pilot", action="store_true")
    a = p.parse_args(argv)
    data = a.data.resolve()
    items = select(a.pilot)
    print("selected:", json.dumps(collections.Counter(g for g, _ in items)), flush=True)
    if a.pilot:
        (data/"bundles").mkdir(parents=True, exist_ok=False)
        (data/"answers").mkdir()
        built, index = {"schema": "footprint-review/1", "pilot": True, "groups": dict(brd.GROUPS), "items": []}, []
    else:
        built = json.loads((data/"index.json").read_text(encoding="utf-8"))
        if any(it["queue"] == "outlines" for it in built["items"]):
            raise ValueError("The outlines queue is already in this data")
        index = list(built["items"])
    start = len(index)
    county = gpd.read_file(brd.LIB/"buildings.gdb", layer="building_heights")
    county_web = gpd.read_file(brd.COUNTY_WEB, layer="buildings").set_index("SOURCE_ID")
    lidar = gpd.read_file(CITY/"lidar.gdb", layer="buildings")
    web = amq.Web(county, county_web)
    print("ITRF08:", web.check, flush=True)
    chips = brd.Chips()
    _, parcels = brd.load_parcels()
    county_by_id = {r.SOURCE_ID: r for r in county.itertuples()}
    lidar_by_id = {r.LB_ID: r for r in lidar.itertuples()}
    ct, lt = shapely.STRtree(list(county.geometry)), shapely.STRtree(list(lidar.geometry))
    cids, lids = list(county.SOURCE_ID), list(lidar.LB_ID)
    details, order = {}, []
    for n, (group, r) in enumerate(items, 1):
        cs = [s for s in r["COUNTY_IDS"].split(";") if s]
        ls = [lb for lb in r["LIDAR_IDS"].split(";") if lb]
        lg = [lidar_by_id[lb].geometry for lb in ls]
        cg = [county_by_id[s].geometry for s in cs]
        allg = shapely.union_all(lg + cg)
        chip, uri = chips.render(allg.bounds)
        box = shapely.box(chip["left"], chip["top"] - chip["n"] * brd.CELL, chip["left"] + chip["n"] * brd.CELL, chip["top"])
        red = [ring for g in lg for ring in brd.rings_of(g)]
        mag = [ring for g in cg for ring in brd.rings_of(g)]
        ctx = {"county_px": [], "county_ll": [], "cand_px": [], "cand_ll": []}
        for j in ct.query(box, "intersects"):
            if cids[j] in cs:
                continue
            ctx["county_px"] += brd.Chips.px(brd.rings_of(county.geometry.iloc[j]), chip)
            if cids[j] in county_web.index:
                ctx["county_ll"] += brd.merc_to_ll(brd.rings_of(county_web.loc[cids[j]].geometry))
        for j in lt.query(box, "intersects"):
            if lids[j] in ls:
                continue
            rings = brd.rings_of(lidar.geometry.iloc[j])
            ctx["cand_px"] += brd.Chips.px(rings, chip)
            ctx["cand_ll"] += web.ll(rings)
        mag_ll = [ring for s in cs if s in county_web.index for ring in brd.merc_to_ll(brd.rings_of(county_web.loc[s].geometry))]
        item_id = "O" + r["GROUP"]
        details[item_id] = {"id": item_id, "queue": "outlines", "group": group,
                            "facts": facts(r, county_by_id, lidar_by_id, parcels),
                            "outline_ll": web.ll(red) if red else [], "outline_px": brd.Chips.px(red, chip) if red else [],
                            "hint_ll": None, "hint_px": None, "focus_ll": mag_ll or None,
                            "focus_px": brd.Chips.px(mag, chip) if mag else None,
                            "related": [f"CF{s}" for s in cs] + [f"PR{s}" for s in cs] + [f"MD{s}" for s in cs],
                            "profile": None, "chip": {"uri": uri, "size": chip["n"], "metres": chip["n"] * brd.CELL}, **ctx}
        order.append(item_id)
        if n % 500 == 0:
            print(f"  {n} items", flush=True)
    for k in range(0, len(order), brd.BUNDLE):
        ids = order[k:k + brd.BUNDLE]
        name = f"o{k // brd.BUNDLE + 1:04d}.json"
        path = data/"bundles"/name
        assert not path.exists(), path
        path.write_text(json.dumps({i: details[i] for i in ids}, separators=(",", ":"), allow_nan=False), encoding="utf-8")
        for i in ids:
            index.append({"id": i, "queue": "outlines", "group": details[i]["group"], "order": len(index) + 1, "bundle": name})
    counts = {}
    for it in index:
        counts.setdefault(it["queue"], {}).setdefault(it["group"], 0)
        counts[it["queue"]][it["group"]] += 1
    built.update(counts=counts, items=index, outlines_added=datetime.datetime.now().isoformat(timespec="seconds"),
                 outlines_sources={"compare": str(CITY/"compare.csv"), "lidar": str(CITY/"lidar.gdb"), "seed": SEED, "sample": SAMPLE})
    partial = data/"index.partial"
    partial.write_text(json.dumps(built, separators=(",", ":")), encoding="utf-8")
    os.replace(partial, data/"index.json")
    print(f"added {len(index) - start} items:", json.dumps(counts["outlines"]))


if __name__ == "__main__":
    main()
