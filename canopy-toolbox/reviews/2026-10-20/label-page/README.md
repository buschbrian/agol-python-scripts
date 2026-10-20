# Click-through training-label page (October 20, 2026)

A local web page for labelling the 1,065 training-review units of 12TVL2804, replacing "open the CSV, find the unit in Pro".
It runs on this machine only (http://127.0.0.1:8765) and reads its data from the SSD; nothing is uploaded.

```
reviews\2026-10-20\label-page\label_page.bat serve            start the page and open it in the browser
reviews\2026-10-20\label-page\label_page.bat import           preview importing the page's answers into the review geodatabase
reviews\2026-10-20\label-page\label_page.bat import --apply   import them (close the review project in Pro first)
reviews\2026-10-20\label-page\label_page.bat build            rebuild the page data (once per packet; Myria3D Python)
```

## Using it
Each unit shows a 3D view of every point within 12 m (drag to rotate, right-drag to pan, scroll to zoom), two 3 m-wide side
sections (west to east, south to north), and a 40 m NAIP 2024 chip. The patch is the red cylinder; its own points are red.
Label only the returns inside the patch, as before.

| Key | Action |
|---|---|
| 1 to 0 | tree, building roof, wall, wire, pole, other structure, shrub/low vegetation, ground, vehicle, water |
| M, U | mixed, unsure |
| Enter or right arrow, left arrow | next, previous |
| Backspace | clear this unit's answer on the page |
| C | point colour: imagery, height, intensity, returns |
| R | reset the view |
| N | type a note (Esc to leave the box) |
| I | switch between the imagery map and the NAIP chip |
| S | split the patch at a height: the line starts mid-patch, up/down arrows move it 10 cm (Shift 50 cm), then the label above, then below; Esc cancels |

"Show" picks the refinement priority list, the recheck list, unlabelled units, all units, the units answered on the page,
mixed answers to split, or the 40 audit-2 units.
- **Refinement priority** (build_priority.py): unlabelled units whose answers settle open refinement questions, interleaved from
  four groups (rule-11 green, rule-11 bare, changed by the rules, model unsure). The page shows the order only; the groups are kept
  beside the packet. These units are chosen by model disagreement, so they test rules and never estimate an accuracy.
- **Recheck**: answers to look at again. On October 20 it held the two SHRUB_LOW_VEG answers that look like mown lawn, which is
  GROUND since that day. Changing an answer already imported needs `label_page.bat import --apply --replace`. After a label the page
moves to the next unanswered unit; the left arrow still goes back to fix one. The first label asks for your initials (REVIEWER).

## Splitting a mixed patch (decided October 20)
A quarter of the first 79 answers were MIXED or UNSURE, mostly tall cylinders holding a roof with a tree above it. For those,
press **S** (or the Split button): a yellow line appears in the middle of the patch and a yellow banner shows each step. Move the
line with the up and down arrows (or click a section at the right height), then press the label key for the points **above** the
line and then for the points **below** it. "Show: Mixed (to split)" lists the units answered MIXED so they can be split later. The line shows in both sections and as a yellow ring in
3D. The answer is stored as LABEL (above), LABEL_BELOW and SPLIT_Z (the elevation of the line); both parts must be real classes
and differ, and the line must lie inside the slab. The training export gives points at or below the line the lower label.
Use MIXED only when no single height separates the objects.

Importing split answers needs two new fields in the review table: close the project in Pro and run
`label_page.bat import --apply --add-split-fields` (the geodatabase is copied first, beside it). Imagery chip export leaves split
units out, because a chip can carry only one label.

## Blind by design
The page data (build_label_data.py) contains no baseline class, model output, triage proposal or queue hypothesis, so the page
cannot show one (decided October 20). Labels made here stay independent of FRACTAL and the triage, so they can keep testing them,
and audit 2 can be labelled here as it must be: without seeing a proposal.

## Higher-resolution imagery (map panel, key I)
The side panel has a zoomable map centred on the unit: the red circle is the patch, the yellow dashed circle the 12 m reach of
the 3D view. Its layers come from `<packet>\label-page\imagery-layers.json` on the SSD, a list you edit yourself
(imagery-layers.example.json shows the shape). It is never in git, because a licensed UGRC Discover link carries the
organisation's quad-word, which UGRC says must not be shared outside it; the page only runs on 127.0.0.1, which keeps it internal.
- **Hexagon 15 cm (July 2024), UGRC Discover**: copy the Hexagon tile link from your Discover registration into the `url`, with
  `{z}/{x}/{y}` where the link has the tile level, column and row. Put it first so it opens by default.
- **USGS National Map imagery** (public domain, NAIP-based, coarse when zoomed in) is in the file now as a fallback.
- **Nearmap** (allowed for imagery verification, October 20): add a `"type": "wms"` layer with your Custom WMS URL from
  MyAccount (it contains the API key, so it stays in this file only) and, as `layers`, the survey nearest the lidar
  (October-November 2023). `python canopy-toolbox\nearmap_historical_wms.py --url-file <file holding the URL> list` lists them.
- **Esri World Imagery** can be added the same way (`https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}`)
  if its terms suit this use; its capture dates vary by area.
Tiles stream while you look; nothing is downloaded or stored. Web imagery and the lidar can be a metre or more apart (NAD83(2011)
versus WGS84, and the imagery's own accuracy), so read the circle as a guide. The NAIP chip tab is still there.

The server also keeps `answers\label-page-log.jsonl`, an append-only record of every save and clear (time, unit, label,
reviewer), so any answer can be traced. One stray test answer appeared during the October 20 testing and was removed; it could
not be reproduced, and re-saving after a note edit now requires a real change on the page.

## Where answers go
Every answer is checked by the server with `training_review.normalize_answer`, the same check `restore` applies, and kept in
`<packet>\label-page\answers\label-page-answers.csv` (the training-label backup format). The review geodatabase is changed only
by `import --apply` (training_labels.bat restore), which writes units that are still blank there and reports any conflict;
`--replace` overwrites a different label. Then run `training_labels.bat save` as usual to back the labels up to the repo.

Checked on October 20: the page's row for Q1-0001 carries the same unit token as the repo backup, the restore preview read it as
"unchanged", an invalid label was refused by the server, and requests outside the data folder are refused.

## Files
- build_label_data.py: points (float32 x, y, z relative to the patch centre and ground; uint8 imagery RGB, intensity, returns),
  chips and units.json, in `<packet>\label-page` (about 2 GB, outside git).
- serve_label_page.py: the local server (ArcGIS Pro Python; listens on 127.0.0.1 only).
- index.html, app.js, style.css: the page (three.js r128 from cdnjs).
