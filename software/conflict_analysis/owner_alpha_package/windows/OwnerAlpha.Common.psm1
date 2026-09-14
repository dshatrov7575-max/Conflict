Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$script:Profiles = @('STUDIO_EDITOR','STUDIO_PUBLISHER','PLAYER_ASSESSOR')
$script:ManifestName = 'OWNER_ALPHA_PACKAGE_MANIFEST_V2.json'
$script:BaseHead = '123f2b081ce2a09d7d193f9e4b20644f5802d7fe'
$script:BaseTree = 'd67e39cbb965483f3c9cabcc91f724d8bf986fb4'

function Stop-OwnerGate([string]$Code) { throw [InvalidOperationException]::new($Code) }
function Assert-OwnerGate([bool]$Condition,[string]$Code) {
    if (-not $Condition) { Stop-OwnerGate $Code }
}
function Get-OwnerFileIdentity([string]$Path) {
    $item = Get-Item -LiteralPath $Path -Force
    Assert-OwnerGate (-not $item.PSIsContainer -and -not ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) 'BLOCKED_G10_PACKAGE_MEMBER_DRIFT'
    return @{ bytes=[long]$item.Length; sha256=(Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant() }
}
function Assert-OwnerPath([string]$Path,[string]$Within = '') {
    Assert-OwnerGate ($Path -match '^[A-Za-z]:\\') 'BLOCKED_G10_UNSAFE_PATH'
    try { $full = [IO.Path]::GetFullPath($Path) }
    catch { Stop-OwnerGate 'BLOCKED_G10_UNSAFE_PATH' }
    Assert-OwnerGate ($full -match '^[A-Za-z]:\\' -and $full.Length -lt 190 -and $full -notmatch '[\r\n"]') 'BLOCKED_G10_UNSAFE_PATH'
    if ($Within) {
        $root = [IO.Path]::GetFullPath($Within).TrimEnd('\') + '\'
        Assert-OwnerGate ($full.StartsWith($root,[StringComparison]::OrdinalIgnoreCase)) 'BLOCKED_G10_UNSAFE_PATH'
    }
    $parent = $full
    while ($parent) {
        if (Test-Path -LiteralPath $parent) {
            Assert-OwnerGate (-not ((Get-Item -LiteralPath $parent -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)) 'BLOCKED_G10_UNSAFE_PATH'
        }
        $parent = [IO.Path]::GetDirectoryName($parent)
    }
    return $full
}
function New-OwnerPrivateDirectory([string]$Path) {
    $full = Assert-OwnerPath $Path
    if (Test-Path -LiteralPath $full) {
        Assert-OwnerPrivateDirectory $full
        return $full
    }
    $null = New-Item -ItemType Directory -Path $full
    $sid = [Security.Principal.WindowsIdentity]::GetCurrent().User
    $acl = [Security.AccessControl.DirectorySecurity]::new()
    $acl.SetOwner($sid)
    $acl.SetAccessRuleProtection($true,$false)
    foreach ($principal in @($sid,[Security.Principal.SecurityIdentifier]::new('S-1-5-18'))) {
        $rule = [Security.AccessControl.FileSystemAccessRule]::new($principal,'FullControl','ContainerInherit,ObjectInherit','None','Allow')
        $acl.AddAccessRule($rule)
    }
    Set-Acl -LiteralPath $full -AclObject $acl
    Assert-OwnerPrivateDirectory $full
    return $full
}
function Assert-OwnerPrivateDirectory([string]$Path) {
    $null = Assert-OwnerPath $Path
    $acl = Get-Acl -LiteralPath $Path
    $sid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
    Assert-OwnerGate $acl.AreAccessRulesProtected 'BLOCKED_G10_PROFILE_ISOLATION_GAP'
    Assert-OwnerGate ($acl.GetOwner([Security.Principal.SecurityIdentifier]).Value -eq $sid) 'BLOCKED_G10_PROFILE_ISOLATION_GAP'
    foreach ($rule in $acl.GetAccessRules($true,$true,[Security.Principal.SecurityIdentifier])) {
        Assert-OwnerGate ($rule.IdentityReference.Value -in @($sid,'S-1-5-18') -and $rule.AccessControlType -eq 'Allow') 'BLOCKED_G10_PROFILE_ISOLATION_GAP'
    }
}
function Read-OwnerJson([string]$Path) {
    return Get-Content -LiteralPath $Path -Raw -Encoding utf8 | ConvertFrom-Json -AsHashtable
}
function Write-OwnerJson([string]$Path,[object]$Value) {
    $pending = $Path + '.pending'
    Assert-OwnerGate (-not (Test-Path -LiteralPath $pending)) 'BLOCKED_G10_OPERATION_UNKNOWN'
    [IO.File]::WriteAllText($pending,($Value | ConvertTo-Json -Depth 70 -Compress),[Text.UTF8Encoding]::new($false))
    [IO.File]::Move($pending,$Path,$true)
}
function Invoke-OwnerProcess {
    param([string]$Executable,[string[]]$Arguments,[byte[]]$InputBytes,[string]$InputPath,[string]$OutputPath,[hashtable]$Environment=@{})
    $start = [Diagnostics.ProcessStartInfo]::new()
    $start.FileName = $Executable
    $start.UseShellExecute = $false
    $start.CreateNoWindow = $true
    $start.RedirectStandardInput = $true
    $start.RedirectStandardOutput = $true
    $start.RedirectStandardError = $true
    foreach ($argument in $Arguments) { $start.ArgumentList.Add($argument) }
    foreach ($key in $Environment.Keys) { $start.Environment[$key]=[string]$Environment[$key] }
    $process = [Diagnostics.Process]::new()
    $process.StartInfo = $start
    $null = $process.Start()
    $errorTask = $process.StandardError.ReadToEndAsync()
    $output = if ($OutputPath) { [IO.File]::Open($OutputPath,[IO.FileMode]::CreateNew) } else { [IO.MemoryStream]::new() }
    try {
        $copy = $process.StandardOutput.BaseStream.CopyToAsync($output)
        if ($InputPath) {
            $source = [IO.File]::OpenRead($InputPath)
            try { $source.CopyTo($process.StandardInput.BaseStream) } finally { $source.Dispose() }
        } elseif ($InputBytes) { $process.StandardInput.BaseStream.Write($InputBytes,0,$InputBytes.Length) }
        $process.StandardInput.Close()
        $process.WaitForExit()
        $null = $copy.GetAwaiter().GetResult()
        $null = $errorTask.GetAwaiter().GetResult()
        Assert-OwnerGate ($process.ExitCode -eq 0) 'BLOCKED_G10_RUNTIME_OPERATION_FAILED'
        if (-not $OutputPath) { return ,$output.ToArray() }
    } finally { $output.Dispose(); $process.Dispose() }
}
function Invoke-OwnerWsl {
    param([string]$Distribution,[string[]]$Command,[string]$InputPath,[string]$OutputPath)
    Assert-OwnerGate ($Distribution -match '^Conflict-Alpha-[0-9a-f]{12}-[0-9a-f]{8}$') 'BLOCKED_G10_RUNTIME_IDENTITY_DRIFT'
    $parameters = @{Executable="$env:WINDIR\System32\wsl.exe";Arguments=@('--distribution',$Distribution,'--user','root','--exec','/opt/owner-alpha/owner-alpha-supervisor.sh')+$Command}
    if ($InputPath) { $parameters.InputPath=$InputPath }
    if ($OutputPath) { $parameters.OutputPath=$OutputPath }
    $bytes = Invoke-OwnerProcess @parameters
    if (-not $OutputPath) {
        try { return [Text.Encoding]::UTF8.GetString($bytes) | ConvertFrom-Json -AsHashtable }
        finally { if ($bytes) { [Array]::Clear($bytes,0,$bytes.Length) } }
    }
}
function Get-OwnerLaunchAdmission([string]$PackageRoot) {
    $policy = Get-ExecutionPolicy
    $list = @(Get-ExecutionPolicy -List | Select-Object Scope,ExecutionPolicy)
    Assert-OwnerGate ($policy -in @('RemoteSigned','AllSigned','Unrestricted')) 'BLOCKED_G10_LAUNCH_ADMISSION'
    $observations = @()
    foreach ($file in Get-ChildItem -LiteralPath (Join-Path $PackageRoot 'windows') -File) {
        if ($file.Extension -notin @('.ps1','.psm1')) { continue }
        $zone = @(Get-Content -LiteralPath $file.FullName -Stream Zone.Identifier -ErrorAction SilentlyContinue)
        $signature = Get-AuthenticodeSignature -LiteralPath $file.FullName
        $marked = [bool]($zone -match 'ZoneId=[3-4]')
        $required = $policy -eq 'AllSigned' -or $marked
        $trusted = $false
        if ($signature.SignerCertificate) {
            $trusted = $signature.SignerCertificate.Thumbprint -in @(Get-ChildItem Cert:\CurrentUser\TrustedPublisher,Cert:\LocalMachine\TrustedPublisher).Thumbprint
        }
        Assert-OwnerGate (-not $required -or ($signature.Status -eq 'Valid' -and $trusted)) 'BLOCKED_G10_LAUNCH_ADMISSION'
        $observations += @{name=$file.Name;zone=$zone;signature=[string]$signature.Status;trustedPublisher=$trusted}
    }
    return @{shell=(Get-Process -Id $PID).Path;psVersion=$PSVersionTable.PSVersion.ToString();effectivePolicy=[string]$policy;policies=$list;files=$observations}
}
function Assert-OwnerManifest([string]$PackageRoot) {
    $root = Assert-OwnerPath $PackageRoot
    $manifest = Read-OwnerJson (Join-Path $root $script:ManifestName)
    Assert-OwnerGate ($manifest.schema -eq 'OWNER_ALPHA_PACKAGE_MANIFEST_V2' -and $manifest.package_version -eq '0.1.0-alpha.1') 'BLOCKED_G10_RUNTIME_IDENTITY_DRIFT'
    Assert-OwnerGate ($manifest.source.base_head -eq $script:BaseHead -and $manifest.source.base_tree -eq $script:BaseTree -and $manifest.source.head -match '^[0-9a-f]{40}$' -and $manifest.source.head -ne $script:BaseHead) 'BLOCKED_G10_PARENT_IDENTITY_DRIFT'
    $expected = @($manifest.payload.Keys) + $script:ManifestName + 'SHA256SUMS'
    $fixed = @('START_HERE_RU.txt','manifest.schema.json','SBOM.cdx.json','THIRD_PARTY_NOTICES.txt','evidence/package-build-evidence.json','rootfs/conflict-analysis-functional-alpha-rootfs.tar',
        'INSTALL_CONFLICT_ANALYSIS.cmd','START_CONFLICT_ANALYSIS.cmd','STOP_CONFLICT_ANALYSIS.cmd','DIAGNOSTICS.cmd','BACKUP_CONFLICT_ANALYSIS.cmd','RESTORE_CONFLICT_ANALYSIS.cmd','RESET_CONFLICT_ANALYSIS.cmd','UNINSTALL_CONFLICT_ANALYSIS.cmd',
        'windows/OwnerAlpha.Common.psm1','windows/OwnerAlpha.Cdp.psm1','windows/Install-OwnerAlpha.ps1','windows/Start-OwnerAlpha.ps1','windows/Grant-Publisher.ps1','windows/Status-OwnerAlpha.ps1','windows/Stop-OwnerAlpha.ps1','windows/Reset-OwnerAlpha.ps1','windows/Uninstall-OwnerAlpha.ps1')
    Assert-OwnerGate ((@($manifest.payload.Keys | Sort-Object) -join '|') -ceq (@($fixed | Sort-Object) -join '|')) 'BLOCKED_G10_PACKAGE_MEMBER_DRIFT'
    $actual = @(Get-ChildItem -LiteralPath $root -File -Recurse -Force | ForEach-Object { [IO.Path]::GetRelativePath($root,$_.FullName).Replace('\','/') })
    Assert-OwnerGate ((@($expected | Sort-Object) -join '|') -ceq (@($actual | Sort-Object) -join '|')) 'BLOCKED_G10_PACKAGE_MEMBER_DRIFT'
    Assert-OwnerGate (@($expected | ForEach-Object { $_.ToLowerInvariant() } | Sort-Object -Unique).Count -eq $expected.Count) 'BLOCKED_G10_PACKAGE_MEMBER_DRIFT'
    $sums = [Collections.Generic.List[string]]::new()
    foreach ($name in @($manifest.payload.Keys)+$script:ManifestName | Sort-Object) {
        Assert-OwnerGate ($name -notmatch '(^/|\\|:|(^|/)\.\.?(/|$))') 'BLOCKED_G10_PACKAGE_MEMBER_DRIFT'
        $path = Assert-OwnerPath (Join-Path $root $name) $root
        $meta = Get-OwnerFileIdentity $path
        if ($name -ne $script:ManifestName) {
            Assert-OwnerGate ($meta.bytes -eq $manifest.payload[$name].bytes -and $meta.sha256 -ceq $manifest.payload[$name].sha256) 'BLOCKED_G10_PACKAGE_MEMBER_DRIFT'
        }
        $sums.Add($meta.sha256+'  '+$name)
    }
    $sumText = [IO.File]::ReadAllText((Join-Path $root 'SHA256SUMS'))
    Assert-OwnerGate ($sumText -ceq (($sums -join [string][char]10)+[char]10)) 'BLOCKED_G10_PACKAGE_MEMBER_DRIFT'
    return $manifest
}
function Assert-OwnerCapacity([int]$Port) {
    Assert-OwnerGate ($IsWindows -and [Environment]::Is64BitOperatingSystem -and [Environment]::Is64BitProcess -and $PSVersionTable.PSEdition -eq 'Core' -and $PSVersionTable.PSVersion.Major -ge 7) 'BLOCKED_G10_WINDOWS_CAPACITY'
    $os = Get-CimInstance Win32_OperatingSystem
    $computer = Get-CimInstance Win32_ComputerSystem
    $processors = @(Get-CimInstance Win32_Processor)
    Assert-OwnerGate ($os.ProductType -eq 1 -and [int]$os.BuildNumber -ge 22000 -and $os.Caption -match 'Windows 11' -and $computer.SystemType -match 'x64') 'BLOCKED_G10_WINDOWS_CAPACITY'
    Assert-OwnerGate ($computer.HypervisorPresent -or ($processors.VirtualizationFirmwareEnabled -contains $true -and $processors.SecondLevelAddressTranslationExtensions -contains $true)) 'BLOCKED_G10_WINDOWS_CAPACITY'
    $wsl = "$env:WINDIR\System32\wsl.exe"
    $version = Invoke-OwnerProcess $wsl @('--version')
    $listing = Invoke-OwnerProcess $wsl @('--list','--verbose')
    $help = Invoke-OwnerProcess $wsl @('--help')
    $decode = {
        param([byte[]]$Data)
        if ($Data -contains 0) { [Text.Encoding]::Unicode.GetString($Data) } else { [Text.Encoding]::UTF8.GetString($Data) }
    }
    Assert-OwnerGate ((& $decode $listing) -match '(?m)\s2\s*$' -and (& $decode $help) -match '--import') 'BLOCKED_G10_WINDOWS_CAPACITY'
    $edge = @('C:\Program Files\Microsoft\Edge\Application\msedge.exe','C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe') | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    Assert-OwnerGate ([bool]$edge) 'BLOCKED_G10_WINDOWS_CAPACITY'
    $info = (Get-Item -LiteralPath $edge).VersionInfo
    Assert-OwnerGate ([version]$info.ProductVersion -ge [version]'153.0.4234.32') 'BLOCKED_G10_WINDOWS_CAPACITY'
    $stream = [IO.File]::OpenRead($edge)
    try {
        $reader=[IO.BinaryReader]::new($stream); $stream.Position=0x3c
        $offset=$reader.ReadInt32(); $stream.Position=$offset+4
        Assert-OwnerGate ($reader.ReadUInt16() -eq 0x8664) 'BLOCKED_G10_WINDOWS_CAPACITY'
    } finally { $stream.Dispose() }
    Assert-OwnerGate ($Port -ge 1024 -and $Port -le 65535) 'BLOCKED_G10_NETWORK_EXPOSURE'
    return @{caption=$os.Caption;build=$os.BuildNumber;architecture=$computer.SystemType;
             hypervisor=$computer.HypervisorPresent;wslVersion=(& $decode $version);wslList=(& $decode $listing);
             edgePath=$edge;edgeVersion=$info.ProductVersion}
}
function Assert-OwnerPortFree([int]$Port) {
    $listener = [Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback,$Port)
    try { $listener.Start() } catch { Stop-OwnerGate 'BLOCKED_G10_PORT_CONFLICT' }
    finally { $listener.Stop() }
}
function Get-OwnerContext([string]$PackageRoot,[string]$StateRoot='',[int]$Port=8765) {
    $followActive = -not $StateRoot
    $manifest=Assert-OwnerManifest $PackageRoot
    $admission=Get-OwnerLaunchAdmission $PackageRoot
    $capacity=Assert-OwnerCapacity $Port
    if (-not $StateRoot) { $StateRoot=Join-Path $env:LOCALAPPDATA ('ConflictAnalysis\OwnerAlpha\'+$manifest.source.tree.Substring(0,12)) }
    $StateRoot=Assert-OwnerPath $StateRoot
    $stateFile=Join-Path $StateRoot 'installation.json'
    $record=$null
    if (Test-Path -LiteralPath $stateFile) {
        Assert-OwnerPrivateDirectory $StateRoot
        $record=Read-OwnerJson $stateFile
        $meta=Get-OwnerFileIdentity (Join-Path $PackageRoot $script:ManifestName)
        Assert-OwnerGate ($record.manifest.sha256 -ceq $meta.sha256 -and $record.manifest.bytes -eq $meta.bytes) 'BLOCKED_G10_RUNTIME_IDENTITY_DRIFT'
        if ($followActive -and $record.ContainsKey('activeRoot')) {
            $candidate=Assert-OwnerPath $record.activeRoot $StateRoot
            return Get-OwnerContext $PackageRoot $candidate $record.activePort
        }
    }
    return @{package=[IO.Path]::GetFullPath($PackageRoot);manifest=$manifest;admission=$admission;capacity=$capacity;
             root=$StateRoot;stateFile=$stateFile;record=$record;port=$Port}
}
function Confirm-OwnerAction([string]$Action,[string]$Instance,[string]$Confirmation) {
    $expected=$Action+' '+$Instance
    if (-not $Confirmation) { $Confirmation=Read-Host ("Для подтверждения введите: "+$expected) }
    Assert-OwnerGate ($Confirmation -ceq $expected) 'BLOCKED_G10_CONFIRMATION_REQUIRED'
}
function New-OwnerInstall {
    param([hashtable]$Context,[switch]$RestoreEmpty)
    Assert-OwnerGate (-not $Context.record) 'BLOCKED_G10_RUNTIME_IDENTITY_DRIFT'
    Assert-OwnerPortFree $Context.port
    $root=New-OwnerPrivateDirectory $Context.root
    $instance=[guid]::NewGuid().ToString('N').Substring(0,8)
    $distro='Conflict-Alpha-'+$Context.manifest.source.tree.Substring(0,12)+'-'+$instance
    $vhd=New-OwnerPrivateDirectory (Join-Path $root 'distribution')
    $record=@{schema='G10_INSTALLATION_V1';instance=$instance;distribution=$distro;phase='IMPORT_PENDING';port=$Context.port;
              manifest=(Get-OwnerFileIdentity (Join-Path $Context.package $script:ManifestName));
              source=$Context.manifest.source;profiles=@{};backupReceipts=@()}
    Write-OwnerJson $Context.stateFile $record
    $rootfs=Join-Path $Context.package 'rootfs/conflict-analysis-functional-alpha-rootfs.tar'
    $null=Invoke-OwnerProcess "$env:WINDIR\System32\wsl.exe" @('--import',$distro,$vhd,$rootfs,'--version','2')
    $id=Invoke-OwnerWsl $distro @('identity')
    Assert-OwnerGate ($id.source.head -ceq $Context.manifest.source.head -and $id.source.tree -ceq $Context.manifest.source.tree -and $id.wheel.sha256 -ceq $Context.manifest.wheel.sha256) 'BLOCKED_G10_RUNTIME_IDENTITY_DRIFT'
    $command=if($RestoreEmpty){'restore-empty'}else{'initialize'}
    $result=Invoke-OwnerWsl $distro @($command,[string]$Context.port)
    $record.phase=$result.phase
    Write-OwnerJson $Context.stateFile $record
    $Context.record=$record
    return $record
}
function Assert-OwnerInstalled([hashtable]$Context) {
    Assert-OwnerGate ([bool]$Context.record) 'BLOCKED_G10_NOT_INSTALLED'
    $id=Invoke-OwnerWsl $Context.record.distribution @('identity')
    Assert-OwnerGate ($id.source.head -ceq $Context.manifest.source.head -and $id.source.tree -ceq $Context.manifest.source.tree -and $id.wheel.sha256 -ceq $Context.manifest.wheel.sha256) 'BLOCKED_G10_RUNTIME_IDENTITY_DRIFT'
}
function Close-OwnerProfiles([hashtable]$Context) {
    foreach ($profile in $Context.record.profiles.Values) {
        $path=Assert-OwnerPath $profile.path $Context.root
        foreach ($pidValue in $profile.pids) {
            $process=Get-CimInstance Win32_Process -Filter "ProcessId=$pidValue" -ErrorAction SilentlyContinue
            if ($process) {
                Assert-OwnerGate ($process.ExecutablePath -eq $Context.capacity.edgePath -and $process.CommandLine.Contains($path)) 'BLOCKED_G10_PROFILE_ISOLATION_GAP'
                $native=Get-Process -Id $pidValue
                $null=$native.CloseMainWindow()
                if (-not $native.WaitForExit(15000)) { Stop-OwnerGate 'BLOCKED_G10_OPERATION_BUSY' }
            }
        }
        Assert-OwnerGate (-not @(Get-CimInstance Win32_Process -Filter "Name='msedge.exe'" | Where-Object { $_.CommandLine -and $_.CommandLine.Contains($path) }).Count) 'BLOCKED_G10_OPERATION_BUSY'
        if (Test-Path -LiteralPath $path) {
            $checked=Assert-OwnerPath $path (Join-Path $Context.root 'profiles')
            Remove-Item -LiteralPath $checked -Recurse -Force
        }
    }
    $Context.record.profiles=@{}
    Write-OwnerJson $Context.stateFile $Context.record
}
function Backup-OwnerState {
    param([hashtable]$Context,[string]$Confirmation)
    Assert-OwnerInstalled $Context
    Confirm-OwnerAction 'BACKUP' $Context.record.instance $Confirmation
    $backupRoot=New-OwnerPrivateDirectory (Join-Path $Context.root 'backups')
    $destination=Join-Path $backupRoot ([guid]::NewGuid().ToString('N')+'.tar')
    Invoke-OwnerWsl -Distribution $Context.record.distribution -Command @('backup') -OutputPath $destination
    $meta=Get-OwnerFileIdentity $destination
    $receipt=@{path=$destination;bytes=$meta.bytes;sha256=$meta.sha256;manifest=$Context.record.manifest;
               sourceInstance=$Context.record.instance;sourceDistribution=$Context.record.distribution}
    $Context.record.backupReceipts=@($Context.record.backupReceipts)+@($receipt)
    $Context.record.phase='STOPPED'
    Write-OwnerJson $Context.stateFile $Context.record
    return $receipt
}
function Stop-OwnerState([hashtable]$Context) {
    Assert-OwnerInstalled $Context
    $result=Invoke-OwnerWsl $Context.record.distribution @('stop')
    Assert-OwnerGate ($result.sessions_revoked -eq $true) 'BLOCKED_G10_ACCESS_PROVISIONING_GAP'
    Close-OwnerProfiles $Context
    $Context.record.phase='STOPPED'
    Write-OwnerJson $Context.stateFile $Context.record
    return @{phase='STOPPED';instance=$Context.record.instance;sessions_revoked=$true}
}
Export-ModuleMember -Function *-Owner*
