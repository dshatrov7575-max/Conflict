[CmdletBinding()]
param([string]$PackageRoot=(Split-Path $PSScriptRoot),[string]$StateRoot='',[int]$Port=8765)
Import-Module (Join-Path $PSScriptRoot 'OwnerAlpha.Common.psm1') -Force
$context=Get-OwnerContext $PackageRoot $StateRoot $Port
if ($context.record) {
    Assert-OwnerInstalled $context
    $health=Invoke-OwnerWsl $context.record.distribution @('health')
} else { $health=@{phase='NOT_INSTALLED'} }
@{health=$health;source=$context.manifest.source;launch=$context.admission;capacity=$context.capacity} | ConvertTo-Json -Depth 30

