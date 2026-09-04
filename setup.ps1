param(
    [switch]$SkipMfa,
    [switch]$SkipModels
)

$ErrorActionPreference = "Stop"
$ProjectRoot = $PSScriptRoot
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$RuntimeRoot = Join-Path $ProjectRoot ".runtime"
$MiniforgeRoot = Join-Path $RuntimeRoot "miniforge"
$MfaPrefix = Join-Path $RuntimeRoot "mfa"
$ModelRoot = Join-Path $ProjectRoot ".models\mfa"

function Assert-ExternalCommand {
    param([string]$Step)
    if ($LASTEXITCODE -ne 0) {
        throw "$Step failed with exit code $LASTEXITCODE."
    }
}

Write-Host "[1/4] Preparing the desktop Python environment..."
if (-not (Test-Path -LiteralPath $VenvPython)) {
    $PythonCommand = Get-Command py -ErrorAction SilentlyContinue
    if ($PythonCommand) {
        & py -3.12 -m venv (Join-Path $ProjectRoot ".venv")
    } else {
        & python -m venv (Join-Path $ProjectRoot ".venv")
    }
    Assert-ExternalCommand "Python virtual environment creation"
}
& $VenvPython -m pip install --upgrade pip
Assert-ExternalCommand "pip upgrade"
& $VenvPython -m pip install -r (Join-Path $ProjectRoot "requirements.txt")
Assert-ExternalCommand "desktop dependency installation"

if ($SkipMfa) {
    Write-Host "MFA skipped. Full-word playback remains available; segmented timing is disabled."
    exit 0
}

New-Item -ItemType Directory -Force -Path $RuntimeRoot | Out-Null
New-Item -ItemType Directory -Force -Path $ModelRoot | Out-Null
$CondaExecutable = Join-Path $MiniforgeRoot "_conda.exe"
if (-not (Test-Path -LiteralPath $CondaExecutable)) {
    Write-Host "[2/4] Downloading project-local Miniforge (no system Python registration)..."
    $Installer = Join-Path $RuntimeRoot "Miniforge3-Windows-x86_64.exe"
    Invoke-WebRequest -Uri "https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-Windows-x86_64.exe" -OutFile $Installer
    $Arguments = @(
        "/InstallationType=JustMe",
        "/AddToPath=0",
        "/RegisterPython=0",
        "/NoRegistry=1",
        "/S",
        "/D=$MiniforgeRoot"
    )
    $Process = Start-Process -FilePath $Installer -ArgumentList $Arguments -Wait -PassThru -WindowStyle Hidden
    if ($Process.ExitCode -ne 0) {
        throw "Miniforge installation failed with exit code $($Process.ExitCode)."
    }
}

$MfaExecutable = Join-Path $MfaPrefix "Scripts\mfa.exe"
if (-not (Test-Path -LiteralPath $MfaExecutable)) {
    Write-Host "[3/4] Installing project-local Montreal Forced Aligner..."
    & $CondaExecutable create --yes --quiet --prefix $MfaPrefix --channel conda-forge "python=3.11" "montreal-forced-aligner>=3.4,<3.5" "kaldi=5.5.1172=cpu_*" "libblas=*=*openblas"
    Assert-ExternalCommand "MFA environment installation"
}

if (-not $SkipModels) {
    Write-Host "[4/4] Downloading US English ARPA acoustic, dictionary, and G2P models..."
    $env:MFA_ROOT_DIR = $ModelRoot
    $ModelKinds = @("acoustic", "dictionary", "g2p")
    foreach ($ModelKind in $ModelKinds) {
        & $CondaExecutable run --prefix $MfaPrefix --no-capture-output mfa model download $ModelKind english_us_arpa
        Assert-ExternalCommand "MFA model download for $ModelKind"
    }
}

Write-Host "Setup complete. Double-click run.bat to start."
