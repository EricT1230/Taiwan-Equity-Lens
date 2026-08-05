param(
    [string]$ScanDir = "demo-dist",
    [string]$BindAddress = "127.0.0.1",
    [ValidateRange(1, 65535)]
    [int]$Port = 8877,
    [switch]$Open
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$repoRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $repoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $pythonPath -PathType Leaf)) {
    throw "Missing project Python at .venv\Scripts\python.exe. Run scripts\install-fubon-sdk.ps1 first."
}

$arguments = @(
    "-m",
    "taiwan_stock_analysis.cli",
    "dashboard",
    "--scan-dir",
    $ScanDir,
    "--serve",
    "--host",
    $BindAddress,
    "--port",
    $Port.ToString()
)
if ($Open) {
    $arguments += "--open"
}

Push-Location $repoRoot
try {
    & $pythonPath @arguments
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
