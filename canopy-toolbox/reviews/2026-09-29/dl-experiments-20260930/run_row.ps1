# Generalized row runner for Classify Point Cloud Using Trained Model experiments (September 30 queue).
# Replaces the September 29 record (dl-experiments-20260929/run_row.ps1), which hard-coded a deleted
# worktree, the 12TVL2804 core file and its boundary.
#
# One row = one model job over one LAS dataset built from fresh exact copies of one or more baseline files.
#   pwsh -File run_row.ps1 -Row NAME -Job tree|building -Sources a.las,b.las [-Label TEXT]
#        [-Boundary XMIN,YMIN,XMAX,YMAX] [-Extra ARGS] [-Watch FILES] [-Root EXPERIMENT_ROOT]
# Without -Boundary the whole dataset is processed. Each source's MD5 is recorded before copying, each copy
# must match it, and every source (plus each -Watch file) is re-hashed after inference. dl_compare then checks
# integrity and writes per-file disagreement tables. work\row.json records all of it.
param(
  [Parameter(Mandatory)][string]$Row,
  [Parameter(Mandatory)][ValidateSet('tree', 'building')][string]$Job,
  [Parameter(Mandatory)][string[]]$Sources,
  [string]$Label = '',
  [double[]]$Boundary = @(),
  [string[]]$Extra = @(),
  [string[]]$Watch = @((Join-Path $(if ($env:CANOPY_LIDAR_ROOT) { $env:CANOPY_LIDAR_ROOT } else { 'H:\lidar' }) '2023-salt-lake-valley\runs\pilot-2026-09-29\12TVL2804\prepared\points\12TVL2804.las')),
  [string]$Root = (Join-Path $(if ($env:CANOPY_LIDAR_ROOT) { $env:CANOPY_LIDAR_ROOT } else { 'H:\lidar' }) '2023-salt-lake-valley\runs\pilot-2026-09-29\deep-learning\experiments-20260930')
)
$ErrorActionPreference = 'Stop'
$env:PYTHONNOUSERSITE = '1'
# Machine-specific paths: override with environment variables on another workstation.
$DL = if ($env:CANOPY_DL_PYTHON) { $env:CANOPY_DL_PYTHON } else { "$env:LOCALAPPDATA\ESRI\conda\envs\arcgispro-py3-dl\python.exe" }
$TB = if ($env:CANOPY_TOOLBOX) { $env:CANOPY_TOOLBOX } else { (Resolve-Path "$PSScriptRoot\..\..\..").Path }
$VENV = if ($env:CANOPY_VENV_PYTHON) { $env:CANOPY_VENV_PYTHON } else { Join-Path (Split-Path $TB -Parent) '.venv\Scripts\python.exe' }
$rowRoot = Join-Path $Root $Row; $work = Join-Path $rowRoot 'work'; $copyDir = Join-Path $rowRoot $Job
if (Test-Path $copyDir) { Write-Output "ABORT copy folder already exists: $copyDir"; exit 4 }
New-Item -ItemType Directory -Force $work | Out-Null
$log = Join-Path $work 'row.log'
function Log($m) { $line = "$(Get-Date -Format o) $m"; Add-Content -Path $log -Value $line; Write-Output $line }
function Md5($p) { (Get-FileHash -LiteralPath $p -Algorithm MD5).Hash.ToLower() }
$record = [ordered]@{ row = $Row; job = $Job; label = $Label; boundary = $(if ($Boundary.Count) { $Boundary } else { $null })
  started = (Get-Date -Format o); files = @(); watch = @(); status = 'running' }
