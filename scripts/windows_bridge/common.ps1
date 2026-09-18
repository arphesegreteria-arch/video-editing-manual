param([ValidatePattern('^PC_[A-Z0-9_]{2,48}$')][string]$WorkstationId = '')

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$script:ArpheRuntimeId = 'ARPHE_WINDOWS_BRIDGE_RUNTIME_V1'
$script:ArpheDataDir = Join-Path $env:LOCALAPPDATA 'ARPHE\WindowsBridgeRuntimeV1'
$script:ArpheConfigPath = Join-Path $script:ArpheDataDir 'bridge_config.json'
$detectedWorkstation = $WorkstationId
if (-not $detectedWorkstation -and (Test-Path -LiteralPath $script:ArpheConfigPath -PathType Leaf)) {
    try { $detectedWorkstation = [string](Get-Content -Raw -LiteralPath $script:ArpheConfigPath | ConvertFrom-Json).workstation_id } catch {}
}
if (-not $detectedWorkstation) { $detectedWorkstation = 'PC_SEGRETERIA' }
if ($detectedWorkstation -notmatch '^PC_[A-Z0-9_]{2,48}$') { throw "Invalid workstation id: $detectedWorkstation" }
$script:ArpheWorkstationId = $detectedWorkstation
$script:ArpheTaskName = "ARPHE Resolve Bridge Runtime V1 - $detectedWorkstation"
$script:ArpheTaskPath = '\'
$script:ArpheStatePath = Join-Path $script:ArpheDataDir 'runtime_state.json'
$script:ArpheStopPath = Join-Path $script:ArpheDataDir 'stop.requested'
$script:ArpheSecretPath = Join-Path $script:ArpheDataDir 'runtime_api_key.dpapi'

function Get-ArpheTask {
    Get-ScheduledTask -TaskName $script:ArpheTaskName -TaskPath $script:ArpheTaskPath -ErrorAction SilentlyContinue
}

function Test-ArpheProcess {
    param([Nullable[int]]$ProcessId)
    if ($null -eq $ProcessId -or $ProcessId -le 0) { return $false }
    return $null -ne (Get-Process -Id $ProcessId -ErrorAction SilentlyContinue)
}

function Quote-ArpheArgument {
    param([Parameter(Mandatory)][string]$Value)
    if ($Value.Contains('"')) { throw "A path contains an unsupported quote character: $Value" }
    return '"' + $Value + '"'
}
