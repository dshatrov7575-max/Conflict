[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[0-9a-f]{40}$')]
    [string]$Head,

    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[0-9a-f]{40}$')]
    [string]$Tree,

    [Parameter(Mandatory = $true)]
    [ValidateNotNullOrEmpty()]
    [string]$OutputDirectory
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RepositoryRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\..\..\.."))
$ProjectPython = Join-Path $RepositoryRoot "software\conflict_analysis\.venv\Scripts\python.exe"
if (Test-Path -LiteralPath $ProjectPython -PathType Leaf) {
    $Python = $ProjectPython
    $Prefix = @()
}
else {
    $PythonCommand = Get-Command py.exe -ErrorAction SilentlyContinue
    if ($null -eq $PythonCommand) {
        $PythonCommand = Get-Command py -ErrorAction SilentlyContinue
    }
    if ($null -eq $PythonCommand) {
        throw "Python 3.12 not found; cannot build deterministic OWNER-TEST package."
    }
    $Python = $PythonCommand.Source
    $Prefix = @("-3.12")
}

& $Python @Prefix (Join-Path $PSScriptRoot "build_owner_test_package.py") `
    --repository-root $RepositoryRoot --head $Head --tree $Tree `
    --output-directory ([System.IO.Path]::GetFullPath($OutputDirectory))
if ($LASTEXITCODE -ne 0) {
    throw "OWNER-TEST package build failed with exit code $LASTEXITCODE."
}
