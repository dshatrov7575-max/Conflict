[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateScript({ Test-Path -LiteralPath $_ -PathType Leaf })]
    [string]$ZipPath,

    [Parameter(Mandatory = $true)]
    [ValidateScript({ Test-Path -LiteralPath $_ -PathType Leaf })]
    [string]$Sha256RecordPath,

    [Parameter(Mandatory = $true)]
    [ValidateScript({ Test-Path -LiteralPath $_ -PathType Leaf })]
    [string]$ManifestSha256RecordPath,

    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[0-9a-f]{40}$')]
    [string]$Head,

    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[0-9a-f]{40}$')]
    [string]$Tree,

    [ValidateRange(0, 65535)]
    [int]$Port = 0,

    [string]$PythonCommand = "",

    [string]$BrowserPath = "",

    [string]$EvidencePath = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Get-FreeLoopbackPort {
    $Listener = [System.Net.Sockets.TcpListener]::new(
        [System.Net.IPAddress]::Loopback,
        0
    )
    try {
        $Listener.Start()
        return ([System.Net.IPEndPoint]$Listener.LocalEndpoint).Port
    }
    finally {
        $Listener.Stop()
    }
}

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

function Read-Sha256Record {
    param(
        [Parameter(Mandatory = $true)][string]$LiteralPath,
        [Parameter(Mandatory = $true)][string]$ExpectedRecordedName,
        [Parameter(Mandatory = $true)][string]$Label
    )

    $Record = (Get-Content -LiteralPath $LiteralPath -Raw -Encoding ASCII).Trim()
    if ($Record -notmatch '^([0-9a-fA-F]{64})\s{2}([^\r\n]+)$') {
        throw "Invalid $Label SHA-256 record format: $LiteralPath"
    }
    $Hash = $Matches[1].ToLowerInvariant()
    $RecordedName = $Matches[2]
    if ($RecordedName -cne $ExpectedRecordedName) {
        throw (
            "$Label SHA-256 record names '$RecordedName', not " +
            "'$ExpectedRecordedName'."
        )
    }
    return [pscustomobject]@{
        Hash = $Hash
        RecordedName = $RecordedName
    }
}

