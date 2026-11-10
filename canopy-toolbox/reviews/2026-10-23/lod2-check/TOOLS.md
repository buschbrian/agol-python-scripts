# Building reconstruction tools beyond Extract LOD2 Buildings (research note, October 24, 2026)

From web searches and two page fetches on October 24. Nothing here was installed or run. Items marked *unverified* were
not confirmed on a source page. The TU Delft pages (3d.bk.tudelft.nl) refused connections during the session, so the
refined-LoD definitions were not read.

## What the installed tool offers
ArcGIS Pro 3.7.3 here: Extract LOD2 Buildings has `LOD1.2`, `LOD1.3` and `LOD2.0` only. Esri's current documentation
([doc.esri.com](https://doc.esri.com/en/arcgis-pro/latest/tool-reference/3d-analyst/extract-lod2-buildings.html)) lists the
same three and no LOD2.2. LOD1.2 puts larger elements at the median height of the building, LOD1.3 at the median of each
element, and LOD2.0 follows roof slope and orientation. The tool also has two parameters the October 22 run left at their
defaults: `smoothness_level` (0.5; lower extracts more sub-elements, higher simplifies) and `extraction_accuracy` (Medium;
High is slower). The 3.7 release added parallel processing to it
([What's new for 3D Analyst in Pro 3.7](https://www.esri.com/arcgis-blog/products/arcgis-pro/3d-gis/whats-new-for-3d-analyst-in-arcgis-pro-3-7)).

## LOD naming
The 1.2 / 1.3 / 2.2 names come from the refined 16-level scheme of Biljecki, Ledoux and Stoter (2016), which replaces the
five CityGML levels ([TU Delft LoD page](https://3d.bk.tudelft.nl/lod),
[paper](https://3d.bk.tudelft.nl/hledoux/pdfs/16_ceus_lod_specs.pdf)). The 2.1 / 2.2 criteria were not read. The Dutch 3D BAG
publishes LoD1.2, 1.3 and 2.2 ([TU Delft course slides](https://3d.bk.tudelft.nl/courses/backup/geo1004/2021/data/slides2.2_3dbag.pdf)).
LOD2.0 in Esri's tool is not the same as LoD2.2 in that scheme, so the labels should not be assumed equivalent.

## roofer (3DGI / TU Delft), the likeliest candidate
- Automatic LoD1.2, 1.3 and 2.2 from a point cloud and a footprint (roofprint) polygon; the production tool behind
  the 3D BAG for about 10 million Dutch buildings ([GitHub](https://github.com/3DBAG/roofer),
  [paper](https://arxiv.org/pdf/2201.01191)).
- Command line, or a C++ / Python library. The CLI writes CityJSONSequence. GPLv3.
- Method: roof planes by region growing on the points, then the footprint is partitioned into roof parts and extruded; a
  graph cut picks the final roof faces ([course notes](https://3d.bk.tudelft.nl/courses/backup/geo1004/2026/data/lod2recon.pdf)).
- Input quality it asks for ([geoflow bundle](https://github.com/geoflow3d/geoflow-bundle), its predecessor): few outliers,
  ground and building classes, good alignment with the footprint; good results at 8 to 10 points per m².
  Our footprints and lidar are the kind that needs checking against that: the county footprints are offset from the lidar in
  places, and the consensus roof classes are what we would feed it.
- **Tried October 24:** the Windows release zip (`roofer-windows-x86_64-v1.0.0.zip`, 12 MB) unzips and runs with no install step.
  It reads LAS or LAZ (classes 2 and 6) and any OGR footprint source (a shapefile worked), takes `--id-attribute`, and writes
  CityJSONSeq only; the docs say a converter to GPKG and OBJ is planned. Results: README, section "Trial: roofer LoD2.2".
- Companion tools in the same repository: tyler (tiling and conversion to OBJ, glTF and 3D Tiles).
- Getting roofer's CityJSON into ArcGIS multipatch: Esri's CityGML toolset imports CityGML 2.0 into a geodatabase and
  needs the Data Interoperability extension ([Esri blog](https://www.esri.com/arcgis-blog/products/arcgis-pro/3d-gis/import3dcitydatainarcgis)).
  A direct CityJSON import was not found; the route would be conversion to CityGML or OBJ first. *Unverified.*

## Others seen in results
- A 2025 ISPRS benchmark for LoD2 reconstruction from lidar and footprints on IGN LiDAR HD, scored with the open-source
  PyScoring tool ([paper](https://isprs-archives.copernicus.org/articles/XLVIII-1-W6-2025/83/2025/)). A candidate way to
  compare tools, not a tool.
- 2026 ISPRS papers on a deep-learning LoD2 method using a weighted straight skeleton and a two-stage pipeline fusing roof
  skeletons with lidar (roof-surface RMSE 0.445 m on 1,000 buildings)
  ([one](https://isprs-annals.copernicus.org/articles/XI-2-2026/127/2026/),
  [two](https://isprs-annals.copernicus.org/articles/XI-2-2026/331/2026/)). Research results; no code or tool was confirmed.
- Esri's own 3D Buildings layer comes from Maxar and TomTom data plus community contributions, with roof type attributes
  ([Esri EA blog](https://www.blog.esriea.com/enhanced-3d-layers-in-arcgis-taking-visualization-to-the-next-level/)). It is
  not a tool we can run on our lidar.

## Web delivery
- 3D Tiles 1.1 with WebGPU viewers: a 2025 TU Delft paper reports a 3D tiler and a WebGPU viewer for CityJSON, with up to 7x
  rendering speed on modern hardware ([paper](https://avesis.ktu.edu.tr/yayin/f931c413-c72a-49d9-ae24-40d2e52c6d3f/an-interoperable-web-based-application-for-3d-city-modelling-and-analysis)).
- The 3D BAG viewer uses 3D Tiles rendered with 3DTilesRendererJS and three.js
  ([TomTom engineering](https://engineering.tomtom.com/bringing-3d-cities-to-the-web/)).
- For ArcGIS Urban the existing-buildings layer is a scene layer, so I3S from the multipatch is the route already built;
  the searches found nothing on how Urban handles other formats. *Unverified.* The searches found nothing on deck.gl,
  CesiumJS or ArcGIS Maps SDK building features in 2026.

## Still open after the roofer trial
- ~~Convert roofer's CityJSON to multipatch or I3S~~ **Done October 24:** collect to CityJSON, cjio 0.10.1 (own venv, needs `triangle`)
  to OBJ, split per part, Import 3D Files (one feature per file), then Create 3D Object Scene Layer Package; checked in the README.
  Tyler and the CityGML tools were not tried.
- ~~A hybrid of roofer LoD2.2 and Esri's levels on the whole city~~ **Done October 24** (README, "Roofer on the whole city"): 52 tiles in
  18 minutes with neighbouring tiles' points merged at the edges; cjio's `triangle` crashes on some whole tiles, so each tile is exported in
  halves when it does; three-way scene layer package built and validated, not viewed in 3D.
