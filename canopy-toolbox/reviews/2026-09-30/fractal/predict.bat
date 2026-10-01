@echo off
rem Run the IGN FRACTAL RandLA-Net model (through Myria3D) on one coloured LAS and write a copy with the model's opinion.
rem
rem     predict.bat INPUT.las OUTPUT_DIR [more Hydra overrides]
rem
rem INPUT is made absolute here (Myria3D changes folder, so a relative path matches nothing). OUTPUT_DIR is created by the run.
rem The copy gains PredictedClassification, entropy and one probability per class. The colour must come from colorize_las.py.
rem See README.md. EPSG 6341 is NAD83(2011) UTM 12N, the tile's system; the model's own default (2154) is France.
setlocal
set "TOOLS=C:\Users\bbusch\tools"
set "ENV=%TOOLS%\envs\myria3d"
if "%~2"=="" (echo Usage: predict.bat INPUT.las OUTPUT_DIR [overrides] & goto :end)
if not exist "%~f1" (echo No such file: %~f1 & goto :end)
set "PYTHONNOUSERSITE=1"
set "PATH=%ENV%;%ENV%\Library\bin;%ENV%\Scripts;%PATH%"
set "SRC=%~f1"
set "OUT=%~f2"
shift
shift
cd /d "%TOOLS%\myria3d"
"%ENV%\python.exe" run.py task.task_name=predict "predict.src_las=%SRC%" "predict.output_dir=%OUT%" "predict.gpus=[0]" datamodule.epsg=6341 datamodule.batch_size=10 datamodule.num_workers=0 datamodule.prefetch_factor=null model.num_workers=0 predict.interpolator.probas_to_save=all %1 %2 %3 %4 %5 %6 %7 %8 %9
:end
endlocal
