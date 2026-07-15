param(
  [int]$Port = 8795,
  [switch]$NoOpen
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Page = "marketing_decision_tool.html"
$Url = "http://127.0.0.1:$Port/$Page"

$pythonCandidates = @(
  "C:\Users\sflem\AppData\Local\Programs\Python\Python312\python.exe",
  "python",
  "py"
)

$python = $null
foreach ($candidate in $pythonCandidates) {
  try {
    $cmd = Get-Command $candidate -ErrorAction Stop
    $python = $cmd.Source
    break
  } catch {}
}

if (-not $python) {
  throw "Python was not found. Install Python or add it to PATH, then rerun this launcher."
}

$existing = Get-NetTCPConnection -LocalAddress 127.0.0.1 -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if (-not $existing) {
  $args = @("-m", "http.server", "$Port", "--bind", "127.0.0.1", "--directory", $Root)
  Start-Process -FilePath $python -ArgumentList $args -WindowStyle Hidden | Out-Null
  Start-Sleep -Seconds 2
}

if (-not $NoOpen) {
  Start-Process $Url | Out-Null
}

Write-Host "Lumina Marketing Decision Workbench is available at $Url"
