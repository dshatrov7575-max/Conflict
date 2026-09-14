[CmdletBinding()]
param([string]$PackageRoot=(Split-Path $PSScriptRoot),[string]$StateRoot='',[int]$Port=8765,
      [string]$Confirmation='')
Import-Module (Join-Path $PSScriptRoot 'OwnerAlpha.Common.psm1') -Force
$context=Get-OwnerContext $PackageRoot $StateRoot $Port
Assert-OwnerInstalled $context
Confirm-OwnerAction 'UNINSTALL' $context.record.instance $Confirmation
$null=Backup-OwnerState $context ('BACKUP '+$context.record.instance)
$null=Stop-OwnerState $context
$null=Invoke-OwnerProcess "$env:WINDIR\System32\wsl.exe" @('--unregister',$context.record.distribution)
$context.record.phase='UNINSTALLED'
Write-OwnerJson $context.stateFile $context.record
@{phase='UNINSTALLED';instance=$context.record.instance;privateBackupsPreserved=$true;immutableZipPreserved=$true} | ConvertTo-Json

