$ErrorActionPreference = "Stop"
$projRoot = Split-Path -Parent $PSScriptRoot
$py = if ($env:CP0_PYTHON) {
    $env:CP0_PYTHON
} elseif ($env:CONDA_PREFIX) {
    Join-Path $env:CONDA_PREFIX "python.exe"
} else {
    "python"
}
$czdevWin = Join-Path $PSScriptRoot "czdev_win.py"

Set-Location $projRoot

$env:GIT_CONFIG_COUNT = "2"
$env:GIT_CONFIG_KEY_0 = "http.proxy"
$env:GIT_CONFIG_VALUE_0 = ""
$env:GIT_CONFIG_KEY_1 = "https.proxy"
$env:GIT_CONFIG_VALUE_1 = ""

Write-Host "=== 1. Running Official CardputerZero Preflight & Store Policy Check ===" -ForegroundColor Cyan
& $py $czdevWin --preflight "dist\cp0-ngspice_0.2.0-1_arm64.deb"

$credPath = Join-Path $env:USERPROFILE ".czdev\credentials"
if (-not (Test-Path $credPath)) {
    Write-Host "`n=== 2. GitHub OAuth Device Login (czdev login) ===" -ForegroundColor Cyan
    & $py $czdevWin login
}

Write-Host "`n=== 3. Publishing dist\cp0-ngspice_0.2.0-1_arm64.deb to CardputerZero Store ===" -ForegroundColor Cyan
& $py $czdevWin publish --deb "dist\cp0-ngspice_0.2.0-1_arm64.deb"
