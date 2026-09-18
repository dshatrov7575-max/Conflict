[CmdletBinding()]
param([string]$PackageRoot=(Split-Path $PSScriptRoot),[string]$StateRoot='',[int]$Port=8765,
      [switch]$Restore,[string]$BackupPath='',[string]$Confirmation='',[switch]$SwitchRestored,[switch]$NoPrompt,[hashtable]$Transaction)
Import-Module (Join-Path $PSScriptRoot 'OwnerAlpha.Common.psm1') -Force
$context=Get-OwnerContext $PackageRoot $StateRoot $Port
if ($Restore) {
    Assert-OwnerInstalled $context
    if (-not $BackupPath) { $BackupPath=Read-Host 'Полный путь к приватной резервной копии' }
    $path=Assert-OwnerPath $BackupPath (Join-Path $context.root 'backups')
    $matches=@($context.record.backupReceipts | Where-Object path -CEQ $path)
    Assert-OwnerGate ($matches.Count -eq 1) 'BLOCKED_G10_BACKUP_ORIGIN_UNKNOWN'
    $meta=Get-OwnerFileIdentity $path
    Assert-OwnerGate ($meta.bytes -eq $matches[0].bytes -and $meta.sha256 -ceq $matches[0].sha256) 'BLOCKED_G10_BACKUP_RESTORE_GAP'
    Confirm-OwnerAction 'RESTORE' $context.record.instance $Confirmation
    $candidateRoot=Join-Path $context.root ('restore-'+[guid]::NewGuid().ToString('N').Substring(0,8))
    $candidate=Get-OwnerContext $PackageRoot $candidateRoot ($Port+1)
    $null=New-OwnerInstall $candidate -RestoreEmpty
    $result=Invoke-OwnerWsl -Distribution $candidate.record.distribution -Command @('restore') -InputPath $path
    Assert-OwnerGate ($result.full_graph_verified -eq $true -and $result.old_sessions -eq 0) 'BLOCKED_G10_BACKUP_RESTORE_GAP'
    $candidate.record.phase='RESTORED'
    $candidate.record.sourceRoot=$context.root
    Write-OwnerJson $candidate.stateFile $candidate.record
    # The source and old backups remain intact. Switching is a separate command.
    $result.candidateRoot=$candidate.root
    $result | ConvertTo-Json -Depth 10
    if (-not $NoPrompt) {
        $decision=Read-Host ('Проверка восстановления завершена. Для отдельного переключения введите SWITCH '+$candidate.record.instance+'; Enter — сохранить обе среды без переключения')
        if ($decision) {
            & $PSCommandPath -PackageRoot $PackageRoot -StateRoot $candidate.root -Port $candidate.record.port -SwitchRestored -Confirmation $decision
        }
    }
} elseif ($SwitchRestored) {
    Assert-OwnerInstalled $context
    Assert-OwnerGate ($context.record.phase -eq 'RESTORED' -and $context.record.ContainsKey('sourceRoot')) 'BLOCKED_G10_BACKUP_RESTORE_GAP'
    Confirm-OwnerAction 'SWITCH' $context.record.instance $Confirmation
    $source=Get-OwnerContext $PackageRoot $context.record.sourceRoot $Port
    $null=Stop-OwnerState $source
    $source.record.activeRoot=$context.root
    $source.record.activePort=$context.record.port
    Write-OwnerJson $source.stateFile $source.record
    & (Join-Path $PSScriptRoot 'Start-OwnerAlpha.ps1') -PackageRoot $PackageRoot -StateRoot $context.root -Port $context.record.port
} elseif ($context.record) {
    Assert-OwnerInstalled $context
    Invoke-OwnerWsl $context.record.distribution @('health') | ConvertTo-Json -Depth 10
} else {
    $record=New-OwnerInstall $context -Transaction $Transaction
    @{phase=$record.phase;instance=$record.instance;distribution=$record.distribution} | ConvertTo-Json
}
