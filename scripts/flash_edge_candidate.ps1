param(
    [Parameter(Mandatory = $true)][string]$Port,
    [Parameter(Mandatory = $true)][string]$ArtifactDir
)

$ErrorActionPreference = "Stop"
$repository = Split-Path -Parent $PSScriptRoot
$artifact = (Resolve-Path -LiteralPath $ArtifactDir).Path
$firmware = Join-Path $repository "firmware\visualec_edge_espidf"
$python = Join-Path $repository "backend\.venv\Scripts\python.exe"

& $python (Join-Path $PSScriptRoot "verify_edge_artifact.py") $artifact
if ($LASTEXITCODE -ne 0) { throw "Candidate verification failed; nothing was flashed" }

$metadata = Get-Content -Raw -LiteralPath (Join-Path $artifact "metadata.json") | ConvertFrom-Json
$modelHash = $metadata.files.'visualec_pico.espdl'.sha256
$modelVersion = $metadata.artifact_version
$generatedDefaults = Join-Path $firmware "sdkconfig.artifact.generated"
[System.IO.File]::WriteAllText(
    $generatedDefaults,
    "CONFIG_VISUALEC_MODEL_SHA256=`"$modelHash`"`nCONFIG_VISUALEC_MODEL_VERSION=`"$modelVersion`"`n",
    [System.Text.UTF8Encoding]::new($false)
)
$env:VISUALEC_MODEL_ARTIFACT = Join-Path $artifact "visualec_pico.espdl"
$env:SDKCONFIG_DEFAULTS = "sdkconfig.defaults;sdkconfig.release;sdkconfig.artifact.generated"
Push-Location $firmware
try {
    idf.py set-target esp32s3
    idf.py build
    if ($LASTEXITCODE -ne 0) { throw "Firmware build failed; nothing was flashed" }
    idf.py -p $Port flash
    if ($LASTEXITCODE -ne 0) { throw "Firmware flash failed" }
} finally {
    Pop-Location
    if (Test-Path -LiteralPath $generatedDefaults) {
        Remove-Item -LiteralPath $generatedDefaults -Force
    }
}
