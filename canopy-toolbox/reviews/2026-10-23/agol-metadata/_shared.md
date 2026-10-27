# Shared text blocks

Each `## name` block below is pasted wherever an item file says `{{name}}`. `apply_metadata.py` expands them before it
converts the Markdown to HTML, so every item carries the same wording for the warning, the lidar source and the
coordinates.

## warning
**Planning estimate.** This layer is an unvalidated estimate derived from lidar by City of Millcreek GIS. It has not been
surveyed, engineered or checked in the field. Use it for planning, screening and display, not for legal, engineering,
property-boundary, permitting or code-compliance decisions.

## lidar
**Lidar source.** The 2023 Salt Lake Valley QL1 lidar (USGS project UT_2023SaltLakeCo_C24, USGS 3D Elevation Program),
flown on October 7, November 2 and November 4, 2023. Quality level 1 means at least 8 pulses per square metre and a vertical accuracy (RMSEz) of 10 cm or better on open,
non-vegetated ground under the USGS specification; the vendor's own accuracy report for this project has not been
reviewed for these products. For these products the building and vegetation classes of the points were refined; the
ground class was not changed. All products are gridded at 0.5 m.

## coordinates
**Coordinates and heights.** Built in NAD83(2011) / UTM zone 12N (EPSG 6341), metres, and taken to WGS84 / Web Mercator
for ArcGIS Online with the transformation `WGS_1984_(ITRF08)_To_NAD_1983_2011`. Every layer in the Millcreek LiDAR 2023
set uses this same transformation, so the layers line up with each other and with Esri's basemaps to a few centimetres;
without it they would sit about 1.2 m apart. Elevations are NAVD88 (Geoid18) in **metres**; heights are metres above the
lidar bare-earth terrain.

## set
**The Millcreek LiDAR 2023 set.** Eight layers from the same lidar and the same processing: buildings and canopy cover
zones (feature layer), 3D buildings (scene layer), bare-earth terrain (elevation layer), hillshade (tile layer), slope
classes, 2 m contours, treetops and tree crowns (vector tile layers). They share one coordinate transformation and one
terrain, so they can be stacked in one map or scene.

## contact
**Questions or corrections:** City of Millcreek GIS. The processing records (scripts, checks and run logs) are kept by City
of Millcreek GIS.

## terms
These data are unvalidated planning estimates produced by City of Millcreek GIS from 2023 lidar. They are not surveyed,
engineered or field-verified, and must not be used to determine property boundaries or ownership, building or site
design, engineering, flood or drainage design, code compliance (including building height), or any legal or regulatory
determination. They are provided as is, without warranty of accuracy, completeness or fitness for any purpose; check
conditions on the ground before relying on them. Credit "City of Millcreek GIS; 2023 Salt Lake Valley QL1 lidar (USGS
3DEP)" when you use or show them.

## terms_county
**Salt Lake County data.** The building footprints and their County attributes come from Salt Lake County (Assessor and
Surveyor). The County's own terms apply to them: the County states that its footprints are not field verified, are for
general reference only, and are not intended to determine property ownership, final building and site design or
jurisdictional boundaries, or to replace a certified topographical or boundary survey or any other legal document.

## terms_parcels
**Parcels.** Ownership groups come from the City of Millcreek parcel layer (2025 tax-year snapshot, read October 8,
2026). A tax year is not an ownership effective date, and the grouping of owners into private, public and uncertain is
the City's own rule set for this analysis, not a legal finding of ownership.

## coordinates_utm
**Coordinates and heights.** NAD83(2011) / UTM zone 12N (EPSG 6341), metres: the lidar's own coordinate system, with no
datum transformation. This copy is for a **local** scene or a local ArcGIS Urban model in 6341. The other layers in the
Millcreek LiDAR 2023 set are WGS84 / Web Mercator copies for global scenes; they hold the same data. Elevations are NAVD88
(Geoid18) in **metres**; heights are metres above the lidar bare-earth terrain.

## set_urban
**The Millcreek ArcGIS Urban layers.** Organization-only layers for ArcGIS Urban. For a local model in UTM 12N: 3D buildings
(scene layer), building footprints (feature layer), bare-earth terrain (elevation layer) and a light basemap on the terrain's
tiling scheme. For a global (Web Mercator) model: the same 3D buildings in WGS84. They come from the same lidar, the same
buildings and the same terrain as the public Millcreek LiDAR 2023 set.
