[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateScript({ Test-Path -LiteralPath $_ -PathType Leaf })]
    [string]$ManifestSha256RecordPath
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$Root = [System.IO.Path]::GetFullPath($PSScriptRoot)
$RootPrefix = $Root.TrimEnd(
    [System.IO.Path]::DirectorySeparatorChar,
    [System.IO.Path]::AltDirectorySeparatorChar
) + [System.IO.Path]::DirectorySeparatorChar
$ManifestPath = Join-Path $Root "MANIFEST.json"
$ResolvedManifestHashRecord = [System.IO.Path]::GetFullPath(
    $ManifestSha256RecordPath
)

function Get-Sha256Hex {
    param([Parameter(Mandatory = $true)][string]$LiteralPath)

    $Stream = [System.IO.File]::OpenRead([System.IO.Path]::GetFullPath($LiteralPath))
    $Hasher = [System.Security.Cryptography.SHA256]::Create()
    try {
        return ([System.BitConverter]::ToString($Hasher.ComputeHash($Stream))).Replace(
            "-",
            ""
        ).ToLowerInvariant()
    }
    finally {
        $Hasher.Dispose()
        $Stream.Dispose()
    }
}

if (-not (Test-Path -LiteralPath $ManifestPath -PathType Leaf)) {
    throw "MANIFEST.json not found. Re-extract the OWNER-TEST ZIP."
}

$ManifestHashRecord = (
    Get-Content -LiteralPath $ResolvedManifestHashRecord -Raw -Encoding ASCII
).Trim()
if ($ManifestHashRecord -notmatch '^([0-9a-fA-F]{64})\s{2}MANIFEST\.json$') {
    throw "Invalid MANIFEST.json SHA-256 record format: $ResolvedManifestHashRecord"
}
$ExpectedManifestHash = $Matches[1].ToLowerInvariant()
$ActualManifestHash = Get-Sha256Hex -LiteralPath $ManifestPath
if ($ExpectedManifestHash -cne $ActualManifestHash) {
    throw "MANIFEST.json SHA-256 mismatch. Do not run this package."
}

$Manifest = Get-Content -LiteralPath $ManifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
$ExpectedManifestRecordName = [string]$Manifest.manifest_sha256_record
if ([System.IO.Path]::GetFileName($ResolvedManifestHashRecord) -cne
    $ExpectedManifestRecordName) {
    throw (
        "Manifest SHA-256 record filename mismatch: expected " +
        "$ExpectedManifestRecordName."
    )
}
$ExpectedFiles = New-Object 'System.Collections.Generic.HashSet[string]' ([System.StringComparer]::Ordinal)
$ExpectedFilesCaseInsensitive = New-Object 'System.Collections.Generic.HashSet[string]' ([System.StringComparer]::OrdinalIgnoreCase)
$ManifestPaths = @()
foreach ($Entry in @($Manifest.files)) {
    foreach ($RequiredProperty in @("path", "size_bytes", "sha256")) {
        if ($null -eq $Entry.PSObject.Properties[$RequiredProperty]) {
            throw "Manifest entry is missing required property '$RequiredProperty'."
        }
    }
    $EntryPath = [string]$Entry.path
    if ([string]::IsNullOrWhiteSpace($EntryPath) -or
        $EntryPath.Contains("\") -or
        $EntryPath.StartsWith("/") -or
        $EntryPath -match '^[A-Za-z]:' -or
        $EntryPath.Split('/') -contains "" -or
        $EntryPath.Split('/') -contains "." -or
        $EntryPath.Split('/') -contains "..") {
        throw "Unsafe or non-normalized manifest path: $EntryPath"
    }
    if ($EntryPath -ceq "MANIFEST.json") {
        throw "MANIFEST.json must not hash itself."
    }
    if (-not $ExpectedFiles.Add($EntryPath)) {
        throw "Duplicate manifest path: $EntryPath"
    }
    if (-not $ExpectedFilesCaseInsensitive.Add($EntryPath)) {
        throw "Case-colliding manifest path: $EntryPath"
    }
    $ManifestPaths += $EntryPath
    $FullPath = [System.IO.Path]::GetFullPath((Join-Path $Root $EntryPath))
    if (-not $FullPath.StartsWith($RootPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Unsafe manifest path: $EntryPath"
    }
    if (-not (Test-Path -LiteralPath $FullPath -PathType Leaf)) {
        throw "Missing package file: $EntryPath"
    }
    $DeclaredSize = 0L
    if (-not [long]::TryParse(
        [string]$Entry.size_bytes,
        [System.Globalization.NumberStyles]::None,
        [System.Globalization.CultureInfo]::InvariantCulture,
        [ref]$DeclaredSize
    ) -or $DeclaredSize -lt 0) {
        throw "Invalid size_bytes for manifest path: $EntryPath"
    }
    $ActualSize = (Get-Item -LiteralPath $FullPath).Length
    if ($ActualSize -ne $DeclaredSize) {
        throw "Size mismatch: $EntryPath"
    }
    $ExpectedHash = [string]$Entry.sha256
    if ($ExpectedHash -cnotmatch '^[0-9a-f]{64}$') {
        throw "Invalid SHA-256 for manifest path: $EntryPath"
    }
    $Actual = Get-Sha256Hex -LiteralPath $FullPath
    if ($Actual -cne $ExpectedHash) {
        throw "SHA-256 mismatch: $EntryPath"
    }
}

$SortedManifestPaths = @($ManifestPaths)
[Array]::Sort($SortedManifestPaths, [System.StringComparer]::Ordinal)
if (($ManifestPaths -join "`n") -cne ($SortedManifestPaths -join "`n")) {
    throw "Manifest paths must be in sorted normalized relative-path order."
}

$ActualFiles = @(Get-ChildItem -LiteralPath $Root -Recurse -File | ForEach-Object {
    $_.FullName.Substring($RootPrefix.Length).Replace(
        [System.IO.Path]::DirectorySeparatorChar,
        [System.IO.Path]::AltDirectorySeparatorChar
    )
})
$ActualFileSet = New-Object 'System.Collections.Generic.HashSet[string]' ([System.StringComparer]::Ordinal)
foreach ($RelativePath in $ActualFiles) {
    if (-not $ActualFileSet.Add($RelativePath)) {
        throw "Duplicate extracted package file: $RelativePath"
    }
    if ($RelativePath -cne "MANIFEST.json" -and -not $ExpectedFiles.Contains($RelativePath)) {
        throw "Unexpected package file not covered by MANIFEST.json: $RelativePath"
    }
}
if (-not $ActualFileSet.Contains("MANIFEST.json")) {
    throw "Missing package metadata file: MANIFEST.json"
}
foreach ($ExpectedPath in $ExpectedFiles) {
    if (-not $ActualFileSet.Contains($ExpectedPath)) {
        throw "Missing package file: $ExpectedPath"
    }
}
if ($ActualFileSet.Count -ne ($ExpectedFiles.Count + 1)) {
    throw "Actual package file set does not exactly match MANIFEST.json."
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
    $ScreenshotHash = Get-Sha256Hex -LiteralPath $ScreenshotPath
    if ($ScreenshotHash -cne $Matches[1]) {
        throw "Screenshot SHA-256 mismatch: $($Matches[2])"
    }
}

Write-Host "OWNER-TEST content verified: $($Manifest.files.Count) files; HEAD $($Manifest.head); TREE $($Manifest.tree)" -ForegroundColor Green
