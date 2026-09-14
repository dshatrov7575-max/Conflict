[CmdletBinding()]
param([string]$PackageRoot=(Split-Path $PSScriptRoot),[string]$StateRoot='',[int]$Port=8765,
      [switch]$Backup,[string]$Confirmation='')
Import-Module (Join-Path $PSScriptRoot 'OwnerAlpha.Common.psm1') -Force
$context=Get-OwnerContext $PackageRoot $StateRoot $Port
if ($Backup) {
    $receipt=Backup-OwnerState $context $Confirmation
    @{phase='BACKUP_COMPLETE';privatePath=$receipt.path;bytes=$receipt.bytes;sha256=$receipt.sha256} | ConvertTo-Json
} else { Stop-OwnerState $context | ConvertTo-Json }

