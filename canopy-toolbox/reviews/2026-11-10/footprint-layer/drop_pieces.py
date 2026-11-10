"""Draw dropped pieces (Brian's 286 touching a building) that lie under a larger OpenStreetMap outline: the piece in orange,
the layer's outlines in blue, OSM green, county magenta. Writes drop-pieces.png here (millcreek-py3 Python, -I).

    python drop_pieces.py OUT
"""
import csv
from pathlib import Path
import random
import sys

import geopandas as gpd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import shapely

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_footprints import COMPARE, COUNTY, DECISIONS, OUTLINES  # noqa: E402
from compare_datasets import MATCH, OVERTURE  # noqa: E402

HERE = Path(__file__).resolve().parent


def main(out):
    with DECISIONS.open(encoding="utf-8-sig") as fh:
        drop = {r["GROUP"] for r in csv.DictReader(fh) if r["DECISION"] == "DROP"}
    with COMPARE.open(encoding="utf-8") as fh:
        lbs = [g["LIDAR_IDS"] for g in csv.DictReader(fh) if g["GROUP"] in drop]
    lidar = gpd.read_file(OUTLINES, layer="buildings").set_index("LB_ID")
    ov = gpd.read_file(OVERTURE, layer="overture_buildings")
    osm = ov[ov.source_datasets.str.contains("OpenStreetMap")].reset_index(drop=True)
    county = gpd.read_file(COUNTY, layer="building_heights")
    ours = gpd.read_file(Path(out)/"footprints.gdb", layer="footprints")
    tree = shapely.STRtree(list(osm.geometry))
    under = []
    for lb in lbs:
        x = lidar.geometry[lb]
        for j in tree.query(x, "intersects"):
            y = osm.geometry.iloc[j]
            if x.intersection(y).area >= MATCH * x.area and y.area > 3 * x.area:
                under.append(lb)
                break
    rng = random.Random(20261110)
    pick = rng.sample(under, 9)
    fig, axes = plt.subplots(3, 3, figsize=(12, 12))
    for ax, lb in zip(axes.flat, pick):
        x = lidar.geometry[lb]
        box = shapely.box(*x.buffer(10).bounds)
        ours[ours.intersects(box)].plot(ax=ax, color="#9ecae1", edgecolor="#08519c", linewidth=1)
        gpd.GeoSeries([x]).plot(ax=ax, color="#fd8d3c", edgecolor="#a63603")
        osm[osm.intersects(box)].boundary.plot(ax=ax, color="green", linewidth=1.5)
        county[county.intersects(box)].boundary.plot(ax=ax, color="magenta", linewidth=1, linestyle=":")
        ax.set_xlim(box.bounds[0], box.bounds[2]); ax.set_ylim(box.bounds[1], box.bounds[3])
        ax.set_title(f"{lb} {x.area:.0f} m²", fontsize=9); ax.set_xticks([]); ax.set_yticks([])
    fig.suptitle(f"Dropped pieces under a larger OSM outline ({len(under)} of {len(lbs)}): piece orange, layer blue, "
                 "OSM green, county magenta dotted", fontsize=10)
    fig.tight_layout()
    fig.savefig(HERE/"drop-pieces.png", dpi=85)
    print(len(under), "of", len(lbs))


if __name__ == "__main__":
    main(sys.argv[1])
