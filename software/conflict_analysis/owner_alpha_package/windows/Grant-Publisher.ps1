[CmdletBinding()]
param([string]$PackageRoot=(Split-Path $PSScriptRoot),[string]$StateRoot='',[int]$Port=8765,
      [string]$ProjectId='',[string]$Confirmation='')
Import-Module (Join-Path $PSScriptRoot 'OwnerAlpha.Common.psm1') -Force
$context=Get-OwnerContext $PackageRoot $StateRoot $Port
Assert-OwnerInstalled $context
if (-not $ProjectId) { $ProjectId=Read-Host 'UUID проекта из Studio Editor' }
$parsed=[guid]::ParseExact($ProjectId,'D')
Confirm-OwnerAction 'GRANT' $parsed.ToString() $Confirmation
Invoke-OwnerWsl $context.record.distribution @('grant',$parsed.ToString()) | ConvertTo-Json

