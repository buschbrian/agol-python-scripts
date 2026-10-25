# Replacing the public 3D buildings layer (plan, October 24, 2026)

**Nothing here has been run against ArcGIS Online. Nothing is uploaded, changed or shared.** The package is built and checked
locally; every step below is Brian's go-ahead, one at a time, the way `upload.py` and `share.py` already work.

## What is live now, and what is wrong with it
| | |
|---|---|
| Layer | Scene Service `5082b5bd063a4a03847f2082dc3533d1`, "Millcreek 3D buildings LOD1.2 (2023 lidar), planning estimate", **public** since the evening of October 23 |
| Source package item | `eb613927529347989755b0fcf9e9c8fa` (private), uploaded from `scene-layers-20261022\buildings_lod12.slpk` |
| What depends on it | the web scene "Millcreek in 3D" `5b5bdf4a63c9466fad5884039aa7357f` (its layer is defined in `reviews/2026-10-23/agol-styling/build_definitions.py`, `ITEMS["buildings3d"]`, and `maps/in-3d.json`), and through the scene the 3D Viewer app `021866ad…`; the StoryMap links to the app |
| The fault | **598 of its 21,561 blocks are slabs within 1 m of the ground** (the October 22 height source filled footprint cells the lidar did not see as roof with terrain). Median 52 m², largest 9,294 m², 79,240 m² in all; 591 of the 598 have under 80% lidar roof cover. The list is [ground-slab-fp-ids.csv](ground-slab-fp-ids.csv). |

## What replaces it
`roofer-city-v2-20261024\v2\buildings_hybrid_v2.slpk`, 20.2 MB, built by [build_v2_package.py](build_v2_package.py) from the
three-way hybrid (README, "Roofer on the whole city"):

- 21,561 buildings, one per county footprint, FP_ID 1 to 22,042 summing to 237,493,394, **exactly the live layer's**.
- **LEVEL** says which model each building uses: roofer LoD 2.2 **20,730**, Esri LOD2.0 **647**, Esri LOD1.2 **184**. The fallbacks are the
  buildings roofer could not do or the check flagged; 152 of them have no roofer solid at all.
- Roof attributes where LEVEL is roofer LoD2.2 (descriptions in `fields.md` next to the package): roof planes, roof area, slopes,
  main azimuth, ridge, eave and building height above ground, flat and south, east, west and north-facing area, snag counts. Across the
  20,730: 4.95 km² of roof surface, of which 1.25 km² flat; median plane slope by area 17°.
- Everything the live layer carries (the county attributes and roof-height statistics, so its renderer and pop-up still work), plus
  LEVEL, CHECK_VERDICT, ROOFER_VERDICT, ESRI_VERDICT, FALLBACK_REASON and the share of the footprint at ground.
- Validate Scene Layer Package passes with no warnings; the package's FP_ID statistics equal the source's; it loads and draws in the
  ArcGIS Maps SDK 5.1 through the local viewer (`viewer\start_viewer_v2.bat`).
- Against the lidar roof (compared cells): within 0.5 m on 96.7% and within 1 m on 98.1%, against 56.9% and 80.4% for the live LOD1.2.
  Against aerial imagery (97 random roofer buildings, README "Independent check on imagery"): 63% match the roof form, 29% partly,
  none poorly, 8% unclear.

## Why a new item, not an overwrite
`upload.py` never overwrites (its docstring says so, and each key uploads a new item), and the live service is public and in a public
scene. So the swap is: publish the new layer private, check it, repoint the scene, then share the new one and unshare the old. The
old layer stays untouched until then, which is also the way back: repoint the scene at the old URL. (`agol-styling/originals` holds earlier item
definitions; confirm it has the scene's before relying on it, or save the scene's JSON first.)

## Decisions only Brian can make
1. **Roof forms were "staff only" on October 23** (PUBLISHING.md, decision 3: "the LOD2.0 roofs ... staff only"; "LOD1.2 is the one to
   publish"). The v2 layer is public roof forms. If that holds, publish v2 and share it with the organisation first, or leave the LOD1.2
   up and add v2 only to staff scenes. That is a call about the roofs now being checked, not about the build.
2. **The wording.** Draft title "Millcreek 3D buildings with roof forms (2023 lidar), planning estimate"; the draft item text is in
   [draft-metadata/buildings3d_v2.md](draft-metadata/buildings3d_v2.md). Its accuracy paragraph quotes the imagery review; **the
   ratings were made by the assistant reading 340-pixel crops, not by a City reviewer**, so rate a sample yourself before it goes public
   (the 14 contact sheets and a blank rating file, `imagery-review-blank.csv`, are in the run folder `imagery-check-20261024`).
3. **Licence line.** Roofer is GPLv3 (the program, run unmodified here); the data is its output. As I understand the GPL, output is not covered
   by the programme's licence, but that is not legal advice: add it to the City Attorney question that already covers the Overture layers.
   The draft credits roofer (3DBAG, TU Delft) as a courtesy.
4. **Whether to wait.** If the roof forms are not to be public yet, the minimum fix is an interim replacement of the 598 slabs; see the last section.

## Steps (each on Brian's go-ahead)
1. **Dry run**, which only prints what would be sent (read from `upload.py`: without `--go` it prints the item and stops; I could not run it
   from this session, the classifier refused it):
   `python reviews/2026-10-22/hosting/upload/upload.py buildings3d_v2`
   The entry `buildings3d_v2` was added to `ITEMS` this session (file `…/roofer-city-v2-20261024/v2/buildings_hybrid_v2.slpk`, folder
   "Millcreek LiDAR 2023", private).
2. **Upload and publish**, private: `python reviews/2026-10-22/hosting/upload/upload.py buildings3d_v2 --go`. It records the new package and
   service ids in `runs\hosting-uploads\uploads.json` and prints them.
3. **Check it online** the way each earlier item was checked: Scene Service, 3D object layer, WGS84 labelled EGM96 as packaged, z about 1,294 to
   1,764 m, 21,561 buildings by the service's own FP_ID statistics (sum 237,493,394), the roof and LEVEL fields present; open it in a scene on
   the city terrain beside the live layer.
4. **Item text:** copy `draft-metadata/buildings3d_v2.md` into `agol-metadata/` with the new `id`, fix the brackets, apply it with
   `apply_metadata.py` as for the others.
5. **Style:** add `buildings3d_v2` (id, url) to `ITEMS` in `agol-styling/build_definitions.py`. The renderer and pop-up on `HEIGHT_P50_M` still
   work as they are; colouring by `BLDG_HT_M` or LEVEL are options. Apply with `apply_styling.py`.
6. **Repoint the scene:** in `maps/in-3d.json` and `build_definitions.py`, change the buildings layer's `url` and `itemId` to the new service;
   apply; check the 3D Viewer app.
7. **Share the new layer** with `share.py` (public or organisation, per decision 1); **unshare** the old one `5082b5bd…` (not delete: deleting
   stays Brian's, and the package items stay private).
8. Add the outcome to PUBLISHING.md.

## If v2 is not ready: the smaller fix
The October 23 filled rerun's LOD1.2 package (`scene-layers-filled-20261023\buildings_lod12.slpk`, 9.0 MB, 21,561 buildings, validated; **3**
ground-level blocks instead of 598) swaps in by the same steps with an `ITEMS` entry of its own. It removes the slabs and nothing else.

## Cost
About twice the old layer's storage (20 MB against 9.3 MB hosted). The old scene layer was recorded as under 0.1 credits a month, so this is on
the order of 0.2. Esri's rates were last read on October 22: check before relying on this.
