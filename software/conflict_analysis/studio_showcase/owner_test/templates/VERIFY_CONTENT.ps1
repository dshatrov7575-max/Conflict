[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$Root = [System.IO.Path]::GetFullPath($PSScriptRoot)
$RootPrefix = $Root.TrimEnd(
    [System.IO.Path]::DirectorySeparatorChar,
    [System.IO.Path]::AltDirectorySeparatorChar
) + [System.IO.Path]::DirectorySeparatorChar
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
$ExpectedFiles = New-Object 'System.Collections.Generic.HashSet[string]' ([System.StringComparer]::Ordinal)
foreach ($Entry in $Manifest.files) {
    if (-not $ExpectedFiles.Add([string]$Entry.path)) {
        throw "Duplicate manifest path: $($Entry.path)"
    }
    $FullPath = [System.IO.Path]::GetFullPath((Join-Path $Root $Entry.path))
    if (-not $FullPath.StartsWith($RootPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
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

$AllowedMetadata = @("MANIFEST.json", "MANIFEST.sha256")
$ActualFiles = Get-ChildItem -LiteralPath $Root -Recurse -File | ForEach-Object {
    $_.FullName.Substring($RootPrefix.Length).Replace(
        [System.IO.Path]::DirectorySeparatorChar,
        [System.IO.Path]::AltDirectorySeparatorChar
    )
}
foreach ($RelativePath in $ActualFiles) {
    if ($AllowedMetadata -notcontains $RelativePath -and
        -not $ExpectedFiles.Contains($RelativePath)) {
        throw "Unexpected package file not covered by MANIFEST.json: $RelativePath"
    }
}
foreach ($MetadataPath in $AllowedMetadata) {
    if ($ActualFiles -notcontains $MetadataPath) {
        throw "Missing package metadata file: $MetadataPath"
    }
}

$ScreenshotRegisterPath = Join-Path $Root "screenshots\SHA256SUMS.txt"
$ScreenshotLines = @(Get-Content -LiteralPath $ScreenshotRegisterPath -Encoding ASCII)
if ($ScreenshotLines.Count -ne 6) {
    throw "Screenshot checksum register must contain exactly six entries."
}
foreach ($Line in $ScreenshotLines) {
    if ($Line -notmatch '^([0-9a-f]{64})\s{2}([^\\/:]+\.(png|jpg))$') {
        throw "Invalid screenshot checksum entry: $Line"
    }
    $ScreenshotPath = Join-Path (Join-Path $Root "screenshots") $Matches[2]
    if (-not (Test-Path -LiteralPath $ScreenshotPath -PathType Leaf)) {
        throw "Screenshot listed in checksum register is missing: $($Matches[2])"
    }
    $ScreenshotHash = (Get-FileHash -LiteralPath $ScreenshotPath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($ScreenshotHash -cne $Matches[1]) {
        throw "Screenshot SHA-256 mismatch: $($Matches[2])"
    }
}

Write-Host "OWNER-TEST content verified: $($Manifest.files.Count) files; HEAD $($Manifest.head); TREE $($Manifest.tree)" -ForegroundColor Green
