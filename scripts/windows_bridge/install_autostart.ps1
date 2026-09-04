[CmdletBinding(SupportsShouldProcess)]
param(
    [Parameter(Mandatory)][ValidatePattern('^tunnel_[A-Za-z0-9_-]+$')][string]$TunnelId,
    [string]$TunnelClientPath = 'C:\ARPHE\MCP\tunnel client\tunnel-client-runtime-cloudflared.exe',
    [string]$McpCommand = 'py -3 C:/ARPHE/MCP/ARPHE_MCP_BRIDGE_SAFE_WRITE_02/ARPHE_MCP_BRIDGE_SAFE_WRITE_02.py',
    [string]$InstallRoot = 'C:\ARPHE\MCP\ARPHE_WINDOWS_BRIDGE_RUNTIME_V1',
    [string]$LogDir = 'C:\ARPHE\MCP\logs\ARPHE_WINDOWS_BRIDGE_RUNTIME_V1',
    [string]$PythonPath = '',
    [string]$PythonwPath = '',
    [switch]$KeepExistingSecret,
    [switch]$DoNotStart
)

. (Join-Path $PSScriptRoot 'common.ps1')

function Resolve-Executable {
    param([string]$Requested, [string[]]$Candidates)
    if ($Requested) {
        $resolved = (Resolve-Path -LiteralPath $Requested -ErrorAction Stop).Path
        if (-not (Test-Path -LiteralPath $resolved -PathType Leaf)) { throw "Executable not found: $Requested" }
        return $resolved
    }
    foreach ($candidate in $Candidates) {
        $command = Get-Command $candidate -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($command -and $command.Source -notlike '*\Microsoft\WindowsApps\*') { return $command.Source }
    }
    throw "Could not find a real executable for: $($Candidates -join ', '). WindowsApps aliases are not valid for Task Scheduler; pass an explicit Python path."
}

if ($env:COMPUTERNAME -and $env:COMPUTERNAME -ne $script:ArpheWorkstationId) {
    Write-Warning "Windows computer name is '$env:COMPUTERNAME'; this package is intentionally configured as PC_SEGRETERIA."
}

$TunnelClientPath = (Resolve-Path -LiteralPath $TunnelClientPath -ErrorAction Stop).Path
$PythonPath = Resolve-Executable -Requested $PythonPath -Candidates @('py.exe', 'python.exe')
$PythonwPath = Resolve-Executable -Requested $PythonwPath -Candidates @('pyw.exe', 'pythonw.exe')

$sourceFiles = @('arphe_bridge_runtime.py', 'health.py', 'secret_store.py')
foreach ($file in $sourceFiles) {
    if (-not (Test-Path -LiteralPath (Join-Path $PSScriptRoot $file) -PathType Leaf)) {
        throw "Installation payload is incomplete: $file"
    }
}

if (-not $PSCmdlet.ShouldProcess("$script:ArpheTaskPath$script:ArpheTaskName", 'Install PC_SEGRETERIA bridge runtime and scheduled task')) { return }

New-Item -ItemType Directory -Path $InstallRoot -Force | Out-Null
New-Item -ItemType Directory -Path $script:ArpheDataDir -Force | Out-Null
New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
foreach ($file in $sourceFiles) {
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot $file) -Destination (Join-Path $InstallRoot $file) -Force
}

$config = [ordered]@{
    schema_version = 1
    runtime_id = $script:ArpheRuntimeId
    workstation_id = $script:ArpheWorkstationId
    tunnel_id = $TunnelId
    tunnel_client_path = $TunnelClientPath.Replace('\', '/')
    mcp_command = $McpCommand
    ready_url = 'http://127.0.0.1:8080/readyz'
    log_dir = $LogDir.Replace('\', '/')
    secret_path = $script:ArpheSecretPath.Replace('\', '/')
    state_path = $script:ArpheStatePath.Replace('\', '/')
    stop_request_path = $script:ArpheStopPath.Replace('\', '/')
    health_interval_seconds = 5
    health_failure_threshold = 6
    startup_grace_seconds = 20
    backoff_initial_seconds = 2
    backoff_max_seconds = 60
    backoff_reset_after_seconds = 300
}
$configJson = $config | ConvertTo-Json
[IO.File]::WriteAllText($script:ArpheConfigPath, $configJson, [Text.UTF8Encoding]::new($false))

if (-not $KeepExistingSecret -or -not (Test-Path -LiteralPath $script:ArpheSecretPath -PathType Leaf)) {
    $secretArgs = @()
    if ([IO.Path]::GetFileName($PythonPath) -ieq 'py.exe') { $secretArgs += '-3' }
    $secretArgs += @((Join-Path $InstallRoot 'secret_store.py'), 'set', '--path', $script:ArpheSecretPath)
    & $PythonPath @secretArgs
    if ($LASTEXITCODE -ne 0) { throw "DPAPI secret storage failed with exit code $LASTEXITCODE" }
}

$runtimePath = Join-Path $InstallRoot 'arphe_bridge_runtime.py'
$runtimeArguments = (Quote-ArpheArgument $runtimePath) + ' --config ' + (Quote-ArpheArgument $script:ArpheConfigPath)
if ([IO.Path]::GetFileName($PythonwPath) -ieq 'pyw.exe') { $runtimeArguments = '-3 ' + $runtimeArguments }
$action = New-ScheduledTaskAction -Execute $PythonwPath -Argument $runtimeArguments -WorkingDirectory $InstallRoot
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$principal = New-ScheduledTaskPrincipal -UserId ([Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -StartWhenAvailable -ExecutionTimeLimit ([TimeSpan]::Zero) -Hidden
$task = New-ScheduledTask -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Description 'ARPHE tunnel supervisor; no autonomous Resolve write operations.'
Register-ScheduledTask -TaskName $script:ArpheTaskName -TaskPath $script:ArpheTaskPath -InputObject $task -Force | Out-Null

if (-not $DoNotStart) {
    Remove-Item -LiteralPath $script:ArpheStopPath -Force -ErrorAction SilentlyContinue
    Start-ScheduledTask -TaskName $script:ArpheTaskName -TaskPath $script:ArpheTaskPath
}

Write-Host "Installed $script:ArpheRuntimeId for $script:ArpheWorkstationId."
Write-Host "Config: $script:ArpheConfigPath"
Write-Host "Task: $script:ArpheTaskPath$script:ArpheTaskName"
