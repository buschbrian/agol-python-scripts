# Vector tile layers past 1:2,257 (October 23, 2026)

The styling session found that Millcreek's four hosted vector tile layers (slope classes, contours, treetops, crowns)
stop drawing in the ArcGIS Maps SDK 5.1 past 1:2,257, so in Map Viewer and the apps crowns and treetops vanish at
1:1,128. ArcGIS Pro overzooms and draws them. This note confirms the cause, picks a fix that needs **no new tiles**, and
applies it one item at a time on Brian's go-ahead.

**Applied to all four** on Brian's go-ahead, October 23 (local time): treetops at 15:50, crowns at 15:55, slope at 15:56,
contours at 15:57. Each service now reads `maxScale` 0, its item ID is unchanged, and `styles/root.json` is still
listed (`applied.json`). Checked in the SDK on the live services, with nothing simulated, at 1:1,128 over Highland
Drive at 3900 South. Each layer drew in its web map and on its own, using its item style:
`canopy_map_live_1128.jpg` (crowns and treetops) and `terrain_map_live_1128.png` (slope and contours). Treetops was
also checked at 1:282. After each change, the layers not yet changed stayed suspended in the same view, as expected.

## Cause: the service's `maxScale`, not the depth of the tiles

Each VectorTileServer JSON (and its admin JSON) carries `"maxScale": 2256.9943525`, the scale of its last level (17).
The SDK suspends the layer view past that scale **even when the layer's own maxScale is 0**, as it is in all three web
maps. Tested with `agol-styling/web/zoom.html` (below), Playwright's Chromium, signed in with Pro's token, at 1:1,128
over Highland Drive at 3900 South:

| What the SDK was given | Layers | `suspended` |
|---|---|---|
| The services and item styles as they are | crowns, treetops (canopy map); treetops alone | true |
| As they are, with the layer's `maxScale` set to 0 after load | treetops | true |
| Service JSON with its LODs extended to level 22, `maxScale` kept | crowns, treetops (canopy map) | **true** |
| Service JSON with `maxScale` 0, nothing else changed | crowns, treetops; slope, contours (both maps) | **false**, draws |
| Item style with its source given as a `tiles` URL template instead of the service `url` | all four (both maps) | **false**, draws |

Extending the LODs alone changes nothing, so rebuilding the packages with deeper levels would only help because a deeper
last level moves `maxScale` with it. The changes were made inside the browser by request interceptors; nothing was
written to ArcGIS Online.

The tiles themselves are fine past level 17. The caches are indexed (sparse areas stop at level 15 or 16; the tilemap
reports levels to 16, `maxLOD` 16), and with `maxScale` 0 the SDK overzooms them as Pro does: at 1:1,128, 1:564 and
1:282 it fetched the same level-15 and level-16 tiles and drew the 0.5 m slope steps, contours, crowns and treetops
(`canopy_map_svcmax0_1128.jpg`, `terrain_map_svcmax0_564.png`).

## The fix chosen: set each service's `maxScale` to 0

`set_max_scale.py` posts `serviceDefinition = {"maxScale": 0}` to the service's admin `edit` operation. That is the
operation the ArcGIS API's `VectorTileLayerManager.edit_tile_service` uses, but the API skips a `max_scale` of 0, so the
script posts the request itself. It changes nothing else: no tiles, levels or style. The item ID, the item text and
`styles/root.json` stay as they are. Because it fixes the service, every client gets it: Map Viewer, the apps,
the item page, and anyone who adds the service by URL rather than by item.

    python reviews/2026-10-23/vt-overzoom/set_max_scale.py list                     each service's maxScale; style resource present
    python reviews/2026-10-23/vt-overzoom/set_max_scale.py treetops                 dry run
    python reviews/2026-10-23/vt-overzoom/set_max_scale.py treetops --go            send, read back, log to applied.json
    python reviews/2026-10-23/vt-overzoom/set_max_scale.py treetops --restore --go  undo: the saved original maxScale

ArcGIS Pro Python with `PYTHONNOUSERSITE=1`; `GIS("pro")` signs in. On `--go`, the script saves the service and admin
JSON to `originals/` before its first change. It then reads the service back, checks that `styles/root.json` is still
listed, and logs the result. **Suggested order:** treetops first. Then check it in the SDK with no interceptor:

    python reviews/2026-10-23/agol-styling/web/serve_check.py --port 8799
    http://127.0.0.1:8799/zoom.html?webmap=e5efa719691045849108553394448f35&mode=item&scale=1128

