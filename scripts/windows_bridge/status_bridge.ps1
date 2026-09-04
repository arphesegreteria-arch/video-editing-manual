[CmdletBinding()]
param()
. (Join-Path $PSScriptRoot 'common.ps1')

$task = Get-ArpheTask
$taskState = if ($task) { [string]$task.State } else { 'NotInstalled' }
$state = $null
if (Test-Path -LiteralPath $script:ArpheStatePath) {
    try { $state = Get-Content -Raw -LiteralPath $script:ArpheStatePath | ConvertFrom-Json } catch {}
}
$supervisorRunning = $false
if ($state) { $supervisorRunning = Test-ArpheProcess -ProcessId $state.supervisor_pid }
$ready = $false
$healthDetail = 'unreachable'
try {
    $response = Invoke-WebRequest -Uri 'http://127.0.0.1:8080/readyz' -TimeoutSec 3 -UseBasicParsing
    $ready = $response.StatusCode -eq 200 -and $response.Content.Trim().ToLowerInvariant() -eq 'ready'
    $healthDetail = "HTTP $($response.StatusCode) $($response.Content.Trim())"
} catch {
    $healthDetail = 'unreachable'
}

[pscustomobject]@{
    Runtime = $script:ArpheRuntimeId
    Workstation = $script:ArpheWorkstationId
    TaskState = $taskState
    SupervisorPid = if ($state) { $state.supervisor_pid } else { $null }
    SupervisorRunning = $supervisorRunning
    TunnelPid = if ($state) { $state.tunnel_pid } else { $null }
    SupervisorState = if ($state) { $state.status } else { 'no-state-file' }
    Readyz = $ready
    Health = $healthDetail
    RestartCount = if ($state) { $state.restart_count } else { $null }
    ConfigPath = $script:ArpheConfigPath
    SecretStored = Test-Path -LiteralPath $script:ArpheSecretPath -PathType Leaf
} | Format-List

if (-not $task -or $task.State -ne 'Running' -or -not $supervisorRunning -or -not $ready) { exit 1 }
