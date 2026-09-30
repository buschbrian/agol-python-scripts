# GPU phase for the September 30 training tiles: Esri pretrained tree + building inference on core + halo.
#   pwsh -NoProfile -File run_training_gpu.ps1 [-Tiles 12TVL3206,...] [-Cutoff 07:30]
# 1. Waits (polling every 5 min) until the September 30 experiment queue.log contains 'GPU QUEUE DONE'.
# 2. Then requires 5 consecutive 1-minute polls with no compute-only GPU process. On this WDDM driver
#    `nvidia-smi --query-compute-apps` lists every desktop app that touches the GPU (explorer, browsers: type
#    C+G), so it never becomes empty; the idle test counts only rows of type "C" in the nvidia-smi process
#    table plus any python/pythonw process in the compute-apps list.
# 3. Runs one row at a time, tile by tile, tree then building, through the other agent's generalized runner
#    reviews/2026-09-29/dl-experiments-20260930/run_row.ps1 (read-only reuse; its SHA-256 and dl_run.py's
#    and dl_compare.py's are recorded per row): fresh exact copies with MD5 before/after, EDIT_ALL, classes
#    7/18 excluded, batch 1, PYTHONNOUSERSITE=1, then dl_compare integrity + disagreement tables.
# 4. Does not START a row at or after the cutoff (local time); stops and records what remains.
# Everything is logged to DL_ROOT\gpu-queue.log and DL_ROOT\gpu-status.json.
param(
  [string[]]$Tiles = @(),
  [string]$Cutoff = '07:30',
  [string]$QueueLog = 'H:\lidar\2023-salt-lake-valley\runs\pilot-2026-09-29\deep-learning\experiments-20260930\queue.log',
  [string]$Marker = 'GPU QUEUE DONE'
)
$ErrorActionPreference = 'Stop'
$env:PYTHONNOUSERSITE = '1'
$TRAIN = 'H:\lidar\2023-salt-lake-valley\runs\training-2026-09-30'
$DLROOT = "$TRAIN\deep-learning"
$TB = if ($env:CANOPY_TOOLBOX) { $env:CANOPY_TOOLBOX } else { (Resolve-Path "$PSScriptRoot\..\..").Path }
$RUNNER = "$TB\reviews\2026-09-29\dl-experiments-20260930\run_row.ps1"
$LABEL = 'TRAINING domain (September 30 seeded draw) -- core + prepared 50 m halo; labels via the training-review workflow'
New-Item -ItemType Directory -Force $DLROOT | Out-Null
$glog = "$DLROOT\gpu-queue.log"
function GLog($m) { $line = "$(Get-Date -Format o) $m"; Add-Content -Path $glog -Value $line; Write-Output $line }
function Sha($p) { if (Test-Path -LiteralPath $p) { (Get-FileHash -LiteralPath $p -Algorithm SHA256).Hash.ToLower() } else { $null } }
if (-not $Tiles.Count) { $Tiles = (Get-Content "$PSScriptRoot\training-tiles.json" -Raw | ConvertFrom-Json).draw_order }
$status = [ordered]@{ started = (Get-Date -Format o); tiles = $Tiles; cutoff = $Cutoff; marker = $Marker;
  phase = 'waiting for marker'; rows = @(); remaining = @(); pid = $PID }
function Save { $status.updated = (Get-Date -Format o); $status | ConvertTo-Json -Depth 8 | Set-Content -Path "$DLROOT\gpu-status.json" -Encoding utf8 }
function PastCutoff { (Get-Date) -ge [datetime]::ParseExact("$(Get-Date -Format yyyy-MM-dd) $Cutoff", 'yyyy-MM-dd HH:mm', $null) -and (Get-Date).Hour -lt 12 }

$plan = foreach ($t in $Tiles) { foreach ($j in 'tree', 'building') { [ordered]@{ tile = $t; job = $j; row = "$t-$j" } } }
function Remaining($from) { $status.remaining = @($plan | Select-Object -Skip $from | ForEach-Object { $_.row }) }
Remaining 0
GLog "gpu queue start (pid $PID): rows $(($plan | ForEach-Object { $_.row }) -join ', '); cutoff $Cutoff"
Save

function ComputeOnly {
  $busy = @()
  foreach ($line in (nvidia-smi)) {
    if ($line -match '^\|\s+\d+\s+\S+\s+\S+\s+(\d+)\s+(C|G|C\+G)\s+(\S.*?)\s+\S+\s*\|$' -and $Matches[2] -eq 'C') {
      $busy += "$($Matches[1]) $($Matches[3])"
    }
  }
  foreach ($line in (nvidia-smi --query-compute-apps=pid,process_name --format=csv,noheader)) {
    if ($line -match 'python') { $busy += "compute-apps: $line" }
  }
  $unique = @($busy | Select-Object -Unique)
  return ,$unique
}

