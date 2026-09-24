# <Year> <Area> — acquisition record

**<Project name and ID>**, <work unit if any>, acquired by <vendor>. The local copy is
`<path as used>`, <how it was obtained and whether it is complete or an extract>.

Generated facts about the local copy are in [acquisition-facts.md](acquisition-facts.md) and
[acquisition.json](acquisition.json); regenerate them rather than editing them (see
[the procedure](../README.md)). This page holds what the vendor declared, what that means for the
toolbox, and what is still open.

## Declared facts

Fill every row. Write "not stated" rather than leaving a row out — a missing leaf condition or
geoid is itself a finding.

| Fact | Declared value | Source |
|---|---|---|
| Collection dates | | |
| Quality level | | |
| Pulse spacing and density | | |
| Vertical accuracy, point cloud | | |
| Vertical accuracy, DEM | | |
| Horizontal CRS | | |
| Vertical datum and geoid | | |
| Delivered classes | | |
| Flag policy | withheld / overlap / synthetic | |
| Sensor and platform | | |
| Ground conditions | including leaf condition | |
| Control | | |
| Project extent | | |
| Delivered products | | |

**Checked against the data.** Compare the table with the generated facts: do the header CRSs match
the declared ones, do swath dates fall inside the declared window, and is the density plausible
for the declared spacing? Say what agreed and what did not.

## Delivered classification

| Class | Meaning |
|---|---|

## Consequences for the toolbox

Work through each of these against the toolbox's defaults:

- Which classes the toolbox must derive, and whether `prepare`'s preserve-ground-and-noise default
  still fits.
- Whether any delivered class is missing from `NON_CANOPY_CLASSES` or the noise set.
- Whether the withheld, overlap and synthetic exclusions have any effect.
- What the season means for canopy figures.
- Whether a vendor DEM exists, and how it compares with the toolbox DTM.

## Documented voids

## Coverage of Millcreek

Summarize the generated coverage section: share of the city covered, missing tiles that matter,
and which boundary layer was used.

## Discrepancies between sources — do not silently resolve

## Comparability with other epochs

| Property | This acquisition |
|---|---|
| Horizontal CRS | |
| Vertical datum and geoid | |
| Season | |
| Quality level and density | |
| Ground class | |
| Building and vegetation classes | |
| Overlap flagged | |

## Open questions and next checks

## Source files

What arrived, when, what is kept in `reference/`, and what was left out and why.
