# Esri building model on every Millcreek tile (October 20, 2026)

A third, independent opinion on buildings beside the October 8 native classes and FRACTAL, for a later consensus roof-height
product. `building_city.py` runs Esri's pretrained building point-classification model (`../../2026-09-29/dl_run.py building`,
batch 8) on a copy of each October 8 working LAS and checks that only classification bytes changed. The working LAS are never
written; the output is an opinion, not a label. Details are in the script's docstring.

**Status: paused at Brian's request at 15:11 on October 20** to free the A4000 for the FRACTAL fine-tune; nothing depends on it.
24 of 61 tiles are complete (2203 to 2706, 2802, 2804); 12TVL2803 was interrupted twice (the system crash, then the pause).
Batch 8 against the September 29 batch-1 output on 12TVL2804: 406 of 26.9 M points differ (0.0015%), within the 0.1% guard.

## Resume
Close Chrome, Teams and other heavy apps, then from `canopy-toolbox`:
```
set CANOPY_LIDAR_ROOT=D:\lidar
set PYTHONNOUSERSITE=1
%LOCALAPPDATA%\ESRI\conda\envs\arcgispro-py3-dl\python.exe reviews\2026-10-20\esri-city\building_city.py --no-wait >> D:\lidar\2023-salt-lake-valley\runs\esri-building-20261020\building.log 2>&1
```
Complete tiles are skipped. A tile that fails is renamed `<tile>.failed-<time>` and tried once more; rerun any that fail twice
with `--tiles`. `--no-wait` skips waiting for the citywide FRACTAL inference, which is long finished. Do not run it beside the
fine-tune or another GPU job: the machine has crashed at its memory commit limit (see [../HANDOFF.md](../HANDOFF.md)).

## Output (under `D:\lidar\2023-salt-lake-valley\runs\esri-building-20261020`)
`<tile>\building\<tile>.las` (class 6 where the model says building, 0 elsewhere, noise 7 and 18 kept), the runner's manifest
and `dl_run.log`, and `integrity.json` (written last; a tile counts as complete only with it). `building.log` is the run log.
Five tiles failed early in the first run (2203, 2303, 2602, 2705, 2802: start-up crashes in 27 to 46 s); all completed on retry.

Still to do once the run is complete: a batch-1 control on 12TVL2804 on this card, to settle whether the 406-point difference
comes from batch size or from the GPU.
