[CmdletBinding()]
param(
    [ValidateNotNullOrEmpty()]
    [string]$BaseUrl = "http://127.0.0.1:8000/",

    [string]$BrowserPath = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$Uri = [System.Uri]$BaseUrl
$AllowedHosts = @("127.0.0.1", "localhost", "::1")
if ($Uri.Scheme -cne "http" -or $AllowedHosts -notcontains $Uri.Host) {
    throw "Browser smoke accepts an HTTP loopback URL only: 127.0.0.1, localhost, or ::1."
}

if ([string]::IsNullOrWhiteSpace($BrowserPath)) {
    $Candidates = @(
        (Join-Path $env:ProgramFiles "Google\Chrome\Application\chrome.exe"),
        (Join-Path ${env:ProgramFiles(x86)} "Microsoft\Edge\Application\msedge.exe"),
        (Join-Path $env:ProgramFiles "Microsoft\Edge\Application\msedge.exe")
    )
    $BrowserPath = $Candidates |
        Where-Object { $_ -and (Test-Path -LiteralPath $_ -PathType Leaf) } |
        Select-Object -First 1
}
if ([string]::IsNullOrWhiteSpace($BrowserPath) -or
    -not (Test-Path -LiteralPath $BrowserPath -PathType Leaf)) {
    throw "Chromium browser not found. Install Chrome/Edge or pass -BrowserPath <chrome.exe|msedge.exe>."
}

$HealthUrl = [System.Uri]::new($Uri, "health/").AbsoluteUri
$Health = Invoke-RestMethod -Uri $HealthUrl -Method Get -TimeoutSec 20
if ($Health.status -cne "ok") {
    throw "Studio health endpoint did not return status=ok: $HealthUrl"
}
$RootResponse = Invoke-WebRequest -UseBasicParsing -Uri $Uri.AbsoluteUri -TimeoutSec 20
if ($RootResponse.StatusCode -ne 200) {
    throw "Studio root returned HTTP $($RootResponse.StatusCode): $($Uri.AbsoluteUri)"
}

$Scratch = Join-Path ([System.IO.Path]::GetTempPath()) (
    "conflict-studio-owner-browser-" + [System.Guid]::NewGuid().ToString("N")
)
[System.IO.Directory]::CreateDirectory($Scratch) | Out-Null
$Profile = Join-Path $Scratch "profile"
$DomPath = Join-Path $Scratch "dom.html"
$ErrorPath = Join-Path $Scratch "browser.stderr.log"

try {
    $BrowserArguments = @(
        "--headless=new",
        "--disable-background-networking",
        "--disable-component-update",
        "--disable-default-apps",
        "--disable-extensions",
        "--disable-gpu",
        "--disable-sync",
        "--no-default-browser-check",
        "--no-first-run",
        "--user-data-dir=`"$Profile`"",
        "--dump-dom",
        $Uri.AbsoluteUri
    )
    $Process = Start-Process -FilePath $BrowserPath -ArgumentList $BrowserArguments `
        -RedirectStandardOutput $DomPath -RedirectStandardError $ErrorPath `
        -WindowStyle Hidden -Wait -PassThru
    if ($Process.ExitCode -ne 0) {
        $Details = Get-Content -LiteralPath $ErrorPath -Raw -ErrorAction SilentlyContinue
        throw "Browser smoke exited with code $($Process.ExitCode). $Details"
    }
    $Dom = Get-Content -LiteralPath $DomPath -Raw -Encoding UTF8
    if ($Dom -notmatch 'id="studio-workspace"' -or
        $Dom -notmatch 'ConflictAnalysis Studio') {
        throw "Browser loaded the URL but the Studio workspace was not rendered."
    }

    [PSCustomObject]@{
        status = "PASS"
        base_url = $Uri.AbsoluteUri
        health = $Health.status
        root_status = $RootResponse.StatusCode
        browser = [System.IO.Path]::GetFullPath($BrowserPath)
        studio_workspace = $true
    } | ConvertTo-Json -Compress
}
finally {
    if (Test-Path -LiteralPath $Scratch) {
        Remove-Item -LiteralPath $Scratch -Recurse -Force
    }
}
