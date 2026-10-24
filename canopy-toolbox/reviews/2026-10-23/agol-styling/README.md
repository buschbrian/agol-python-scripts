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
| Web scene "Millcreek buildings in 3D" (was "Millcreek in 3D") | `5b5bdf4a63c9466fad5884039aa7357f` | city terrain in the ground above World Elevation, LOD1.2 buildings in greys by height with edges, hillshade draped, OpenStreetMap 3D place labels; four slides with pictures |
| Web scene "Millcreek terrain and slope in 3D" (October 23 evening, **private**) | `71b680b486b245fd8ec17eb80387be94` | the same ground, with the hillshade (0.65), slope classes and contours draped, OpenStreetMap 3D place labels; five slides with pictures (the east bench, Olympus Cove, Mount Olympus foothills, Millcreek Canyon mouth, Canyon Rim bench) |

Each map has bookmarks (whole city, Millcreek Common, Canyon Rim, Evergreen and East Millcreek, Olympus Cove foothills,
Scott Avenue), the estimate warning in its summary and description, and the hillshade kept out of the legend.

## Layer-level defaults (what a layer looks like wherever it is added)

| Layer | Where it lives | Change |
|---|---|---|
| Slope, contours, treetops, crowns | the item's resource `styles/root.json` | see below; the service's own style is untouched (`originals/*_service_style.json`) |
| Buildings, canopy cover zones | the feature service item's data (drawing and pop-ups), and each layer's service `drawingInfo` (updateDefinition with that key only) | class renderers and pop-ups |
| 3D buildings | the scene service item's data | greys by height with edges, pop-up |
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

- **3D buildings** (revised October 23 evening): the same five height classes in near-white to mid grey (taller
  darker), pale sand for no lidar height, dark solid edges at 35% transparency, as Esri's 3D basemaps draw buildings;
  the scene's sun and shadows give the form. The 2D buildings map keeps its purple classes.

## Legend keys for the vector tile layers (October 23 evening)

Map Viewer and the apps showed the four vector tile layers' styles but "No legend": the Legend cannot read a vector
tile style. Each vector tile layer in the two maps now sits in a group layer with a **key layer**, an empty feature
collection stored in the map (no item, nothing to share) whose class renderer repeats the item style: slope's six
classes, the 10 m index and 2 m contour lines, the five treetop heights (dots sized as at level 17) and the five crown
classes. The key carries its layer's scale range, so it is listed only while the tiles draw (treetops from 1:10,000,
crowns from 1:18,056). The group gives one entry and one switch in the layer list; the tile layer itself has
`showLegend` off. Checked in Map Viewer itself as an anonymous viewer: the Legend lists slope and contours at city
scale and treetops and crowns at level 17 over Canyon Rim. A key for a map built elsewhere would need a separate
(shared) item.

## The web scene (October 23 evening)

- Esri's OpenStreetMap 3D place labels (`OpenStreetMap3D_DarkLabels_v1`, public) replace the basemap's draped
  reference labels. They include businesses, so commercial streets are busy.
- Esri's OpenStreetMap trees (`OpenStreetMap3D_Trees_Thematic_v1`) were tried and left out: OpenStreetMap maps no trees
  in Millcreek, so the layer drew none at any slide or at 1:1,500 over Canyon Rim Park.
- Each slide has a picture: a 600 x 400 JPEG of the slide from `check.html?thumb=1&slide=N`, stored as the scene's item
  resource `slides/slide_N.jpg`, which the slide's thumbnail URL names (`thumbnails.json` entries with a `resource`).
  Scene Viewer had shown broken images; it now loads all four for an anonymous viewer.

## Terrain and slope in 3D, apps and clean-up (October 23 evening)

Brian asked to rebuild some apps in 3D (terrain and slope, buildings) and to clean up map contents, basemaps and look,
and item pages, and to remove the StoryMap.

- **New scene "Millcreek terrain and slope in 3D"** (`71b680b4…`, private). A scene has no blend modes (the Maps SDK draws
  every layer normally in 3D), so the hillshade lies under the half-transparent slope classes instead of being multiplied
  over them, and the terrain's sun lighting adds the larger relief. Slide ground heights were read from the scene's own
  ground (`queryElevation`). The slides' visible-layer lists name the layers inside each group too: a slide hides every
  layer it does not list, which first hid the slope and contours.
