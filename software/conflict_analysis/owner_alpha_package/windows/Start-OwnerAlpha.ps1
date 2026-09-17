[CmdletBinding()]
param([string]$PackageRoot=(Split-Path $PSScriptRoot),[string]$StateRoot='',[int]$Port=8765,[switch]$NoPrompt)
Import-Module (Join-Path $PSScriptRoot 'OwnerAlpha.Common.psm1') -Force
Import-Module (Join-Path $PSScriptRoot 'OwnerAlpha.Cdp.psm1') -Force
$context=Get-OwnerContext $PackageRoot $StateRoot $Port
Assert-OwnerInstalled $context
if ($context.record.profiles.Count -gt 0 -or $context.record.phase -eq 'READY') { $null=Stop-OwnerState $context }
Assert-OwnerPortFree $context.record.port
$health=Invoke-OwnerWsl $context.record.distribution @('start')
Assert-OwnerGate ($health.phase -eq 'READY') 'BLOCKED_G10_RUNTIME_OPERATION_FAILED'
$bundle=Invoke-OwnerWsl $context.record.distribution @('access')
try {
    Assert-OwnerGate ($bundle.profiles.Count -eq 3 -and ((@($bundle.profiles.profile | Sort-Object) -join '|') -ceq 'PLAYER_ASSESSOR|STUDIO_EDITOR|STUDIO_PUBLISHER')) 'BLOCKED_G10_PROFILE_ISOLATION_GAP'
    $public=@()
    foreach ($cookie in $bundle.profiles) { $public+=Open-OwnerProfile $context $cookie }
    $context.record.phase='READY'
    Write-OwnerJson $context.stateFile $context.record
    @{phase='READY';instance=$context.record.instance;profiles=$public} | ConvertTo-Json -Depth 10

} catch {
    $null=Invoke-OwnerWsl $context.record.distribution @('revoke')
    throw
} finally { $bundle=$null }
