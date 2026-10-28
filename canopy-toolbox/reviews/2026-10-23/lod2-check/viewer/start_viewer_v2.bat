@echo off
rem The 3D viewer on the v2 packages: Esri LOD2.0 hybrid (October 23), roofer alone (v2) and the three-way hybrid with roof attributes (v2).
rem http://127.0.0.1:8802/ only; the page loads the ArcGIS Maps SDK from js.arcgis.com. Nothing is uploaded. Stop with Ctrl+C.
set RUNS=H:\lidar\2023-salt-lake-valley\runs
python "%~dp0serve_scene.py" "%RUNS%\viewer-20261024\screens-v2" ^
  --slpk "esri=%RUNS%\scene-layers-hybrid-20261023\buildings_hybrid.slpk" ^
  --slpk "roofer=%RUNS%\roofer-city-v2-20261024\buildings_roofer_only.slpk" ^
  --slpk "threeway=%RUNS%\roofer-city-v2-20261024\v2\buildings_hybrid_v2.slpk" ^
  --bookmarks "%~dp0web\bookmarks-v2.json" --port 8802
