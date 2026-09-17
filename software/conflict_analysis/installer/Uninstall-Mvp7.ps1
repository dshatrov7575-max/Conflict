[CmdletBinding()]
param()
$ErrorActionPreference='Stop'
try {
    Import-Module (Join-Path $PSScriptRoot 'Mvp7.Setup.psm1') -Force
    $root=Get-Mvp7ProgramRoot
    $app=Join-Path $root 'app'
    & (Join-Path $app 'windows/Uninstall-OwnerAlpha.ps1') -PackageRoot $app -StateRoot (Get-Mvp7StateRoot)
    Remove-Mvp7Program $root
    Write-Output 'Программа удалена. Состояние, дистрибутив WSL и резервные копии сохранены.'
} catch { Write-Output ('Удаление остановлено: '+$_.Exception.Message);exit 1 }
