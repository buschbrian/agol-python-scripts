param([Parameter(Mandatory)][string]$Row)
$ErrorActionPreference = 'Stop'
$env:PYTHONNOUSERSITE = '1'
$LIDAR = $(if ($env:CANOPY_LIDAR_ROOT) { $env:CANOPY_LIDAR_ROOT } else { 'H:\lidar' })
$E = (Join-Path $LIDAR '2023-salt-lake-valley\runs\pilot-2026-09-29\deep-learning\experiments-20260929')
$FULL = (Join-Path $LIDAR '2023-salt-lake-valley\runs\pilot-2026-09-29\12TVL2804\prepared\points\12TVL2804.las')
$FULL_MD5 = '82787095336690D2909344206F9A80FC'
$DL = 'C:\Users\Brian\AppData\Local\ESRI\conda\envs\arcgispro-py3-dl\python.exe'
$VENV = 'V:\Developer\agol-python-scripts\.venv\Scripts\python.exe'
$TB = 'V:\Developer\agol-python-scripts\.claude\worktrees\agent-a3b10aa15ccee097a\canopy-toolbox'
$rows = @{
  'tree-full'    = @{job='tree';     source=$FULL; name='12TVL2804.las'; extra=@()}
  'tree-thin3'   = @{job='tree';     source="$E\tree-thin3\baseline\12TVL2804-thin3.las"; name='12TVL2804-thin3.las'; extra=@()}
  'building-abs' = @{job='building'; source=$FULL; name='12TVL2804.las'; extra=@()}
  'building-hag' = @{job='building'; source=$FULL; name='12TVL2804.las'; extra=@('--reference-height', "$E\building-hag\reference\ground.tif")}
}
$r = $rows[$Row]; $root = "$E\$Row"; $work = "$root\work"
New-Item -ItemType Directory -Force $work | Out-Null
$log = "$work\row.log"
function Log($m) { $line = "$(Get-Date -Format o) $m"; Add-Content -Path $log -Value $line; Write-Output $line }
function Md5($p) { (Get-FileHash $p -Algorithm MD5).Hash }
Log "row $Row start"
$pre = Md5 $FULL; Log "full baseline MD5 before: $pre"
if ($pre -ne $FULL_MD5) { Log 'ABORT full baseline MD5 mismatch'; exit 3 }
$srcMd5 = Md5 $r.source; Log "row baseline $($r.source) MD5 before: $srcMd5"
$copyDir = "$root\$($r.job)"
if (Test-Path $copyDir) { Log "ABORT copy folder already exists: $copyDir"; exit 4 }
New-Item -ItemType Directory $copyDir | Out-Null
$copy = "$copyDir\$($r.name)"
Copy-Item $r.source $copy
$copyMd5 = Md5 $copy; Log "fresh copy $copy MD5: $copyMd5"
if ($copyMd5 -ne $srcMd5) { Log 'ABORT copy MD5 differs'; exit 5 }
nvidia-smi --query-gpu=memory.used,utilization.gpu --format=csv,noheader | ForEach-Object { Log "GPU before: $_" }
$dlargs = @('-B', "$TB\reviews\2026-09-29\dl_run.py", $r.job, '--source', $r.source, '--copy', $copy,
          '--output-root', $root, '--boundary', '428000', '4504000', '429000', '4505000', '--batch', '1') + $r.extra
Log "dl_run: $DL $($dlargs -join ' ')"
$t0 = Get-Date
$ErrorActionPreference = 'Continue'
& $DL @dlargs *> "$work\dl_run.log"
$code = $LASTEXITCODE
$ErrorActionPreference = 'Stop'
Log "dl_run exit $code after $([math]::Round(((Get-Date)-$t0).TotalSeconds,1)) s"
$post = Md5 $FULL; Log "full baseline MD5 after: $post"
$srcPost = Md5 $r.source; Log "row baseline MD5 after: $srcPost"
if ($post -ne $FULL_MD5 -or $srcPost -ne $srcMd5) { Log 'BASELINE CHANGED'; exit 6 }
if ($r.extra.Count) { Log "reference raster SHA-256 after: $((Get-FileHash $r.extra[1] -Algorithm SHA256).Hash)" }
if ($code -ne 0) { Log "row $Row FAILED (see dl_run.log and work\run-$($r.job).json)"; exit 7 }
$ErrorActionPreference = 'Continue'
& $VENV -B "$TB\reviews\2026-09-29\dl_compare.py" --original $r.source --manifest "$($r.job)=$work\run-$($r.job).json" --out "$work\compare-$Row.json" *> "$work\dl_compare.log"
$ccode = $LASTEXITCODE
Log "dl_compare exit $ccode"
Log "row $Row done"
