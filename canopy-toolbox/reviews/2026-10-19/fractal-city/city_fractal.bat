@echo off
rem Citywide FRACTAL refinement of the Millcreek working LAS. Each step resumes where it stopped; run them in order:
rem
rem     city_fractal.bat prepare     NAIP 2024 tile and colourised copy per tile (ArcGIS Pro Python, about 10 min)
rem     city_fractal.bat infer       three FRACTAL passes and consensus per tile (A4000 GPU, about 10 hours)
rem     city_fractal.bat refine      provisional refined copies with coded, reversible changes (CPU)
rem     city_fractal.bat summarize OUT_DIR   citywide totals and the treetop impact (CPU)
rem
rem Extra arguments are passed on, e.g. "city_fractal.bat infer --tiles 12TVL2804". The lidar disk is found as
rem CANOPY_LIDAR_ROOT, else D:\lidar, else H:\lidar. Tools come from %FRACTAL_TOOLS% (default %USERPROFILE%\tools).
rem Nothing here changes the original or working LAS, labels or any GIS layer. See README.md beside this file.
setlocal
set "PYTHONNOUSERSITE=1"
set "HERE=%~dp0"
if not defined CANOPY_LIDAR_ROOT if exist "D:\lidar\2023-salt-lake-valley" set "CANOPY_LIDAR_ROOT=D:\lidar"
if not defined CANOPY_LIDAR_ROOT if exist "H:\lidar\2023-salt-lake-valley" set "CANOPY_LIDAR_ROOT=H:\lidar"
if not defined CANOPY_LIDAR_ROOT (echo Could not find the lidar disk; set CANOPY_LIDAR_ROOT. & goto :end)
if not defined FRACTAL_TOOLS set "FRACTAL_TOOLS=%USERPROFILE%\tools"
set "PRO_PY=C:\Program Files\ArcGIS\Pro\bin\Python\envs\arcgispro-py3\python.exe"
set "M3D_PY=%FRACTAL_TOOLS%\envs\myria3d\python.exe"
set "STEP=%~1"
if "%STEP%"=="" (findstr /b "rem" "%~f0" & goto :end)
shift
set "ARGS="
:collect
if "%~1"=="" goto :run
set "ARGS=%ARGS% %1"
shift
goto :collect
:run
if /i "%STEP%"=="prepare" "%PRO_PY%" "%HERE%prepare_city.py" %ARGS% & goto :end
if /i "%STEP%"=="infer" "%M3D_PY%" "%HERE%infer_city.py" %ARGS% & goto :end
if /i "%STEP%"=="refine" "%M3D_PY%" "%HERE%refine_city.py" %ARGS% & goto :end
if /i "%STEP%"=="summarize" "%M3D_PY%" "%HERE%summarize_refined.py" %ARGS% & goto :end
echo Unknown step "%STEP%": use prepare, infer, refine or summarize.
:end
endlocal
