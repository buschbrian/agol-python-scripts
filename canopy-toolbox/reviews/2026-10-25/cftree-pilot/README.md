# CFTree for citywide trees — October 25, 2026

**Brian's explicit decision:** “we are using cftree bc citywide”. Use
[NoahAlting/CFTree](https://github.com/NoahAlting/CFTree), not AdTree, as the citywide workflow.
Earlier AdTree exploration is scratch evidence only and is not part of the integration.

## Feasibility pilot

Upstream commit `13be34b412a2f83f3ec1c89487665120348bb9d9` is pinned in the driver. Its TreeSeparation
and CGAL AlphaWrap C++ tools were built unmodified in the existing Ubuntu WSL runtime. Dependencies
installed from Ubuntu's official repository: CMake 4.2.3, CGAL 6.1.1, Eigen and their prerequisites.
Trimesh 5.2.0 is isolated in the chat's scratch directory because the Pro environment's older trimesh
calls `np.product`, which its installed NumPy no longer supplies. Pro's installed packages were not changed.

`pilot.py` runs a bounded 200 m core plus a trial 20 m margin in tile 12TVL2804, using the existing refined
LAS classes 3/4/5, excluding withheld, overlap and synthetic points, and requiring height >=2 m above
valid terrain. It uses NAD83(2011)/UTM12N (EPSG 6341), with original NAVD88 Geoid18 elevation values.
It bypasses Dutch AHN acquisition and HOMED, preserving the local classification for this trial.
Existing October 22 crown regions remain a separate comparison product; the CFTree pilot does its own segmentation.

The original CGAL defaults (ralpha 15, roffset 50) and TreeSeparation defaults (radius 2.5 m, vertical resolution
1.5 m, minimum cluster points 3) are retained. Core ownership uses each segment's highest point; only the first
12 eligible segments with >=50 points are reconstructed. This limited selection is not representative accuracy testing.
Experimental IDs are scoped to the pilot, not a durable citywide ID scheme.

Every crown and trunk is checked for finite coordinates and closed meshes. The wrapper supplies feet attributes
and local OBJ exports in feet while CityJSON retains georeferenced metric coordinates. LoD values are strings
as required by current CityJSON; the upstream writer's numeric LoD values are adapted at the boundary.
The output is checked against the official CityJSON 2.0.2 schema (specs commit
`877ee49e16c82a4bc7ab598926efcb9ba1075374`). This is schema validation, not field or full solid-topology validation.

The first completed pilot computed full CFD metrics. For future visualization runs, the driver defaults to
geometry-only metrics: the same upstream crown width, ground base and allometric trunk calculations, without
expensive r50/porosity work. `verify_geometry_mode.py` compares those dimensions with the full pilot. Use
`--cfd-metrics` only when those analytical attributes are required. Allometric trunk position/diameter are inferred,
not observed stems or measured DBH. No species, condition, hazard or field accuracy is claimed.

## Run

Use Pro Python with `PYTHONNOUSERSITE=1`, `PYTHONDONTWRITEBYTECODE=1` and the isolated trimesh directory:

```
pilot.py --repository CFTREE_CHECKOUT --python-deps ISOLATED_TRIMESH --las REFINED_TILE_LAS \
  --terrain TERRAIN_TIF --output NEW_SCRATCH_DIRECTORY --max-trees 12
```

Build the upstream C++ tools with CMake in their own `build/` directories. The wrapper launches those binaries
through WSL; staged input/output must be on C:. It does not install packages, publish, edit source LAS or overwrite
an existing output directory. The input LAS has a compound horizontal/vertical CRS, so the horizontal component
is checked explicitly. Raster-edge points outside the cropped terrain's index bounds are excluded and counted.

## Before a citywide release

1. Compare dense canopy, isolated trees and sparse returns; inspect merged/split crowns and building contamination.
   Integrate the current consensus roof exclusion if it improves the evidence; the pilot only uses refined classes.
2. Validate margins and cross-tile identity on neighboring tiles. A 20 m trial halo is not proof of exact seams.
3. Establish durable IDs and one core owner per tree, resume manifests, rejected-tree reporting and memory limits.
4. Benchmark geometry-only throughput and scene size on representative full tiles, then choose citywide batching.
5. Build a georeferenced scene package and inspect terrain alignment, simplification and pop-ups before replacing
   or extending the live scene. No trees were published by this pilot. Brian subsequently requested all
   61 tiles; that resumable run began October 25 and is documented in [cftree-city](../cftree-city/README.md).

The local HTML viewer, feet OBJ archive, CityJSON and manifest are in the chat's outputs folder. Mesh/data files
remain outside Git. Evidence under this review records the completed pilot and geometry-mode comparison.
