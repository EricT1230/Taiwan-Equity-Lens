$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$repoRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $repoRoot ".venv\Scripts\python.exe"
$downloadDirectory = Join-Path $repoRoot ".tmp-fubon-sdk"
$bootstrapDirectory = Join-Path $downloadDirectory "bootstrap"
$dependencyDirectory = Join-Path $downloadDirectory "locked-dependencies"
$dependencyLock = Join-Path $PSScriptRoot "fubon-dependencies-py310-win_amd64.lock"
$archivePath = Join-Path $downloadDirectory "fubon_neo-2.2.8-win64.zip"
$wheelPath = Join-Path $downloadDirectory "fubon_neo-2.2.8-cp37-abi3-win_amd64.whl"
$downloadUrl = "https://www.fbs.com.tw/TradeAPI_SDK/fubon_binary/fubon_neo-2.2.8-cp37-abi3-win_amd64.zip"
$archiveSha256 = "E0058535D3F69C333E636DE3EAE97F463B74BC91FB1AB5D7518C002630FE7D53"
$wheelSha256 = "EF4A65CCAC90A9ED88076752CF746F2B68C8775507E879D5A8514BD819A0D56F"
$pipWheel = Join-Path $bootstrapDirectory "pip-26.1.2-py3-none-any.whl"
$pipWheelSha256 = "382FF9F685EE3BC25864F820AA50505825F10F5458FFFF07E30A6D96E5715CAB"

if (-not (Test-Path -LiteralPath $pythonPath -PathType Leaf)) {
    throw "Missing project Python at .venv\Scripts\python.exe. Create a 64-bit CPython 3.10 virtual environment first."
}

& $pythonPath -c "import os, struct, sys; assert sys.version_info[:2] == (3, 10), 'The verified dependency lock requires project Python 3.10'; assert os.name == 'nt' and struct.calcsize('P') * 8 == 64, 'Fubon SDK package requires 64-bit Windows'"
if ($LASTEXITCODE -ne 0) {
    throw "The project virtual environment must use 64-bit Windows CPython 3.10 for the verified Fubon lock."
}

New-Item -ItemType Directory -Path $downloadDirectory -Force | Out-Null
New-Item -ItemType Directory -Path $bootstrapDirectory -Force | Out-Null
New-Item -ItemType Directory -Path $dependencyDirectory -Force | Out-Null
if (-not (Test-Path -LiteralPath $archivePath -PathType Leaf)) {
    $partialPath = "$archivePath.download"
    Invoke-WebRequest -Uri $downloadUrl -OutFile $partialPath -UseBasicParsing
    $partialHash = (Get-FileHash -LiteralPath $partialPath -Algorithm SHA256).Hash
    if ($partialHash -ne $archiveSha256) {
        throw "Downloaded Fubon SDK archive failed SHA-256 verification."
    }
    Move-Item -LiteralPath $partialPath -Destination $archivePath
}

$actualArchiveHash = (Get-FileHash -LiteralPath $archivePath -Algorithm SHA256).Hash
if ($actualArchiveHash -ne $archiveSha256) {
    throw "Existing Fubon SDK archive failed SHA-256 verification. Remove only .tmp-fubon-sdk\fubon_neo-2.2.8-win64.zip and retry."
}

if (-not (Test-Path -LiteralPath $wheelPath -PathType Leaf)) {
    Expand-Archive -LiteralPath $archivePath -DestinationPath $downloadDirectory -Force
}
$actualWheelHash = (Get-FileHash -LiteralPath $wheelPath -Algorithm SHA256).Hash
if ($actualWheelHash -ne $wheelSha256) {
    throw "Extracted Fubon SDK wheel failed SHA-256 verification."
}

& $pythonPath -m ensurepip --upgrade
if ($LASTEXITCODE -ne 0) {
    throw "Unable to bootstrap pip in the project virtual environment."
}
& $pythonPath -m pip download --disable-pip-version-check --only-binary=:all: --no-deps --dest $bootstrapDirectory "pip==26.1.2"
if ($LASTEXITCODE -ne 0) {
    throw "Unable to download the pinned pip bootstrap wheel."
}
$actualPipWheelHash = (Get-FileHash -LiteralPath $pipWheel -Algorithm SHA256).Hash
if ($actualPipWheelHash -ne $pipWheelSha256) {
    throw "Pinned pip bootstrap wheel failed SHA-256 verification."
}
& $pythonPath -m pip install --disable-pip-version-check --force-reinstall --no-index --no-deps $pipWheel
if ($LASTEXITCODE -ne 0) {
    throw "Unable to install the verified pip bootstrap wheel."
}
& $pythonPath -c "from importlib.metadata import version; assert version('pip') == '26.1.2'"
if ($LASTEXITCODE -ne 0) {
    throw "Verified pip bootstrap version check failed."
}

