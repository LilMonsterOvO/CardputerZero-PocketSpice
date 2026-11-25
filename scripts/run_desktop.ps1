$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Py = if ($env:CP0_PYTHON) {
    $env:CP0_PYTHON
} elseif ($env:CONDA_PREFIX) {
    Join-Path $env:CONDA_PREFIX "python.exe"
} else {
    "python"
}
Push-Location $Root
try {
    $env:CP0_WINDOWED = "1"
    & $Py -m cp0_ngspice.ui.app
} finally {
    Pop-Location
}
