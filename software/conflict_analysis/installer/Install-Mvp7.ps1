[CmdletBinding()]
param([Parameter(Mandatory)][string]$Zip,[Parameter(Mandatory)][string]$Sha256,[Parameter(Mandatory)][long]$Bytes,[switch]$VerifyOnly)
$ErrorActionPreference='Stop'
try {
    Import-Module (Join-Path $PSScriptRoot 'Mvp7.Setup.psm1') -Force
    $null=Assert-Mvp7Archive $Zip $Sha256 $Bytes
    # VerifyOnly is a read-only artifact contract. It never extracts or installs.
    if ($VerifyOnly) { Write-Output 'OFFLINE_PAYLOAD_VERIFY=PASS';exit 0 }
    Assert-Mvp7Host
    $root=Assert-Mvp7Path (Get-Mvp7ProgramRoot)
    Assert-Mvp7 (-not (Test-Path -LiteralPath $root)) 'Программа уже установлена. Сначала удалите её; состояние будет сохранено.'
    $null=New-Item -ItemType Directory -Path $root -Force
    $app=Join-Path $root 'app'
    Expand-Mvp7Archive $Zip $app $Sha256 $Bytes
    $control=Join-Path $root 'installer'
    $null=New-Item -ItemType Directory -Path $control
    foreach ($name in @('Mvp7.Setup.psm1','Launch-Mvp7.ps1','Uninstall-Mvp7.ps1')) {
        Copy-Item -LiteralPath (Join-Path $PSScriptRoot $name) -Destination (Join-Path $control $name)
    }
    & (Join-Path $app 'windows/Install-OwnerAlpha.ps1') -PackageRoot $app -StateRoot (Get-Mvp7StateRoot) -NoPrompt
    $pending=Join-Path $root 'mvp7-installation.json.pending'
    @{source='85a253126bf270664c4786d159994e7359b5d2c5';program=$root;inner_sha256=$Sha256} | ConvertTo-Json | Set-Content -LiteralPath $pending -Encoding utf8
    [IO.File]::Move($pending,(Join-Path $root 'mvp7-installation.json'))
    Write-Output 'Установка завершена. Состояние и резервные копии хранятся отдельно.'
} catch { Write-Output ('Установка остановлена: '+$_.Exception.Message);exit 1 }
