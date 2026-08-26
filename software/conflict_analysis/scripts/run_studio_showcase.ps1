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
            "Порт {0} на loopback-адресе {1} недоступен (Port {0} is unavailable). " +
            "Остановите процесс, который занимает этот порт, или повторите запуск " +
            "с параметром -Port <свободный-порт>. Техническая деталь: {2}"
        ) -f $PortNumber, $SocketAddress, $_.Exception.Message
    }
    finally {
        $Listener.Stop()
    }
}

function Assert-StudioShowcasePythonVersion {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [ValidateNotNullOrEmpty()]
        [string]$Version,

        [Parameter(Mandatory = $true)]
        [ValidateNotNullOrEmpty()]
        [string]$PythonSource
    )

    if ($Version.Trim() -cne "3.12") {
        throw (
            "Для OWNER-TEST требуется Python 3.12; выбранный источник '{0}' " +
            "сообщил версию '{1}'. Установите Python 3.12 x64 или пересоздайте " +
            "локальную среду .venv с помощью 'py -3.12 -m venv .venv'."
        ) -f $PythonSource, $Version.Trim()
    }
}

function Assert-StudioShowcaseDjangoVersion {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [ValidateNotNullOrEmpty()]
        [string]$Version,

        [Parameter(Mandatory = $true)]
        [ValidateNotNullOrEmpty()]
        [string]$PythonSource
    )

    $RequiredVersion = "5.2.17"
    if ($Version.Trim() -cne $RequiredVersion) {
        throw (
            "Для OWNER-TEST требуется Django {0}; выбранный источник '{1}' " +
            "сообщил версию '{2}'. Установите точные зависимости командой " +
            "'py -3.12 -m pip install -r requirements-owner-test.txt'."
        ) -f $RequiredVersion, $PythonSource, $Version.Trim()
    }
}

function Invoke-StudioShowcasePythonProbe {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [ValidateNotNullOrEmpty()]
        [string]$PythonExecutable,

        [AllowEmptyCollection()]
        [object[]]$PythonPrefixArguments = @(),

        [Parameter(Mandatory = $true)]
        [ValidateNotNullOrEmpty()]
        [string]$Code
    )

    # Windows PowerShell 5.1 turns a native process' stderr into a terminating
    # NativeCommandError when the launcher-wide ErrorActionPreference is Stop.
    # Probe failures must reach our short actionable OWNER-TEST diagnostics.
    $PreviousErrorActionPreference = $ErrorActionPreference
    $ProbeOutput = @()
    $ProbeExitCode = -1
    try {
        $ErrorActionPreference = "Continue"
        $ProbeOutput = @(& $PythonExecutable @PythonPrefixArguments -c $Code 2>$null)
        $ProbeExitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $PreviousErrorActionPreference
    }

    return [PSCustomObject]@{
        ExitCode = $ProbeExitCode
        Output = $ProbeOutput
    }
}

function Throw-StudioShowcaseMissingPython {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [ValidateNotNullOrEmpty()]
        [string]$ExpectedPath
    )

    throw (
        "Python 3.12 не найден. Ожидался файл '{0}' или Windows-команда " +
        "'py -3.12'. Установите Python 3.12 x64, затем повторите шаги из " +
        "START_HERE_RU.txt."
    ) -f $ExpectedPath
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
        Throw-StudioShowcaseMissingPython -ExpectedPath $ProjectVenvPython
    }
    $PythonExecutable = $PyLauncher.Source
    $PythonPrefixArguments = @("-3.12")
    $PythonSource = "Windows Python launcher (py -3.12)"
}

if (-not (Test-Path -LiteralPath $ManagePy -PathType Leaf)) {
    throw "Точка входа Django не найдена: '$ManagePy'. Распакуйте OWNER-TEST заново и не перемещайте каталог scripts отдельно от app."
}

$VersionProbe = Invoke-StudioShowcasePythonProbe `
    -PythonExecutable $PythonExecutable `
    -PythonPrefixArguments $PythonPrefixArguments `
    -Code "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
if ($VersionProbe.ExitCode -ne 0) {
    throw (
        "Не удалось запустить выбранный интерпретатор '$PythonSource'. " +
        "Установите Python 3.12 x64 или пересоздайте '$ProjectVenvPython'."
    )
}
Assert-StudioShowcasePythonVersion `
    -Version ([string]($VersionProbe.Output | Select-Object -Last 1)) `
    -PythonSource $PythonSource
$VersionProbe = $null

$DjangoProbe = Invoke-StudioShowcasePythonProbe `
    -PythonExecutable $PythonExecutable `
    -PythonPrefixArguments $PythonPrefixArguments `
    -Code "import django; print(django.get_version())"
if ($DjangoProbe.ExitCode -ne 0) {
    throw (
        "Django не импортируется выбранным интерпретатором '$PythonSource'. " +
        "Из каталога '$ProjectRoot' установите OWNER-TEST зависимости командой: " +
        "py -3.12 -m pip install -r requirements-owner-test.txt"
    )
}
Assert-StudioShowcaseDjangoVersion `
    -Version ([string]($DjangoProbe.Output | Select-Object -Last 1)) `
    -PythonSource $PythonSource
$DjangoProbe = $null

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
