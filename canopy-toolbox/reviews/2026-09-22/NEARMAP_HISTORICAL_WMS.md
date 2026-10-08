# Nearmap historical WMS handoff for the Millcreek pilot

The 300 m pilot used by the model comparisons is in Millcreek at EPSG:6341 extent `428100,4504100,428400,4504400`. The LiDAR was collected 2 and 4 November 2023. The ready-to-upload [WGS84 GeoJSON AOI](millcreek_nearmap_aoi.geojson) adds a 35 m margin.

## Create the dated service in MyAccount

1. Sign in to [Nearmap MyAccount](https://apps.nearmap.com/account). In **Integrations > API Apps**, select an existing application for this project. A Nearmap administrator must create an API application if none is available; the account also needs an assigned subscription.
2. In **Integrations > API Keys**, choose that application and click **CREATE KEY**. Keep the key private. An API key is linked to the user who creates it. [Nearmap key instructions](https://help.nearmap.com/kb/articles/650-create-an-api-key).
3. In **Integrations > API Services**, choose **CREATE SERVICE > ADD AREA** and upload `millcreek_nearmap_aoi.geojson` from this folder, or draw the same area. Set the date range to **2023-09-01 through 2023-12-15** to include fall captures around the LiDAR date. Give the area and service clear names, then **CONTINUE > Finish**. Copy the **Custom WMS** URL, with form `https://api.nearmap.com/wms/v1/places/<PLACES_ID>/apikey/<APIKEY>`. [Nearmap custom service instructions](https://help.nearmap.com/kb/articles/753-custom-api-services).
4. Save that complete URL in a private text file outside this repository, one line only. Do not put the key or URL in chat, Git, screenshots, or a report. Give this task the **file path** once ready. The Python helper reads the file without printing the URL.

A **Simple WMS** URL contains `/latest/` and cannot browse dates. The date range on a Custom WMS filters survey layers; select the *specific survey-date layer* in ArcGIS Pro or in the helper, not a combined/latest layer. The survey date shown in WMS can differ from an individual photo's capture date; verify the local photo date in Nearmap at the pilot center when interpreting tree labels. [Nearmap WMS details](https://help.nearmap.com/kb/articles/88-wms-2-0-integration), [photo vs survey date](https://help.nearmap.com/kb/articles/699-view-location-details).

## Validate and export one dated pilot tile

Run these commands in PowerShell from `U:\agol-python-scripts\canopy-toolbox`, substituting the private URL file path and an actual layer name/date returned by the first command:

```powershell
$py = 'C:\Program Files\ArcGIS\Pro\bin\Python\envs\arcgispro-py3\python.exe'
& $py .\nearmap_historical_wms.py --url-file 'C:\path\outside-repo\nearmap-custom-wms.txt' list --year 2023
& $py .\nearmap_historical_wms.py --url-file 'C:\path\outside-repo\nearmap-custom-wms.txt' fetch --layer '<exact dated layer Name>' --date '2023-MM-DD' --output .\scratch\models\nearmap_2023_pilot.tif
```

The helper requests WMS 1.1.1 capabilities, lists survey-date layers, checks that the chosen layer contains the exact date, requests a 2048 × 2048 JPEG WMS image for the fixed pilot extent, and writes a georeferenced GeoTIFF plus metadata JSON. It uses an advertised coordinate system (EPSG:6341 when available; otherwise EPSG:3857 or EPSG:4326). It does not fall back to latest imagery. The 2048-pixel pilot tile has an approximate ground sample of 0.15 m if the server supplies that detail. Nearmap WMS requests count toward the account's usage allowance. [Nearmap WMS integration](https://help.nearmap.com/kb/articles/88-wms-2-0-integration).

The generated tile is for the [fixed model review sample](../../scratch/models/model_imagery_sample.json): 206 candidate points and 24 separate 10 m plots with empty imagery label fields. Select a fall 2023 survey close to 2–4 November 2023, inspect roof eaves and vegetation, and record the source and capture date for each label. If no 2023 survey appears, check the service date range and subscription coverage before using another season.

To stream in ArcGIS Pro instead of exporting, use **Insert > Connections > New WMS Server** and paste the Custom WMS URL, leaving username/password empty. Expand the area and select the dated survey layer. [Nearmap ArcGIS Pro WMS instructions](https://help.nearmap.com/kb/articles/320-arcgis-pro-wms-integration).
