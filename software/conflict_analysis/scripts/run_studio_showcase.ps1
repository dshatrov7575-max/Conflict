[CmdletBinding()]
param(
    [ValidateNotNullOrEmpty()]
    [string]$ListenAddress = "127.0.0.1",

    [ValidateRange(1, 65535)]
    [int]$Port = 8000
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Resolve-StudioShowcaseLoopbackEndpoint {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [ValidateNotNullOrEmpty()]
        [string]$Address
    )

    $Candidate = $Address.Trim().ToLowerInvariant()
    switch ($Candidate) {
        "127.0.0.1" {
            return [PSCustomObject]@{
                BindAddress = "127.0.0.1"
                SocketAddress = [System.Net.IPAddress]::Loopback
                UrlHost = "127.0.0.1"
            }
        }
        "localhost" {
            # Bind localhost deterministically to IPv4 loopback. The browser may
            # still use the familiar localhost URL.
            return [PSCustomObject]@{
                BindAddress = "127.0.0.1"
                SocketAddress = [System.Net.IPAddress]::Loopback
                UrlHost = "localhost"
            }
        }
        "::1" {
            if (-not [System.Net.Sockets.Socket]::OSSupportsIPv6) {
                throw "IPv6 loopback (::1) is not supported on this computer. Use 127.0.0.1 or localhost."
            }
            return [PSCustomObject]@{
                BindAddress = "[::1]"
                SocketAddress = [System.Net.IPAddress]::IPv6Loopback
                UrlHost = "[::1]"
            }
        }
        "[::1]" {
            if (-not [System.Net.Sockets.Socket]::OSSupportsIPv6) {
                throw "IPv6 loopback (::1) is not supported on this computer. Use 127.0.0.1 or localhost."
            }
            return [PSCustomObject]@{
                BindAddress = "[::1]"
                SocketAddress = [System.Net.IPAddress]::IPv6Loopback
                UrlHost = "[::1]"
            }
        }
        default {
            throw (
                "Unsafe listen address '{0}' was rejected before Django startup. " +
                "ConflictAnalysis Studio is session-only and may bind only to " +
                "127.0.0.1, localhost, or the supported IPv6 loopback ::1."
            ) -f $Address
        }
    }
}

function New-StudioShowcaseSecret {
    [CmdletBinding()]
    param()

    $SecretBytes = New-Object byte[] 48
    $Generator = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $Generator.GetBytes($SecretBytes)
        return [System.Convert]::ToBase64String($SecretBytes)
    }
    finally {
        $Generator.Dispose()
        [System.Array]::Clear($SecretBytes, 0, $SecretBytes.Length)
    }
}

function Assert-StudioShowcasePortAvailable {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [System.Net.IPAddress]$SocketAddress,

        [Parameter(Mandatory = $true)]
        [ValidateRange(1, 65535)]
        [int]$PortNumber
    )

    $Listener = [System.Net.Sockets.TcpListener]::new($SocketAddress, $PortNumber)
    try {
        $Listener.Server.ExclusiveAddressUse = $true
        $Listener.Start()
    }
    catch {
        throw (
            "Port {0} on loopback address {1} is unavailable. Stop the process " +
            "using that port or launch with -Port <free-port>. Technical detail: {2}"
        ) -f $PortNumber, $SocketAddress, $_.Exception.Message
    }
    finally {
        $Listener.Stop()
    }
}

function Set-StudioShowcaseProcessEnvironment {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [hashtable]$Values
    )

    $Previous = @{}
    foreach ($Name in $Values.Keys) {
        $Previous[$Name] = [System.Environment]::GetEnvironmentVariable($Name, "Process")
        [System.Environment]::SetEnvironmentVariable($Name, $Values[$Name], "Process")
    }
    return $Previous
}

function Restore-StudioShowcaseProcessEnvironment {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [hashtable]$Previous
    )

    foreach ($Name in $Previous.Keys) {
        [System.Environment]::SetEnvironmentVariable($Name, $Previous[$Name], "Process")
    }
}

# Dot-sourcing imports the small pure helpers for the Windows launcher contract
# tests without starting Python or Django. A normal -File invocation continues.
if ($MyInvocation.InvocationName -eq ".") {
    return
}

