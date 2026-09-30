# Step b of the September 30 handoff: repeat the absolute-Z tree row on the 12TVL2804 core.
#   pwsh -NoProfile -File queue_tree_repeat.ps1 [-WaitPid 1234]
# Same file, boundary, model and batch size as experiments-20260929\tree-full, so any difference from it is
# run-to-run nondeterminism of the tree model. One GPU job at a time: with -WaitPid it first waits for that process
# (for example the 12TVL3006 run_training_gpu.ps1) to exit, then for three consecutive minutes with no DL Python
# running. The row runs through dl-experiments-20260930\run_row.ps1 (fresh exact copy, MD5 before/after, dl_compare
# integrity), then repeat_compare.py pairs its output with the September 29 tree-full output by point index.
# Logs to experiments-20260930\repeat-queue.log (not queue.log, whose 'GPU QUEUE DONE' marker other scripts read).
# Asks Windows not to sleep while it runs (SetThreadExecutionState, ends with this process; no settings changed).
# Root: CANOPY_LIDAR_ROOT (default H:\lidar). Paths and overrides as in run_row.ps1.
param([int]$WaitPid = 0)
Add-Type -Namespace Win -Name Power -MemberDefinition '[DllImport("kernel32.dll")] public static extern uint SetThreadExecutionState(uint f);'
[void][Win.Power]::SetThreadExecutionState([uint32]2147483649)   # ES_CONTINUOUS | ES_SYSTEM_REQUIRED
$ErrorActionPreference = 'Stop'
$env:PYTHONNOUSERSITE = '1'
$LIDAR = $(if ($env:CANOPY_LIDAR_ROOT) { $env:CANOPY_LIDAR_ROOT } else { 'H:\lidar' })
$P = (Join-Path $LIDAR '2023-salt-lake-valley\runs\pilot-2026-09-29')
$E = "$P\deep-learning\experiments-20260930"
$E29 = "$P\deep-learning\experiments-20260929"
$ABS = "$P\12TVL2804\prepared\points\12TVL2804.las"
$TB = if ($env:CANOPY_TOOLBOX) { $env:CANOPY_TOOLBOX } else { (Resolve-Path "$PSScriptRoot\..\..").Path }
$VENV = if ($env:CANOPY_VENV_PYTHON) { $env:CANOPY_VENV_PYTHON } else { Join-Path (Split-Path $TB -Parent) '.venv\Scripts\python.exe' }
$RUNNER = "$TB\reviews\2026-09-29\dl-experiments-20260930\run_row.ps1"
$Row = 'tree-abs-repeat'
$log = "$E\repeat-queue.log"
function QLog($m) { $line = "$(Get-Date -Format o) $m"; Add-Content -Path $log -Value $line; Write-Output $line }

if ($WaitPid) {
  QLog "step b queued: waiting for pid $WaitPid to exit"
  while (Get-Process -Id $WaitPid -ErrorAction SilentlyContinue) { Start-Sleep -Seconds 30 }
  QLog "pid $WaitPid exited"
}
$quiet = 0
while ($quiet -lt 3) {
  $dl = @(Get-Process python, pythonw -ErrorAction SilentlyContinue | Where-Object { $_.Path -like '*arcgispro-py3-dl*' })
  if ($dl.Count) { $quiet = 0; QLog "DL python still running (pids $($dl.Id -join ', ')); waiting" } else { $quiet++ }
  if ($quiet -lt 3) { Start-Sleep -Seconds 60 }
}
if (Test-Path "$E\$Row") { QLog "ABORT: $E\$Row already exists"; exit 4 }
$label = 'Step b reproducibility: repeat of September 29 tree-full (absolute Z, 12TVL2804 core, batch 1); compare by index with experiments-20260929\tree-full only'
QLog "row $Row start"
$t0 = Get-Date
$global:LASTEXITCODE = 0
try {
  & $RUNNER -Row $Row -Job tree -Sources @($ABS) -Label $label -Boundary 428000,4504000,429000,4505000 -Root $E *>> "$E\$Row.runner.log"
  $status = "exit $LASTEXITCODE"
} catch { $status = "error: $($_.Exception.Message)" }
QLog "row $Row $status after $([math]::Round(((Get-Date) - $t0).TotalMinutes, 1)) min"
$rowJson = "$E\$Row\work\row.json"
$r = $null
if (Test-Path $rowJson) { $r = Get-Content $rowJson -Raw | ConvertFrom-Json; QLog "row status: $($r.status)" }
$new = "$E\$Row\tree\12TVL2804.las"; $old = "$E29\tree-full\tree\12TVL2804.las"
if ((Test-Path $new) -and $r -and $r.status -like 'complete*') {
  $ErrorActionPreference = 'Continue'
  & $VENV -B "$PSScriptRoot\repeat_compare.py" $old $new "$E\$Row\repeat-vs-tree-full.json" *> "$E\$Row\repeat-compare.log"
  QLog "repeat comparison exit $LASTEXITCODE (see $E\$Row\repeat-vs-tree-full.json)"
} else { QLog 'repeat comparison skipped: row did not complete' }
QLog 'step b done'
