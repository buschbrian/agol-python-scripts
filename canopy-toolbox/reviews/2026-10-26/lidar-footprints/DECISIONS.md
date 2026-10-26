# Decisions for Brian after the LiDAR-first rebuild (October 26, 2026)

The public buildings scene now shows the LiDAR-first buildings, with metres and feet
([release](release/release_lidar_first.py)). What is left needs Brian's calls. Most can be made once for a whole class,
from the "Sample" group of that class in the review page's **LiDAR outlines vs county** queue (40 random items each),
instead of item by item.

## Building outlines: one call per class

| # | Class (county footprints) | Proposed default | What the sample decides |
|---|---|---|---|
| 1 | MATCH (17,245) | Keep as matched; no review queue | Roof line or wall line (see 7) |
| 2 | RESHAPED (1,636) | LiDAR outline replaces the county outline | How often trees cut the LiDAR short (UNDER_TREES) or the county is right |
| 3 | LIDAR_JOINS (1,023 LiDAR buildings over 2,260 county outlines) | LiDAR outer shape, county unit lines kept inside it (KEEP_UNITS) | Whether the county lines are units (townhouses) or junk to drop (LIDAR_RIGHT) |
| 4 | LIDAR_SPLITS (137) | LiDAR buildings replace the county outline | Usually separate buildings the county drew as one |
| 5 | TANGLE (13) | Hand edit | All 13 can be reviewed |
| 6 | COUNTY_ONLY (733) | Keep where trees cover 30% or more (480); otherwise gone | The GONE / UNDER_TREES split, and whether sheds the LiDAR missed are kept |
| 7 | LIDAR_ONLY (3,080) | Add as buildings | How many are vehicles, sheds or trees (NOT_A_BUILDING, SHED) |

**Roof line or wall line.** The LiDAR traces the roof edge, a median 0.39 m (1.3 ft) outside the county wall lines.
Either keep the roof outline (what the 3D models use), or derive a wall line by shrinking it 0.39 m. The latter is an
estimate, not a measurement.

**Attributes.** Addresses, parcels and year built live on the county rows. Proposed: carry them onto the LiDAR outline
of the same group (COUNTY_IDS), with the parcel from the outline's location where there is no county row.

## Publishing

8. **Azure download.** It still serves the October 25 v2 package and the feet CSV. Proposed: publish the LiDAR-first
   package as a new dated object (`.../buildings/20261026/`). The feet CSV is no longer needed, because the layer
   carries feet itself. Keep the October 25 objects; their URLs are immutable.
9. **Buildings in 3D app** (private). Its text still describes the three-way hybrid. Update the wording, and decide
   whether to share the app.
10. **Building heights layer** (hosted 2D, the 22,042 county footprints with lidar heights). Proposed: rebuild it on
    the LiDAR outlines once 1-7 are decided.
11. **The old v2 layer** stays public for rollback. Decide when to unshare it; it is delete-protected.

## Trees

12. **Second CFTree run.** The plan is in [model-review](../model-review/README.md): mask the LiDAR buildings, give
    shrubs and brush their own layer, split merged crowns, mark REDO models. So far 126 sample answers in the 2-8 m bands
    found 29% one good tree. Decide after the 8 m+ bands are answered.

## The County

13. **What to send the County.** Reshaped outlines, buildings gone since their layer, and new buildings, as a list or
    layer for their Assessor/Surveyor. Decide the format and whether to send it.
