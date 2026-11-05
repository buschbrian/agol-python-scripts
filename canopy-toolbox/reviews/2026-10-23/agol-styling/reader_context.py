"""Reader-facing context shared by each app's opening screen, details panel and item page."""

AZURE = 'https://stmillcreeklidar.blob.core.windows.net/cogs/millcreek-lidar/buildings/20261025/'


def link(url, label):
    return f"<a href='{url}' rel='nofollow ugc'>{label}</a>"


def item(item_id, label):
    return link('https://www.arcgis.com/home/item.html?id=' + item_id, label)


SOURCE = (
    '<h3>Dates and units</h3><p>The source is the 2023 Salt Lake Valley QL1 lidar, flown in October and November '
    '2023. These maps describe that survey, not present-day conditions. Buildings removed, trees planted or '
    'construction completed since then may differ. Basemap imagery can be from a different date.</p>'
    '<p>Height legends and building heights use feet; building areas use square feet. Canopy-zone summaries '
    'use acres and percentages. One international foot is exactly '
    '0.3048 meter. The original coordinate system, elevation reference and metric analysis files remain intact '
    'so all layers stay aligned. Rounded display values do not imply survey precision.</p>'
    '<p><b>Questions or corrections:</b> City of Millcreek GIS. Include the map location and building ID when available.</p>'
)


