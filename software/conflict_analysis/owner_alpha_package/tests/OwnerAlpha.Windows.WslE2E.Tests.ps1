# These are real Windows E2E nodes. They fail, never skip, without exact final
# downloaded ZIP bytes and an independently bound evidence channel.
# No host software, Windows policy, trust, zone marker or transport is configured.
param(
    [string]$ZipPath=$env:G10_FINAL_ZIP,
    [string]$PackageRoot=$env:G10_EXTRACTED_PACKAGE,
    [string]$ExpectedSha256=$env:G10_ZIP_SHA256,
    [long]$ExpectedBytes=$env:G10_ZIP_BYTES,
    [string]$ChannelId=$env:G10_WINDOWS_E2E_CHANNEL_ID,
    [string]$DownloadEvidence=$env:G10_DOWNLOAD_EVIDENCE,
    [string]$EvidenceRoot=$env:G10_PRIVATE_E2E_ROOT,
    [string]$NodePath=$env:G10_EXISTING_NODE
)
Import-Module (Join-Path $PSScriptRoot '../windows/OwnerAlpha.Common.psm1') -Force
Import-Module (Join-Path $PSScriptRoot '../windows/OwnerAlpha.Cdp.psm1') -Force

function Assert-RealOwnerInput {
    Assert-OwnerGate ($ChannelId -and $ChannelId -notin @('NOT_YET_BOUND','UNKNOWN')) 'BLOCKED_G10_CI_EVIDENCE_GAP'
    Assert-OwnerGate ($ExpectedSha256 -cmatch '^[0-9a-f]{64}$' -and $ExpectedBytes -gt 0) 'BLOCKED_G10_ARTIFACT_IDENTITY_GAP'
    $identity=Get-OwnerFileIdentity $ZipPath
    Assert-OwnerGate ($identity.sha256 -ceq $ExpectedSha256 -and $identity.bytes -eq $ExpectedBytes) 'BLOCKED_G10_ARTIFACT_IDENTITY_GAP'
    $acquisition=Read-OwnerJson $DownloadEvidence
    Assert-OwnerGate ($acquisition.source -eq 'downloaded_final_zip' -and $acquisition.zip.sha256 -ceq $ExpectedSha256 -and $acquisition.zip.bytes -eq $ExpectedBytes -and $acquisition.download_method -and $acquisition.extraction_method) 'BLOCKED_G10_LAUNCH_ADMISSION'
    Assert-OwnerGate ($acquisition.configuration_changes.Count -eq 0 -and $acquisition.zone_markers_preserved -eq $true -and $acquisition.offline -eq $true) 'BLOCKED_G10_LAUNCH_ADMISSION'
    Assert-OwnerGate ($NodePath -and (Test-Path -LiteralPath $NodePath)) 'BLOCKED_G10_CI_EVIDENCE_GAP'
    $null=Assert-OwnerCapacity 19765
    $null=Get-OwnerLaunchAdmission $PackageRoot
    $manifest=Assert-OwnerManifest $PackageRoot
    # Read hardware adapter state. WSL's virtual interface does not prove
    # Internet connectivity or justify modifying any adapter.
    $adapters=@(Get-NetAdapter -Physical -ErrorAction Stop)
    Assert-OwnerGate (@($adapters | Where-Object Status -eq 'Up').Count -eq 0) 'BLOCKED_G10_LAUNCH_ADMISSION'
    return @{manifest=$manifest;acquisition=$acquisition;zip=$identity}
}
function New-RealOwnerInstance([int]$Port) {
    $input=Assert-RealOwnerInput
    $null=New-OwnerPrivateDirectory $EvidenceRoot
    $private=New-OwnerPrivateDirectory (Join-Path $EvidenceRoot ([guid]::NewGuid().ToString('N').Substring(0,8)))
    $stateRoot=Join-Path $private 'state'
    $before=Get-OwnerFileIdentity $ZipPath
    # The external CMD admission boundary really executes from the supplied
    # downloaded/extracted ZIP. No checkout script substitutes for this L05.
    $wrapper=Join-Path $PackageRoot 'INSTALL_CONFLICT_ANALYSIS.cmd'
    $null=Invoke-OwnerProcess -Executable "$env:WINDIR\System32\cmd.exe" -Arguments @('/d','/c',('call "'+$wrapper+'"')) -Environment @{G10_STATE_ROOT=$stateRoot;G10_PORT=[string]$Port}
    $context=Get-OwnerContext $PackageRoot $stateRoot $Port
    Assert-OwnerInstalled $context
    $null=& (Join-Path $PackageRoot 'windows/Start-OwnerAlpha.ps1') -PackageRoot $PackageRoot -StateRoot $stateRoot -Port $Port -NoPrompt
    $context=Get-OwnerContext $PackageRoot $stateRoot $Port
    Assert-OwnerGate ($context.record.profiles.Count -eq 3 -and @($context.record.profiles.Values | Where-Object debug_closed -ne $true).Count -eq 0) 'BLOCKED_G10_PROFILE_ISOLATION_GAP'
    $health=Invoke-OwnerWsl $context.record.distribution @('health')
    Assert-OwnerGate ($health.phase -eq 'READY') 'BLOCKED_G10_RUNTIME_OPERATION_FAILED'
    Assert-OwnerGate ((Get-OwnerFileIdentity $ZipPath).sha256 -ceq $before.sha256) 'BLOCKED_G10_ARTIFACT_IDENTITY_GAP'
    return @{context=$context;input=$input;private=$private;userPks=$health.user_pks;port=$Port}
}
function Get-RealOwnerGraph([hashtable]$Instance) {
    $graph=Invoke-OwnerWsl $Instance.context.record.distribution @('graph')
    return $graph | ConvertTo-Json -Depth 70 -Compress
}
function Assert-RealOwnerContinuity([hashtable]$Instance,[string]$Before) {
    $null=Stop-OwnerState $Instance.context
    $null=Invoke-OwnerWsl $Instance.context.record.distribution @('start')
    $new=Invoke-OwnerWsl $Instance.context.record.distribution @('access')
    foreach ($cookie in $new.profiles) {
        Assert-OwnerGate ($cookie.user_pk -eq $Instance.userPks[$cookie.profile]) 'BLOCKED_G10_ACCESS_PROVISIONING_GAP'
        $cookie.value=$null
    }
    Assert-OwnerGate ((Get-RealOwnerGraph $Instance) -ceq $Before) 'BLOCKED_G10_BACKUP_RESTORE_GAP'
}
function Invoke-RealOwnerRestore([hashtable]$Instance,[hashtable]$Receipt) {
    $source=Get-RealOwnerGraph $Instance
    $result=& (Join-Path $PackageRoot 'windows/Install-OwnerAlpha.ps1') -PackageRoot $PackageRoot -StateRoot $Instance.context.root -Port $Instance.port -Restore -BackupPath $Receipt.path -Confirmation ('RESTORE '+$Instance.context.record.instance) -NoPrompt
    $proof=$result | ConvertFrom-Json -AsHashtable
    Assert-OwnerGate ($proof.full_graph_verified -eq $true -and $proof.old_sessions -eq 0) 'BLOCKED_G10_BACKUP_RESTORE_GAP'
    $candidate=Get-OwnerContext $PackageRoot $proof.candidateRoot ($Instance.port+1)
    $restored=@{context=$candidate;userPks=$Instance.userPks}
    Assert-OwnerGate ((Get-RealOwnerGraph $restored) -ceq $source -and (Get-RealOwnerGraph $Instance) -ceq $source) 'BLOCKED_G10_BACKUP_RESTORE_GAP'
    $health=Invoke-OwnerWsl $candidate.record.distribution @('start')
    foreach ($profile in $Instance.userPks.Keys) {
        Assert-OwnerGate ($health.user_pks[$profile] -eq $Instance.userPks[$profile]) 'BLOCKED_G10_ACCESS_PROVISIONING_GAP'
    }
    return $candidate
}
function Remove-RealOwnerDisposable([hashtable]$Context) {
    # Only the fresh, independently identified test instance is eligible.
    Assert-OwnerGate ($Context.root.StartsWith([IO.Path]::GetFullPath($EvidenceRoot)+[IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)) 'BLOCKED_G10_UNSAFE_PATH'
    $null=& (Join-Path $PackageRoot 'windows/Uninstall-OwnerAlpha.ps1') -PackageRoot $PackageRoot -StateRoot $Context.root -Port $Context.record.port -Confirmation ('UNINSTALL '+$Context.record.instance)
    $record=Read-OwnerJson $Context.stateFile
    Assert-OwnerGate ($record.phase -eq 'UNINSTALLED' -and $record.backupReceipts.Count -gt 0) 'BLOCKED_G10_BACKUP_RESTORE_GAP'
}
Describe 'G10 final ZIP on a real Windows 11 WSL2 Edge host' {
    It 'test_windows_owner_alpha_complete_three_profile_studio_player_xlsx_evidence_package_backup_and_restart' {
        $instance=New-RealOwnerInstance 19765
        $journey=Invoke-OwnerProductJourney $instance 'complete'
        $before=Get-RealOwnerGraph $instance
        Assert-RealOwnerContinuity $instance $before
        $receipt=Backup-OwnerState $instance.context ('BACKUP '+$instance.context.record.instance)
        $candidate=Invoke-RealOwnerRestore $instance $receipt
        Assert-OwnerProductProof $instance $journey
        Remove-RealOwnerDisposable $candidate
        Remove-RealOwnerDisposable $instance.context
        Write-OwnerE2EEvidence $instance $journey 'complete'
    }
    It 'test_windows_owner_alpha_loss_scope_negative_recovery_restore_and_destructive_cleanup' {
        $instance=New-RealOwnerInstance 19865
        $journey=Invoke-OwnerProductJourney $instance 'negative'
        $before=Get-RealOwnerGraph $instance
        $receipt=Backup-OwnerState $instance.context ('BACKUP '+$instance.context.record.instance)
        $negative=Invoke-OwnerRestoreNegatives $instance $receipt
        Assert-OwnerGate ((Get-RealOwnerGraph $instance) -ceq $before) 'BLOCKED_G10_BACKUP_RESTORE_GAP'
        $candidate=Invoke-RealOwnerRestore $instance $receipt
        Assert-OwnerProductProof $instance $journey
        Remove-RealOwnerDisposable $candidate
        Remove-RealOwnerDisposable $instance.context
        Write-OwnerE2EEvidence $instance $journey 'negative' $negative
    }
}

