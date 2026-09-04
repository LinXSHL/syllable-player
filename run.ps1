$ErrorActionPreference = "Stop"
$ProjectRoot = $PSScriptRoot
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $Python)) {
    throw "The app is not installed. Run setup.ps1 first."
}
Set-Location -LiteralPath $ProjectRoot
& $Python (Join-Path $ProjectRoot "main.py")