function Expand-SafeOwnerArchive {
    param(
        [Parameter(Mandatory = $true)][string]$ArchivePath,
        [Parameter(Mandatory = $true)][string]$DestinationPath
    )

    Add-Type -AssemblyName System.IO.Compression
    $ArchiveRootName = "ConflictAnalysis-Studio-OWNER-TEST"
    $PackageRoot = Join-Path $DestinationPath $ArchiveRootName
    $PackageRootFull = [System.IO.Path]::GetFullPath($PackageRoot)
    $PackageRootPrefix = $PackageRootFull.TrimEnd(
        [System.IO.Path]::DirectorySeparatorChar,
        [System.IO.Path]::AltDirectorySeparatorChar
    ) + [System.IO.Path]::DirectorySeparatorChar
    $ExactPaths = New-Object 'System.Collections.Generic.HashSet[string]' ([System.StringComparer]::Ordinal)
    $CaseInsensitivePaths = New-Object 'System.Collections.Generic.HashSet[string]' ([System.StringComparer]::OrdinalIgnoreCase)
    $ValidatedEntries = New-Object 'System.Collections.Generic.List[object]'
    $ArchiveStream = [System.IO.File]::Open(
        $ArchivePath,
        [System.IO.FileMode]::Open,
        [System.IO.FileAccess]::Read,
        [System.IO.FileShare]::Read
    )
    $Archive = $null
    try {
        $Archive = New-Object System.IO.Compression.ZipArchive(
            $ArchiveStream,
            [System.IO.Compression.ZipArchiveMode]::Read,
            $false
        )
        foreach ($Entry in $Archive.Entries) {
            $EntryName = [string]$Entry.FullName
            $Segments = @($EntryName.Split([char]'/', [System.StringSplitOptions]::None))
            if ([string]::IsNullOrWhiteSpace($EntryName) -or
                $EntryName.Contains("\") -or
                $EntryName.Contains(":") -or
                $EntryName.StartsWith("/") -or
                $EntryName -match '^[A-Za-z]:' -or
                $Segments.Count -lt 2 -or
                $Segments[0] -cne $ArchiveRootName -or
                $Segments -contains "" -or
                $Segments -contains "." -or
                $Segments -contains ".." -or
                [string]::IsNullOrEmpty([string]$Entry.Name)) {
                throw "Unsafe or non-normalized ZIP entry: $EntryName"
            }
            foreach ($Segment in $Segments) {
                if ($Segment.EndsWith(".") -or $Segment.EndsWith(" ") -or
                    $Segment -match '^(?i:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(\..*)?$') {
                    throw "Unsafe Windows ZIP entry segment in: $EntryName"
                }
            }
            $RelativePath = [string]::Join("/", $Segments[1..($Segments.Count - 1)])
            if (-not $ExactPaths.Add($RelativePath)) {
                throw "Duplicate ZIP entry path: $RelativePath"
            }
            if (-not $CaseInsensitivePaths.Add($RelativePath)) {
                throw "Case-colliding ZIP entry path: $RelativePath"
            }
            $PlatformRelativePath = $RelativePath.Replace(
                [System.IO.Path]::AltDirectorySeparatorChar,
                [System.IO.Path]::DirectorySeparatorChar
            )
            $OutputPath = [System.IO.Path]::GetFullPath(
                (Join-Path $PackageRootFull $PlatformRelativePath)
            )
            if (-not $OutputPath.StartsWith(
                $PackageRootPrefix,
                [System.StringComparison]::OrdinalIgnoreCase
            )) {
                throw "ZIP entry escapes extraction root: $EntryName"
            }
            $ValidatedEntries.Add([pscustomobject]@{
                Entry = $Entry
                OutputPath = $OutputPath
            })
        }

        if ($ValidatedEntries.Count -eq 0) {
            throw "OWNER-TEST ZIP contains no payload entries."
        }

        [System.IO.Directory]::CreateDirectory($PackageRootFull) | Out-Null
        foreach ($Validated in $ValidatedEntries) {
            $ParentDirectory = [System.IO.Path]::GetDirectoryName(
                $Validated.OutputPath
            )
            [System.IO.Directory]::CreateDirectory($ParentDirectory) | Out-Null
            $InputStream = $Validated.Entry.Open()
            $OutputStream = [System.IO.File]::Open(
                $Validated.OutputPath,
                [System.IO.FileMode]::CreateNew,
                [System.IO.FileAccess]::Write,
                [System.IO.FileShare]::None
            )
            try {
                $InputStream.CopyTo($OutputStream)
            }
            finally {
                $OutputStream.Dispose()
                $InputStream.Dispose()
            }
        }
    }
    finally {
        if ($null -ne $Archive) {
            $Archive.Dispose()
        }
        $ArchiveStream.Dispose()
    }
    return $PackageRootFull
}

function Test-HealthUnavailable {
    param([Parameter(Mandatory = $true)][string]$HealthUrl)

    try {
        Invoke-WebRequest -UseBasicParsing -Uri $HealthUrl -TimeoutSec 1 | Out-Null
        return $false
    }
    catch {
        return $true
    }
}

$ResolvedZip = [System.IO.Path]::GetFullPath($ZipPath)
$ResolvedHashRecord = [System.IO.Path]::GetFullPath($Sha256RecordPath)
$ResolvedManifestHashRecord = [System.IO.Path]::GetFullPath(
    $ManifestSha256RecordPath
)
$ExpectedHashRecordPath = "$ResolvedZip.sha256"
$ExpectedManifestHashRecordPath = "$ResolvedZip.manifest.sha256"
if (-not $ResolvedHashRecord.Equals(
    $ExpectedHashRecordPath,
    [System.StringComparison]::OrdinalIgnoreCase
)) {
    throw "Package SHA-256 record must be adjacent at: $ExpectedHashRecordPath"
}
if (-not $ResolvedManifestHashRecord.Equals(
    $ExpectedManifestHashRecordPath,
    [System.StringComparison]::OrdinalIgnoreCase
)) {
    throw (
        "Manifest SHA-256 record must be adjacent at: " +
        $ExpectedManifestHashRecordPath
    )
}
$ZipHashRecord = Read-Sha256Record -LiteralPath $ResolvedHashRecord `
    -ExpectedRecordedName ([System.IO.Path]::GetFileName($ResolvedZip)) `
    -Label "package"
$ExpectedZipHash = $ZipHashRecord.Hash
$ActualZipHash = Get-Sha256Hex -LiteralPath $ResolvedZip
if ($ActualZipHash -cne $ExpectedZipHash) {
    throw "OWNER-TEST ZIP SHA-256 mismatch. Expected $ExpectedZipHash, got $ActualZipHash."
}

if ($Port -eq 0) {
    $Port = Get-FreeLoopbackPort
}
$BaseUrl = "http://127.0.0.1:$Port/"
$HealthUrl = "${BaseUrl}health/"
$Scratch = Join-Path ([System.IO.Path]::GetTempPath()) (
    "conflict-studio-owner-clean-room-" + [System.Guid]::NewGuid().ToString("N")
)
$ExtractPath = Join-Path $Scratch "extracted"
$ServerOut = Join-Path $Scratch "server.stdout.log"
$ServerError = Join-Path $Scratch "server.stderr.log"
$ServerProcess = $null
$Result = $null
$Failure = $null
$FailureLogs = ""

try {
    [System.IO.Directory]::CreateDirectory($ExtractPath) | Out-Null
    $PackageRoot = Expand-SafeOwnerArchive -ArchivePath $ResolvedZip `
        -DestinationPath $ExtractPath

    $ManifestPath = Join-Path $PackageRoot "MANIFEST.json"
    if (-not (Test-Path -LiteralPath $ManifestPath -PathType Leaf)) {
        throw "MANIFEST.json not found in the OWNER-TEST ZIP."
    }
    $ManifestHashRecord = Read-Sha256Record `
        -LiteralPath $ResolvedManifestHashRecord `
        -ExpectedRecordedName "MANIFEST.json" -Label "manifest"
    $ExpectedManifestHash = $ManifestHashRecord.Hash
    $ActualManifestHash = Get-Sha256Hex -LiteralPath $ManifestPath
    if ($ActualManifestHash -cne $ExpectedManifestHash) {
        throw (
            "MANIFEST.json SHA-256 mismatch. Expected " +
            "$ExpectedManifestHash, got $ActualManifestHash."
        )
    }

    $Verifier = Join-Path $PackageRoot "VERIFY_CONTENT.ps1"
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $Verifier `
        -ManifestSha256RecordPath $ResolvedManifestHashRecord
    if ($LASTEXITCODE -ne 0) {
        throw "VERIFY_CONTENT.ps1 failed with exit code $LASTEXITCODE."
    }

    $Manifest = Get-Content -LiteralPath (Join-Path $PackageRoot "MANIFEST.json") `
        -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($Manifest.head -cne $Head -or $Manifest.tree -cne $Tree) {
        throw "Package revision mismatch: manifest $($Manifest.head)/$($Manifest.tree), expected $Head/$Tree."
    }
    if (-not $Manifest.build_environment.dependency_install_requires_network) {
        throw "Manifest must disclose that dependency installation requires network access."
    }

    if ([string]::IsNullOrWhiteSpace($PythonCommand)) {
        $PythonLauncher = Get-Command py.exe -ErrorAction SilentlyContinue
        if ($null -eq $PythonLauncher) {
            $PythonLauncher = Get-Command py -ErrorAction SilentlyContinue
        }
        if ($null -eq $PythonLauncher) {
            throw "Python 3.12 launcher not found. Install Python 3.12 or pass -PythonCommand <python.exe>."
        }
        $PythonExecutable = $PythonLauncher.Source
        $PythonPrefix = @("-3.12")
    }
    else {
        $PythonExecutable = [System.IO.Path]::GetFullPath($PythonCommand)
        if (-not (Test-Path -LiteralPath $PythonExecutable -PathType Leaf)) {
            throw "Python executable not found: $PythonExecutable"
        }
        $PythonPrefix = @()
    }

    $AppRoot = Join-Path $PackageRoot "app"
    $VenvRoot = Join-Path $AppRoot ".venv"
    & $PythonExecutable @PythonPrefix -m venv $VenvRoot
    if ($LASTEXITCODE -ne 0) {
        throw "Fresh clean-room virtual environment creation failed with exit code $LASTEXITCODE."
    }
    $VenvPython = Join-Path $VenvRoot "Scripts\python.exe"
    & $VenvPython -m pip install --disable-pip-version-check `
        -r (Join-Path $AppRoot "requirements-owner-test.txt")
    if ($LASTEXITCODE -ne 0) {
        throw (
            "OWNER-TEST dependency installation failed with exit code $LASTEXITCODE. " +
            "This step requires PyPI network access unless the packages are cached."
        )
    }

    $Launcher = Join-Path $AppRoot "scripts\run_studio_showcase.ps1"
    $LauncherArguments = @(
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-File", "`"$Launcher`"",
        "-ListenAddress", "127.0.0.1",
        "-Port", [string]$Port
    )
    $ServerProcess = Start-Process -FilePath "powershell.exe" `
        -ArgumentList $LauncherArguments -RedirectStandardOutput $ServerOut `
        -RedirectStandardError $ServerError -WindowStyle Hidden -PassThru

    $Deadline = [DateTime]::UtcNow.AddSeconds(45)
    $Health = $null
    while ([DateTime]::UtcNow -lt $Deadline) {
        if ($ServerProcess.HasExited) {
            throw "OWNER-TEST launcher exited before health became ready (exit $($ServerProcess.ExitCode))."
        }
        try {
            $Health = Invoke-RestMethod -Uri $HealthUrl -Method Get -TimeoutSec 2
            if ($Health.status -ceq "ok") {
                break
            }
        }
        catch {
            Start-Sleep -Milliseconds 200
        }
    }
    if ($null -eq $Health -or $Health.status -cne "ok") {
        throw "OWNER-TEST /health/ did not become ready within 45 seconds: $HealthUrl"
    }
    $RootResponse = Invoke-WebRequest -UseBasicParsing -Uri $BaseUrl -TimeoutSec 20
    if ($RootResponse.StatusCode -ne 200 -or
        $RootResponse.Content -notmatch 'id="studio-workspace"') {
        throw "OWNER-TEST root HTTP/DOM smoke failed at $BaseUrl"
    }

    $BrowserSmoke = Join-Path $PackageRoot "RUN_BROWSER_SMOKE.ps1"
    $BrowserArguments = @(
        "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $BrowserSmoke,
        "-BaseUrl", $BaseUrl
    )
    if (-not [string]::IsNullOrWhiteSpace($BrowserPath)) {
        $BrowserArguments += @("-BrowserPath", [System.IO.Path]::GetFullPath($BrowserPath))
    }
    $BrowserEvidence = & powershell.exe @BrowserArguments
    if ($LASTEXITCODE -ne 0) {
        throw "RUN_BROWSER_SMOKE.ps1 failed with exit code $LASTEXITCODE."
    }

    $Result = [ordered]@{
        status = "PASS"
        head = $Head
        tree = $Tree
        zip_path = $ResolvedZip
        zip_sha256 = $ActualZipHash
        manifest_sha256 = $ActualManifestHash
        dependency_install_requires_network = $true
        fresh_temporary_directory = $Scratch
        manifest_verified = $true
        health = "PASS"
        root = "PASS"
        browser_smoke = ($BrowserEvidence -join [Environment]::NewLine)
        stop_no_orphan = $false
        cleanup = "PENDING"
    }
}
catch {
    $Failure = $_
}
finally {
    if ($null -ne $ServerProcess) {
        try {
            $ServerProcess.Refresh()
            if (-not $ServerProcess.HasExited) {
                & taskkill.exe /PID $ServerProcess.Id /T /F 2>&1 | Out-Null
                $ServerProcess.WaitForExit(10000) | Out-Null
            }
        }
        catch {
            if ($null -eq $Failure) {
                $Failure = $_
            }
        }
    }

    $StopDeadline = [DateTime]::UtcNow.AddSeconds(10)
    while ([DateTime]::UtcNow -lt $StopDeadline -and
        -not (Test-HealthUnavailable -HealthUrl $HealthUrl)) {
        Start-Sleep -Milliseconds 200
    }
    $LauncherGone = $true
    if ($null -ne $ServerProcess) {
        $ServerProcess.Refresh()
        $LauncherGone = $ServerProcess.HasExited
    }
    $Stopped = (Test-HealthUnavailable -HealthUrl $HealthUrl) -and $LauncherGone
    if ($null -ne $Result) {
        $Result.stop_no_orphan = $Stopped
    }
    elseif (-not $Stopped -and $null -eq $Failure) {
        $Failure = [System.Management.Automation.RuntimeException]::new(
            "Server health remains reachable after clean-room shutdown: $HealthUrl"
        )
    }

    if (Test-Path -LiteralPath $ServerOut) {
        $FailureLogs += Get-Content -LiteralPath $ServerOut -Raw -ErrorAction SilentlyContinue
    }
    if (Test-Path -LiteralPath $ServerError) {
        $FailureLogs += Get-Content -LiteralPath $ServerError -Raw -ErrorAction SilentlyContinue
    }
    if (Test-Path -LiteralPath $Scratch) {
        Remove-Item -LiteralPath $Scratch -Recurse -Force
    }
}

$Cleaned = -not (Test-Path -LiteralPath $Scratch)
if ($null -ne $Result) {
    $Result.cleanup = if ($Cleaned) { "PASS" } else { "FAIL" }
}
if ($null -ne $Failure) {
    throw "Clean-room OWNER-TEST gate failed: $($Failure.Exception.Message)`n$FailureLogs"
}
if (-not $Result.stop_no_orphan -or -not $Cleaned) {
    throw "Clean-room OWNER-TEST lifecycle gate failed: stop_no_orphan=$($Result.stop_no_orphan), cleanup=$Cleaned"
}

$ResultJson = $Result | ConvertTo-Json -Depth 5
if (-not [string]::IsNullOrWhiteSpace($EvidencePath)) {
    $ResolvedEvidencePath = [System.IO.Path]::GetFullPath($EvidencePath)
    $EvidenceDirectory = [System.IO.Path]::GetDirectoryName($ResolvedEvidencePath)
    if (-not [string]::IsNullOrWhiteSpace($EvidenceDirectory)) {
        [System.IO.Directory]::CreateDirectory($EvidenceDirectory) | Out-Null
    }
    [System.IO.File]::WriteAllText(
        $ResolvedEvidencePath,
        $ResultJson + [Environment]::NewLine,
        [System.Text.UTF8Encoding]::new($false)
    )
}
$ResultJson