& $pythonPath -m pip download --disable-pip-version-check --only-binary=:all: --require-hashes --dest $dependencyDirectory --requirement $dependencyLock
if ($LASTEXITCODE -ne 0) {
    throw "Unable to download the hash-locked Fubon runtime dependencies."
}

$expectedDependencies = [ordered]@{
    "certifi-2026.7.22-py3-none-any.whl" = "62F22742B58A1A33014A2B6B706588A8D7E2A88AE7BD1A6EBE8C992928483775"
    "charset_normalizer-3.4.9-cp310-cp310-win_amd64.whl" = "8C041122946B7BA21BB32C45B1AA57B1BE35527690AEB3C5C234521085632EEE"
    "fugle_marketdata-2.4.1-py3-none-any.whl" = "33EBAFBCF49F614D6B699AA54C9E36C6A9882A017300333DCBDE065AE9236832"
    "idna-3.18-py3-none-any.whl" = "7F952CBE720B688055E3F87DE14F5C3E5FDAA8BC3928985C4077CA689DE849A2"
    "orjson-3.11.9-cp310-cp310-win_amd64.whl" = "8697AB6A080A5C46EDAAD50E2BC5BD8C7CA5C66442D24104FA44EC74910A8244"
    "pyee-9.1.1-py2.py3-none-any.whl" = "F4A9853503D2F5A69D4350B54BA70841EBC535C53EBFAAA40C0FB47E63E78B3E"
    "requests-2.34.2-py3-none-any.whl" = "2A0D60C172F83AC6AB31E4554906C0F3B3588D37B5CB939B1C061F4907E278E0"
    "typing_extensions-4.16.0-py3-none-any.whl" = "481CAA481374E813C1B176ADA14E97F1F67A4539CE9CFEB3F350D78D6370C2E8"
    "urllib3-2.7.0-py3-none-any.whl" = "9FB4C81EBBB1CE9531CCE37674BBC6F1360472BC18CA9A553EDE278EF7276897"
    "websocket_client-1.9.0-py3-none-any.whl" = "AF248A825037EF591EFBF6ED20CC5FAA03D3B47B9E5A2230A529EEEE1C1FC3EF"
}
foreach ($entry in $expectedDependencies.GetEnumerator()) {
    $artifactPath = Join-Path $dependencyDirectory $entry.Key
    if (-not (Test-Path -LiteralPath $artifactPath -PathType Leaf)) {
        throw "Missing hash-locked dependency artifact: $($entry.Key)"
    }
    $artifactHash = (Get-FileHash -LiteralPath $artifactPath -Algorithm SHA256).Hash
    if ($artifactHash -ne $entry.Value) {
        throw "Hash-locked dependency failed SHA-256 verification: $($entry.Key)"
    }
}

& $pythonPath -m pip install --disable-pip-version-check --force-reinstall --no-index --find-links $dependencyDirectory --require-hashes --requirement $dependencyLock
if ($LASTEXITCODE -ne 0) {
    throw "Unable to install the verified Fubon runtime dependencies."
}
& $pythonPath -m pip install --disable-pip-version-check --force-reinstall --no-deps $wheelPath
if ($LASTEXITCODE -ne 0) {
    throw "Unable to install the pinned Fubon SDK into the project virtual environment."
}
& $pythonPath -m pip check
if ($LASTEXITCODE -ne 0) {
    throw "The installed Fubon dependency set is inconsistent."
}
& $pythonPath -c "from importlib.metadata import version; assert version('fubon-neo') == '2.2.8'; from fubon_neo.sdk import FubonSDK; print('Fubon Neo SDK 2.2.8 is ready in .venv')"
if ($LASTEXITCODE -ne 0) {
    throw "Fubon SDK import verification failed."
}
