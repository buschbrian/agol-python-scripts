@echo off
rem Training-label helpers for the person labelling in ArcGIS Pro. Double-click for help, or run from a prompt:
rem
rem     training_labels.bat status     progress by queue and the next unit
rem     training_labels.bat backup     copy every answered unit into the repo (packets\training-labels)
rem     training_labels.bat save       backup, then commit just those two files (no push)
rem     training_labels.bat restore    preview putting the repo copy back into the geodatabase
rem     training_labels.bat restore --apply [--replace]
rem     training_labels.bat repair     re-point the project's toolbox at this machine's repo (close Pro first)
rem
rem It finds the lidar disk (CANOPY_LIDAR_ROOT, else D:\lidar, else H:\lidar) and runs the driver with ArcGIS Pro's
rem Python, so no PowerShell script (AllSigned) is involved. Nothing here changes evaluation data or the LAS files.
setlocal
set "PYTHONNOUSERSITE=1"
set "PACKET_REL=2023-salt-lake-valley\runs\pilot-2026-09-29\training-review\packet-20260929"
if not defined CANOPY_LIDAR_ROOT (
  if exist "D:\lidar\%PACKET_REL%" (set "CANOPY_LIDAR_ROOT=D:\lidar")
)
if not defined CANOPY_LIDAR_ROOT (
  if exist "H:\lidar\%PACKET_REL%" (set "CANOPY_LIDAR_ROOT=H:\lidar")
)
if not defined CANOPY_LIDAR_ROOT (
  echo Could not find the lidar disk: no %PACKET_REL% under D:\lidar or H:\lidar.
  echo Plug in the disk, or set CANOPY_LIDAR_ROOT to its lidar folder, then run this again.
  goto :end
)
set "PRO_PY=C:\Program Files\ArcGIS\Pro\bin\Python\envs\arcgispro-py3\python.exe"
if not exist "%PRO_PY%" (
  echo ArcGIS Pro's Python was not found at "%PRO_PY%".
  goto :end
)
set "HERE=%~dp0"
set "DRIVER=%HERE%..\2026-09-29\training_review_driver.py"
set "LABELS_DIR=%HERE%..\2026-09-29\packets\training-labels"
set "CMD=%~1"
if "%CMD%"=="" goto :usage
if /i "%CMD%"=="status"  goto :run
if /i "%CMD%"=="backup"  goto :run
if /i "%CMD%"=="restore" goto :run
if /i "%CMD%"=="repair"  goto :repair
if /i "%CMD%"=="save"    goto :save
:usage
echo Usage: training_labels.bat status ^| backup ^| save ^| restore [--apply] [--replace] ^| repair
echo Using the lidar disk at %CANOPY_LIDAR_ROOT%
goto :end

:run
"%PRO_PY%" -B "%DRIVER%" %*
set "RC=%ERRORLEVEL%"
goto :done

:repair
"%PRO_PY%" -B "%DRIVER%" repair-project
set "RC=%ERRORLEVEL%"
goto :done

:save
"%PRO_PY%" -B "%DRIVER%" backup
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" if not "%RC%"=="3" goto :done
git -C "%HERE%." add -- "%LABELS_DIR%\labels-progress.csv" "%LABELS_DIR%\progress.json"
git -C "%HERE%." diff --cached --quiet -- "%LABELS_DIR%"
if not errorlevel 1 (
  echo No change since the last commit; nothing to commit.
  goto :done
)
git -C "%HERE%." commit -m "Back up training labels" -- "%LABELS_DIR%\labels-progress.csv" "%LABELS_DIR%\progress.json"
if errorlevel 1 (set "RC=1") else (echo Committed. To share it: git push)
goto :done

:done
if "%RC%"=="3" echo Exit code 3 means something needs a look: see the CHECK / SKIPPED lines above. Nothing was lost.
endlocal & exit /b %RC%

:end
endlocal
