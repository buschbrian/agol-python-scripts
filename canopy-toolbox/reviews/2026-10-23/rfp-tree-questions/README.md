# RFP bidder questions on the tree estimate (October 23, 2026)

A bidder on the city's tree inventory RFP asked how the "approximately 45,000 trees" figure was developed, whether the
city will accept estimated tree height and canopy spread, and about heritage and specimen trees. Brian asked what the
lidar work can give back. This note reads the [October 22 product library](../../2026-10-22/PRODUCTS.md); every figure
below comes from [counts.py](counts.py) (output [counts.json](counts.json)). Nothing has been sent.

## The figure: about 49,000, replacing the 45,000
The 45,000 is not recorded anywhere in this repo and Brian does not know its source, so on October 23 he chose to answer
with the lidar figure instead: **about 49,000**, the treetops outside every parcel plus those on city-owned land, not
SUSPECT (49,052, the "Both" row). The lidar figures by scope:

| Scope (treetops at least 2 m / 6.6 ft) | All | Not SUSPECT | Not SUSPECT, at least 4 m / 13 ft | Not SUSPECT, crown at least 3 m2 |
|---|---:|---:|---:|---:|
| Outside every parcel (mostly streets and park strips) | 48,697 | **47,535** | 37,784 | 33,774 |
| Owned by Millcreek | 1,593 | 1,517 | 1,296 | 1,301 |
| **Both** | 50,290 | **49,052** | 39,080 | 35,075 |
| Other public owners except Salt Lake County | 11,533 | 10,892 | 8,883 | 8,923 |
| Salt Lake County | 61,295 | 61,211 | 30,369 | 43,724 |
| October 8 count, outside every parcel (older classification) | 59,212 | | | |

SUSPECT treetops are those the independent geometric checks flag as possible roof edges, wires, poles or walls. Salt
Lake County land in the city holds 61,295 treetops with a median height of 4.0 m (13 ft), which reads as foothill scrub
rather than park trees; it is left out of "public lands" in the drafts below unless the RFP covers county land.

"Outside every parcel" is not a mapped right-of-way: it is the city outside every parcel polygon in the 2025-tax-year
snapshot. Most of it is streets and park strips, but it also holds canal and creek corridors, and a treetop from a yard
tree that leans over the street counts there. A right-of-way layer was not available here (`G:` was not mounted); a
count inside one would be the firmer figure.

## Draft answers for the bidder
### 1. How was the estimate of approximately 45,000 trees developed? (final)
> The city has refined this figure: the current estimate is **approximately 49,000 trees** in the public right-of-way
> and on city-owned property. It comes from aerial lidar of the Salt Lake Valley collected in October and November 2023.
> City GIS staff classified the lidar points, built a canopy height model at 0.5 m (1.6 ft) resolution and detected
> individual treetops at least 2 m (6.6 ft) tall: about 527,000 across the city. Each treetop was assigned to the parcel
> it falls on, using the city's 2025 parcel layer. About 47,500 treetops fall outside every parcel, mostly in street
> rights-of-way and park strips, and about 1,500 are on city-owned property, after removing points that look like roof
> edges, wires or poles. Trees on land owned by Salt Lake County, other agencies and private owners are not included.
>
> This is a planning estimate, not a field count, and has not been field verified. Lidar can miss small or understory
> trees, can split one large tree into several tops or merge a clump of small trees into one, and counts tall shrubs
> as well as trees. A treetop can sit a few feet from its trunk, so trees near a property line may belong to either side,
> and some trees counted in the right-of-way may be private trees leaning over it. The number of trees in scope will be
> set by the inventory itself.

If the RFP text or price sheet still says 45,000, it should be changed to "approximately 49,000" by addendum so every
bidder prices the same figure; that is the procurement lead's step.

### 2. Will the city accept estimated tree height and canopy spread measurements?
This is the city's call; the lidar only changes what the city can offer. What exists, for every detected treetop:
- **Height** (`HEIGHT_M`): the highest canopy cell at the treetop, from the 0.5 m canopy height model. Measured in autumn
  2023, so trees have had three growing seasons since.
- **Canopy spread** (`CROWN_AREA_M2`, `CROWN_DIAM_M`): an estimated crown region around each treetop; 400,063 have a
  crown of at least 3 m2 (city median 4.0 m / 13 ft across). A broad tree can be split across several regions and a clump
  of small trees can form one, so these are not surveyed crown widths.
- **Not available from lidar**: species, DBH, condition, the trunk location, and anything about trees under a taller
  crown. These have to come from the field.

Two drafts, depending on what the city decides:

> **(a) Estimates accepted.** Yes. Height and canopy spread may be estimated in the field, recorded in [5 ft] classes.
> The city can provide lidar-derived height and crown estimates for detected trees as a reference; the contractor's
> field values govern where they differ.

> **(b) Field values required.** Height and canopy spread are to be recorded from field observation [by clinometer or
> laser rangefinder / ocular estimate in 5 ft classes]. The city's lidar-derived heights and crowns are planning
> estimates from 2023 and may be provided for reference only; they will not be accepted in place of field values.

Either way, the treetops and crowns are staff-only until the SUSPECT review ([publishing decision 3](../PUBLISHING.md)),
so sharing them with the awarded contractor would be a deliberate exception.

### 3. Identification of any and all significant heritage and specimen trees
The city holds no heritage or specimen tree inventory, and lidar cannot identify one by itself: those designations
usually rest on DBH, species or history, none of which lidar measures. It can screen by size. With not SUSPECT, a crown of
at least 3 m2, a height of at least 20 m (66 ft) and a crown at least 12 m (39 ft) across, there are **1,033 candidates
citywide: 53 outside every parcel and 2 on city-owned land** (61 on Salt Lake City land, 12 on county land, 895 private).
The crown filter matters: the tallest treetops in the city, about 42 m with crowns under 4 m, are almost certainly towers
or poles that the checks missed, and the rate of missed non-trees has not been measured (calibration sample 2 is still
unlabelled). Any list sent out should be checked against imagery first.

> The city does not maintain an inventory of heritage or specimen trees. The contractor should identify and flag trees
> that meet [the city's definition, e.g. a DBH of at least 30 in, or species or historic significance] during the
> inventory. [Optional: The city can provide a lidar screening list of about 55 unusually tall, broad trees in the
> rights-of-way and on city property as a starting point; it is not a designation.]

Check whether Millcreek's code or urban forestry plan defines heritage or specimen trees before choosing the bracketed
wording.

## Limits
- These are unvalidated planning estimates. No detection accuracy is stated: the 12TVL2804 label figures in PRODUCTS.md
  are training diagnostics on one hard tile, and calibration sample 2 is unlabelled.
- Ownership uses the 2025-tax-year parcels on 2023 detections, at the treetop cell.
- The 2 m minimum height includes tall shrubs; the 4 m and 6 m columns are there for that reason.