# This validation is intentionally the first runtime operation. Unsafe binds
# fail before Python discovery, Django import, settings loading, or server start.
$Endpoint = Resolve-StudioShowcaseLoopbackEndpoint -Address $ListenAddress
Assert-StudioShowcasePortAvailable -SocketAddress $Endpoint.SocketAddress -PortNumber $Port

$ProjectRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$ProjectVenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$ManagePy = Join-Path $ProjectRoot "manage.py"

$PythonExecutable = $null
$PythonPrefixArguments = @()
$PythonSource = $null

if (Test-Path -LiteralPath $ProjectVenvPython -PathType Leaf) {
    $PythonExecutable = $ProjectVenvPython
    $PythonSource = "project virtual environment"
}
else {
    $PyLauncher = Get-Command "py.exe" -ErrorAction SilentlyContinue
    if ($null -eq $PyLauncher) {
        $PyLauncher = Get-Command "py" -ErrorAction SilentlyContinue
    }
    if ($null -eq $PyLauncher) {
        throw (
            "Python 3.12 was not found. Expected '{0}' or the Windows Python " +
            "launcher command 'py -3.12'. Install Python 3.12, then follow " +
            "START_HERE_RU.txt if this is an OWNER-TEST package."
        ) -f $ProjectVenvPython
    }
    $PythonExecutable = $PyLauncher.Source
    $PythonPrefixArguments = @("-3.12")
    $PythonSource = "Windows Python launcher (py -3.12)"
}

if (-not (Test-Path -LiteralPath $ManagePy -PathType Leaf)) {
    throw "Django entry point not found: '$ManagePy'. Re-extract the OWNER-TEST package and do not move the scripts directory."
}

& $PythonExecutable @PythonPrefixArguments -c (
    "import sys; assert sys.version_info[:2] == (3, 12), " +
    "f'Python 3.12 required, got {sys.version.split()[0]}'"
)
if ($LASTEXITCODE -ne 0) {
    throw "The selected $PythonSource is not Python 3.12. Install Python 3.12 or recreate '$ProjectVenvPython'."
}

& $PythonExecutable @PythonPrefixArguments -c "import django; print('Django', django.get_version())"
if ($LASTEXITCODE -ne 0) {
    throw (
        "The selected $PythonSource cannot import Django. From '$ProjectRoot', " +
        "install the OWNER-TEST dependencies with: " +
        "py -3.12 -m pip install -r requirements-owner-test.txt"
    )
}

$PerRunSecret = New-StudioShowcaseSecret
$PreviousEnvironment = Set-StudioShowcaseProcessEnvironment -Values @{
    DJANGO_SETTINGS_MODULE = "conflict_analysis.studio_showcase_settings"
    DJANGO_DEBUG = "false"
    DJANGO_ALLOWED_HOSTS = "127.0.0.1,localhost,[::1]"
    DJANGO_SECRET_KEY = $PerRunSecret
    PYTHONDONTWRITEBYTECODE = "1"
    PYTHONUNBUFFERED = "1"
}

$ShowcaseUrl = "http://$($Endpoint.UrlHost):$Port/"
Write-Host "ConflictAnalysis Studio - research prototype" -ForegroundColor Cyan
Write-Host "Interpreter: $PythonSource"
Write-Host "Settings: conflict_analysis.studio_showcase_settings (DEBUG=false)"
Write-Host "Session data is not written to the Foundation ORM or production database." -ForegroundColor Yellow
Write-Host "Open: $ShowcaseUrl" -ForegroundColor Green
Write-Host "Press Ctrl+C to stop. The foreground server process will stop with this launcher."

Push-Location $ProjectRoot
try {
    # --insecure serves the packaged static presentation assets while DEBUG is
    # deliberately false. Exposure is still constrained to a loopback socket.
    & $PythonExecutable @PythonPrefixArguments $ManagePy runserver "$($Endpoint.BindAddress):$Port" `
        --settings conflict_analysis.studio_showcase_settings --noreload --insecure
    if ($LASTEXITCODE -ne 0) {
        throw "Studio showcase server exited with code $LASTEXITCODE. Review the preceding Django error and START_HERE_RU.txt."
    }
}
finally {
    Pop-Location
    Restore-StudioShowcaseProcessEnvironment -Previous $PreviousEnvironment
    $PerRunSecret = $null
}
