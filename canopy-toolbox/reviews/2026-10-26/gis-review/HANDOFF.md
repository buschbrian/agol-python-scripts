# Drive transfer handoff — October 26, 2026

Brian asked to stop current work and commit all changes so the LiDAR drive can move to a CUDA computer.

## Complete

- All 61 CFTree tiles: 119,410 draft crown/trunk models, 506 compressed CityJSON shards, 75 excluded candidates. No active CFTree coordinator. See `reviews/2026-10-25/cftree-city/README.md` for the pinned upstream revision, methods and verification limits.
- Public three-way building hybrid, Azure SLPK/feet CSV and feet-based app context were already released and committed in earlier work.
- All 470 previously unanswered classification examples have separate assistant assessments. Human labels and calibration/reference data are unchanged.
- New review rules: five tests pass. Inverting the missing-model condition causes three failures; restoring it returns all five to green.
- ArcGIS Pro review pilot: all 22,042 County footprints, 77 tree outlines and one excluded candidate. Projection with the established ITRF08 operation, counts, domains, defaults, attachments and editor tracking passed. Pilot elapsed 37.7 seconds.

## Stopped / outstanding

- The new all-city review build was stopped during locating excluded segments. Roof footprints and 119,410 crown outlines had been written; later geodatabase stages and the final manifest were not completed. Treat `city/` as partial, not a completed product.
- No new review layer, editing map, scene or app was created in ArcGIS Online. The publishing/configuration scripts are unexecuted drafts requiring live verification.
- Detailed CFTree meshes are not online with the buildings. The existing canopy app remains separate. The proposed combined review scene uses 2D crown outlines alongside the existing 3D buildings; it must not be described as publishing full CFTree meshes.
- Seam, merge/split, visual, field and trunk-allometry validation remain open. Missing roof evidence does not prove demolition; separate presence at the 2023 survey from changes afterward.

## Locations

- Git repository/common metadata: `V:\Developer\agol-python-scripts`. Worktree: `C:\Users\Brian\Documents\Codex\2026-10-24\go-x20\work\lidar-wrapup`. Branch: `codex/lidar-wrapup-20261024`.
- Source drive: `H:\lidar\2023-salt-lake-valley\runs`. Original LAS and source geodatabases remain unchanged.
- Complete CFTree outputs/checkpoints: `C:\Users\Brian\Documents\Codex\2026-10-24\go-x20\work\cftree-city-20261025`.
- New review work/pilot/source inventory: `C:\Users\Brian\Documents\Codex\2026-10-24\go-x20\work\gis-review-20261026`. `pilot2/manifest.json` is complete; `city/manifest.json` does not exist.
- User-facing deliverables: `C:\Users\Brian\Documents\Codex\2026-10-24\go-x20\outputs`.
- Portable drive handoff: `H:\lidar\2023-salt-lake-valley\runs\codex-handoff-20261026`. Transfer manifest in that folder records actual copied files and checksums. It includes a Git bundle of this branch and completed CityJSON products/statuses; it is **not** a copy of all large intermediate segmentation/staging data or native runtime binaries.

## On the other computer

Clone the Git bundle or fetch this branch from the original repository. Keep generated geodatabases, models, imagery and LAS outside Git. Use `CANOPY_LIDAR_ROOT` to point supported toolbox scripts at the new drive letter. Some dated review scripts and the frozen CFTree configuration contain absolute machine paths: inspect them before running; do not blindly resume a Windows/WSL configuration on another machine.

CFTree's TreeSeparation/CGAL reconstruction stages in this run are CPU tools; moving to a CUDA machine does not automatically accelerate them. CUDA is relevant to the separate learned point-classification workflows. ArcGIS Pro preparation/packaging requires a licensed Windows Pro Python environment. Reinstall/rebuild native CFTree dependencies for the destination platform rather than copying Windows/WSL paths.

To finish the review build, use a **new output folder** and rerun `prepare.py` from the complete original CFTree run with its checkpoints and `segmentation.xyz` files. The portable CityJSON-only export supports successful-model review and mesh verification, but locating all 75 rejected candidates also needs their segment coordinates from the original run. Do not overwrite existing human findings if a review service is later created.

The user requested the stop; do not restart processing or publish anything merely because this handoff exists.
