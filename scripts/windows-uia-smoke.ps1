param([Parameter(Mandatory=$true)][int]$ApplicationProcessId)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
Add-Type -AssemblyName System.Drawing
Add-Type @'
using System;
using System.Runtime.InteropServices;
public static class NativeWindowSmoke {
 [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr handle);
 [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr handle, int command);
}
'@
try {
  $process = Get-Process -Id $ApplicationProcessId
  $root = $null
  for ($attempt=0; $attempt -lt 60; $attempt++) {
    $process.Refresh()
    if ($process.HasExited) { throw 'Native application exited before accessibility became ready' }
    if ($process.MainWindowHandle -ne [IntPtr]::Zero) {
      [NativeWindowSmoke]::ShowWindow($process.MainWindowHandle,9) | Out-Null
      [NativeWindowSmoke]::SetForegroundWindow($process.MainWindowHandle) | Out-Null
      $root = [System.Windows.Automation.AutomationElement]::FromHandle($process.MainWindowHandle)
      break
    }
    Start-Sleep -Milliseconds 500
  }
  if (-not $root) { throw 'Installed app did not create a native window on the Windows desktop' }
  function Find-Element([string]$pattern,[bool]$button=$false) {
    $elements = $root.FindAll([System.Windows.Automation.TreeScope]::Descendants,[System.Windows.Automation.Condition]::TrueCondition)
    foreach ($element in $elements) {
      try {
        if ($element.Current.Name -like $pattern -and (-not $button -or $element.Current.ControlType -eq [System.Windows.Automation.ControlType]::Button)) { return $element }
      } catch { }
    }
    return $null
  }
  function Wait-Element([string]$pattern,[bool]$button=$false) {
    for ($attempt=0; $attempt -lt 60; $attempt++) {
      $element=Find-Element $pattern $button
      if ($element) { return $element }
      Start-Sleep -Milliseconds 500
    }
    $names=@($root.FindAll([System.Windows.Automation.TreeScope]::Descendants,[System.Windows.Automation.Condition]::TrueCondition) | ForEach-Object { $_.Current.Name } | Select-Object -First 30)
    throw "Native accessibility element '$pattern' missing. Visible names: $($names -join '; ')"
  }
  function Click-Element([string]$pattern) {
    $element=Wait-Element $pattern $true
    if (-not $element.Current.IsEnabled) { throw "Native button '$pattern' is disabled" }
    $invoke=$element.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern)
    $invoke.Invoke()
  }
  function Capture-Window([string]$path,[bool]$checkOffice=$false) {
    $rectangle=$root.Current.BoundingRectangle
    if ($rectangle.Width -lt 800 -or $rectangle.Height -lt 600) { throw 'Native window has invalid bounds' }
    $bitmap=New-Object System.Drawing.Bitmap ([int]$rectangle.Width),([int]$rectangle.Height)
    $graphics=[System.Drawing.Graphics]::FromImage($bitmap)
    try {
      $graphics.CopyFromScreen([int]$rectangle.Left,[int]$rectangle.Top,0,0,$bitmap.Size)
      $bitmap.Save((Join-Path (Get-Location) $path),[System.Drawing.Imaging.ImageFormat]::Png)
      if ($checkOffice) {
        # Sample inside the office playfield, away from labels, borders and controls.
        # A flat background/error surface cannot satisfy this rendered-color check.
        $colors=New-Object 'System.Collections.Generic.HashSet[int]'
        for ($x=[int]($bitmap.Width*.55);$x -lt [int]($bitmap.Width*.85);$x+=8) {
          for ($y=[int]($bitmap.Height*.35);$y -lt [int]($bitmap.Height*.65);$y+=8) {
            $colors.Add($bitmap.GetPixel($x,$y).ToArgb()) | Out-Null
          }
        }
        if ($colors.Count -lt 48) { throw "Native office appears blank: only $($colors.Count) sampled colors" }
      }
    } finally { $graphics.Dispose();$bitmap.Dispose() }
  }
  New-Item -ItemType Directory -Force artifacts | Out-Null
  Wait-Element '*3D Trading Floor*' | Out-Null
  Wait-Element '*LOCAL ENGINE CONNECTED*' | Out-Null
  Start-Sleep -Seconds 2
  if (Find-Element '*3D rendering unavailable*') { throw 'Native WebGL rendering failed' }
  Capture-Window 'artifacts/windows-office.png' $true
  Click-Element '*Bot Team*'
  foreach ($name in @('Market Scout','Technical Analyst','Wallet Tracker','Liquidity Analyst','Risk Officer','Execution Specialist','Momentum Maverick','Mean Reversion Quant')) {
    Wait-Element $name | Out-Null
  }
  Click-Element '*Live Trading*'
  Wait-Element 'Link your personal account' | Out-Null
  $activate=Wait-Element 'Enable individually approved live orders' $true
  if ($activate.Current.IsEnabled) { throw 'Live activation was enabled without a connected account' }
  if (Find-Element '*Account linking is unavailable in this Linux/cloud browser*') { throw 'Windows app incorrectly disabled native account storage' }
  Wait-Element '*Coinbase key JSON export*' | Out-Null
  Capture-Window 'artifacts/windows-account-link.png'
  Write-Host 'Installed Windows accessibility navigation, eight agents, rendered office and locked live activation passed. No credentials imported or orders submitted.'
} catch {
  $message=$_.Exception.Message -replace '%','%25' -replace "`r?`n",'%0A'
  Write-Host "::error title=Native Windows UI::$message"
  throw
}
