@echo off
rem Local 3D viewer for the three scene layer packages (Esri LOD2.0 hybrid, roofer only, three-way hybrid).
rem Serves the page and the packages on http://127.0.0.1:8801/ only; the page loads the ArcGIS Maps SDK from js.arcgis.com.
rem Nothing is uploaded. Needs Python 3 (standard library only). Stop with Ctrl+C.
set RUNS=H:\lidar\2023-salt-lake-valley\runs
python "%~dp0serve_scene.py" "%RUNS%\viewer-20261024\screens" ^
  --slpk "esri=%RUNS%\scene-layers-hybrid-20261023\buildings_hybrid.slpk" ^
  --slpk "roofer=%RUNS%\roofer-city-20261024\buildings_roofer_only.slpk" ^
  --slpk "threeway=%RUNS%\roofer-city-20261024\buildings_three_way.slpk" --port 8801
