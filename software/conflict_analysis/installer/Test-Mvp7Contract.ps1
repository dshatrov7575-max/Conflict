[CmdletBinding()]
param([Parameter(Mandatory)][string]$EvidenceRoot,[string]$InnerZip='')
$ErrorActionPreference='Stop'
Import-Module (Join-Path $PSScriptRoot 'Mvp7.Setup.psm1') -Force
$null=New-Item -ItemType Directory -Path $EvidenceRoot -Force
$results=[Collections.Generic.List[object]]::new()
function Check([string]$Name,[scriptblock]$Body) {
    & $Body
    $results.Add(@{name=$Name;result='PASS';environment='BUILD_CONTRACT_ONLY'})
}
function Reject([scriptblock]$Body) {
    $rejected=$false
    try { & $Body } catch { $rejected=$true }
    if (-not $rejected) { throw 'Ожидался отказ контрактной проверки.' }
}
Check 'PowerShell parse all installer and packaged scripts' {
    $paths=@(Get-ChildItem -LiteralPath $PSScriptRoot -Filter '*.ps*')+@(Get-ChildItem -LiteralPath (Join-Path $PSScriptRoot '../owner_alpha_package/windows') -Filter '*.ps*')
    foreach ($path in $paths) {
        $tokens=$null;$errors=$null
        $null=[Management.Automation.Language.Parser]::ParseFile($path.FullName,[ref]$tokens,[ref]$errors)
        if ($errors.Count) { throw ($errors | Out-String) }
    }
}
Check 'Unsafe Windows path rejected' {
    Reject { Assert-Mvp7Path '\\server\share\package' }
    Reject { Assert-Mvp7Path 'C:\bad"path' }
}
Check 'Windows Server is never Windows 11 E2E' {
    $os=Get-CimInstance Win32_OperatingSystem
    if ($os.ProductType -ne 1) { Reject { Assert-Mvp7Host } }
    # On a developer Windows 11 host this does not attempt a positive E2E.
}
Check 'Program removal preserves real external state and backup bytes' {
    $previous=$env:LOCALAPPDATA
    try {
        $env:LOCALAPPDATA=Join-Path $EvidenceRoot 'isolated-contract-user'
        $program=Get-Mvp7ProgramRoot;$state=Get-Mvp7StateRoot
        $null=New-Item -ItemType Directory -Path $program,(Join-Path $state 'backups') -Force
        $stateFile=Join-Path $state 'installation.json';$backup=Join-Path $state 'backups/private.bin'
        [IO.File]::WriteAllText($stateFile,'contract-state')
        [IO.File]::WriteAllBytes($backup,[byte[]](0,255,17,0))
        $before=@((Get-FileHash -LiteralPath $stateFile).Hash,(Get-FileHash -LiteralPath $backup).Hash)
        @{source='85a253126bf270664c4786d159994e7359b5d2c5';program=$program} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $program 'mvp7-installation.json') -Encoding utf8
        Reject { Remove-Mvp7Program $state }
        Remove-Mvp7Program $program
        Assert-Mvp7 (-not (Test-Path -LiteralPath $program)) 'Программа не удалена.'
        Assert-Mvp7 (((Get-FileHash -LiteralPath $stateFile).Hash -ceq $before[0]) -and ((Get-FileHash -LiteralPath $backup).Hash -ceq $before[1])) 'Состояние изменилось.'
    } finally { $env:LOCALAPPDATA=$previous }
}
if ($InnerZip) {
    Check 'Exact inner payload verified without installation or WSL' {
        $sha=(Get-FileHash -LiteralPath $InnerZip).Hash.ToLowerInvariant();$bytes=(Get-Item -LiteralPath $InnerZip).Length
        $null=Assert-Mvp7Archive $InnerZip $sha $bytes
        Reject { Assert-Mvp7Archive $InnerZip ('0'*64) $bytes }
        Reject { Assert-Mvp7Archive $InnerZip $sha ($bytes+1) }
    }
}
Check 'Transactional install fault matrix and clean retry (mocked WSL only)' {
    if (-not (Get-Variable -Name Mvp7TransactionContractResults -Scope Global -ErrorAction SilentlyContinue)) { throw 'Pester transaction matrix evidence required' }
    if ($global:Mvp7TransactionContractResults.Count -ne 14) { throw 'Incomplete transaction fault matrix' }
    $runtimeCopy=@($global:Mvp7TransactionContractResults | Where-Object { $_.fault -eq 'runtime_copy' })
    if ($runtimeCopy.Count -ne 1 -or $runtimeCopy[0].runtime_copy_interruption -ne 'PASS' -or $runtimeCopy[0].retry_after_runtime_copy_failure -ne 'PASS') { throw 'Runtime copy rollback contract missing' }
}
$report=@{transaction_fault_matrix=$global:Mvp7TransactionContractResults.ToArray();host_powershell_required=$false;powershell_system_install=$false;powershell_path_mutation=$false;powershell_network_install=$false;private_runtime_shortcuts=$true;private_runtime_uninstall_bootstrap=$true;disk_capacity_policy=@{program_reserve_bytes=[long]512MB;state_reserve_bytes=[long]1GB;same_volume='sum both reservations'};WINDOWS_CONTRACT='PASS';tests=$results.ToArray();WINDOWS11_WSL2_E2E='NOT_EXECUTED';CLEAN_PC_SMOKE='NOT_EXECUTED';PARTNER_RELEASE_READY=$false}
$report | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath (Join-Path $EvidenceRoot 'windows-contract.json') -Encoding utf8
$report | ConvertTo-Json -Depth 12
