# LiDAR review implementation tasks

- [x] Commit the verified current work in scoped commits (194-test suite already passed).
- [x] Merge building/footprint commands and fixtures; write BUILDINGS.md (28 tests and new 250 m CLI pilot passed).
- [x] Fix interior-face/eave roof estimates; 22 tests and residential copy pilot; ROOF_SURFACE.md.
- [x] Consolidate LAS readers and roof context; pure and ArcGIS fixtures plus fresh 250 m pilot passed.
- [x] Port four selected September 23 changes; ArcGIS regressions, CHM pilot and CONSERVATIVE preparation passed.
- [x] Add blind 12-plot census, one-to-one object scoring, cause sidecars and review QA; manual census/labels pending.
- [x] Add analytic stratified Taylor/t intervals with finite-population correction; retain bootstrap cross-checks and suppression rules.
- [x] Freeze prospective 3302 plus halo; separate Millcreek pilot/external/exploratory domains.
- [x] Parameterize density/HAG experiment inputs and provenance; document paired/product scoring; inference deferred by user.
- [x] Add four-band NAIP greenness review; synthetic tests and dated 250 m USGS pilot passed, no automatic class edits.
- [x] Final integration suite: 271 tests, one expected skip, 451.298 s; additional dated-WMS export passed; slices committed.

Manual acquisition-matched review, independent tree census and any inference runs
are prerequisites for new accuracy claims; implementation must not fabricate them.