DETAILS = {
    'buildings2d': (
        '<h3>Explore building footprints</h3><p>Select a footprint for its median and upper roof heights in '
        'feet, footprint area in square feet, parcel identifier and lidar support notes. Colors group '
        'buildings by median roof height above local ground. Gray buildings without roof support have '
        'no estimated height. Height is not the same as elevation above sea level.</p>'
        '<p>This 2D layer contains 22,042 county footprints, including footprints without usable roof '
        'height estimates. It differs from the 21,561 reconstructed buildings in the 3D hybrid. Roof '
        'surface, ridge, eave and roof-facing measurements belong to the 3D model product.</p>'
        '<h3>Related data</h3><p>' + item('5b5bdf4a63c9466fad5884039aa7357f', 'Buildings in 3D') + ' · ' +
        item('d5effaee6c66497eaeb64e4c2e0f496e', 'Footprint methods and source fields') + '</p>'
        '<p>The support percentage describes how much of a footprint has roof returns. It is not a '
        'confidence score. Footprints and roof heights are planning estimates and are not parcel '
        'boundaries, surveyed roof elevations or code-compliance measurements.</p>'
    ),
    'in3d': (
        '<h3>Explore the buildings</h3><p>Use Search to find an address, choose a slide for a neighborhood, '
        'then zoom in and select a building. Drag to rotate the scene; Home returns to the starting view. '
        'The legend explains the gray height classes. Daylight changes the illustrative lighting.</p>'
        '<h3>What the models show</h3><p>The three-way hybrid contains 21,561 buildings: 20,730 detailed roofer '
        'LoD2.2 models, 647 Esri LOD2.0 roofs and 184 Esri LOD1.2 blocks. Each building uses the selected model '
        'for that footprint. Simpler roofs retain city coverage where a detailed roof did not pass the model checks. '
        'The pop-up reports the model source and any fallback reason.</p>'
        '<h3>Read a building pop-up</h3><p>Median and upper roof heights describe the lidar points above the local '
        'ground. Modelled ridge and eave heights describe the reconstructed roof; they are different measurements. '
        'Footprint area is horizontal ground coverage. Roof surface area includes the sloping roof faces, so it '
        'can exceed the footprint area. The support percentage reports how much of the footprint contains roof '
        'points, not a probability that the model is correct.</p>'
        '<p>Detailed roof measurements are present only for the 20,730 retained roofer models. A blank value on '
        'an Esri fallback means unavailable; zero means the model has none of that measured area. Flat roof area '
        'uses slopes below 5 degrees; compass-facing areas use slopes from 5 to 70 degrees. Bearings are degrees '
        'clockwise from north. Facing areas are screening measurements, not estimates of usable solar area '
        'or electricity production. Roof angles remain in degrees.</p>'
        '<h3>Downloads and limitations</h3><p>' + link(AZURE + 'buildings_hybrid_v2_feet.csv', 'Building measurements in feet and square feet (CSV)') +
        ' · ' + link(AZURE + 'buildings_hybrid_v2.slpk', '3D building package (SLPK)') + ' · ' +
        item('ce3617ac9b884bbcbee7c47a3e166999', 'Full model methods and field definitions') + '</p>'
        '<p>Join the CSV to the models using FP_ID. The SLPK keeps its original metric coordinates and source '
        'fields; the CSV provides converted measurements. A detailed-looking roof is still an inferred planning '
        'model. Dormers, overhangs, small structures and occluded roof sections can be simplified or incorrect. '
        'Lighting and shadows illustrate geometry and are not a validated solar or shadow study.</p>'
    ),
    'canopy': (
        '<h3>Explore canopy cover</h3><p>Select an ownership zone for its canopy percentage, then zoom in '
        'to see tree crowns and treetop markers. Use the legend to compare heights in feet. The crown and '
        'treetop tiles are display layers and have no individual-tree pop-ups.</p>'
        '<h3>Three measures with different meanings</h3><p>Citywide canopy cover is 25.59% of the area observed by lidar. '
        'It measures classified vegetation at least 6.56 ft above the local ground, independently of how '
        'many treetops or crowns the algorithms find. Missing coverage is not silently counted as bare ground.</p>'
        '<p>The 527,140 treetop detections are local peaks in the canopy surface. The 400,063 crown regions '
        'are segmented portions of that surface. Neither count is a field census: a large tree can produce '
        'multiple peaks, adjacent trees can merge, and small or shaded trees can be missed. The two counts '
        'should not be expected to match.</p>'
        '<h3>Interpret carefully</h3><p>Heights are above local ground, not elevations above sea level. '
        'Crown boundaries estimate the overhead canopy extent; they do not identify trunks or ownership '
        'of individual trees. Zone summaries group canopy by the analysis ownership categories and are not '
        'parcel-boundary determinations. Roof edges, wires and other objects can cause false detections. '
        'Automated suspect flags are review evidence, not confirmed errors or field checks.</p>'
        '<p>These layers do not establish species, trunk diameter, condition, hazard, heritage status or '
        'the number of trees that should be removed or planted. They support screening and prioritizing '
        'field work.</p><h3>Citywide 3D trees in development</h3><p>The citywide 3D workflow uses ' +
        link('https://github.com/NoahAlting/CFTree', 'CFTree') +
        ' to reconstruct crown surfaces from airborne lidar. Trunk positions and diameters are inferred '
        'from crown dimensions and terrain; they are not field measurements. That 3D work is being tested '
        'separately and is not yet included in this map. The existing canopy percentages and detection '
        'counts remain the October 22 analysis of the 2023 survey.</p>'
        '<h3>Data and methods</h3><p>' + item('924b993cb23046cb87641253bcf786de', 'Treetop methods') + ' · ' +
        item('d9388dc83f894edbb63e0510a8c62fa8', 'Crown methods') + ' · ' +
        item('d5effaee6c66497eaeb64e4c2e0f496e', 'Canopy zones and building footprints') + '</p>'
    ),
    'terrain': (
        '<h3>Explore terrain</h3><p>Use the slides to visit the east bench, canyon mouth and foothills. '
        'Rotate the scene to see relief, and use the layer list to compare slope colors, contours and '
        'hillshade. The elevation profile tool reports a drawn transect in feet; choose the ground profile '
        'when comparing bare-earth terrain.</p>'
        '<h3>Read the legend</h3><p>Slope is percent rise: 20% means 20 ft of vertical rise over 100 ft '
        'of horizontal distance, not a 20-degree angle. The six color classes run from under 10% to '
        '30% and over. They summarize the ground surface and do not establish a regulatory slope finding.</p>'
        '<p>Thin contours are 6.56 ft apart vertically and heavy index contours are 32.81 ft apart. '
        'These are the original 2 m and 10 m intervals converted to feet, not newly generated 5 ft '
        'or 10 ft contours. The vector tiles have no elevation pop-ups or line labels.</p>'
        '<h3>Resolution and limits</h3><p>The bare-earth terrain has an approximately 1.64 ft grid '
        '(0.5 m), with slope computed over a roughly 9.84 ft neighborhood. Small slope patches below '
        'about 43 sq ft were removed in the display polygons. Grid spacing is not an accuracy claim. '
        'Hillshade and scene lighting help reveal landforms; they do not show a measured surface color.</p>'
        '<p>Bare-earth processing removes buildings and vegetation where classification permits. '
        'Walls, bridges, steep banks, water and gaps in ground returns can still create artifacts. '
        'Outside the city terrain coverage, the scene can use Esri World Elevation, which has a '
        'different source and resolution. These layers support reconnaissance, not grading design, '
        'drainage engineering or surveyed elevations.</p>'
        '<h3>Data and methods</h3><p>' + item('ce1680a5196e458ebfb60ead5150b946', 'Terrain elevation') + ' · ' +
        item('3b5b1a9110f14e93af68752be89e0df2', 'Slope methods') + ' · ' +
        item('50573eeba93f405a869a1d78a08d68e8', 'Contour methods') + '</p>'
    ),
}


def context(key):
    return DETAILS[key] + SOURCE
