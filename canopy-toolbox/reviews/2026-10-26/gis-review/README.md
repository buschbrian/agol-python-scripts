# Roof and tree review — October 26, 2026

Brian requested reviewable GIS layers after observing that some old County footprints and fallback blocks may represent buildings absent from the LiDAR survey. A missing Roofer reconstruction is an evidence gap, never an automatic demolition finding. He did not recall a specific address, so the queue starts with citywide mismatches.

## Stopped for drive transfer

Brian requested an immediate stop and repository commit on October 26. The all-city preparation process was stopped during exclusion-point location, after all 22,042 roof footprints and 119,410 tree outlines were generated. The `city` geodatabase is **partial and not validated**; it has no final manifest and is not publish-ready. Do not use it as a completed package. The separate `pilot2` run completed successfully (22,042 roofs, 77 tree outlines and one exclusion), including projection and geodatabase checks.

**Nothing from this review workflow was uploaded or published.** `upload_review.py` and `configure_online.py` are saved drafts; the latter has not been exercised against a live review service. The following online workflow describes the intended configuration, not a completed deployment. Existing public buildings and the separate canopy app remain unchanged. The complete 61-tile CFTree model run from the previous night is intact.

See [HANDOFF.md](HANDOFF.md) for source paths, checks and transfer details.

## Review copies

- All 22,042 County footprints, joined by the unique SOURCE_ID to the hybrid and massing inventories. 481 have no hybrid model. Priority 2 adds 2,579 fallback/support/coverage cases; the 831 fallbacks overlap other cues. Routine footprints remain available.
- All 119,410 successful CFTree models from the completed 61-tile run, represented by convex XY hulls of crown mesh vertices. These polygons are approximate review outlines, **not the full 3D CFTree meshes**, surveyed crowns or a tree census.
- All 75 excluded reconstruction candidates, located at the highest vegetation return of the segment. These are not measured stem positions.

No source LAS, footprint, mesh, human label, calibration answer, or evaluation/reference feature is edited. These review findings do not enter model training. Source metric geometry and source attributes are retained; new review measurements use international feet (1 ft = 0.3048 m) and square feet.

Roof priorities use missing models, fallback source and existing support/coverage flags. Tree cues use inferred trunk centers within County footprints, at least 25% convex-outline overlap with footprints, existing 100 m tile-edge cues, and different-tile outlines overlapping at least 70% of the smaller outline. Those thresholds are queue heuristics, not validated error classifiers. Overhang, separate neighboring trees and old footprints can all produce legitimate overlaps. No models are merged, deleted or corrected automatically.

## Editing workflow

The configuration draft creates items private to GISMillcreek and administrators. The planned editing web map has five-field forms: status, finding, evidence source, evidence capture date, and notes. Its new service is intended to permit attribute updates and attachments, with source fields read-only and geometry/create/delete disabled for editors. Owner/admin capabilities follow ArcGIS rules; source datasets are separate in all cases. These controls still need live verification.

Use Edit in Map Viewer, select a review feature, record a finding and evidence, and save/update the feature. Priorities exclude records marked reviewed. Toggle the all-features layers to revisit them or inspect routine examples. The companion private 3D scene/Instant App uses the existing building and terrain services and drapes the review outlines on the ground. Use its link to the map for editing. It does not render the detailed CFTree meshes.

Dates must be recorded explicitly: LiDAR October–November 2023; County footprint vintage not established; imagery capture dates vary by location. Findings distinguish absence at the survey from removal or construction after the survey. An assistant's automated cues are not human findings.

## Reproduce

Run with ArcGIS Pro Python, PYTHONNOUSERSITE=1. Working GDBs, model exports, source inventories, portal snapshots and full reports are outside Git in the chat's `work/gis-review-20261026` directory. The input run is `work/cftree-city-20261025`; its frozen config hash must match the published manifest.

1. `python -m unittest discover -s reviews/2026-10-26/gis-review -p test_rules.py`
2. `python reviews/2026-10-26/gis-review/prepare.py --run RUN --output NEW_PILOT_FOLDER --pilot`
3. Repeat preparation without `--pilot`, using a new output folder. It refuses existing output folders to protect review edits.
4. `python reviews/2026-10-26/gis-review/upload_review.py --gdb NEW_OUTPUT/gis_review.gdb` for the dry run, then add `--go` on Brian's existing instruction to create his review layer. This routes through the established one-item uploader and its hash/upload log. It never shares or deletes.
5. `python reviews/2026-10-26/gis-review/configure_online.py --service NEW_SERVICE_ID --audit AUDIT --manifest NEW_OUTPUT/manifest.json` for the plan; add `--go` to apply.

Creation checkpoints prevent duplicate map/scene/app items on a retry. Verification checks hosted counts, domains, field permissions, attachments, private access, form configuration and a reversible note edit in each new layer. Review records are never replaced from the GDB after publication. The reversible smoke edit restores the original note; it does not submit a human finding.

The Pro pilot includes all roof footprints, the first tree shard and one exclusion location. It checks projected geometry, counts, defaults/domains, attachments and editor tracking. Five pure tests exercise conservative classification of evidence gaps, fallback/support cues, routine models, tree overlaps and null-preserving feet conversion. This verifies workflow mechanics, not positional or detection accuracy.

Official references: [Map Viewer editing forms](https://doc.arcgis.com/en/arcgis-online/create-maps/create-form-mv.htm), [formInfo schema](https://developers.arcgis.com/web-map-specification/objects/formInfo/), [field elements](https://developers.arcgis.com/web-map-specification/objects/formFieldElement/), [editing controls](https://doc.arcgis.com/en/arcgis-online/manage-data/manage-editing-hfl.htm), [service definition updates](https://developers.arcgis.com/rest/services-reference/online/update-definition-feature-service/).

## Recovery

Existing public scenes, apps and layers remain unchanged. If a new review display needs repair, update its map/item configuration; never recreate the service over human edits. Retain the uploaded File Geodatabase item while the review service depends on it. Retire unwanted items through the portal recycle bin only on Brian's instruction. The full CFTree meshes remain local pending spatial/visual review and a separate mesh publication.