- **Legend in a scene.** A web scene drops the 2D maps' in-map key layers ("Feature layer must be created with either a
  url or a source") and takes only 3D symbols. Its keys point at the hosted canopy-zones layer with the filter `1=0`: they
  draw nothing and have no pop-up, and their renderers (PolygonSymbol3D, LineSymbol3D) give the legend the slope and
  contour classes. Checked in the SDK at every slide.
- **Names.** The layer list shows a group's title and the legend shows it again above the key's own title, so the keys
  now name what is classed: "Slope (percent rise)", "Contour interval", "Treetop height". Groups: "Slope classes",
  "Contours (2 m, 10 m index)", "Tree crowns by treetop height", "Treetops by height", the same in the maps and the scene.
- **Item pages** of the three maps and two scenes follow the item-text session's house style (`agol-metadata`): summary
  ending "Unvalidated planning estimates; not surveyed or field-verified.", the warning first in the description, then the
  lidar, coordinates and contact blocks read from `agol-metadata/_shared.md`, its terms of use, its tags and credits.
  The repository line was dropped from the public descriptions. "Millcreek in 3D" became "Millcreek buildings in 3D".
- **Apps** (`../agol-apps/make_apps.py update` and `delete`): the terrain app (`66693381…`) became a 3D Viewer app on the
  new scene, updated in place; the "Millcreek in 3D" app (`021866ad…`) became "Millcreek Buildings in 3D"; the tree canopy
  app stays a Sidebar app. The Sidebar buildings app (`370a1f38…`) and the StoryMap (`8d43f724…`) were deleted to the
  recycle bin (both listed there afterwards; restorable for the bin's retention period). All apps private, each with the
  warning splash and a thumbnail; the 2D buildings web map stays, without an app.

## Thumbnails

All twelve items (the eight layers, the three maps, the scene) have a 600 x 400 thumbnail rendered from their own
symbology by `web/check.html?thumb=1` in Playwright's Chromium, at the views in `thumbnails.json`: slope, contours,
hillshade and the buildings on light grey; treetops and crowns over imagery at Canyon Rim Park; the 3D buildings and
the terrain from the scene's Olympus Cove slide (terrain with the buildings hidden). The feature service's thumbnail
shows both its layers. The PNGs hold basemap imagery, so they are not in the repo; render them again from
`thumbnails.json` to resend. The seven layer thumbnails generated at publishing (JPEGs) were saved before being
replaced, outside the repo. ArcGIS Online stores the PNG as sent (`/info/<thumbnail>?w=800` returns it byte for
byte) and serves 200-pixel copies by default. Once, on October 23, six thumbnails read back a few bytes different from
the local PNGs and were resent; the copies saved to `replaced/` had identical pixels, so nothing visible changed. The
scene, 3D buildings and terrain thumbnails were rendered again after the scene restyle.

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
  support VectorTileLayer (Esri's Legend reference lists it as unsupported; seen here as "No legend"). Worked around in
  the two maps with key layers (above); the item styles are not involved, so the vector tile items added to a new map
  still show "No legend". The map descriptions keep their coloured swatch keys.
- **Vector tile layers stopped drawing past 1:2,257** in the SDK. The cause was each service's `maxScale` (2,257), not
  its levels; a separate session cleared it on all four services on October 23 (`set_max_scale.py`, branch
  `claude/silly-shaw-01edf4`), and they now draw closer in, with no new tiles.
- **3D trees are not possible from the treetops**: they are vector tiles, which drape flat. 3D tree symbols need the
  treetops as a hosted point layer with heights (feature storage cost; see `hosting/PLAN.md`).
- The web maps were first checked with the SDK only; since the items went public, Map Viewer and Scene Viewer have been
  checked anonymously in Playwright's Chromium (legends, layer list, slide pictures).

## Rerun

    python reviews/2026-10-23/agol-styling/build_definitions.py          standard library; writes styles/, layers/, maps/
    python reviews/2026-10-23/agol-styling/apply_styling.py [STEP ...]   ArcGIS Pro Python; dry run (styles, layers, maps)
    python reviews/2026-10-23/agol-styling/apply_styling.py ... --go     send what differs, read it back
    python reviews/2026-10-23/agol-styling/apply_styling.py thumbnails --thumbs DIR [--go]   DIR holds <key>.png and slide <key>.jpg
    python reviews/2026-10-23/agol-styling/web/serve_check.py            ArcGIS Pro Python; check page on 127.0.0.1:8797

Edit `build_definitions.py`, not the JSON. `created.json` records the new map and scene IDs so reruns update them in place.
