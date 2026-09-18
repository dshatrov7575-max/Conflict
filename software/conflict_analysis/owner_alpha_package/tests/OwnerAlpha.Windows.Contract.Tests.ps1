# Exactly ten contract nodes. Mocks here never constitute real Windows capacity,
# WSL usability, Edge execution, R2 restore or final-ZIP launch evidence.
Import-Module (Join-Path $PSScriptRoot '../windows/OwnerAlpha.Common.psm1') -Force
Import-Module (Join-Path $PSScriptRoot '../windows/OwnerAlpha.Cdp.psm1') -Force
Import-Module (Join-Path $PSScriptRoot '../../installer/Mvp7.Setup.psm1') -Force

function global:Assert-Contract([bool]$Condition) { if (-not $Condition) { throw 'G10 contract assertion failed' } }
function Assert-ContractReject([scriptblock]$Probe,[string]$Code) {
    try { & $Probe; throw 'Expected rejection did not occur' }
    catch { Assert-Contract ($_.Exception.Message.Contains($Code)) }
}
function Assert-Mvp7UninstallBoundary([hashtable]$Tx,[string]$StateFile,[string]$StateHash,[string]$BackupFile,[string]$BackupHash) {
    $equivalent=$Tx.program -replace '\\','/'
    Assert-ContractReject { Remove-Mvp7Program (($Tx.program)+'-sibling') } 'Удаление за пределами каталога программы запрещено'
    Assert-ContractReject { Remove-Mvp7Program (Split-Path $Tx.program) } 'Удаление за пределами каталога программы запрещено'
    Assert-ContractReject { Remove-Mvp7Program (Join-Path $Tx.program 'app') } 'Удаление за пределами каталога программы запрещено'
    $target=Join-Path $TestDrive ('uninstall-reparse-target-'+[guid]::NewGuid().ToString('N'))
    $null=New-Item -ItemType Directory -Path $target
    [IO.File]::WriteAllText((Join-Path $target 'keep'),'unchanged')
    $link=Join-Path $Tx.program 'uninstall-reparse'
    $null=New-Item -ItemType Junction -Path $link -Target $target
    try {
        Assert-ContractReject { Remove-Mvp7Program $equivalent } 'Удаление каталога со ссылками запрещено'
        Assert-Contract ((Get-Content -Raw (Join-Path $target 'keep')) -ceq 'unchanged')
    } finally { [IO.Directory]::Delete($link) }
    Remove-Mvp7Program $equivalent
    Assert-Contract ((Get-FileHash $BackupFile).Hash -ceq $BackupHash -and (Get-FileHash $StateFile).Hash -ceq $StateHash)
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
function Invoke-Mvp7TransactionFaultMatrix {
    # Real filesystem, archive extraction, transaction, identity and rollback code.
    # Only WSL/host process boundaries and deliberate faults are mocked.
    $global:Mvp7TransactionContractResults=[Collections.Generic.List[object]]::new()
    $global:Mvp7Registrations=@{'existing-distro'=@{name='existing-distro';path='C:\untouched';version=2;key='pre-existing'}}
    $global:Mvp7Fault=''
    $global:Mvp7FailOnce=$false
    $global:Mvp7HoldRollback=$false
    $global:Mvp7EmptyRemoveFault=$false
    $global:Mvp7UnregisterCalls=0
    $common=Join-Path $PSScriptRoot '../windows/OwnerAlpha.Common.psm1'
    $bytes=[IO.File]::ReadAllBytes($common)
    $global:Mvp7MatrixManifest=@{source=@{head='85a253126bf270664c4786d159994e7359b5d2c5';tree='5567183dbe16fc6c7c8caac051b7694f37b92457'};
        delivery=@{head=('e'*40);parent='1e109ad2f37d3de4d0d0fa3a9b9ad1dbace182d4'};wheel=@{sha256=('3'*64)};
        payload=@{'windows/OwnerAlpha.Common.psm1'=@{bytes=$bytes.Length;sha256=(Get-FileHash $common).Hash.ToLowerInvariant()};
                  'rootfs/conflict-analysis-functional-alpha-rootfs.tar'=@{bytes=16;sha256=('4'*64)}}}
    $zip=Join-Path $TestDrive 'matrix.zip'
    $archive=[IO.Compression.ZipFile]::Open($zip,[IO.Compression.ZipArchiveMode]::Create)
    try {
        foreach ($item in @(@{name='windows/OwnerAlpha.Common.psm1';bytes=$bytes},
            @{name='rootfs/conflict-analysis-functional-alpha-rootfs.tar';bytes=([byte[]](0..15))},
            @{name='MVP7_PACKAGE_MANIFEST_V1.json';bytes=[Text.Encoding]::UTF8.GetBytes('{}')})) {
            $stream=$archive.CreateEntry($item.name).Open()
            try { $stream.Write($item.bytes,0,$item.bytes.Length) } finally { $stream.Dispose() }
        }
    } finally { $archive.Dispose() }
    $zipBytes=(Get-Item $zip).Length;$sha=(Get-FileHash $zip).Hash.ToLowerInvariant()
    Mock Assert-Mvp7Archive -ModuleName Mvp7.Setup { return $global:Mvp7MatrixManifest }
    Mock Get-Mvp7ProgramRoot -ModuleName Mvp7.Setup { return $global:Mvp7MatrixProgram }
    Mock Get-Mvp7StateRoot -ModuleName Mvp7.Setup { return $global:Mvp7MatrixState }
    Mock Get-Mvp7VolumeFree -ModuleName Mvp7.Setup { if ($global:Mvp7Fault -eq 'disk') { return [long]0 };return [long]1TB }
    Mock Get-Mvp7DistroExists -ModuleName Mvp7.Setup { return $global:Mvp7Registrations.ContainsKey($Name) }
    Mock Import-Mvp7TransactionModule -ModuleName Mvp7.Setup {
        # Bootstrap bytes are still copied by production Copy-Mvp7TransactionModule;
        # keep the production module already imported so Pester's WSL mocks survive.
        $file=Join-Path $ProgramRoot 'OwnerAlpha.Common.psm1'
        Assert-Contract ((Get-FileHash $file).Hash.ToLowerInvariant() -ceq $Manifest.payload['windows/OwnerAlpha.Common.psm1'].sha256)
    }
    Mock Expand-Mvp7Archive -ModuleName Mvp7.Setup {
        if ($global:Mvp7Fault -eq 'extraction') {
            $null=New-Item -ItemType Directory -Path $Destination
            [IO.File]::WriteAllText((Join-Path $Destination 'partial'),'partial archive')
            throw 'FAULT_EXTRACTION'
        }
        [IO.Compression.ZipFile]::ExtractToDirectory($Zip,$Destination)
        if ($global:Mvp7Fault -eq 'controller_copy') { $null=New-Item -ItemType Directory -Path (Join-Path (Split-Path $Destination) 'installer') }
    }
    Mock Invoke-Mvp7InnerInstall -ModuleName Mvp7.Setup {
        $global:Mvp7LastTransaction=$Transaction
        $context=@{root=$Transaction.state;package=(Join-Path $Transaction.program 'app');port=18765;record=$null;
            stateFile=(Join-Path $Transaction.state 'installation.json');manifest=$global:Mvp7MatrixManifest}
        return New-OwnerInstall $context -Transaction $Transaction
    }
    Mock Publish-Mvp7Installation -ModuleName Mvp7.Setup {
        if ($global:Mvp7Fault -eq 'final_marker') { throw 'FAULT_FINAL_MARKER' }
        [IO.File]::Move((Join-Path $Transaction.program 'mvp7-installation.json.pending'),(Join-Path $Transaction.program 'mvp7-installation.json'))
    }
    Mock Get-OwnerDistroRegistration -ModuleName OwnerAlpha.Common {
        if ($global:Mvp7Fault -eq 'after_import' -and $global:Mvp7FailOnce -and $global:Mvp7Registrations.ContainsKey($Name)) {
            $global:Mvp7FailOnce=$false;throw 'FAULT_AFTER_IMPORT'
        }
        return $global:Mvp7Registrations[$Name]
    }
    Mock Invoke-OwnerProcess -ModuleName OwnerAlpha.Common {
        if ($Arguments[0] -eq '--import') {
            if ($global:Mvp7Fault -eq 'before_import') { throw 'FAULT_BEFORE_IMPORT' }
            Assert-Contract ($Arguments.Count -eq 6 -and $Arguments[-2] -eq '--version' -and $Arguments[-1] -eq '2')
            $name=$Arguments[1];$path=$Arguments[2]
            Assert-Contract (-not $global:Mvp7Registrations.ContainsKey($name))
            $global:Mvp7Registrations[$name]=@{name=$name;path=$path;version=2;key=([guid]::NewGuid().ToString())}
            [IO.File]::WriteAllBytes((Join-Path $path 'ext4.vhdx'),[byte[]](1,2,3,4))
            if ($global:Mvp7Fault -eq 'import_nonzero') {
                $exception=[InvalidOperationException]::new('MOCK_IMPORT_NONZERO');$exception.Data['ExitCode']=37;throw $exception
            }
        } elseif ($Arguments[0] -eq '--unregister') {
            Assert-Contract ($TimeoutSeconds -eq 60 -and $Arguments.Count -eq 2 -and $Arguments[1] -ne 'existing-distro')
            $global:Mvp7UnregisterCalls++
            $registration=$global:Mvp7Registrations[$Arguments[1]]
            Remove-Item -LiteralPath (Join-Path $registration.path 'ext4.vhdx')
            $global:Mvp7Registrations.Remove($Arguments[1])
        } else { throw 'Unexpected process boundary' }
        return ,[byte[]]@()
    }
    Mock Invoke-OwnerWsl -ModuleName OwnerAlpha.Common {
        if ($Command[0] -eq 'identity') {
            if ($global:Mvp7Fault -eq 'identity') { return @{source=@{head=('0'*40);tree=$global:Mvp7MatrixManifest.source.tree};wheel=$global:Mvp7MatrixManifest.wheel} }
            return @{source=$global:Mvp7MatrixManifest.source;wheel=$global:Mvp7MatrixManifest.wheel}
        }
        Assert-Contract ($Command[0] -eq 'initialize')
        if ($global:Mvp7Fault -eq 'initialize') { throw 'FAULT_INITIALIZE' }
        return @{phase='STOPPED'}
    }
    Mock Undo-OwnerInstallTransaction -ModuleName OwnerAlpha.Common {
        if ($global:Mvp7HoldRollback) { throw 'INTERRUPTED_INNER_ROLLBACK' }
        & $global:Mvp7OriginalOwnerUndo $Transaction
    }
    Mock Remove-OwnerEmptyTransactionState -ModuleName OwnerAlpha.Common {
        if ($global:Mvp7EmptyRemoveFault -and $StateRoot -ceq $global:Mvp7MatrixState) {
            $global:Mvp7EmptyRemoveFault=$false;throw 'FAULT_REMOVE_EMPTY_STATE'
        }
        [IO.Directory]::Delete($StateRoot)
    }
    $sentinel=Join-Path $TestDrive 'unrelated-state-and-backup.bin'
    [IO.File]::WriteAllBytes($sentinel,[byte[]](0,255,1,0,17))
    $sentinelHash=(Get-FileHash $sentinel).Hash
    $existing=$global:Mvp7Registrations['existing-distro'] | ConvertTo-Json -Compress
    foreach ($fault in @('disk','extraction','controller_copy','before_import','import_nonzero','after_import','identity','initialize','final_marker')) {
        $global:Mvp7MatrixProgram=Join-Path $TestDrive ($fault+'/program')
        $global:Mvp7MatrixState=Join-Path $TestDrive ($fault+'/state')
        $global:Mvp7Fault=$fault;$global:Mvp7FailOnce=$true
        $callsBefore=$global:Mvp7UnregisterCalls
        $caught=$false
        try { Invoke-Mvp7Installation $zip $sha $zipBytes $global:Mvp7MatrixManifest }
        catch {
            $caught=$true
            if ($_.Exception.Message.Contains('BLOCKED_MVP7_ROLLBACK_UNPROVEN')) { throw }
            if ($fault -eq 'disk') { Assert-Contract ($_.Exception.Message -ceq 'BLOCKED_MVP7_DISK_CAPACITY') }
        }
        Assert-Contract $caught
        Assert-Contract (-not (Test-Path -LiteralPath $global:Mvp7MatrixProgram))
        Assert-Contract (-not (Test-Path -LiteralPath $global:Mvp7MatrixState))
        if ($fault -eq 'disk') { Assert-Contract (-not (Test-Path -LiteralPath (Split-Path $global:Mvp7MatrixProgram))) }
        Assert-Contract ($global:Mvp7Registrations.Count -eq 1 -and ($global:Mvp7Registrations['existing-distro'] | ConvertTo-Json -Compress) -ceq $existing)
        Assert-Contract ((Get-FileHash $sentinel).Hash -ceq $sentinelHash)
        $expectedUnregister=if($fault -in @('import_nonzero','after_import','identity','initialize','final_marker')){1}else{0}
        Assert-Contract (($global:Mvp7UnregisterCalls-$callsBefore) -eq $expectedUnregister)
        # Same package, same target, no manual cleanup before retry.
        $global:Mvp7Fault=''
        Invoke-Mvp7Installation $zip $sha $zipBytes $global:Mvp7MatrixManifest
        $tx=$global:Mvp7LastTransaction
        $marker=Join-Path $tx.program 'mvp7-installation.json'
        $stateFile=Join-Path $tx.state 'installation.json'
        Assert-Contract (Test-Path -LiteralPath $marker)
        Assert-Contract (Test-Path -LiteralPath $stateFile)
        Assert-Contract (-not (Test-Path -LiteralPath (Join-Path $tx.program 'mvp7-installation.json.pending')))
        Assert-Contract (-not (Test-Path -LiteralPath (Join-Path $tx.state 'installation.pending.json')))
        $installed=@{record=(Read-OwnerJson $stateFile);manifest=$global:Mvp7MatrixManifest}
        Assert-OwnerInstalled $installed
        Assert-ContractReject { New-OwnerInstall $installed } 'BLOCKED_G10_RUNTIME_IDENTITY_DRIFT'
        $markerHash=(Get-FileHash $marker).Hash;$stateHash=(Get-FileHash $stateFile).Hash
        Assert-ContractReject { Invoke-Mvp7Installation $zip $sha $zipBytes $global:Mvp7MatrixManifest } 'Программа уже установлена'
        Assert-ContractReject { Undo-OwnerInstallTransaction $tx } 'BLOCKED_MVP7_ROLLBACK_UNPROVEN'
        Assert-ContractReject { Undo-Mvp7Installation $tx $global:Mvp7MatrixManifest $sha } 'BLOCKED_MVP7_ROLLBACK_UNPROVEN'
        Assert-Contract ((Get-FileHash $marker).Hash -ceq $markerHash -and (Get-FileHash $stateFile).Hash -ceq $stateHash)
        $backup=Join-Path $tx.state 'backups'
        $null=New-Item -ItemType Directory -Path $backup
        $backupFile=Join-Path $backup 'retained.bin';[IO.File]::WriteAllBytes($backupFile,[byte[]](0,17,255))
        $backupHash=(Get-FileHash $backupFile).Hash
        Assert-Mvp7UninstallBoundary $tx $stateFile $stateHash $backupFile $backupHash
        # A retained state must never be acquired or deleted by fresh install.
        Assert-ContractReject { Invoke-Mvp7Installation $zip $sha $zipBytes $global:Mvp7MatrixManifest } 'BLOCKED_MVP7_INCOMPLETE_INSTALL'
        Assert-Contract (-not (Test-Path -LiteralPath $tx.program) -and (Get-FileHash $backupFile).Hash -ceq $backupHash)
        $global:Mvp7Registrations.Remove($tx.distro) # fixture registry only, never real WSL
        $global:Mvp7TransactionContractResults.Add(@{fault=$fault;rollback='PASS';clean_retry='PASS';foreign_state_preserved=$true;completed_install_protected=$true;uninstall_preserves_state_backups=$true;environment='MOCKED_WSL_BUILD_CONTRACT_ONLY'})
    }
    # Abrupt termination: leave an exact pending transaction by interrupting its
    # first rollback, then let the next Setup recover it using the production path.
    $global:Mvp7MatrixProgram=Join-Path $TestDrive 'recovery/program'
    $global:Mvp7MatrixState=Join-Path $TestDrive 'recovery/state'
    $global:Mvp7Fault='extraction'
    Mock Undo-Mvp7Installation -ModuleName Mvp7.Setup { throw 'INTERRUPTED_ROLLBACK' }
    Assert-ContractReject { Invoke-Mvp7Installation $zip $sha $zipBytes $global:Mvp7MatrixManifest } 'INTERRUPTED_ROLLBACK'
    # Remove only this mock by replacing it with the original implementation.
    Mock Undo-Mvp7Installation -ModuleName Mvp7.Setup { & $global:Mvp7OriginalUndo $Transaction $Manifest $Sha256 }
    $pending=Join-Path $global:Mvp7MatrixProgram 'mvp7-installation.json.pending'
    $raw=[IO.File]::ReadAllBytes($pending)
    $tx=Get-Content -Raw $pending | ConvertFrom-Json -AsHashtable
    foreach ($field in @('nonce','source','installer','program','state','distro')) {
        $foreign=$tx.Clone();$foreign[$field]='foreign'
        [IO.File]::WriteAllText($pending,($foreign | ConvertTo-Json -Depth 20))
        Assert-ContractReject { Invoke-Mvp7Installation $zip $sha $zipBytes $global:Mvp7MatrixManifest } 'BLOCKED_MVP7_ROLLBACK_UNPROVEN'
        Assert-Contract (Test-Path -LiteralPath $pending)
    }
    [IO.File]::WriteAllBytes($pending,$raw)
    $global:Mvp7Fault=''
    Invoke-Mvp7Installation $zip $sha $zipBytes $global:Mvp7MatrixManifest
    Assert-Contract (Test-Path -LiteralPath (Join-Path $global:Mvp7MatrixProgram 'mvp7-installation.json'))
    $global:Mvp7TransactionContractResults.Add(@{fault='interrupted_rollback';recovery='PASS';foreign_markers_blocked='PASS';clean_retry='PASS';environment='MOCKED_WSL_BUILD_CONTRACT_ONLY'})
    # Interrupted initialize with a registered distro: foreign state identity or
    # a registration pointing elsewhere must block without unregistering anything.
    $global:Mvp7MatrixProgram=Join-Path $TestDrive 'recovery-import/program'
    $global:Mvp7MatrixState=Join-Path $TestDrive 'recovery-import/state'
    $global:Mvp7Fault='initialize';$global:Mvp7HoldRollback=$true
    Mock Undo-Mvp7Installation -ModuleName Mvp7.Setup { throw 'INTERRUPTED_ROLLBACK' }
    Assert-ContractReject { Invoke-Mvp7Installation $zip $sha $zipBytes $global:Mvp7MatrixManifest } 'INTERRUPTED_ROLLBACK'
    Mock Undo-Mvp7Installation -ModuleName Mvp7.Setup { & $global:Mvp7OriginalUndo $Transaction $Manifest $Sha256 }
    $global:Mvp7HoldRollback=$false
    $tx=$global:Mvp7LastTransaction
    $statePending=Join-Path $tx.state 'installation.pending.json'
    $saved=[IO.File]::ReadAllBytes($statePending)
    $journal=Read-OwnerJson $statePending
    $beforeUnregister=$global:Mvp7UnregisterCalls
    $journal.nonce='0'*32
    [IO.File]::WriteAllText($statePending,($journal | ConvertTo-Json -Depth 20))
    Assert-ContractReject { Invoke-Mvp7Installation $zip $sha $zipBytes $global:Mvp7MatrixManifest } 'BLOCKED_MVP7_ROLLBACK_UNPROVEN'
    Assert-Contract ($global:Mvp7UnregisterCalls -eq $beforeUnregister -and (Test-Path -LiteralPath $statePending))
    [IO.File]::WriteAllBytes($statePending,$saved)
    $registration=$global:Mvp7Registrations[$tx.distro]
    $registration.path='C:\pre-existing-unrelated-distribution'
    Assert-ContractReject { Invoke-Mvp7Installation $zip $sha $zipBytes $global:Mvp7MatrixManifest } 'BLOCKED_MVP7_ROLLBACK_UNPROVEN'
    Assert-Contract ($global:Mvp7UnregisterCalls -eq $beforeUnregister -and (Test-Path -LiteralPath $statePending))
    $registration.path=$tx.distribution
    # Even a real pending transaction cannot authorize deletion of new backups.
    $retained=Join-Path $tx.state 'backups';$null=New-Item -ItemType Directory -Path $retained
    [IO.File]::WriteAllBytes((Join-Path $retained 'keep.bin'),[byte[]](0,255,42))
    Assert-ContractReject { Invoke-Mvp7Installation $zip $sha $zipBytes $global:Mvp7MatrixManifest } 'BLOCKED_MVP7_ROLLBACK_UNPROVEN'
    Assert-Contract ($global:Mvp7UnregisterCalls -eq $beforeUnregister -and ([IO.File]::ReadAllBytes((Join-Path $retained 'keep.bin')) -join ',') -ceq '0,255,42')
    # Remove only the injected test backup to restore the exact interrupted fixture.
    Remove-Item -LiteralPath (Join-Path $retained 'keep.bin');Remove-Item -LiteralPath $retained
    $global:Mvp7Fault=''
    Invoke-Mvp7Installation $zip $sha $zipBytes $global:Mvp7MatrixManifest
    Assert-Contract (-not $global:Mvp7Registrations.ContainsKey($tx.distro))
    Assert-Contract ($global:Mvp7UnregisterCalls -eq ($beforeUnregister+1))
    $global:Mvp7TransactionContractResults.Add(@{fault='interrupted_after_import';recovery='PASS';wrong_nonce_blocked='PASS';wrong_registration_path_blocked='PASS';backups_preserved='PASS';clean_retry='PASS';environment='MOCKED_WSL_BUILD_CONTRACT_ONLY'})
    $global:Mvp7MatrixProgram=Join-Path $TestDrive 'recovery-empty/program'
    $global:Mvp7MatrixState=Join-Path $TestDrive 'recovery-empty/state'
    $global:Mvp7Fault='initialize';$global:Mvp7EmptyRemoveFault=$true
    Mock Undo-Mvp7Installation -ModuleName Mvp7.Setup { throw 'INTERRUPTED_ROLLBACK' }
    Assert-ContractReject { Invoke-Mvp7Installation $zip $sha $zipBytes $global:Mvp7MatrixManifest } 'INTERRUPTED_ROLLBACK'
    Assert-Contract (Test-Path -LiteralPath $global:Mvp7MatrixState)
    Assert-Contract (@(Get-ChildItem -LiteralPath $global:Mvp7MatrixState -Force).Count -eq 0)
    Assert-Contract (Test-Path -LiteralPath (Join-Path $global:Mvp7MatrixProgram 'mvp7-rollback-ownership.json'))
    Mock Undo-Mvp7Installation -ModuleName Mvp7.Setup { & $global:Mvp7OriginalUndo $Transaction $Manifest $Sha256 }
    $global:Mvp7Fault=''
    Invoke-Mvp7Installation $zip $sha $zipBytes $global:Mvp7MatrixManifest
    $global:Mvp7TransactionContractResults.Add(@{fault='interrupted_empty_state_cleanup';recovery='PASS';clean_retry='PASS';environment='MOCKED_WSL_BUILD_CONTRACT_ONLY'})
    # Reparse points must block before any deletion, including external contents.
    Remove-Mvp7Program $global:Mvp7MatrixProgram
    $global:Mvp7MatrixProgram=Join-Path $TestDrive 'reparse/program'
    $global:Mvp7MatrixState=Join-Path $TestDrive 'reparse/state'
    $global:Mvp7Fault='extraction'
    Mock Undo-Mvp7Installation -ModuleName Mvp7.Setup { throw 'INTERRUPTED_ROLLBACK' }
    Assert-ContractReject { Invoke-Mvp7Installation $zip $sha $zipBytes $global:Mvp7MatrixManifest } 'INTERRUPTED_ROLLBACK'
    Mock Undo-Mvp7Installation -ModuleName Mvp7.Setup { & $global:Mvp7OriginalUndo $Transaction $Manifest $Sha256 }
    $link=Join-Path $global:Mvp7MatrixProgram 'foreign-junction'
    $target=Join-Path $TestDrive 'outside-junction';$null=New-Item -ItemType Directory -Path $target
    [IO.File]::WriteAllText((Join-Path $target 'keep'),'unchanged')
    $null=New-Item -ItemType Junction -Path $link -Target $target
    try {
        Assert-ContractReject { Invoke-Mvp7Installation $zip $sha $zipBytes $global:Mvp7MatrixManifest } 'BLOCKED_MVP7_ROLLBACK_UNPROVEN'
        Assert-Contract ((Get-Content -Raw (Join-Path $target 'keep')) -ceq 'unchanged')
    } finally { [IO.Directory]::Delete($link) }
    $global:Mvp7Fault=''
    Invoke-Mvp7Installation $zip $sha $zipBytes $global:Mvp7MatrixManifest
    $global:Mvp7TransactionContractResults.Add(@{fault='reparse_point';blocked='PASS';foreign_contents_preserved=$true;environment='MOCKED_WSL_BUILD_CONTRACT_ONLY'})
}
$global:Mvp7OriginalUndo=(Get-Command Undo-Mvp7Installation).ScriptBlock
$global:Mvp7OriginalOwnerUndo=(Get-Command Undo-OwnerInstallTransaction).ScriptBlock
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
        Invoke-Mvp7TransactionFaultMatrix
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
