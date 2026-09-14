[CmdletBinding()]
param([string]$PackageRoot=(Split-Path $PSScriptRoot),[string]$StateRoot='',[int]$Port=8765,
      [string]$Confirmation='',[string]$SwitchConfirmation='',[switch]$NoPrompt)
Import-Module (Join-Path $PSScriptRoot 'OwnerAlpha.Common.psm1') -Force
$context=Get-OwnerContext $PackageRoot $StateRoot $Port
Assert-OwnerInstalled $context
Confirm-OwnerAction 'RESET' $context.record.instance $Confirmation
$null=Backup-OwnerState $context ('BACKUP '+$context.record.instance)
$null=Stop-OwnerState $context
# Reset creates a fresh empty sibling; the source distro and backup are retained.
$newRoot=Join-Path $context.root ('reset-'+[guid]::NewGuid().ToString('N').Substring(0,8))
$fresh=Get-OwnerContext $PackageRoot $newRoot $Port
$record=New-OwnerInstall $fresh
if (-not $NoPrompt -or $SwitchConfirmation) {
    Confirm-OwnerAction 'SWITCH' $record.instance $SwitchConfirmation
    $context.record.activeRoot=$fresh.root
    $context.record.activePort=$fresh.record.port
    Write-OwnerJson $context.stateFile $context.record
}
@{phase='RESET_CANDIDATE';candidateRoot=$fresh.root;instance=$record.instance;sourcePreserved=$true} | ConvertTo-Json