# 1. Marker
$lastSeen = ''
while ($true) {
  $content = if (Test-Path $QueueLog) { Get-Content $QueueLog } else { @() }
  if ($content | Where-Object { $_ -like "*$Marker*" }) { GLog "marker '$Marker' found in queue.log"; break }
  $last = ($content | Select-Object -Last 1)
  if ($last -ne $lastSeen) { GLog "marker not yet present; queue.log last line: $last"; $lastSeen = $last }
  if (PastCutoff) { $status.phase = "stopped at cutoff while waiting for marker; last queue.log line: $last"; Save; GLog $status.phase; exit 0 }
  Start-Sleep -Seconds 300
}
# 2. Five consecutive idle minutes
$status.phase = 'waiting for 5 idle minutes'; Save
$idle = 0
while ($idle -lt 5) {
  $busy = ComputeOnly
  if ($busy.Count) { if ($idle -gt 0 -or -not $status.idle_wait_logged) { GLog "GPU busy: $($busy -join '; ')" }; $status.idle_wait_logged = $true; $idle = 0 }
  else { $idle += 1; GLog "GPU idle poll $idle/5" }
  if (PastCutoff) { $status.phase = 'stopped at cutoff while waiting for idle GPU'; Save; GLog $status.phase; exit 0 }
  if ($idle -lt 5) { Start-Sleep -Seconds 60 }
}
# 3. Rows
$status.phase = 'running rows'; Save
for ($i = 0; $i -lt $plan.Count; $i++) {
  $p = $plan[$i]
  if (PastCutoff) { Remaining $i; $status.phase = "cutoff $Cutoff reached; no new rows started"; Save; GLog $status.phase; break }
  $pts = "$TRAIN\$($p.tile)\prepared\points"
  $prepJson = "$TRAIN\$($p.tile)\prepared\preparation.json"
  $entry = [ordered]@{ row = $p.row; tile = $p.tile; job = $p.job; started = (Get-Date -Format o);
    runner_sha256 = Sha $RUNNER; dl_run_sha256 = Sha "$TB\reviews\2026-09-29\dl_run.py"; dl_compare_sha256 = Sha "$TB\reviews\2026-09-29\dl_compare.py" }
  if (-not (Test-Path $prepJson) -or (Get-Content $prepJson -Raw | ConvertFrom-Json).status -ne 'complete') {
    $entry.status = 'skipped: preparation not complete'; $status.rows += $entry; Remaining ($i + 1); Save; GLog "row $($p.row) skipped: preparation not complete"; continue
  }
  $core = "$pts\$($p.tile).las"
  $sources = @($core) + @(Get-ChildItem "$pts\*.las" | Where-Object { $_.FullName -ne $core } | Sort-Object Name | ForEach-Object { $_.FullName })
  $entry.sources = $sources
  $busy = ComputeOnly
  if ($busy.Count) { GLog "note: compute process present at row start: $($busy -join '; ')" ; $entry.compute_at_start = $busy }
  GLog "row $($p.row) start ($($sources.Count) files)"
  $status.current = $p.row; Remaining $i; Save
  $t0 = Get-Date
  $global:LASTEXITCODE = 0
  try {
    & $RUNNER -Row $p.row -Job $p.job -Sources $sources -Label $LABEL -Root $DLROOT -Watch @($core) *>> "$DLROOT\$($p.row).runner.log"
    $entry.exit = $LASTEXITCODE
  } catch { $entry.exit = "error: $($_.Exception.Message)" }
  $entry.minutes = [math]::Round(((Get-Date) - $t0).TotalMinutes, 1)
  $rowJson = "$DLROOT\$($p.row)\work\row.json"
  if (Test-Path $rowJson) { $r = Get-Content $rowJson -Raw | ConvertFrom-Json; $entry.row_status = $r.status; $entry.dl_run_wall_seconds = $r.dl_run_wall_seconds; $entry.dl_compare_exit = $r.dl_compare_exit }
  $entry.finished = (Get-Date -Format o)
  $status.rows += $entry; $status.current = $null; Remaining ($i + 1); Save
  GLog "row $($p.row) exit $($entry.exit) after $($entry.minutes) min; status: $($entry.row_status)"
}
if ($status.phase -eq 'running rows') { $status.phase = 'done' }
Save
GLog "gpu queue end: $($status.phase); remaining: $($status.remaining -join ', ')"
