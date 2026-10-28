@echo off
rem Footprint review page: LiDAR candidates, county footprints with no 2023 roof, possible new buildings,
rem 3D buildings without a detailed roof and the CFTree tree models.
rem
rem     footprint_review.bat serve              start the page on this machine and open it (http://127.0.0.1:8770)
rem     footprint_review.bat backup             copy the page's answers into the repo (answers\footprint-review-answers.csv);
rem                                             an answer already in the repo is never changed
rem     footprint_review.bat backup --replace   ... and take the page's answer where the two differ
rem     footprint_review.bat build              rebuild the page data (Pro env millcreek-py3; about an hour; once)
rem     footprint_review.bat add-pairs          append the "offset or rebuilt" queue to built data (once; then restart serve)
rem     footprint_review.bat facts             refresh only the side-panel facts in the built data (a few minutes;
rem                                             safe while the page is open; answers are not touched)
rem     footprint_review.bat serve-pilot        the 20-candidate pilot data on port 8771
rem     footprint_review.bat model-queues       size the 3D-building and CFTree queues (reviews\2026-10-26\model-review)
rem     footprint_review.bat add-models         append those queues to built data (once; then restart serve)
rem     footprint_review.bat serve-model-pilot  the 5-per-queue pilot of those queues on port 8772
rem
rem Answers are kept in <data>\answers\footprint-review-answers.csv on the lidar disk, saved after every key press.
rem Nothing is uploaded; the imagery comes from Esri World Imagery over the internet.
setlocal
set "PYTHONNOUSERSITE=1"
set "HERE=%~dp0"
if not defined CANOPY_LIDAR_ROOT if exist "D:\lidar\2023-salt-lake-valley\runs\footprint-review-20261023" set "CANOPY_LIDAR_ROOT=D:\lidar"
if not defined CANOPY_LIDAR_ROOT if exist "H:\lidar\2023-salt-lake-valley\runs\footprint-review-20261023" set "CANOPY_LIDAR_ROOT=H:\lidar"
if not defined CANOPY_LIDAR_ROOT (echo Could not find the lidar disk; set CANOPY_LIDAR_ROOT. & goto :end)
set "PRO_PY=C:\Program Files\ArcGIS\Pro\bin\Python\envs\arcgispro-py3\python.exe"
set "BUILD_PY=%LOCALAPPDATA%\ESRI\conda\envs\millcreek-py3\python.exe"
set "RUN=%CANOPY_LIDAR_ROOT%\2023-salt-lake-valley\runs\footprint-review-20261023"
set "STEP=%~1"
if /i "%STEP%"=="serve" (
  start "" "http://127.0.0.1:8770/"
  "%PRO_PY%" -I "%HERE%serve_footprint_review.py" --data "%RUN%\data" --port 8770
  goto :end
)
if /i "%STEP%"=="serve-pilot" (
  start "" "http://127.0.0.1:8771/"
  "%PRO_PY%" -I "%HERE%serve_footprint_review.py" --data "%RUN%\pilot-data" --port 8771
  goto :end
)
if /i "%STEP%"=="serve-model-pilot" (
  start "" "http://127.0.0.1:8772/"
  "%PRO_PY%" -I "%HERE%serve_footprint_review.py" --data "%RUN%\model-pilot-data" --port 8772
  goto :end
)
set "MODELS=%HERE%..\..\2026-10-26\model-review"
set "MQ=%CANOPY_LIDAR_ROOT%\2023-salt-lake-valley\runs\model-review-20261026"
if /i "%STEP%"=="model-queues" ("%BUILD_PY%" -I "%MODELS%\queues.py" "%MQ%" & goto :end)
if /i "%STEP%"=="add-models" ("%BUILD_PY%" -I "%MODELS%\add_model_queues.py" "%MQ%" "%RUN%\data" & goto :end)
if /i "%STEP%"=="backup" ("%PRO_PY%" -I "%HERE%serve_footprint_review.py" backup --data "%RUN%\data" %2 & goto :end)
if /i "%STEP%"=="build" ("%BUILD_PY%" -I "%HERE%build_review_data.py" "%RUN%\data" & goto :end)
if /i "%STEP%"=="add-pairs" ("%BUILD_PY%" -I "%HERE%build_review_data.py" "%RUN%\data" --add-pairs & goto :end)
if /i "%STEP%"=="facts" ("%BUILD_PY%" -I "%HERE%build_review_data.py" "%RUN%\data" --facts-only & goto :end)
findstr /b "rem" "%~f0"
:end
endlocal
