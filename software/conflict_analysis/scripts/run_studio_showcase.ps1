[CmdletBinding()]
param(
    [ValidateNotNullOrEmpty()]
    [string]$ListenAddress = "127.0.0.1",

    [ValidateRange(1, 65535)]
    [int]$Port = 8000
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ProjectRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$RepositoryRoot = [System.IO.Path]::GetFullPath((Join-Path $ProjectRoot "..\.."))
$ProjectVenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$RepositoryVenvPython = Join-Path $RepositoryRoot ".venv\Scripts\python.exe"
$ManagePy = Join-Path $ProjectRoot "manage.py"

$PythonExecutable = $null
$PythonPrefixArguments = @()
$PythonSource = $null

if (Test-Path -LiteralPath $ProjectVenvPython -PathType Leaf) {
    $PythonExecutable = $ProjectVenvPython
    $PythonSource = "project virtual environment"
}
elseif (Test-Path -LiteralPath $RepositoryVenvPython -PathType Leaf) {
    $PythonExecutable = $RepositoryVenvPython
    $PythonSource = "repository virtual environment"
}
else {
    $PyLauncher = Get-Command "py.exe" -ErrorAction SilentlyContinue
    if ($null -eq $PyLauncher) {
        $PyLauncher = Get-Command "py" -ErrorAction SilentlyContinue
    }
    if ($null -eq $PyLauncher) {
        throw (
            "Python 3.12 was not found. Expected '{0}' or '{1}', " +
            "or the Windows Python launcher command 'py -3.12'."
        ) -f $ProjectVenvPython, $RepositoryVenvPython
    }
    $PythonExecutable = $PyLauncher.Source
    $PythonPrefixArguments = @("-3.12")
    $PythonSource = "Windows Python launcher (py -3.12)"
}

if (-not (Test-Path -LiteralPath $ManagePy -PathType Leaf)) {
    throw "Django entry point not found: '$ManagePy'."
}

& $PythonExecutable @PythonPrefixArguments -c (
    "import sys; assert sys.version_info[:2] == (3, 12), " +
    "f'Python 3.12 required, got {sys.version.split()[0]}'"
)
if ($LASTEXITCODE -ne 0) {
    throw "The selected $PythonSource is not Python 3.12."
}

& $PythonExecutable @PythonPrefixArguments -c "import django; print('Django', django.get_version())"
if ($LASTEXITCODE -ne 0) {
    throw (
        "The selected $PythonSource cannot import Django. From '$ProjectRoot', " +
        "install the development dependencies with: py -3.12 -m pip install -e `".[dev]`""
    )
}

$env:DJANGO_SETTINGS_MODULE = "conflict_analysis.studio_showcase_settings"
$env:DJANGO_DEBUG = "true"
$env:DJANGO_ALLOWED_HOSTS = "$ListenAddress,localhost,127.0.0.1,[::1]"
$env:DJANGO_SECRET_KEY = "showcase-session-only-not-for-production"
$env:USE_SQLITE = "true"
$env:PYTHONDONTWRITEBYTECODE = "1"
$env:PYTHONUNBUFFERED = "1"

$ShowcaseUrl = "http://${ListenAddress}:$Port/"
Write-Host "ConflictAnalysis Studio - research prototype" -ForegroundColor Cyan
Write-Host "Interpreter: $PythonSource"
Write-Host "Settings: $env:DJANGO_SETTINGS_MODULE"
Write-Host "Session data is not written to the Foundation ORM or production database." -ForegroundColor Yellow
Write-Host "Open: $ShowcaseUrl" -ForegroundColor Green
Write-Host "Press Ctrl+C to stop."

Push-Location $ProjectRoot
try {
    & $PythonExecutable @PythonPrefixArguments $ManagePy runserver "${ListenAddress}:$Port" `
        --settings conflict_analysis.studio_showcase_settings --noreload
    if ($LASTEXITCODE -ne 0) {
        throw "Studio showcase server exited with code $LASTEXITCODE."
    }
}
finally {
    Pop-Location
}
