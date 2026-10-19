# Xiaomi Pad 5 (nabu) Stage 6 test-only PowerShell fastboot preflight.
# Default dry run. Use -Boot only after checking the experimental image.
param([Parameter(Mandatory=$true)][string]$Image, [switch]$Boot)
$ErrorActionPreference = 'Stop'
function Fail([string]$Reason) { Write-Error $Reason; exit 1 }
$fb = Get-Command fastboot.exe -CommandType Application -ErrorAction SilentlyContinue
if ($null -eq $fb) { Fail 'fastboot.exe not in PATH' }
function Invoke-FB([string]$Arguments) {
  $psi = New-Object System.Diagnostics.ProcessStartInfo
  $psi.FileName = $fb.Source
  $psi.Arguments = $Arguments
  $psi.UseShellExecute = $false
  $psi.RedirectStandardOutput = $true
  $psi.RedirectStandardError = $true
  $psi.CreateNoWindow = $true
  $proc = New-Object System.Diagnostics.Process
  $proc.StartInfo = $psi
  try {
    if (-not $proc.Start()) { Fail 'Cannot start fastboot' }
    $out = $proc.StandardOutput.ReadToEndAsync()
    $err = $proc.StandardError.ReadToEndAsync()
    if (-not $proc.WaitForExit(30000)) {
      try { $proc.Kill() } catch {}
      Fail 'fastboot timed out'
    }
    return [pscustomobject]@{
      ExitCode = $proc.ExitCode
      Output = ($out.Result + [Environment]::NewLine + $err.Result)
    }
  } finally {
    $proc.Dispose()
  }
}
$abs = (Resolve-Path -LiteralPath $Image -ErrorAction Stop).Path
$fs = [System.IO.File]::OpenRead($abs)
try {
  if ($fs.Length -gt 35651584 -or $fs.Length -lt 8192) { Fail 'Bad image size' }
  $header = New-Object byte[] 44
  $null = $fs.Read($header, 0, 44)
  if ([System.Text.Encoding]::ASCII.GetString($header, 0, 8) -ne 'ANDROID!' -or
      [System.BitConverter]::ToUInt32($header, 40) -ne 3) { Fail 'Not Android boot v3' }
} finally { $fs.Dispose() }
if ([System.IO.Path]::GetFileName($abs) -cne 'nabu-stage6-handoff.img') {
  Fail 'Wrong diagnostic image name'
}
$shaPath = Join-Path (Split-Path -Parent $PSScriptRoot) 'out\SHA256SUMS.txt'
if (-not [System.IO.File]::Exists($shaPath)) { Fail 'Missing SHA256SUMS.txt' }
$shaText = [System.IO.File]::ReadAllText($shaPath)
if ($shaText -notmatch '(?im)^([a-f0-9]{64})\s+out/nabu-stage6-handoff\.img\s*$') {
  Fail 'Expected hash entry missing'
}
$expected = $Matches[1].ToLowerInvariant()
$actual = (Get-FileHash -LiteralPath $abs -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actual -cne $expected) { Fail 'SHA256 image mismatch' }
$devs = Invoke-FB 'devices'
$rows = @($devs.Output -split '\r?\n' | Where-Object { $_ -match '^\S+\s+fastboot\s*$' })
if ($devs.ExitCode -ne 0 -or $rows.Count -ne 1) { Fail 'Requires exactly one bootloader fastboot device' }
$product = Invoke-FB 'getvar product'
if ($product.ExitCode -ne 0 -or $product.Output -notmatch '(?im)^\s*(?:\(bootloader\)\s*)?product:\s*nabu\s*$') {
  Fail 'Not confirmed product=nabu'
}
$unlocked = Invoke-FB 'getvar unlocked'
if ($unlocked.ExitCode -ne 0 -or $unlocked.Output -notmatch '(?im)^\s*(?:\(bootloader\)\s*)?unlocked:\s*(?:yes|true)\s*$') {
  Fail 'Bootloader not unlocked'
}
$userspace = Invoke-FB 'getvar is-userspace'
if ($userspace.ExitCode -ne 0 -or $userspace.Output -notmatch '(?im)^\s*(?:\(bootloader\)\s*)?is-userspace:\s*(?:no|false)\s*$') {
  Fail 'fastbootd is not supported'
}
Write-Host 'PASS: nabu, unlocked, boot v3, SHA256 verified' -ForegroundColor Green
if (-not $Boot) {
  Write-Host 'DRY RUN: no device action.'
  exit 0
}
Write-Host 'Warning: read-only FDT survey. 8/16/28/40-second reboot codes are diagnostics ONLY. Never flash any partition.' -ForegroundColor Yellow
$ack = Read-Host 'Type BOOT to permit a single temporary fastboot boot'
if ($ack -cne 'BOOT') { Write-Host 'Cancelled.'; exit 0 }
& $fb.Source boot $abs
exit $LASTEXITCODE
