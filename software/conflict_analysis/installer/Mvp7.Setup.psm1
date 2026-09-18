Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$script:SourceC='85a253126bf270664c4786d159994e7359b5d2c5'
$script:TreeC='5567183dbe16fc6c7c8caac051b7694f37b92457'
function Assert-Mvp7([bool]$Ok,[string]$Message) { if (-not $Ok) { throw $Message } }
function Get-Mvp7ProgramRoot { Join-Path $env:LOCALAPPDATA 'Programs\ConflictPartnerDemo\MVP7' }
function Get-Mvp7StateRoot { Join-Path $env:LOCALAPPDATA 'ConflictPartnerDemoState\mvp7' }
function Assert-Mvp7Path([string]$Path) {
    $full=[IO.Path]::GetFullPath($Path)
    Assert-Mvp7 ($full -match '^[A-Za-z]:\\' -and $full -notmatch '[\r\n"]') 'Недопустимый путь.'
    $parent=$full
    while ($parent) {
        if (Test-Path -LiteralPath $parent) {
            Assert-Mvp7 (-not ((Get-Item -Force -LiteralPath $parent).Attributes -band [IO.FileAttributes]::ReparsePoint)) 'Ссылки и перенаправления каталогов запрещены.'
        }
        $parent=[IO.Path]::GetDirectoryName($parent)
    }
    return $full
}
function Invoke-Mvp7WslProbe([string]$Executable,[string]$Option) {
    $text=(& $Executable $Option 2>&1 | Out-String) -replace [char]0,''
    Assert-Mvp7 ($LASTEXITCODE -eq 0) ('BLOCKED_MVP7_WSL_CAPABILITY: WSL не ответила на '+$Option)
    return $text
}
function Convert-Mvp7RuntimeRelativePath([string]$RelativePath) {
    Assert-Mvp7 ($RelativePath -and $RelativePath -ceq $RelativePath.Normalize() -and $RelativePath -notmatch '^[\\/]|(^|[\\/])\.\.([\\/]|$)|[\x00-\x1f:]|[\\/]$|[. ]([\\/]|$)') 'Повреждён манифест встроенной среды PowerShell.'
    return ($RelativePath -replace '/', [IO.Path]::DirectorySeparatorChar)
}
function Read-Mvp7RuntimeManifest([string]$RuntimeManifest) {
    $path=Assert-Mvp7Path $RuntimeManifest
    $manifest=Get-Content -LiteralPath $path -Raw -Encoding utf8 | ConvertFrom-Json -AsHashtable
    Assert-Mvp7 ($manifest.schema -ceq 'MVP7_POWERSHELL_RUNTIME_MANIFEST_V1') 'Повреждён манифест встроенной среды PowerShell.'
    Assert-Mvp7 ($manifest.archive.version -ceq '7.6.6' -and $manifest.archive.bytes -eq 106328873 -and $manifest.archive.sha256 -ceq '02fe458be20493fbdf43f61ea20610b811ee6c738ab1676c61b9cfcd1a33c860') 'Повреждена встроенная среда PowerShell.'
    return $manifest
}
function Assert-Mvp7BundledPowerShellProcess {
    Assert-Mvp7 ($PSVersionTable.PSEdition -ceq 'Core' -and $PSVersionTable.PSVersion.ToString() -ceq '7.6.6' -and [Environment]::Is64BitProcess -and [Runtime.InteropServices.RuntimeInformation]::ProcessArchitecture.ToString() -ceq 'X64') 'Повреждена встроенная среда PowerShell.'
}
function Assert-Mvp7Runtime([string]$RuntimeRoot,[string]$RuntimeManifest,[switch]$CurrentProcess) {
    $root=(Assert-Mvp7Path $RuntimeRoot).TrimEnd([IO.Path]::DirectorySeparatorChar)
    $manifest=Read-Mvp7RuntimeManifest $RuntimeManifest
    $seen=[Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
    $total=[long]0;$count=0
    foreach ($file in $manifest.files) {
        $relative=$file.relative_path
        Assert-Mvp7 ($seen.Add($relative)) 'Повторный путь во встроенной среде PowerShell.'
        $target=[IO.Path]::GetFullPath((Join-Path $root (Convert-Mvp7RuntimeRelativePath $relative)))
        Assert-Mvp7 ($target.StartsWith($root+[IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)) 'Недопустимый путь во встроенной среде PowerShell.'
        Assert-Mvp7 (Test-Path -LiteralPath $target -PathType Leaf) 'Отсутствует файл встроенной среды PowerShell.'
        $item=Get-Item -LiteralPath $target -Force
        Assert-Mvp7 (-not ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) 'Ссылки во встроенной среде PowerShell запрещены.'
        Assert-Mvp7 ($item.Length -eq [long]$file.bytes -and (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash.ToLowerInvariant() -ceq $file.sha256) 'Контрольная сумма встроенной среды PowerShell не совпадает.'
        $total+=[long]$file.bytes;$count++
    }
    foreach ($entry in Get-ChildItem -LiteralPath $root -Recurse -Force) {
        Assert-Mvp7 (-not ($entry.Attributes -band [IO.FileAttributes]::ReparsePoint)) 'Ссылки во встроенной среде PowerShell запрещены.'
        if (-not $entry.PSIsContainer) {
            $relative=$entry.FullName.Substring($root.Length).TrimStart('\') -replace '\\','/'
            Assert-Mvp7 ($seen.Contains($relative)) 'Лишний файл во встроенной среде PowerShell.'
        }
    }
    Assert-Mvp7 ($count -eq [int]$manifest.file_count -and $total -eq [long]$manifest.expanded_bytes) 'Размер встроенной среды PowerShell не совпадает.'
    $entrypoint=[IO.Path]::GetFullPath((Join-Path $root (Convert-Mvp7RuntimeRelativePath $manifest.entrypoint.relative_path)))
    Assert-Mvp7 ((Split-Path $entrypoint -Leaf) -ceq 'pwsh.exe' -and (Test-Path -LiteralPath $entrypoint -PathType Leaf)) 'Не найден встроенный pwsh.exe.'
    Assert-Mvp7 ((Get-Item -LiteralPath $entrypoint).Length -eq [long]$manifest.entrypoint.bytes -and (Get-FileHash -LiteralPath $entrypoint -Algorithm SHA256).Hash.ToLowerInvariant() -ceq $manifest.entrypoint.sha256) 'Контрольная сумма встроенного pwsh.exe не совпадает.'
    if ($CurrentProcess) {
        Assert-Mvp7BundledPowerShellProcess
        $process=(Get-Process -Id $PID).Path
        Assert-Mvp7 ((Assert-Mvp7Path $process) -ieq $entrypoint) 'Установщик запущен не собственной встроенной средой PowerShell.'
    }
    return $manifest
}
function Copy-Mvp7Runtime([string]$RuntimeRoot,[string]$RuntimeManifest,[string]$ProgramRoot) {
    $null=Assert-Mvp7Runtime $RuntimeRoot $RuntimeManifest
    $runtimeParent=Join-Path $ProgramRoot 'runtime'
    $target=Join-Path $runtimeParent 'pwsh'
    Assert-Mvp7 (-not (Test-Path -LiteralPath $target)) 'Каталог встроенной среды уже существует.'
    $null=New-Item -ItemType Directory -Path $runtimeParent
    Copy-Item -LiteralPath $RuntimeRoot -Destination $target -Recurse
    $null=Assert-Mvp7Runtime $target $RuntimeManifest
}
function Assert-Mvp7Host {
    Assert-Mvp7BundledPowerShellProcess
    Assert-Mvp7 ($IsWindows -and [Environment]::Is64BitProcess) 'Нужна Windows x64.'
    $os=Get-CimInstance Win32_OperatingSystem
    Assert-Mvp7 ($os.ProductType -eq 1 -and [int]$os.BuildNumber -ge 22000 -and $os.Caption -match 'Windows 11') 'Установка разрешена только на Windows 11 x64.'
    $computer=Get-CimInstance Win32_ComputerSystem
    $processors=@(Get-CimInstance Win32_Processor)
    Assert-Mvp7 ($computer.SystemType -match 'x64' -and ($computer.HypervisorPresent -or ($processors.VirtualizationFirmwareEnabled -contains $true -and $processors.SecondLevelAddressTranslationExtensions -contains $true))) 'Не подтверждена поддержка аппаратной виртуализации.'
    $edge=@((Join-Path ([Environment]::GetEnvironmentVariable('ProgramFiles(x86)')) 'Microsoft\Edge\Application\msedge.exe'),"$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe") | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    Assert-Mvp7 ([bool]$edge) 'Требуется установленный Microsoft Edge.'
    $wsl="$env:WINDIR\System32\wsl.exe"
    Assert-Mvp7 (Test-Path -LiteralPath $wsl) 'Требуется заранее подготовленная WSL2.'
    $version=Invoke-Mvp7WslProbe $wsl '--version'
    $help=Invoke-Mvp7WslProbe $wsl '--help'
    Assert-Mvp7 (-not [string]::IsNullOrWhiteSpace($version) -and $help -match '--import') 'BLOCKED_MVP7_WSL_CAPABILITY: WSL не подтверждает поддержку импорта.'
    # No existing distro is required. Only package --import --version 2 proves usable WSL2.

}
function Assert-Mvp7Archive([string]$Zip,[string]$ExpectedSha256,[long]$ExpectedBytes) {
    Assert-Mvp7 ($ExpectedSha256 -cmatch '^[0-9a-f]{64}$') 'Отсутствует контрольная сумма архива.'
    $file=Get-Item -LiteralPath $Zip
    Assert-Mvp7 ($file.Length -eq $ExpectedBytes -and (Get-FileHash -LiteralPath $Zip -Algorithm SHA256).Hash.ToLowerInvariant() -ceq $ExpectedSha256) 'Контрольная сумма или размер внутреннего архива не совпадают.'
    $archive=[IO.Compression.ZipFile]::OpenRead($file.FullName)
    try {
        $names=[Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
        foreach ($entry in $archive.Entries) {
            $n=$entry.FullName
            Assert-Mvp7 ($n -ceq $n.Normalize() -and $n -notmatch '[\\:\x00-\x1f]' -and $n -notmatch '^/|(^|/)(\.{1,2}|)(/|$)|[. ](/|$)' -and $names.Add($n)) 'Недопустимый или повторный путь в архиве.'
            Assert-Mvp7 ((($entry.ExternalAttributes -shr 16) -band 61440) -ne 40960) 'Ссылки в архиве запрещены.'
        }
        $manifestEntry=$archive.GetEntry('MVP7_PACKAGE_MANIFEST_V1.json')
        Assert-Mvp7 ($null -ne $manifestEntry) 'Нет манифеста внутреннего архива.'
        $reader=[IO.StreamReader]::new($manifestEntry.Open(),[Text.Encoding]::UTF8)
        try { $manifest=$reader.ReadToEnd() | ConvertFrom-Json -AsHashtable } finally { $reader.Dispose() }
        Assert-Mvp7 ($manifest.schema -ceq 'MVP7_PACKAGE_MANIFEST_V1' -and $manifest.source.head -ceq $script:SourceC -and $manifest.source.tree -ceq $script:TreeC) 'Источник приложения не соответствует принятой версии.'
        Assert-Mvp7 ($manifest.acceptance.PARTNER_RELEASE_READY -eq $false -and $manifest.acceptance.WINDOWS11_WSL2_E2E -ceq 'BLOCKED_NO_RUNNER') 'Неверная маркировка тестового кандидата.'
        $expected=@($manifest.payload.Keys)+@('MVP7_PACKAGE_MANIFEST_V1.json','SHA256SUMS')
        Assert-Mvp7 ($expected.Count -eq $names.Count) 'В архиве есть лишние или отсутствующие файлы.'
        $sums=[Collections.Generic.SortedDictionary[string,string]]::new([StringComparer]::Ordinal)
        foreach ($n in @($expected | Where-Object { $_ -ne 'SHA256SUMS' })) {
            Assert-Mvp7 ($names.Contains($n)) 'Отсутствует файл архива.'
            $e=$archive.GetEntry($n); Assert-Mvp7 ($null -ne $e) 'Регистр пути не совпадает.'
            $stream=$e.Open();$hash=[Security.Cryptography.SHA256]::Create()
            try { $digest=[Convert]::ToHexString($hash.ComputeHash($stream)).ToLowerInvariant() } finally { $stream.Dispose();$hash.Dispose() }
            if ($n -ne 'MVP7_PACKAGE_MANIFEST_V1.json') {
                Assert-Mvp7 ($e.Length -eq $manifest.payload[$n].bytes -and $digest -ceq $manifest.payload[$n].sha256) 'Файл архива повреждён.'
            }
            $sums.Add($n,"$digest  $n")
        }
        $reader=[IO.StreamReader]::new($archive.GetEntry('SHA256SUMS').Open())
        try { $actual=$reader.ReadToEnd() } finally { $reader.Dispose() }
        Assert-Mvp7 ($actual -ceq (($sums.Values -join [char]10)+[char]10)) 'Список SHA256SUMS повреждён.'
        return $manifest
    } finally { $archive.Dispose() }
}
function Expand-Mvp7Archive([string]$Zip,[string]$Destination,[string]$Sha256,[long]$Bytes) {
    $null=Assert-Mvp7Archive $Zip $Sha256 $Bytes
    $destination=Assert-Mvp7Path $Destination
    Assert-Mvp7 (-not (Test-Path -LiteralPath $destination)) 'Каталог назначения уже существует.'
    [IO.Compression.ZipFile]::ExtractToDirectory($Zip,$destination)
}
# Capacity uses verified archive lengths; it never creates a directory or marker.
function Get-Mvp7DiskPlan([string]$Zip,[hashtable]$Manifest,[string]$ProgramRoot,[string]$StateRoot,[hashtable]$Runtime) {
    $archive=[IO.Compression.ZipFile]::OpenRead($Zip)
    try { $expanded=[long]0;foreach ($entry in $archive.Entries) { $expanded+=$entry.Length } }
    finally { $archive.Dispose() }
    $rootfs=[long]$Manifest.payload['rootfs/conflict-analysis-functional-alpha-rootfs.tar'].bytes
    $runtimeBytes=[long]$Runtime.expanded_bytes
    Assert-Mvp7 ($expanded -gt 0 -and $expanded -le 1TB -and $rootfs -gt 0 -and $rootfs -le $expanded -and $runtimeBytes -gt 0 -and $runtimeBytes -le 1GB) 'BLOCKED_MVP7_DISK_CAPACITY'
    $controllers=[long]0
    foreach ($name in @('Mvp7.Setup.psm1','Launch-Mvp7.ps1','Uninstall-Mvp7.ps1')) { $controllers+=(Get-Item -LiteralPath (Join-Path $PSScriptRoot $name)).Length }
    $bootstrap=[long]$Manifest.payload['windows/OwnerAlpha.Common.psm1'].bytes
    return @{programVolume=[IO.Path]::GetPathRoot($ProgramRoot);stateVolume=[IO.Path]::GetPathRoot($StateRoot);
        zipBytes=[long](Get-Item -LiteralPath $Zip).Length;expandedBytes=$expanded;rootfsBytes=$rootfs;expanded_runtime_bytes=$runtimeBytes;
        programReserveBytes=[long]512MB;stateReserveBytes=[long]1GB;
        programRequiredBytes=[long]($expanded+$runtimeBytes+(Get-Item -LiteralPath $Zip).Length+$controllers+$bootstrap+512MB);
        stateRequiredBytes=[long](2*$rootfs+1GB)}
}
function Get-Mvp7VolumeFree([string]$Volume) {
    $drive=[IO.DriveInfo]::new($Volume)
    Assert-Mvp7 $drive.IsReady 'BLOCKED_MVP7_DISK_CAPACITY'
    return [long]$drive.AvailableFreeSpace
}
function Assert-Mvp7DiskCapacity([hashtable]$Plan) {
    try {
        $requirements=@{}
        foreach ($kind in @('program','state')) {
            $volume=$Plan[$kind+'Volume']
            if (-not $requirements.ContainsKey($volume)) { $requirements[$volume]=[long]0 }
            $requirements[$volume]+=$Plan[$kind+'RequiredBytes']
        }
        foreach ($volume in $requirements.Keys) {
            Assert-Mvp7 ((Get-Mvp7VolumeFree $volume) -ge $requirements[$volume]) 'BLOCKED_MVP7_DISK_CAPACITY'
        }
    } catch { throw 'BLOCKED_MVP7_DISK_CAPACITY' }
}
function Get-Mvp7DistroExists([string]$Name) {
    $key='HKCU:\Software\Microsoft\Windows\CurrentVersion\Lxss'
    if (-not (Test-Path -LiteralPath $key)) { return $false }
    return [bool]@(Get-ChildItem -LiteralPath $key | Where-Object { (Get-ItemProperty -LiteralPath $_.PSPath).DistributionName -ceq $Name }).Count
}
function Assert-Mvp7Transaction([hashtable]$Transaction,[hashtable]$Manifest,[string]$Sha256) {
    $tx=$Transaction;$code='BLOCKED_MVP7_ROLLBACK_UNPROVEN'
    Assert-Mvp7 ($tx.schema -ceq 'MVP7_INSTALL_TRANSACTION_V1' -and $tx.source -ceq $script:SourceC -and
        $tx.installer -ceq $Manifest.delivery.head -and $tx.inner_sha256 -ceq $Sha256 -and
        $tx.nonce -cmatch '^[0-9a-f]{32}$' -and $tx.outer -eq $true -and
        $tx.program -ceq (Assert-Mvp7Path (Get-Mvp7ProgramRoot)) -and
        $tx.state -ceq (Assert-Mvp7Path (Get-Mvp7StateRoot)) -and
        $tx.distribution -ceq (Join-Path $tx.state 'distribution') -and
        $tx.distro -ceq ('Conflict-Alpha-'+$script:TreeC.Substring(0,12)+'-'+$tx.nonce.Substring(0,8)) -and
        $tx.programExisted -eq $false -and $tx.stateExisted -eq $false -and $tx.distroExisted -eq $false -and $tx.distributionExisted -eq $false) $code
}
function New-Mvp7PrivateProgram([string]$ProgramRoot) {
    $full=Assert-Mvp7Path $ProgramRoot
    $null=New-Item -ItemType Directory -Path $full
    $sid=[Security.Principal.WindowsIdentity]::GetCurrent().User
    $acl=[Security.AccessControl.DirectorySecurity]::new()
    $acl.SetOwner($sid);$acl.SetAccessRuleProtection($true,$false)
    foreach ($principal in @($sid,[Security.Principal.SecurityIdentifier]::new('S-1-5-18'))) {
        $acl.AddAccessRule([Security.AccessControl.FileSystemAccessRule]::new($principal,'FullControl','ContainerInherit,ObjectInherit','None','Allow'))
    }
    Set-Acl -LiteralPath $full -AclObject $acl
}
function Write-Mvp7Pending([hashtable]$Transaction) {
    $path=Join-Path $Transaction.program 'mvp7-installation.json.pending'
    $raw=[Text.UTF8Encoding]::new($false).GetBytes(($Transaction | ConvertTo-Json -Depth 20 -Compress))
    $stream=[IO.File]::Open($path,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
    try { $stream.Write($raw,0,$raw.Length);$stream.Flush($true) } finally { $stream.Dispose() }
}
function Copy-Mvp7TransactionModule([string]$Zip,[string]$ProgramRoot,[hashtable]$Manifest) {
    $target=Join-Path $ProgramRoot 'OwnerAlpha.Common.psm1'
    $archive=[IO.Compression.ZipFile]::OpenRead($Zip)
    try {
        $stream=$archive.GetEntry('windows/OwnerAlpha.Common.psm1').Open()
        $output=[IO.File]::Open($target,[IO.FileMode]::CreateNew)
        try { $stream.CopyTo($output) } finally { $stream.Dispose();$output.Dispose() }
    } finally { $archive.Dispose() }
    Import-Mvp7TransactionModule $ProgramRoot $Manifest
}
function Import-Mvp7TransactionModule([string]$ProgramRoot,[hashtable]$Manifest) {
    $target=Assert-Mvp7Path (Join-Path $ProgramRoot 'OwnerAlpha.Common.psm1')
    $meta=$Manifest.payload['windows/OwnerAlpha.Common.psm1']
    Assert-Mvp7 ((Get-Item -LiteralPath $target).Length -eq $meta.bytes -and
        (Get-FileHash -LiteralPath $target).Hash.ToLowerInvariant() -ceq $meta.sha256) 'BLOCKED_MVP7_ROLLBACK_UNPROVEN'
    Import-Module $target -Force -Global
}
function Copy-Mvp7Controllers([string]$ProgramRoot) {
    $control=Join-Path $ProgramRoot 'installer'
    $null=New-Item -ItemType Directory -Path $control
    foreach ($name in @('Mvp7.Setup.psm1','Launch-Mvp7.ps1','Uninstall-Mvp7.ps1')) {
        Copy-Item -LiteralPath (Join-Path $PSScriptRoot $name) -Destination (Join-Path $control $name)
    }
}
function Invoke-Mvp7InnerInstall([hashtable]$Transaction) {
    & (Join-Path $Transaction.program 'app/windows/Install-OwnerAlpha.ps1') -PackageRoot (Join-Path $Transaction.program 'app') -StateRoot $Transaction.state -NoPrompt -Transaction $Transaction
}
function Publish-Mvp7Installation([hashtable]$Transaction) {
    # Last mutating step. Once this atomic rename succeeds the installation is
    # complete; no subsequent rollback may delete it.
    [IO.File]::Move((Join-Path $Transaction.program 'mvp7-installation.json.pending'),(Join-Path $Transaction.program 'mvp7-installation.json'))
}
function Undo-Mvp7Installation([hashtable]$Transaction,[hashtable]$Manifest,[string]$Sha256) {
    $code='BLOCKED_MVP7_ROLLBACK_UNPROVEN'
    try {
        Assert-Mvp7Transaction $Transaction $Manifest $Sha256
        $root=Assert-Mvp7Path $Transaction.program
        Assert-Mvp7 (-not (Test-Path -LiteralPath (Join-Path $root 'mvp7-installation.json'))) $code
        $acl=Get-Acl -LiteralPath $root
        $sid=[Security.Principal.WindowsIdentity]::GetCurrent().User.Value
        Assert-Mvp7 ($acl.AreAccessRulesProtected -and $acl.GetOwner([Security.Principal.SecurityIdentifier]).Value -eq $sid) $code
        foreach ($rule in $acl.GetAccessRules($true,$true,[Security.Principal.SecurityIdentifier])) {
            Assert-Mvp7 ($rule.IdentityReference.Value -in @($sid,'S-1-5-18') -and $rule.AccessControlType -eq 'Allow') $code
        }
        $pending=Join-Path $root 'mvp7-installation.json.pending'
        $actual=Get-Content -LiteralPath $pending -Raw -Encoding utf8 | ConvertFrom-Json -AsHashtable
        Assert-Mvp7Transaction $actual $Manifest $Sha256
        Assert-Mvp7 ($actual.nonce -ceq $Transaction.nonce -and $actual.programCreatedTicks -eq $Transaction.programCreatedTicks -and
            (Get-Item -LiteralPath $root).CreationTimeUtc.Ticks -eq $actual.programCreatedTicks) $code
        foreach ($entry in Get-ChildItem -LiteralPath $root -Recurse -Force) {
            Assert-Mvp7 (-not ($entry.Attributes -band [IO.FileAttributes]::ReparsePoint)) $code
        }
        if (-not $actual.stateExisted -and ((Test-Path -LiteralPath $actual.state) -or (Get-Mvp7DistroExists $actual.distro))) {
            Import-Mvp7TransactionModule $root $Manifest
            Undo-OwnerInstallTransaction $actual
        }
        # Never recursively delete state or backups. Only the proven program tree.
        Remove-Item -LiteralPath $root -Recurse -Force
    } catch { throw $code }
}
function Invoke-Mvp7Installation([string]$Zip,[string]$Sha256,[long]$Bytes,[hashtable]$Manifest,[hashtable]$Runtime,[string]$RuntimeRoot,[string]$RuntimeManifest) {
    Assert-Mvp7 ($Runtime -and $RuntimeRoot -and $RuntimeManifest) 'Повреждена встроенная среда PowerShell.'
    $null=Assert-Mvp7Runtime $RuntimeRoot $RuntimeManifest
    $root=Assert-Mvp7Path (Get-Mvp7ProgramRoot);$state=Assert-Mvp7Path (Get-Mvp7StateRoot)
    Assert-Mvp7 ($Manifest.delivery.head -cmatch '^[0-9a-f]{40}$' -and
        $Manifest.delivery.parent -ceq '1e109ad2f37d3de4d0d0fa3a9b9ad1dbace182d4') 'BLOCKED_MVP7_HISTORY'
    $plan=Get-Mvp7DiskPlan $Zip $Manifest $root $state $Runtime
    Assert-Mvp7DiskCapacity $plan
    if (Test-Path -LiteralPath $root) {
        Assert-Mvp7 (-not (Test-Path -LiteralPath (Join-Path $root 'mvp7-installation.json'))) 'Программа уже установлена. Сначала используйте удаление программы; состояние сохранится.'
        try {
            $prior=Get-Content -LiteralPath (Join-Path $root 'mvp7-installation.json.pending') -Raw -Encoding utf8 | ConvertFrom-Json -AsHashtable
            Undo-Mvp7Installation $prior $Manifest $Sha256
        } catch { throw 'BLOCKED_MVP7_ROLLBACK_UNPROVEN' }
    }
    $nonce=[guid]::NewGuid().ToString('N')
    $distro='Conflict-Alpha-'+$script:TreeC.Substring(0,12)+'-'+$nonce.Substring(0,8)
    $tx=@{schema='MVP7_INSTALL_TRANSACTION_V1';source=$script:SourceC;installer=$Manifest.delivery.head;nonce=$nonce;
        program=$root;state=$state;distribution=(Join-Path $state 'distribution');distro=$distro;outer=$true;
        programExisted=(Test-Path -LiteralPath $root);stateExisted=(Test-Path -LiteralPath $state);
        distributionExisted=(Test-Path -LiteralPath (Join-Path $state 'distribution'));distroExisted=(Get-Mvp7DistroExists $distro);
        inner_sha256=$Sha256;runtime=$Runtime;disk=$plan}
    Assert-Mvp7 (-not $tx.programExisted -and -not $tx.distroExisted) 'BLOCKED_MVP7_INCOMPLETE_INSTALL'
    # Existing state, including retained backups, is never modified by fresh install.
    Assert-Mvp7 (-not $tx.stateExisted -and -not $tx.distributionExisted) 'BLOCKED_MVP7_INCOMPLETE_INSTALL'
    try {
        New-Mvp7PrivateProgram $root
        $tx.programCreatedTicks=(Get-Item -LiteralPath $root).CreationTimeUtc.Ticks
        Write-Mvp7Pending $tx
        Copy-Mvp7Runtime $RuntimeRoot $RuntimeManifest $root
        Copy-Mvp7TransactionModule $Zip $root $Manifest
        Expand-Mvp7Archive $Zip (Join-Path $root 'app') $Sha256 $Bytes
        Copy-Mvp7Controllers $root
        $null=Invoke-Mvp7InnerInstall $tx
        Complete-OwnerInstallTransaction $tx
        Publish-Mvp7Installation $tx
    } catch {
        $failure=$_
        Undo-Mvp7Installation $tx $Manifest $Sha256
        throw $failure
    }
}
function Remove-Mvp7Program([string]$ProgramRoot) {
    $full=Assert-Mvp7Path $ProgramRoot
    $expected=Assert-Mvp7Path (Get-Mvp7ProgramRoot)
    Assert-Mvp7 ($full -ieq $expected) 'Удаление за пределами каталога программы запрещено.'
    $marker=Join-Path $full 'mvp7-installation.json'
    Assert-Mvp7 (Test-Path -LiteralPath $marker) 'Не найден маркер установленной программы.'
    $record=Get-Content -Raw -LiteralPath $marker | ConvertFrom-Json -AsHashtable
    Assert-Mvp7 ($record.source -ceq $script:SourceC -and $record.program -ieq $full) 'Маркер установки не совпадает.'
    foreach ($entry in Get-ChildItem -LiteralPath $full -Recurse -Force) {
        Assert-Mvp7 (-not ($entry.Attributes -band [IO.FileAttributes]::ReparsePoint)) 'Удаление каталога со ссылками запрещено.'
    }
    Remove-Item -LiteralPath $full -Recurse -Force
}
Export-ModuleMember -Function *-Mvp7*
