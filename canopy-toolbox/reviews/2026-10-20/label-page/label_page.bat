@echo off
rem Click-through training-label page for the 12TVL2804 review packet.
rem
rem     label_page.bat serve     start the page on this machine and open it (http://127.0.0.1:8765)
rem     label_page.bat build     (re)build the page data from the packet, the LAS and NAIP 2024 (Myria3D Python; once per packet)
rem     label_page.bat import    preview importing the page's answers into the review geodatabase
rem     label_page.bat import --apply [--add-split-fields]   (the second the first time split answers are imported; Pro closed)
rem     label_page.bat serve-refined     the refined-cylinder packet (MIXED/UNSURE split into 0.5 m layers) on port 8766
rem     label_page.bat import-refined [--apply]   import its answers into that packet's own review geodatabase
rem     label_page.bat serve-rare        the rare-class packet (vehicles, wires, poles, fences; 0.5 m patches) on port 8767
rem     label_page.bat import-rare [--apply]      import its answers into that packet's own review geodatabase
rem
rem The page is blind: it shows points, sections and imagery, never a model or baseline class. Answers are kept in
rem <packet>\label-page\answers\label-page-answers.csv and reach the geodatabase only through "restore", which checks them.
setlocal
set "PYTHONNOUSERSITE=1"
set "HERE=%~dp0"
if not defined CANOPY_LIDAR_ROOT if exist "D:\lidar\2023-salt-lake-valley" set "CANOPY_LIDAR_ROOT=D:\lidar"
if not defined CANOPY_LIDAR_ROOT if exist "H:\lidar\2023-salt-lake-valley\runs\pilot-2026-09-29" set "CANOPY_LIDAR_ROOT=H:\lidar"
if not defined CANOPY_LIDAR_ROOT (echo Could not find the lidar disk; set CANOPY_LIDAR_ROOT. & goto :end)
if not defined FRACTAL_TOOLS set "FRACTAL_TOOLS=%USERPROFILE%\tools"
set "PRO_PY=C:\Program Files\ArcGIS\Pro\bin\Python\envs\arcgispro-py3\python.exe"
set "PACKET=%CANOPY_LIDAR_ROOT%\2023-salt-lake-valley\runs\pilot-2026-09-29\training-review\packet-20260929"
set "REFINED=%CANOPY_LIDAR_ROOT%\2023-salt-lake-valley\runs\pilot-2026-09-29\training-review\packet-20261020-refined"
set "RARE=%CANOPY_LIDAR_ROOT%\2023-salt-lake-valley\runs\pilot-2026-09-29\training-review\packet-20261020-rare"
set "STEP=%~1"
if /i "%STEP%"=="serve" (
  start "" "http://127.0.0.1:8765/"
  "%PRO_PY%" "%HERE%serve_label_page.py" --packet "%PACKET%"
  goto :end
)
if /i "%STEP%"=="serve-refined" (
  start "" "http://127.0.0.1:8766/"
  "%PRO_PY%" "%HERE%serve_label_page.py" --packet "%REFINED%" --port 8766
  goto :end
)
if /i "%STEP%"=="import-refined" (
  call "%HERE%..\..\2026-09-30\training_labels.bat" restore --packet "%REFINED%" --csv "%REFINED%\label-page\answers\label-page-answers.csv" %2 %3
  goto :end
)
if /i "%STEP%"=="serve-rare" (
  start "" "http://127.0.0.1:8767/"
  "%PRO_PY%" "%HERE%serve_label_page.py" --packet "%RARE%" --port 8767
  goto :end
)
if /i "%STEP%"=="import-rare" (
  call "%HERE%..\..\2026-09-30\training_labels.bat" restore --packet "%RARE%" --csv "%RARE%\label-page\answers\label-page-answers.csv" %2 %3
  goto :end
)
if /i "%STEP%"=="build" ("%FRACTAL_TOOLS%\envs\myria3d\python.exe" "%HERE%build_label_data.py" --packet "%PACKET%" & goto :end)
if /i "%STEP%"=="import" (
  call "%HERE%..\..\2026-09-30\training_labels.bat" restore --csv "%PACKET%\label-page\answers\label-page-answers.csv" %2 %3 %4
  goto :end
)
findstr /b "rem" "%~f0"
:end
endlocal
