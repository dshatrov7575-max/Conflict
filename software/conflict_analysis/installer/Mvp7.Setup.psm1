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
function Assert-Mvp7Host {
    Assert-Mvp7 ($IsWindows -and [Environment]::Is64BitProcess -and $PSVersionTable.PSVersion.Major -ge 7) 'Нужны Windows x64 и PowerShell 7.'
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
function Remove-Mvp7Program([string]$ProgramRoot) {
    $full=Assert-Mvp7Path $ProgramRoot
    Assert-Mvp7 ($full -ieq (Get-Mvp7ProgramRoot)) 'Удаление за пределами каталога программы запрещено.'
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
