# Cartography for the Millcreek LiDAR layers on ArcGIS Online (October 23, 2026)

Brian asked for the eight hosted layers to be styled professionally ("symbology and blend modes on most of these layers
and clean up the legends"). Done from the repo with the ArcGIS API for Python 2.4.3 and REST, account GISMillcreek.
**Nothing was shared or deleted**; every new item is private in the "Millcreek LiDAR 2023" folder. Item text (titles,
summaries, descriptions, tags) and field descriptions of the eight layers were not touched: another session owns them.

## New items

| Item | ID | What it shows |
|---|---|---|
| Web map "Millcreek terrain and slope" | `177bfc592415451585ba72ab9207b3c6` | slope classes, hillshade blended over them (multiply), contours; Light Gray Canvas |
| Web map "Millcreek tree canopy" | `e5efa719691045849108553394448f35` | canopy cover zones at city scale, crowns and treetops from 1:18,000 / 1:10,000; hillshade soft-light over Imagery Hybrid |
| Web map "Millcreek buildings" | `504554bd5a9545559db06aa6098e8e49` | buildings by median roof height over the hillshade (multiply); Light Gray Canvas |
| Web scene "Millcreek in 3D" | `5b5bdf4a63c9466fad5884039aa7357f` | city terrain in the ground above World Elevation, LOD1.2 buildings by height, hillshade draped; four slides |

Each map has bookmarks (whole city, Millcreek Common, Canyon Rim, Evergreen and East Millcreek, Olympus Cove foothills,
Scott Avenue), the estimate warning in its summary and description, and the hillshade kept out of the legend.

## Layer-level defaults (what a layer looks like wherever it is added)

| Layer | Where it lives | Change |
|---|---|---|
| Slope, contours, treetops, crowns | the item's resource `styles/root.json` | see below; the service's own style is untouched (`originals/*_service_style.json`) |
| Buildings, canopy cover zones | the feature service item's data (drawing and pop-ups), and each layer's service `drawingInfo` (updateDefinition with that key only) | class renderers and pop-ups |
| 3D buildings | the scene service item's data | renderer by height, pop-up |
| Hillshade, terrain | none | blend modes and opacity live in the maps |

The ArcGIS Maps SDK (5.1) loads a vector tile item's style from `{item}/resources/styles/root.json` when the item has
one, else from the service (checked: `currentStyleInfo.styleUrl` is the item resource). The item style needs absolute
`sources`, `sprite` and `glyphs` URLs, since relative ones would resolve against the item. **To undo** a style, remove
the item resource (`removeResources`); the layer falls back to the service's style. The service styles and the original
layer definitions are in `originals/`; the feature and scene items had no item data and no resources before this work.

- **Slope**: the six classes and their labels kept; YlOrRd, flat ground nearly clear (15% opacity) rising to 62% for
  30% and over, so the hillshade and basemap read through.
- **Contours**: 10 m index lines 0.9 to 2.0 px by zoom, dark brown; 2 m lines 0.5 to 0.8 px at 30 to 50% opacity; round
  joins. **No labels**: the tiles keep no elevation value (`hosting/vector-tiles/README.md`), so there is nothing to label.
- **Treetops**: radius grows with height class (2.0 to 5.2 px at level 17, half that at level 14), YlGn, dark outline.
- **Crowns**: the same YlGn classes at 50% fill with a dark green outline.
- **Buildings**: median roof height in five classes (under 4 m, 4-6, 6-9, 9-12, 12 m and over, each with feet), grey
  for no lidar height. Pop-up: median and 95th percentile heights in m and ft, roof support, the HEIGHT_STATUS flags in
  plain words (thresholds from `canopy/planning.py`), footprint area, parcel and county ID, the warning.
- **Canopy cover zones**: the 13 zones are three nested tiers (the city; four ownership zones; the eight public owners,
  which make up the public / government zone exactly, 838.9 acres). The renderer (an Arcade value expression) draws the
  finest non-overlapping tier only, in four classes (under 10%, 10-20, 20-30, 30% and over); the city and the public /
  government total draw nothing. Pop-up: cover, bounds, acres, the October 19 comparison, observed share, the warning.

## Checks (October 23)

- `apply_styling.py` reads everything back after sending; a dry run afterwards reports every style, item data, service
  drawingInfo and map **unchanged**. ArcGIS Online rewrites pop-up HTML (`<br>` to `<br />`, double-quoted attributes to
  single), so the definitions are written in that form. A replaced style resource is served stale for a few seconds to
  minutes; the script retries the read and browsers may show the old style until their cache expires.
- Rendered each map and the scene with the ArcGIS Maps SDK 5.1 on a local page (`web/`), signed in with ArcGIS Pro's
  token, at city scale and at a neighbourhood bookmark or slide, in the in-app browser and in Playwright's Chromium (the
  3D view does not draw in a hidden browser pane). All layers load with no errors. One fix round: the hillshade under a
  multiply blend greyed the whole city, so it now carries a brightness effect (1.3 to 1.4) that lifts flat ground to
  white; slope opacities were lowered and contours darkened; zone colours given more contrast; building outlines thinned
  for city scale; the scene's legend title set.
- Pop-ups read through the SDK's Feature widget: buildings (tall, low support, no roof points) and zones (Salt Lake City,
  no parcel) read as intended.

## Limits found

- **The legend cannot list vector tile layers.** The SDK's Legend widget, which Map Viewer and the apps use, does not
  support VectorTileLayer (Esri's Legend reference lists it as unsupported; seen here as "No legend"). The legends show
  the buildings, zones and 3D buildings; the class keys for slope, contours, crowns and treetops are in the map
  descriptions with coloured swatches. A real legend entry needs a feature layer (or a legend image in the app).
- **Vector tile layers stop drawing past 1:2,257** in the SDK. Pro overzooms. The cause is the services' `maxScale`
  (2,257), not their levels. The fix needs no new tiles and is waiting for Brian's go-ahead: `../vt-overzoom/README.md`.
- **3D trees are not possible from the treetops**: they are vector tiles, which drape flat. 3D tree symbols need the
  treetops as a hosted point layer with heights (feature storage cost; see `hosting/PLAN.md`).
- The web maps were checked with the SDK, not in Map Viewer itself (that needs a browser sign-in).

## Rerun

    python reviews/2026-10-23/agol-styling/build_definitions.py          standard library; writes styles/, layers/, maps/
    python reviews/2026-10-23/agol-styling/apply_styling.py [STEP ...]   ArcGIS Pro Python; dry run (styles, layers, maps)
    python reviews/2026-10-23/agol-styling/apply_styling.py ... --go     send what differs, read it back
    python reviews/2026-10-23/agol-styling/web/serve_check.py            ArcGIS Pro Python; check page on 127.0.0.1:8797

Edit `build_definitions.py`, not the JSON. `created.json` records the new map and scene IDs so reruns update them in place.
