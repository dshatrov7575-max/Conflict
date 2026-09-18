[CmdletBinding()]
param([Parameter(Mandatory)][string]$Zip,[Parameter(Mandatory)][string]$Sha256,
      [Parameter(Mandatory)][long]$Bytes,[switch]$VerifyOnly)
$ErrorActionPreference='Stop'
try {
    Import-Module (Join-Path $PSScriptRoot 'Mvp7.Setup.psm1') -Force
    $manifest=Assert-Mvp7Archive $Zip $Sha256 $Bytes
    if ($VerifyOnly) { Write-Output 'OFFLINE_PAYLOAD_VERIFY=PASS';exit 0 }
    Assert-Mvp7Host
    Invoke-Mvp7Installation $Zip $Sha256 $Bytes $manifest
    Write-Output 'Установка завершена. Состояние и резервные копии хранятся отдельно от программы.'
} catch { Write-Output ('Установка остановлена: '+$_.Exception.Message);exit 1 }
