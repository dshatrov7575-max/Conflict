Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
Import-Module (Join-Path $PSScriptRoot 'OwnerAlpha.Common.psm1')
$script:CdpSequence=0

function Invoke-OwnerCdp([Net.WebSockets.ClientWebSocket]$Socket,[string]$Method,[hashtable]$Parameters,[string]$SessionId='') {
    $script:CdpSequence++
    $id=$script:CdpSequence
    $message=@{id=$id;method=$Method;params=$Parameters}
    if ($SessionId) { $message.sessionId=$SessionId }
    $bytes=[Text.Encoding]::UTF8.GetBytes(($message | ConvertTo-Json -Depth 30 -Compress))
    $cancel=[Threading.CancellationTokenSource]::new(15000)
    try {
        $null=$Socket.SendAsync([ArraySegment[byte]]::new($bytes),[Net.WebSockets.WebSocketMessageType]::Text,$true,$cancel.Token).GetAwaiter().GetResult()
        while ($true) {
            $buffer=[byte[]]::new(65536)
            $memory=[IO.MemoryStream]::new()
            try {
                do {
                    $received=$Socket.ReceiveAsync([ArraySegment[byte]]::new($buffer),$cancel.Token).GetAwaiter().GetResult()
                    Assert-OwnerGate ($received.MessageType -eq 'Text') 'BLOCKED_G10_PROFILE_ISOLATION_GAP'
                    $memory.Write($buffer,0,$received.Count)
                    Assert-OwnerGate ($memory.Length -lt 4194304) 'BLOCKED_G10_PROFILE_ISOLATION_GAP'
                } until ($received.EndOfMessage)
                $response=[Text.Encoding]::UTF8.GetString($memory.ToArray()) | ConvertFrom-Json -AsHashtable
            } finally { $memory.Dispose(); [Array]::Clear($buffer,0,$buffer.Length) }
            if ($response.ContainsKey('id') -and $response.id -eq $id) {
                Assert-OwnerGate (-not $response.ContainsKey('error')) 'BLOCKED_G10_PROFILE_ISOLATION_GAP'
                return $response.result
            }
        }
    } finally { [Array]::Clear($bytes,0,$bytes.Length); $cancel.Dispose() }
}
function Start-OwnerEdgeProcess([string]$Edge,[string[]]$Arguments) {
    $start=[Diagnostics.ProcessStartInfo]::new()
    $start.FileName=$Edge
    $start.UseShellExecute=$false
    $start.CreateNoWindow=$true
    foreach ($argument in $Arguments) { $start.ArgumentList.Add($argument) }
    return [Diagnostics.Process]::Start($start)
}
function Assert-OwnerDebugClosed([int]$Port) {
    $listener=@([Net.NetworkInformation.IPGlobalProperties]::GetIPGlobalProperties().GetActiveTcpListeners() | Where-Object Port -eq $Port)
    Assert-OwnerGate ($listener.Count -eq 0) 'BLOCKED_G10_NETWORK_EXPOSURE'
}
function Open-OwnerProfile([hashtable]$Context,[hashtable]$Cookie) {
    Assert-OwnerGate ($Cookie.profile -in @('STUDIO_EDITOR','STUDIO_PUBLISHER','PLAYER_ASSESSOR')) 'BLOCKED_G10_PROFILE_ISOLATION_GAP'
    Assert-OwnerGate ($Cookie.name -eq 'sessionid' -and $Cookie.httpOnly -eq $true -and $Cookie.sameSite -eq 'Lax' -and $Cookie.path -eq '/' -and $Cookie.secure -eq $false -and $Cookie.value -match '^[a-z0-9]{32}$') 'BLOCKED_G10_ACCESS_PROVISIONING_GAP'
    $profilesRoot=New-OwnerPrivateDirectory (Join-Path $Context.root 'profiles')
    $directory=Join-Path $profilesRoot ($Cookie.profile+'-'+[guid]::NewGuid().ToString('N').Substring(0,8))
    $null=New-OwnerPrivateDirectory $directory
    $Context.record.profiles[$Cookie.profile]=@{path=$directory;pids=@();user_pk=$Cookie.user_pk;debug_closed=$false}
    Write-OwnerJson $Context.stateFile $Context.record
    $base=@('--user-data-dir='+$directory,'--no-first-run','--no-default-browser-check','--disable-background-networking','--disable-component-update','--disable-sync')
    $process=Start-OwnerEdgeProcess $Context.capacity.edgePath ($base+@('--headless=new','--remote-debugging-address=127.0.0.1','--remote-debugging-port=0','about:blank'))
    $Context.record.profiles[$Cookie.profile].pids=@($process.Id)
    Write-OwnerJson $Context.stateFile $Context.record
    $active=Join-Path $directory 'DevToolsActivePort'
    $deadline=[datetime]::UtcNow.AddSeconds(20)
    while (-not (Test-Path -LiteralPath $active) -and [datetime]::UtcNow -lt $deadline -and -not $process.HasExited) { Start-Sleep -Milliseconds 100 }
    Assert-OwnerGate (Test-Path -LiteralPath $active) 'BLOCKED_G10_PROFILE_ISOLATION_GAP'
    $lines=[IO.File]::ReadAllLines($active)
    $port=[int]$lines[0]
    Assert-OwnerGate ($lines[1] -match '^/devtools/browser/[a-zA-Z0-9-]+$') 'BLOCKED_G10_PROFILE_ISOLATION_GAP'
    $listeners=@(Get-NetTCPConnection -State Listen | Where-Object LocalPort -eq $port)
    Assert-OwnerGate ($listeners.Count -gt 0 -and @($listeners | Where-Object { $_.LocalAddress -notin @('127.0.0.1','::1') -or $_.OwningProcess -ne $process.Id }).Count -eq 0) 'BLOCKED_G10_NETWORK_EXPOSURE'
    $socket=[Net.WebSockets.ClientWebSocket]::new()
    $cancel=[Threading.CancellationTokenSource]::new(15000)
    try {
        $null=$socket.ConnectAsync([uri]('ws://127.0.0.1:'+$port+$lines[1]),$cancel.Token).GetAwaiter().GetResult()
        $target=Invoke-OwnerCdp $socket 'Target.createTarget' @{url='about:blank'}
        $session=Invoke-OwnerCdp $socket 'Target.attachToTarget' @{targetId=$target.targetId;flatten=$true}
        $origin='http://127.0.0.1:'+$Context.record.port
        $parameters=@{name=$Cookie.name;value=$Cookie.value;url=$origin+'/';path='/';httpOnly=$true;secure=$false;sameSite='Lax';expires=$Cookie.expires}
        $set=Invoke-OwnerCdp $socket 'Network.setCookie' $parameters $session.sessionId
        Assert-OwnerGate ($set.success -eq $true) 'BLOCKED_G10_ACCESS_PROVISIONING_GAP'
        $observed=Invoke-OwnerCdp $socket 'Network.getCookies' @{urls=@($origin+'/')} $session.sessionId
        Assert-OwnerGate ($observed.cookies.Count -eq 1 -and $observed.cookies[0].value -ceq $Cookie.value -and $observed.cookies[0].domain -eq '127.0.0.1' -and $observed.cookies[0].httpOnly -eq $true) 'BLOCKED_G10_PROFILE_ISOLATION_GAP'
        # Browser.close flushes only the ACL-protected profile cookie jar.
        # Do not leave a debugging browser running behind the visible UI.
        try { $null=Invoke-OwnerCdp $socket 'Browser.close' @{} } catch {
            if (-not $process.WaitForExit(15000)) { throw }
        }
    } finally {
        $socket.Dispose(); $cancel.Dispose()
        $parameters=$null; $observed=$null; $Cookie.value=$null
    }
    Assert-OwnerGate ($process.WaitForExit(15000)) 'BLOCKED_G10_NETWORK_EXPOSURE'
    Assert-OwnerDebugClosed $port
    $route=if($Cookie.profile -eq 'PLAYER_ASSESSOR'){'/player/'}else{'/studio/drafts/'}
    $pages=@(('http://127.0.0.1:'+$Context.record.port+$route))
    if($Cookie.profile -eq 'STUDIO_PUBLISHER') { $pages+=('http://127.0.0.1:'+$Context.record.port+'/analysis/') }
    $visible=Start-OwnerEdgeProcess $Context.capacity.edgePath ($base+@('--new-window')+$pages)
    $Context.record.profiles[$Cookie.profile].pids=@($visible.Id)
    $Context.record.profiles[$Cookie.profile].debug_closed=$true
    Write-OwnerJson $Context.stateFile $Context.record
    return @{profile=$Cookie.profile;user_pk=$Cookie.user_pk;debug_closed=$true}
}
Export-ModuleMember -Function *-Owner*
