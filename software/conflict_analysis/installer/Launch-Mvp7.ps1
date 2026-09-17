[CmdletBinding()]
param([ValidateSet('Start','Stop','Diagnostics')][string]$Action='Start')
$ErrorActionPreference='Stop'
try {
    Import-Module (Join-Path $PSScriptRoot 'Mvp7.Setup.psm1') -Force
    $root=Get-Mvp7ProgramRoot
    $app=Join-Path $root 'app'
    $script=@{Start='Start-OwnerAlpha.ps1';Stop='Stop-OwnerAlpha.ps1';Diagnostics='Status-OwnerAlpha.ps1'}[$Action]
    & (Join-Path $app ('windows/'+$script)) -PackageRoot $app -StateRoot (Get-Mvp7StateRoot)
} catch { Write-Output ('Операция остановлена: '+$_.Exception.Message);exit 1 }
