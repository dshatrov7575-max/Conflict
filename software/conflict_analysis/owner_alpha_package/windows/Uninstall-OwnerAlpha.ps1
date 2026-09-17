[CmdletBinding()]
param([string]$PackageRoot=(Split-Path $PSScriptRoot),[string]$StateRoot='',[int]$Port=8765,[string]$Confirmation='')
Import-Module (Join-Path $PSScriptRoot 'OwnerAlpha.Common.psm1') -Force
$context=Get-OwnerContext $PackageRoot $StateRoot $Port
if ($context.record) { $null=Stop-OwnerState $context }
# The outer uninstaller deletes program files only. WSL distribution, DB,
# installation.json and every backup remain under the external StateRoot.
@{phase='PROGRAM_REMOVAL_READY';statePreserved=$true;backupsPreserved=$true} | ConvertTo-Json
