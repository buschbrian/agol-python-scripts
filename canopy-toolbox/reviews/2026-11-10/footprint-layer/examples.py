"""One picture of each kind of fix in the built layer: output filled, LiDAR outline red dashed, county magenta.

    python examples.py OUT     writes examples.png here (millcreek-py3 Python, -I)
"""
from pathlib import Path
import random
import sys

import geopandas as gpd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import shapely

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_footprints import COUNTY, OUTLINES

KINDS = [("Units cut (joins moved to the LiDAR)", lambda f: (f.SOURCE == "LIDAR_UNITS") & (f.DECIDED_BY == "rule-20261109")),
         ("Tangle split by rule", lambda f: (f.SOURCE == "LIDAR_UNITS") & (f.DECIDED_BY == "rule-20261110")),
         ("Split (Brian)", lambda f: (f.SOURCE == "LIDAR_UNITS") & (f.DECISION == "SPLIT_BUILDINGS") & (f.DECIDED_BY == "Brian")),
         ("County plus extra roof", lambda f: f.SOURCE == "COUNTY_PLUS_LIDAR"),
         ("County shifted onto the LiDAR", lambda f: f.SOURCE == "COUNTY_SHIFTED"),
         ("Part of a building joined", lambda f: (f.SOURCE == "LIDAR") & f.LB_IDS.str.contains(";")),
         ("Kept county (under trees)", lambda f: (f.SOURCE == "COUNTY") & (f.CLASS == "RESHAPED")),
         ("Redrawn from the LiDAR (reshaped)", lambda f: (f.SOURCE == "LIDAR") & (f.CLASS == "RESHAPED")),
         ("Split by hand (flagged)", lambda f: f.REVIEW_FLAG == "SPLIT_BY_HAND")]


def main(out):
    f = gpd.read_file(Path(out)/"footprints.gdb", layer="footprints")
    lidar = gpd.read_file(OUTLINES, layer="buildings")
    county = gpd.read_file(COUNTY, layer="building_heights")
    rng = random.Random(20261110)
    fig, axes = plt.subplots(3, 3, figsize=(13, 13))
    for ax, (title, pick) in zip(axes.flat, KINDS):
        rows = f[pick(f)]
        if rows.empty:
            ax.set_title(title + " (none)"); ax.axis("off"); continue
        g = rows.iloc[rng.randrange(len(rows))]
        box = shapely.box(*g.geometry.buffer(12).bounds)
        f[f.intersects(box)].plot(ax=ax, color="#9ecae1", edgecolor="#08519c", linewidth=1.2)
        lidar[lidar.intersects(box)].boundary.plot(ax=ax, color="red", linestyle="--", linewidth=1)
        county[county.intersects(box)].boundary.plot(ax=ax, color="magenta", linewidth=1)
        ax.set_xlim(box.bounds[0], box.bounds[2]); ax.set_ylim(box.bounds[1], box.bounds[3])
        ax.set_title(f"{title}\n{g.BLDG_ID} {g.GROUP_ID}", fontsize=9); ax.set_xticks([]); ax.set_yticks([])
    fig.suptitle("Corrected footprints (blue) over the LiDAR outlines (red dashed) and county (magenta)", fontsize=11)
    fig.tight_layout()
    fig.savefig(HERE/"examples.png", dpi=90)


HERE = Path(__file__).resolve().parent
if __name__ == "__main__":
    main(sys.argv[1])
