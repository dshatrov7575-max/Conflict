# MVP7 capability contracts only: mocks are never WSL2 E2E evidence.
Import-Module (Join-Path $PSScriptRoot '../owner_alpha_package/windows/OwnerAlpha.Common.psm1') -Force
Import-Module (Join-Path $PSScriptRoot 'Mvp7.Setup.psm1') -Force
function Assert-PreflightReject([scriptblock]$Probe) {
    $caught=$false
    try { & $Probe } catch { if ($_.Exception.Message -notmatch 'BLOCKED_MVP7_WSL_CAPABILITY') { throw };$caught=$true }
    if (-not $caught) { throw 'Expected WSL capability rejection' }
}
Describe 'MVP7 preflight without registered Linux distros' {
    BeforeEach {
        foreach ($module in @('OwnerAlpha.Common','Mvp7.Setup')) {
            Mock Get-CimInstance -ModuleName $module {
                if ($ClassName -eq 'Win32_OperatingSystem') { return @{ProductType=1;BuildNumber='22631';Caption='Windows 11 Pro'} }
                if ($ClassName -eq 'Win32_ComputerSystem') { return @{SystemType='x64-based PC';HypervisorPresent=$true} }
                return @{VirtualizationFirmwareEnabled=$true;SecondLevelAddressTranslationExtensions=$true}
            }
            Mock Test-Path -ModuleName $module { $true }
        }
        Mock Get-OwnerEdgeCapacity -ModuleName OwnerAlpha.Common { @{path='C:\mock\msedge.exe';version='153.0.4234.32'} }
        Mock Assert-Mvp7BundledPowerShellProcess -ModuleName Mvp7.Setup { }
    }
    It 'WSL2 capability present with no registered distros passes both preflights' {
        Mock Invoke-OwnerProcess -ModuleName OwnerAlpha.Common {
            if ($Arguments[0] -eq '--list') { return ,[Text.Encoding]::UTF8.GetBytes('No installed distributions.') }
            if ($Arguments[0] -eq '--help') { return ,[Text.Encoding]::UTF8.GetBytes('Usage: --import --version') }
            return ,[Text.Encoding]::UTF8.GetBytes('WSL version: 2.6.3')
        }
        Mock Invoke-Mvp7WslProbe -ModuleName Mvp7.Setup {
            if ($Option -eq '--help') { return 'Usage: --import --version' }
            return 'WSL version: 2.6.3'
        }
        $capacity=Assert-OwnerCapacity 18765
        if ($capacity.registeredDistroRequired -ne $false -or $capacity.packageImportVerified -ne $false) { throw 'Capability is not actual import proof' }
        Assert-Mvp7Host
        Assert-MockCalled Invoke-OwnerProcess -ModuleName OwnerAlpha.Common -Times 0 -Exactly -ParameterFilter { $Arguments[0] -eq '--list' }
        Assert-MockCalled Invoke-OwnerProcess -ModuleName OwnerAlpha.Common -Times 0 -Exactly -ParameterFilter { $Arguments[0] -eq '--import' }
        # Same-volume requirements must be summed; separate volumes must each pass.
        Mock Get-Mvp7VolumeFree -ModuleName Mvp7.Setup { return [long]100 }
        $plan=@{programVolume='C:\';stateVolume='C:\';programRequiredBytes=40L;stateRequiredBytes=60L}
        Assert-Mvp7DiskCapacity $plan
        $plan.stateRequiredBytes=61L
        $rejected=$false
        try { Assert-Mvp7DiskCapacity $plan } catch { $rejected=$_.Exception.Message -ceq 'BLOCKED_MVP7_DISK_CAPACITY' }
        if (-not $rejected) { throw 'Shared-volume disk reservation must fail closed' }
        $plan.stateVolume='D:\';$plan.programRequiredBytes=100L;$plan.stateRequiredBytes=100L
        Assert-Mvp7DiskCapacity $plan
        foreach ($kind in @('program','state')) {
            $plan[$kind+'RequiredBytes']=101L;$rejected=$false
            try { Assert-Mvp7DiskCapacity $plan } catch { $rejected=$_.Exception.Message -ceq 'BLOCKED_MVP7_DISK_CAPACITY' }
            if (-not $rejected) { throw 'Each volume must independently have enough space' }
            $plan[$kind+'RequiredBytes']=100L
        }

    }
    It 'Missing WSL import capability fails both preflights' {
        Mock Invoke-OwnerProcess -ModuleName OwnerAlpha.Common {
            if ($Arguments[0] -eq '--help') { return ,[Text.Encoding]::UTF8.GetBytes('Unsupported legacy command') }
            return ,[Text.Encoding]::UTF8.GetBytes('WSL version: test')
        }
        Mock Invoke-Mvp7WslProbe -ModuleName Mvp7.Setup {
            if ($Option -eq '--help') { return 'Unsupported legacy command' }
            return 'WSL version: test'
        }
        Assert-PreflightReject { Assert-OwnerCapacity 18765 }
        Assert-PreflightReject { Assert-Mvp7Host }
    }
}
