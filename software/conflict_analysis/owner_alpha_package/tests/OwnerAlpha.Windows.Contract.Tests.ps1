# Exactly ten contract nodes. Mocks here never constitute real Windows capacity,
# WSL usability, Edge execution, R2 restore or final-ZIP launch evidence.
Import-Module (Join-Path $PSScriptRoot '../windows/OwnerAlpha.Common.psm1') -Force
Import-Module (Join-Path $PSScriptRoot '../windows/OwnerAlpha.Cdp.psm1') -Force

function Assert-Contract([bool]$Condition) { if (-not $Condition) { throw 'G10 contract assertion failed' } }
function Assert-ContractReject([scriptblock]$Probe,[string]$Code) {
    try { & $Probe; throw 'Expected rejection did not occur' }
    catch { Assert-Contract ($_.Exception.Message.Contains($Code)) }
}
function New-ContractContext {
    $root=Join-Path $TestDrive ([guid]::NewGuid().ToString('N'))
    $package=Join-Path $TestDrive ('package-'+[guid]::NewGuid().ToString('N'))
    $null=New-Item -ItemType Directory -Path $package
    [IO.File]::WriteAllText((Join-Path $package 'MVP7_PACKAGE_MANIFEST_V1.json'),'{}')
    return @{root=$root;package=$package;port=18765;stateFile=(Join-Path $root 'installation.json');record=$null;
        capacity=@{edgePath='C:\Program Files\Microsoft\Edge\Application\msedge.exe'};
        manifest=@{source=@{head=('1'*40);tree=('2'*40)};wheel=@{sha256=('3'*64)}}}
}
Describe 'G10 Windows package contract (not real Windows E2E)' {
    It 'test_preflight_rejects_unsupported_windows_wsl_edge_path_port_acl_and_stale_identity_before_import' {
        foreach ($path in @('\\server\share\package','C:\bad"path',('C:\'+('a'*200)))) {
            Assert-ContractReject { Assert-OwnerPath $path } 'BLOCKED_G10_UNSAFE_PATH'
        }
        Assert-ContractReject { Assert-OwnerPath 'C:\other\file' 'C:\allowed' } 'BLOCKED_G10_UNSAFE_PATH'
        Mock Get-CimInstance -ModuleName OwnerAlpha.Common {
            if ($ClassName -eq 'Win32_OperatingSystem') { return @{ProductType=3;BuildNumber='26200';Caption='Windows Server'} }
            if ($ClassName -eq 'Win32_ComputerSystem') { return @{SystemType='x64-based PC';HypervisorPresent=$true} }
            return @{VirtualizationFirmwareEnabled=$true;SecondLevelAddressTranslationExtensions=$true}
        }
        Mock Invoke-OwnerProcess -ModuleName OwnerAlpha.Common { throw 'must not execute WSL' }
        Assert-ContractReject { Assert-OwnerCapacity 18765 } 'BLOCKED_G10_WINDOWS_CAPACITY'
        Assert-MockCalled Invoke-OwnerProcess -ModuleName OwnerAlpha.Common -Times 0 -Exactly
        $listener=[Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback,18765)
        try { $listener.Start(); Assert-ContractReject { Assert-OwnerPortFree 18765 } 'BLOCKED_G10_PORT_CONFLICT' }
        finally { $listener.Stop() }
    }
    It 'test_install_verifies_all_bytes_imports_one_exact_wsl2_distribution_and_reconciles_exact_replay' {
        $ctx=New-ContractContext
        $ctx.root=Join-Path $TestDrive 'clean-localappdata/ConflictPartnerDemoState/mvp7'
        $ctx.stateFile=Join-Path $ctx.root 'installation.json'
        Assert-Contract (-not (Test-Path -LiteralPath (Split-Path $ctx.root)))
        Mock Invoke-OwnerProcess -ModuleName OwnerAlpha.Common { return ,[byte[]]@() }
        Mock Invoke-OwnerWsl -ModuleName OwnerAlpha.Common {
            if ($Command[0] -eq 'identity') { return @{source=@{head=('1'*40);tree=('2'*40)};wheel=@{sha256=('3'*64)}} }
            return @{phase='STOPPED'}
        }
        $record=New-OwnerInstall $ctx
        Assert-Contract ($record.phase -eq 'STOPPED' -and $record.distribution -match '^Conflict-Alpha-222222222222-[0-9a-f]{8}$')
        Assert-MockCalled Invoke-OwnerProcess -ModuleName OwnerAlpha.Common -Times 1 -Exactly -ParameterFilter { $Arguments[0] -eq '--import' -and $Arguments[-2] -eq '--version' -and $Arguments[-1] -eq '2' }
        Assert-OwnerInstalled $ctx
        Assert-ContractReject { New-OwnerInstall $ctx } 'BLOCKED_G10_RUNTIME_IDENTITY_DRIFT'
        Assert-MockCalled Invoke-OwnerProcess -ModuleName OwnerAlpha.Common -Times 1 -Exactly
        Assert-Contract (Test-Path -LiteralPath $ctx.stateFile)
        Assert-Contract (-not (Test-Path -LiteralPath (Join-Path $ctx.root 'installation.pending.json')))
        $failed=New-ContractContext
        Mock Invoke-OwnerWsl -ModuleName OwnerAlpha.Common {
            if ($Command[0] -eq 'identity') { return @{source=@{head=('1'*40);tree=('2'*40)};wheel=@{sha256=('3'*64)}} }
            throw 'BLOCKED_G10_RUNTIME_OPERATION_FAILED'
        }
        Assert-ContractReject { New-OwnerInstall $failed } 'BLOCKED_G10_RUNTIME_OPERATION_FAILED'
        Assert-Contract (-not (Test-Path -LiteralPath $failed.stateFile))
        Assert-Contract (Test-Path -LiteralPath (Join-Path $failed.root 'installation.pending.json'))
        $policyRoot=Join-Path $TestDrive 'policy'
        Mock Get-ExecutionPolicy -ModuleName OwnerAlpha.Common { 'Restricted' }
        Assert-ContractReject { Get-OwnerLaunchAdmission $policyRoot } 'BLOCKED_G10_LAUNCH_ADMISSION'
    }
    It 'test_start_generates_no_public_secret_and_binds_only_the_frozen_loopback_origin' {
        $module=Get-Content -Raw -LiteralPath (Join-Path $PSScriptRoot '../windows/OwnerAlpha.Cdp.psm1')
        Assert-Contract ($module.Contains("'http://127.0.0.1:'") -and $module.Contains('Network.setCookie'))
        Assert-Contract (-not $module.Contains('0.0.0.0') -and -not $module.Contains('Write-Host $Cookie'))
        Assert-Contract ($module.Contains("if("+[char]36+"Cookie.profile -eq 'STUDIO_PUBLISHER')"))
        Assert-Contract ($module.Contains("'/analysis/'") -and $module.Contains([char]36+'base+@(''--new-window'')+'+[char]36+'pages'))
        Assert-Contract ($module.Contains([char]36+'Context.record.profiles['+[char]36+'Cookie.profile].pids=@('+[char]36+'visible.Id)'))
        $ctx=New-ContractContext
        $ctx.record=@{distribution='Conflict-Alpha-222222222222-12345678'}
        Mock Invoke-OwnerWsl -ModuleName OwnerAlpha.Common {
            return @{source=@{head=('0'*40);tree=('2'*40)};wheel=@{sha256=('3'*64)}}
        }
        Assert-ContractReject { Assert-OwnerInstalled $ctx } 'BLOCKED_G10_RUNTIME_IDENTITY_DRIFT'
    }
    It 'test_access_prepare_stream_is_memory_only_and_exact_three_profile_permissions_are_preserved' {
        $secret=[guid]::NewGuid().ToString('N')
        $input=[Text.Encoding]::UTF8.GetBytes($secret)
        $shell=(Get-Process -Id $PID).Path
        $bytes=Invoke-OwnerProcess $shell @('-NoProfile','-Command','[Console]::Write([Console]::In.ReadToEnd())') $input
        Assert-Contract ([Text.Encoding]::UTF8.GetString($bytes) -ceq $secret)
        [Array]::Clear($input,0,$input.Length); [Array]::Clear($bytes,0,$bytes.Length)
        $linux=Get-Content -Raw -LiteralPath (Join-Path $PSScriptRoot '../linux/owner-alpha-supervisor.sh')
        Assert-Contract ($linux.Contains('G8_REQUIRED_PERMISSIONS') -and $linux.Contains('studio_principal_from_user') -and $linux.Contains('User.objects.get(pk=mapping[profile])'))
        Assert-Contract (-not $linux.Contains('is_superuser=True') -and -not $linux.Contains('is_staff=True'))
    }
    It 'test_cdp_sets_exact_cookie_in_three_acl_profiles_then_closes_every_debug_endpoint' {
        $ctx=New-ContractContext
        Assert-ContractReject { Open-OwnerProfile $ctx @{profile='UNKNOWN'} } 'BLOCKED_G10_PROFILE_ISOLATION_GAP'
        $listener=[Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback,18766)
        try { $listener.Start(); Assert-ContractReject { Assert-OwnerDebugClosed 18766 } 'BLOCKED_G10_NETWORK_EXPOSURE' }
        finally { $listener.Stop() }
        Assert-OwnerDebugClosed 18766
        $directory=New-OwnerPrivateDirectory (Join-Path $TestDrive 'cookie-profile')
        Assert-OwnerPrivateDirectory $directory
        $before=(Get-Acl -LiteralPath $directory).Sddl
        $null=New-OwnerPrivateDirectory $directory
        Assert-Contract ((Get-Acl -LiteralPath $directory).Sddl -ceq $before)
    }
    It 'test_studio_editor_publisher_and_player_assessor_sessions_and_project_scope_are_separate' {
        $ctx=New-ContractContext
        foreach ($profile in @('STUDIO_EDITOR','STUDIO_PUBLISHER','PLAYER_ASSESSOR')) {
            Assert-ContractReject { Open-OwnerProfile $ctx @{profile=$profile;name='sessionid';httpOnly=$false;sameSite='Lax';path='/';secure=$false;value=('a'*32)} } 'BLOCKED_G10_ACCESS_PROVISIONING_GAP'
        }
        Assert-ContractReject { Confirm-OwnerAction 'GRANT' 'project-a' 'GRANT project-b' } 'BLOCKED_G10_CONFIRMATION_REQUIRED'
        $linux=Get-Content -Raw -LiteralPath (Join-Path $PSScriptRoot '../linux/owner-alpha-supervisor.sh')
        Assert-Contract ($linux.Contains('group.permissions.exists()') -and $linux.Contains('project_access_group_name(project_id)'))
    }
    It 'test_status_restart_and_stop_are_replay_safe_and_database_and_receipt_state_persists' {
        $ctx=New-ContractContext
        $null=New-OwnerPrivateDirectory $ctx.root
        $ctx.record=@{distribution='Conflict-Alpha-222222222222-12345678';instance='12345678';profiles=@{};phase='READY';backupReceipts=@(@{sha256='prior'})}
        Mock Assert-OwnerInstalled -ModuleName OwnerAlpha.Common {}
        Mock Invoke-OwnerWsl -ModuleName OwnerAlpha.Common { return @{sessions_revoked=$true;phase='STOPPED'} }
        $first=Stop-OwnerState $ctx
        $second=Stop-OwnerState $ctx
        Assert-Contract ($first.phase -eq 'STOPPED' -and $second.phase -eq 'STOPPED' -and $ctx.record.backupReceipts[0].sha256 -eq 'prior')
        Assert-MockCalled Invoke-OwnerWsl -ModuleName OwnerAlpha.Common -Times 2 -Exactly -ParameterFilter { $Command[0] -eq 'stop' }
    }
    It 'test_stop_requires_no_busy_unknown_confirmation_and_revokes_before_profile_deletion' {
        $ctx=New-ContractContext
        $ctx.record=@{distribution='Conflict-Alpha-222222222222-12345678';profiles=@{}}
        Mock Assert-OwnerInstalled -ModuleName OwnerAlpha.Common {}
        Mock Invoke-OwnerWsl -ModuleName OwnerAlpha.Common { throw 'BLOCKED_G10_OPERATION_BUSY' }
        Mock Close-OwnerProfiles -ModuleName OwnerAlpha.Common { throw 'must not delete profiles' }
        Assert-ContractReject { Stop-OwnerState $ctx } 'BLOCKED_G10_OPERATION_BUSY'
        Assert-MockCalled Close-OwnerProfiles -ModuleName OwnerAlpha.Common -Times 0 -Exactly
    }
    It 'test_backup_restore_reset_and_uninstall_require_exact_confirmation_and_leave_the_declared_state' {
        foreach ($action in @('BACKUP','RESTORE','SWITCH','RESET','UNINSTALL')) {
            Assert-ContractReject { Confirm-OwnerAction $action 'instance-a' ($action+' instance-b') } 'BLOCKED_G10_CONFIRMATION_REQUIRED'
            Confirm-OwnerAction $action 'instance-a' ($action+' instance-a')
        }
        $ctx=New-ContractContext
        $null=New-OwnerPrivateDirectory $ctx.root
        $ctx.record=@{instance='12345678';distribution='Conflict-Alpha-222222222222-12345678';manifest=@{sha256='m'};backupReceipts=@(@{sha256='old'});phase='READY'}
        Mock Assert-OwnerInstalled -ModuleName OwnerAlpha.Common {}
        Mock Invoke-OwnerWsl -ModuleName OwnerAlpha.Common { [IO.File]::WriteAllBytes($OutputPath,[byte[]](1,2,3,4)) }
        $receipt=Backup-OwnerState $ctx 'BACKUP 12345678'
        Assert-Contract ($receipt.bytes -eq 4 -and $ctx.record.backupReceipts.Count -eq 2 -and $ctx.record.backupReceipts[0].sha256 -eq 'old')
        Assert-OwnerPrivateDirectory (Split-Path $receipt.path)
    }
    It 'test_no_lan_postgres_gunicorn_debug_port_normal_edge_profile_or_secret_exposure' {
        $all=(Get-ChildItem -LiteralPath (Join-Path $PSScriptRoot '../windows') -File | ForEach-Object { Get-Content -Raw -LiteralPath $_.FullName }) -join ' '
        foreach ($forbidden in @('Set-ExecutionPolicy','Unblock-File','New-NetFirewallRule','Import-Certificate','-ExecutionPolicy Bypass','--remote-debugging-address=0.0.0.0','Edge\User Data','-Verb RunAs')) {
            Assert-Contract (-not $all.Contains($forbidden))
        }
        $path=Join-Path $TestDrive 'ordinary-inherited'
        $null=New-Item -ItemType Directory -Path $path
        $sddl=(Get-Acl -LiteralPath $path).Sddl
        Assert-ContractReject { New-OwnerPrivateDirectory $path } 'BLOCKED_G10_PROFILE_ISOLATION_GAP'
        Assert-Contract ((Get-Acl -LiteralPath $path).Sddl -ceq $sddl)
    }
}
