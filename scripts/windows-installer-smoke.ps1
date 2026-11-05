$ErrorActionPreference = 'Stop'
$installer = Get-ChildItem 'src-tauri/target/x86_64-pc-windows-msvc/release/bundle/nsis/*.exe' | Select-Object -First 1
if (-not $installer) { throw 'Installer not found' }
$installDirectory = Join-Path $env:RUNNER_TEMP 'NightShift-Installed-Smoke'
$process = $null
$stage = 'installer'
try {
  if (Get-NetTCPConnection -State Listen -LocalPort 8765 -ErrorAction SilentlyContinue) { throw 'Engine port already in use; refusing to attach to another process' }
  $install = Start-Process -FilePath $installer.FullName -ArgumentList @('/S', "/D=$installDirectory") -PassThru -Wait
  if ($install.ExitCode -ne 0) { throw "Installer failed with exit code $($install.ExitCode)" }
  $executable = Join-Path $installDirectory 'irontrade-nightshift.exe'
  if (-not (Test-Path $executable)) { throw 'Installed native application missing' }
  $stage = 'installed-engine-readiness'
  $process = Start-Process -FilePath $executable -PassThru
  $ready = $false
  for ($attempt=0; $attempt -lt 90; $attempt++) {
    if ($process.HasExited) { throw 'Installed application exited before readiness' }
    try {
      $state = Invoke-RestMethod 'http://127.0.0.1:8765/api/state' -TimeoutSec 2
      if ($state.live.enabled -or $state.coinbase_connection.connected -or $state.coinbase_connection.saved) { throw 'Expected clean, disabled live state' }
      if (-not $state.coinbase_connection.secure_storage_available) { throw 'Native secure storage is unavailable' }
      if ($state.bots.Count -ne 8) { throw 'Eight agents were not initialized' }
      $ready = $true
      break
    } catch {
      if ($attempt -eq 89) { throw }
      Start-Sleep -Milliseconds 500
    }
  }
  if (-not $ready) { throw 'Installed engine readiness failed' }
  $stage = 'native-webview'
  powershell.exe -NoProfile -File scripts/windows-uia-smoke.ps1 -ApplicationProcessId $process.Id
  if ($LASTEXITCODE -ne 0) { throw 'Native frontend smoke checks failed' }
  # Close the native window normally so the app must clean up its own engine child.
  $stage = 'process-cleanup'
  $process.Refresh()
  if (-not $process.CloseMainWindow()) { throw 'Could not close installed native window normally' }
  if (-not $process.WaitForExit(20000)) { throw 'Native application did not exit cleanly' }
  for ($attempt=0; $attempt -lt 30; $attempt++) {
    if (-not (Get-NetTCPConnection -State Listen -LocalPort 8765 -ErrorAction SilentlyContinue)) { break }
    Start-Sleep -Milliseconds 500
  }
  if (Get-NetTCPConnection -State Listen -LocalPort 8765 -ErrorAction SilentlyContinue) { throw 'Engine child remained after application exit' }
  Write-Host 'Installer, installed app, native frontend and process cleanup verified; no live orders submitted.'
} catch {
  $message = "Stage $stage failed: $($_.Exception.Message)"
  Write-Host "::error title=Windows installed app::$message"
  New-Item -ItemType Directory -Force artifacts | Out-Null
  $message | Set-Content artifacts/windows-smoke-error.txt
  if (-not (Get-NetTCPConnection -State Listen -LocalPort 8765 -ErrorAction SilentlyContinue)) {
    $engineExecutable = Join-Path $installDirectory 'nightshift-engine.exe'
    if (Test-Path $engineExecutable) {
      $env:IRONTRADE_DATA_DIR = Join-Path $env:RUNNER_TEMP 'NightShift-Frozen-Diagnostic'
      $diagnostic = Start-Process -FilePath $engineExecutable -PassThru -RedirectStandardOutput artifacts/frozen-engine-stdout.txt -RedirectStandardError artifacts/frozen-engine-stderr.txt
      Start-Sleep -Seconds 3
      if ($diagnostic.HasExited) {
        $detail = (Get-Content artifacts/frozen-engine-stderr.txt -Tail 12 -ErrorAction SilentlyContinue) -join ' | '
        Write-Host "::error title=Packaged engine startup::$detail"
      } else {
        Write-Host '::error title=Packaged engine startup::Engine launches directly; inspect desktop startup path or readiness contract.'
      }
    }
  }
  throw
} finally {
  if ($process -and -not $process.HasExited) { Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue }
  # Clean up only binaries installed by this isolated CI smoke run.
  Get-CimInstance Win32_Process | Where-Object { $_.ExecutablePath -and $_.ExecutablePath.StartsWith($installDirectory, [System.StringComparison]::OrdinalIgnoreCase) } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
}