Treetops should read `suspended: false`, with `styleUrl` still the item resource. Then do crowns, slope and contours the
same way. Port 8797 may already be in use by another session's check server. Windows let a second server bind it
silently, and the page then came from the other checkout.

**ArcGIS Online accepts it**: all four answered `{"status": "success"}`, and their admin and service JSON read 0.

**Allow up to an hour before it shows everywhere.** CloudFront caches the service JSON (`s-maxage=3600`) separately
for each `Origin` header. After the treetops edit, the check page on `http://127.0.0.1:8799` still got the copy cached
at 21:28:58 GMT, 22 minutes before the edit (`Hit from cloudfront`), so the layer stayed suspended. On
`http://localhost:8799`, a new origin, it got the new JSON and drew. Map Viewer and the apps behave the same way: each
origin sees the change once its cached copy, at most an hour old, expires. To check sooner, open the page on an origin
not used in the last hour. Crowns and slope were checked on `http://localhost:8800` and contours on
`http://localhost:8801`, opened after each edit. The script's read-back now adds a unique query string so it is not fooled. Its first run
was fooled, and it reported a failure that a fresh read then disproved (`applied.json`).

## Fallback: a `tiles` source in the item styles

If the service edit is refused, the item style can name its source by URL template:
`"tiles": ["…/VectorTileServer/tile/{z}/{y}/{x}.pbf"]` in place of `"url"`. This works in the SDK (table above). The
change belongs in `agol-styling/build_definitions.py`, sent with `apply_styling.py --go`. Compared with the service fix:
- The SDK no longer reads the tilemap and asks for every tile at the view's own level: 2 to 10 times as many tile
  requests (for example 30 against 9 at 1:4,514). The tiles the tilemap leaves out still answer 200, some with 0 bytes.
- No features were lost. At 8 places (city centre, foothills, west side, north edge) and at 1:4,514 and 1:2,257, both
  maps were screenshotted with and without it. The differences were only basemap label placement, the attribution order
  and faint tile seams. At 1:1,128 the treetops drew pixel for pixel the same as with the service fix
  (`treetops_tiles_vs_svcmax0.png`).
- It fixes only clients that load the layer from its item (the item resource). It does not help one added by service
  URL, or one that uses the service's own style.

## Rebuilding: not needed

The service fix needs no new tiles, so the packages were not rebuilt and no size or credit cost was measured. If a rebuild
is ever wanted, the last level sets `maxScale` again. Run `set_max_scale.py` after any republish or replacement.

## Replacing a hosted vector tile service without losing the item ID or the style

Use this only if the services ever need new tiles. It was not run.
- **Do not publish again with `upload.py`.** That makes new items with new IDs, and the web maps, the scene and the item
  resources all point at the old IDs.
- **Keep the item, swap what is behind it.** In ArcGIS Online: publish the new `.vtpk` as a temporary layer. Then, on the
  existing layer's item page, use Settings > *Replace layer* and pick the temporary layer. The existing item keeps its
  ID and takes the new service; the old service moves to the temporary item, which keeps it as an archive until
  deleted. Before relying on this, check that the item page offers *Replace layer* for vector tile layers; that was
  not checked here. Alternatively, update the package item's file in place (`item.update(data=...)`) and run the admin `update`
  operation on the service (the API's `VectorTileLayerManager.update_tiles()`, which posts `/update` for package-sourced
  services). Each step is Brian's go-ahead.
- **Then restore and check, in this order:**
  1. `apply_styling.py styles` (dry run) shows whether `styles/root.json` survived. `--go` sends it back if not.
  2. The new service's tile URL path may change. The item style has absolute `sources`, `sprite` and `glyphs` URLs, so
     update `build_definitions.py` if it does.
  3. `set_max_scale.py ITEM --go` clears the new `maxScale`.
  4. `zoom.html` at 1:1,128 confirms the layer draws.

## Files

- `set_max_scale.py`: the fix, one item per command, dry run unless `--go`. `applied.json`: what was sent, the
  answer and the read-back. `originals/`: each service's JSON before its first change.
- `../agol-styling/web/zoom.html`, `zoom.js`: the SDK check page. `layer=` or `webmap=`, `mode=` one of item, maxscale0,
  tiles, patch (`tiles` source in flight), svcmax0, svclods; `center=`, `scale=`. Served by `serve_check.py`.
- Screenshots: `canopy_map_live_1128.jpg` and `terrain_map_live_1128.png` (live, after the edits), `canopy_map_svcmax0_1128.jpg`, `canopy_map_patched_1128.jpg`, `terrain_map_svcmax0_564.png`,
  `treetops_tiles_vs_svcmax0.png` (the two fixes side by side).
