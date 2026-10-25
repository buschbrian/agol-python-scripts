# 3D buildings release candidate — October 24, 2026

The **v2 package is built, validated locally, and not uploaded**. The upload dry run now passes. This plan supersedes the earlier draft's stale StoryMap reference, roof-area totals, and claim that the existing scene is private.

## Candidate and evidence

- Package: `H:\lidar\2023-salt-lake-valley\runs\roofer-city-v2-20261024\v2\buildings_hybrid_v2.slpk` (21,228,379 bytes, 20.2 MiB).
- SHA-256: `62674f95c4e7a292c4ce66e8c2b55aac9d60c360e2ea50e3e7bde5521495949f`.
- 21,561 buildings: 20,730 roofer LoD2.2, 647 Esri LOD2.0, 184 Esri LOD1.2.
- Fresh ArcGIS Pro validation: no warnings or errors. Source IDs are unique; package ID count and sum equal source (sum 237,493,394). This is not an exhaustive comparison of the package's ID list.
- All 831 fallbacks have null roof attributes. The retained roofer models contain 4,855,408.3 m² roof surface, including 1,230,559.8 m² flat. Earlier 4.95/1.25 km² totals included discarded roofer models.
- All 45 packaged fields are documented in [the draft](draft-metadata/buildings3d_v2.md). LOD20_GROUND_PCT is not present and is no longer advertised.
- The v2 local viewer uses v2 bookmark measurements. Source geometry and the SLPK were not changed in the wrap-up.
- Source-lidar fit is not independent accuracy. The assistant's imagery ratings are not City-reviewed validation; the blank human rating file remains blank.

## Existing dependencies

The existing public LOD1.2 layer is `5082b5bd063a4a03847f2082dc3533d1`, with private source package `eb613927529347989755b0fcf9e9c8fa`. Its 598 ground-level slabs were identified in the prior checks; replacing the package must not be described as correcting every stale footprint or every ground-placement issue.

The public buildings scene `5b5bdf4a63c9466fad5884039aa7357f` uses that layer. The Buildings in 3D app `021866adf7ab40fea430d4d10fc3a934` is private. The StoryMap and 2D buildings app were already retired in Claude; they are not dependencies to update.

## Release sequence

1. Review the candidate and draft text. Record the chosen audience: the last explicit roof-form decision was staff-only, so replacing the public layer needs a new audience decision. Keep assistant imagery observations labelled as such.
2. From canopy-toolbox, run `python reviews/2026-10-22/hosting/upload/upload.py buildings3d_v2` to check the file/hash, then add `--go` only for the approved private upload. The command creates new items, never overwrites.
3. Read back the new service: 3D object type, IDs/counts, LEVEL and the 45 fields; compare its statistic totals with `../wrapup-evidence/release-audit.json`. Record its new item and service IDs.
4. Apply the prepared item text and a renderer/pop-up that uses fields actually present. Review it in a **new private scene** on the city terrain. Retain source packages and enable delete protection.
5. For an approved public swap, save the current public scene JSON, make the new layer available to the scene's intended audience **before** repointing the scene, then verify the scene and app. A public scene pointing at a private layer will be blank for anonymous viewers.
6. Keep the old layer available during verification and check other dependencies before reducing its sharing. Rollback is restoring the saved scene definition; do not delete either source package.
7. Record the actual outcome and any remaining review limits in PUBLISHING.md.

The filled LOD1.2 package is an alternative if detailed roofs remain staff-only. Its earlier check found three ground-level blocks instead of 598, but it also requires a new private item and online validation before a public swap.