function Save { $record | ConvertTo-Json -Depth 6 | Set-Content -Path (Join-Path $work 'row.json') -Encoding utf8 }
if ($Label) { Set-Content -Path (Join-Path $rowRoot 'LABEL.txt') -Value $Label -Encoding utf8 }
Log "row $Row ($Job) start; label: $Label"
foreach ($w in $Watch) { $h = Md5 $w; $record.watch += [ordered]@{ path = $w; md5_before = $h }; Log "watch $w MD5 before: $h" }
New-Item -ItemType Directory $copyDir | Out-Null
$pairArgs = @()
foreach ($s in $Sources) {
  $before = Md5 $s
  $copy = Join-Path $copyDir (Split-Path $s -Leaf)
  Copy-Item -LiteralPath $s -Destination $copy
  # Copy-Item keeps a read-only source attribute (the HAG writer sets it); the tool edits the copy in place and
  # would fail only after inference. The attribute is not file content, so the MD5 check below is unaffected.
  $item = Get-Item -LiteralPath $copy
  $wasReadOnly = $item.IsReadOnly
  if ($wasReadOnly) { $item.IsReadOnly = $false; Log "cleared read-only attribute on copy $copy (source keeps it)" }
  $copyMd5 = Md5 $copy
  Log "source $s MD5 $before; copy $copy MD5 $copyMd5"
  $record.files += [ordered]@{ source = $s; copy = $copy; source_md5_before = $before; copy_md5 = $copyMd5
    copy_read_only_attribute_cleared = $wasReadOnly }
  if ($copyMd5 -ne $before) { $record.status = 'aborted: copy MD5 differs'; Save; Log 'ABORT copy MD5 differs'; exit 5 }
  $pairArgs += @('--source', $s, '--copy', $copy)
}
Save
nvidia-smi --query-gpu=memory.used,utilization.gpu --format=csv,noheader | ForEach-Object { Log "GPU before: $_" }
$dlargs = @('-B', "$TB\reviews\2026-09-29\dl_run.py", $Job) + $pairArgs + @('--output-root', $rowRoot, '--batch', '1')
if ($Label) { $dlargs += @('--label', $Label) }
if ($Boundary.Count) { $dlargs += @('--boundary') + ($Boundary | ForEach-Object { "$_" }) }
$dlargs += $Extra
Log "dl_run: $DL $($dlargs -join ' ')"
$t0 = Get-Date
$ErrorActionPreference = 'Continue'
& $DL @dlargs *> (Join-Path $work 'dl_run.log')
$code = $LASTEXITCODE
$ErrorActionPreference = 'Stop'
$secs = [math]::Round(((Get-Date) - $t0).TotalSeconds, 1)
$record.dl_run_exit = $code; $record.dl_run_wall_seconds = $secs
Log "dl_run exit $code after $secs s"
nvidia-smi --query-gpu=memory.used,utilization.gpu --format=csv,noheader | ForEach-Object { Log "GPU after: $_" }
$changed = $false
foreach ($f in $record.files) {
  $f.source_md5_after = Md5 $f.source
  Log "source $($f.source) MD5 after: $($f.source_md5_after)"
  if ($f.source_md5_after -ne $f.source_md5_before) { $changed = $true }
}
foreach ($w in $record.watch) {
  $w.md5_after = Md5 $w.path; Log "watch $($w.path) MD5 after: $($w.md5_after)"
  if ($w.md5_after -ne $w.md5_before) { $changed = $true }
}
if ($changed) { $record.status = 'BASELINE CHANGED'; Save; Log 'BASELINE CHANGED'; exit 6 }
if ($code -ne 0) { $record.status = 'failed'; Save; Log "row $Row FAILED (see dl_run.log and work\run-$Job.json)"; exit 7 }
$manifest = Join-Path $work "run-$Job.json"
if ($Sources.Count -gt 1) { $cargs = @('--row-manifest', "$Job=$manifest") }
else { $cargs = @('--original', $Sources[0], '--manifest', "$Job=$manifest") }
$out = Join-Path $work "compare-$Row.json"
$ErrorActionPreference = 'Continue'
& $VENV -B "$TB\reviews\2026-09-29\dl_compare.py" @cargs --out $out *> (Join-Path $work 'dl_compare.log')
$ccode = $LASTEXITCODE
$ErrorActionPreference = 'Stop'
$record.dl_compare_exit = $ccode
$record.status = $(if ($ccode -eq 0) { 'complete; integrity verified' } else { 'inference complete; comparison rejected or failed' })
$record.finished = (Get-Date -Format o)
Save
Log "dl_compare exit $ccode"
Log "row $Row done"
