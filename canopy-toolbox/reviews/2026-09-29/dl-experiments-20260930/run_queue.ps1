# September 30 GPU queue: strictly sequential, one GPU job at a time. A failed row is logged and the queue
# continues with the next row. Rows a-c only; row d (HAG) is started separately once its baseline exists.
$ErrorActionPreference = 'Stop'
$P = 'H:\lidar\2023-salt-lake-valley\runs\pilot-2026-09-29'
$E = "$P\deep-learning\experiments-20260930"
New-Item -ItemType Directory -Force $E | Out-Null
$queueLog = "$E\queue.log"
function QLog($m) { $line = "$(Get-Date -Format o) $m"; Add-Content -Path $queueLog -Value $line; Write-Output $line }
$runner = Join-Path $PSScriptRoot 'run_row.ps1'
function Files($tile, [string[]]$names) { $names | ForEach-Object { "$P\$tile\prepared\points\$_.las" } }

$halo2804 = Files '12TVL2804' @('12TVL2703', '12TVL2704', '12TVL2705', '12TVL2803', '12TVL2805', '12TVL2904', '12TVL2905')
$all3302 = Files '12TVL3302' @('12TVL3302', '12TVL3201', '12TVL3202', '12TVL3203', '12TVL3301', '12TVL3303', '12TVL3402', '12TVL3403')
$all2203 = Files '12TVL2203' @('12TVL2203', '12TVL2204', '12TVL2303', '12TVL2304')
$holdout = 'prospective holdout -- inference only, never training'
$transfer = 'external transfer -- outside Millcreek estimate'
$rows = @(
  @{ Row = '12TVL2804-halo-tree'; Job = 'tree'; Sources = $halo2804; Label = '12TVL2804 halo files only; core inferred separately on 2026-09-29' },
  @{ Row = '12TVL2804-halo-building'; Job = 'building'; Sources = $halo2804; Label = '12TVL2804 halo files only; core inferred separately on 2026-09-29' },
  @{ Row = '12TVL3302-prospective-holdout-inference-only-tree'; Job = 'tree'; Sources = $all3302; Label = $holdout },
  @{ Row = '12TVL3302-prospective-holdout-inference-only-building'; Job = 'building'; Sources = $all3302; Label = $holdout },
  @{ Row = '12TVL2203-external-transfer-tree'; Job = 'tree'; Sources = $all2203; Label = $transfer },
  @{ Row = '12TVL2203-external-transfer-building'; Job = 'building'; Sources = $all2203; Label = $transfer }
)
if ($args.Count) { $rows = $rows | Where-Object { $args -contains $_.Row } }
QLog "queue start: $($rows.Row -join ', ')"
foreach ($r in $rows) {
  $t0 = Get-Date
  QLog "row $($r.Row) start"
  $global:LASTEXITCODE = 0
  try {
    & $runner -Row $r.Row -Job $r.Job -Sources $r.Sources -Label $r.Label -Root $E *>> "$E\$($r.Row).runner.log"
    $status = "exit $LASTEXITCODE"
  } catch {
    $status = "error: $($_.Exception.Message)"
  }
  QLog "row $($r.Row) $status after $([math]::Round(((Get-Date)-$t0).TotalMinutes,1)) min"
}
QLog 'queue done'
