[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$Root = [System.IO.Path]::GetFullPath($PSScriptRoot)
$ManifestPath = Join-Path $Root "MANIFEST.json"
$ManifestHashPath = Join-Path $Root "MANIFEST.sha256"

if (-not (Test-Path -LiteralPath $ManifestPath -PathType Leaf)) {
    throw "MANIFEST.json not found. Re-extract the OWNER-TEST ZIP."
}

$ExpectedManifestHash = ((Get-Content -LiteralPath $ManifestHashPath -Raw) -split '\s+')[0].ToLowerInvariant()
$ActualManifestHash = (Get-FileHash -LiteralPath $ManifestPath -Algorithm SHA256).Hash.ToLowerInvariant()
if ($ExpectedManifestHash -cne $ActualManifestHash) {
    throw "MANIFEST.json SHA-256 mismatch. Do not run this package."
}

$Manifest = Get-Content -LiteralPath $ManifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
foreach ($Entry in $Manifest.files) {
    $FullPath = [System.IO.Path]::GetFullPath((Join-Path $Root $Entry.path))
    if (-not $FullPath.StartsWith($Root, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Unsafe manifest path: $($Entry.path)"
    }
    if (-not (Test-Path -LiteralPath $FullPath -PathType Leaf)) {
        throw "Missing package file: $($Entry.path)"
    }
    $Actual = (Get-FileHash -LiteralPath $FullPath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($Actual -cne $Entry.sha256.ToLowerInvariant()) {
        throw "SHA-256 mismatch: $($Entry.path)"
    }
}

Write-Host "OWNER-TEST content verified: $($Manifest.files.Count) files; HEAD $($Manifest.head); TREE $($Manifest.tree)" -ForegroundColor Green
