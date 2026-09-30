# Row d of the September 30 queue: tree-hag-z and building-hag-z on the z-mode HAG copy of the 12TVL2804 core.
# Waits for run_queue.ps1 to log "queue done" (rows a-c), so only one GPU job ever runs. Runs only if the HAG
# manifest says "complete". The HAG LAS is its own baseline; dl_hag_check first verifies that it differs from the
# absolute baseline only in Z, and afterwards pairs each HAG prediction with its September 29 absolute-Z row by
# point index. Always ends by appending "GPU QUEUE DONE" to queue.log; no GPU work follows.
$ErrorActionPreference = 'Stop'
$P = 'H:\lidar\2023-salt-lake-valley\runs\pilot-2026-09-29'
$E = "$P\deep-learning\experiments-20260930"
$E29 = "$P\deep-learning\experiments-20260929"
$HAG = "$P\hag-20260929\12TVL2804"
$ABS = "$P\12TVL2804\prepared\points\12TVL2804.las"
$TB = if ($env:CANOPY_TOOLBOX) { $env:CANOPY_TOOLBOX } else { (Resolve-Path "$PSScriptRoot\..\..\..").Path }
$VENV = if ($env:CANOPY_VENV_PYTHON) { $env:CANOPY_VENV_PYTHON } else { Join-Path (Split-Path $TB -Parent) '.venv\Scripts\python.exe' }
$queueLog = "$E\queue.log"
function QLog($m) { $line = "$(Get-Date -Format o) $m"; Add-Content -Path $queueLog -Value $line; Write-Output $line }
while (-not (Select-String -Path $queueLog -Pattern 'queue done' -SimpleMatch -Quiet)) { Start-Sleep -Seconds 60 }
try {
  $manifest = Get-Content "$HAG\manifest.json" -Raw | ConvertFrom-Json
  if ($manifest.status -ne 'complete') { QLog "row d skipped: HAG manifest status '$($manifest.status)'"; return }
  $hagLas = $manifest.files.'12TVL2804.las'.z.output.path
  if (-not $hagLas -or -not (Test-Path $hagLas)) { QLog 'row d skipped: HAG core file missing'; return }
  $recorded = $manifest.files.'12TVL2804.las'.z.output.md5
  $actual = (Get-FileHash -LiteralPath $hagLas -Algorithm MD5).Hash.ToLower()
  if ($recorded -and $recorded -ne $actual) { QLog "row d skipped: HAG core MD5 $actual differs from manifest $recorded"; return }
  New-Item -ItemType Directory -Force "$E\hag-z-check" | Out-Null
  $ErrorActionPreference = 'Continue'
  & $VENV -B "$TB\reviews\2026-09-29\dl_hag_check.py" --absolute $ABS --hag $hagLas --out "$E\hag-z-check\hag-vs-absolute.json" *> "$E\hag-z-check\check.log"
  $code = $LASTEXITCODE
  $ErrorActionPreference = 'Stop'
  QLog "HAG non-Z byte check exit $code"
  if ($code -ne 0) { QLog 'row d skipped: HAG baseline differs from the absolute baseline outside Z'; return }
  $runner = Join-Path $PSScriptRoot 'run_row.ps1'
  $label = 'HAG z-mode baseline (hag-20260929); compare by index with the HAG baseline only'
  foreach ($r in @(@{ Row = 'tree-hag-z'; Job = 'tree' }, @{ Row = 'building-hag-z'; Job = 'building' })) {
    $t0 = Get-Date
    QLog "row $($r.Row) start"
    $global:LASTEXITCODE = 0
    try {
      & $runner -Row $r.Row -Job $r.Job -Sources @($hagLas) -Label $label -Root $E -Watch @($ABS) *>> "$E\$($r.Row).runner.log"
      $status = "exit $LASTEXITCODE"
    } catch { $status = "error: $($_.Exception.Message)" }
    QLog "row $($r.Row) $status after $([math]::Round(((Get-Date)-$t0).TotalMinutes,1)) min"
  }
  $pairs = @()
  if (Test-Path "$E\tree-hag-z\tree\12TVL2804.las") { $pairs += @('--pair', 'tree', "$E29\tree-full\tree\12TVL2804.las", "$E\tree-hag-z\tree\12TVL2804.las") }
  if (Test-Path "$E\building-hag-z\building\12TVL2804.las") { $pairs += @('--pair', 'building', "$E29\building-abs\building\12TVL2804.las", "$E\building-hag-z\building\12TVL2804.las") }
  $ErrorActionPreference = 'Continue'
  & $VENV -B "$TB\reviews\2026-09-29\dl_hag_check.py" --absolute $ABS --hag $hagLas --out "$E\hag-z-check\hag-vs-absolute-paired.json" @pairs *> "$E\hag-z-check\paired.log"
  QLog "HAG paired prediction check exit $LASTEXITCODE"
} catch {
  QLog "row d error: $($_.Exception.Message)"
} finally {
  QLog 'GPU QUEUE DONE'
}
