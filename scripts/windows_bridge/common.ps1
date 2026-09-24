param([ValidatePattern('^PC_[A-Z0-9_]{2,48}$')][string]$WorkstationId = '')

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$script:ArpheRuntimeId = 'ARPHE_WINDOWS_BRIDGE_RUNTIME_V1'
$script:ArpheBaseDataDir = Join-Path $env:LOCALAPPDATA 'ARPHE\WindowsBridgeRuntimeV1'
$script:ArpheLegacyConfigPath = Join-Path $script:ArpheBaseDataDir 'bridge_config.json'
$script:ArpheLegacySecretPath = Join-Path $script:ArpheBaseDataDir 'runtime_api_key.dpapi'
$detectedWorkstation = $WorkstationId
if (-not $detectedWorkstation -and (Test-Path -LiteralPath $script:ArpheLegacyConfigPath -PathType Leaf)) {
    try { $detectedWorkstation = [string](Get-Content -Raw -LiteralPath $script:ArpheLegacyConfigPath | ConvertFrom-Json).workstation_id } catch {}
}
if (-not $detectedWorkstation -and (Test-Path -LiteralPath $script:ArpheBaseDataDir -PathType Container)) {
    $candidates = @(Get-ChildItem -LiteralPath $script:ArpheBaseDataDir -Directory -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -match '^PC_[A-Z0-9_]{2,48}$' -and (Test-Path -LiteralPath (Join-Path $_.FullName 'bridge_config.json') -PathType Leaf) })
    if ($candidates.Count -eq 1) { $detectedWorkstation = $candidates[0].Name }
}
if (-not $detectedWorkstation) { $detectedWorkstation = 'PC_SEGRETERIA' }
if ($detectedWorkstation -notmatch '^PC_[A-Z0-9_]{2,48}$') { throw "Invalid workstation id: $detectedWorkstation" }
$script:ArpheWorkstationId = $detectedWorkstation
$profileDataDir = Join-Path $script:ArpheBaseDataDir $script:ArpheWorkstationId
# Backward compatibility: older validated installs kept the config directly under
# WindowsBridgeRuntimeV1. Reuse that profile only when its identity matches; new
# workstation profiles continue to use the isolated directory.
$script:ArpheDataDir = $profileDataDir
if (-not (Test-Path -LiteralPath (Join-Path $profileDataDir 'bridge_config.json') -PathType Leaf) -and
    (Test-Path -LiteralPath $script:ArpheLegacyConfigPath -PathType Leaf)) {
    $script:ArpheDataDir = $script:ArpheBaseDataDir
}
$script:ArpheConfigPath = Join-Path $script:ArpheDataDir 'bridge_config.json'
$script:ArpheTaskName = "ARPHE Resolve Bridge Runtime V1 - $detectedWorkstation"
$script:ArpheTaskPath = '\'
$script:ArpheStatePath = Join-Path $script:ArpheDataDir 'runtime_state.json'
$script:ArpheStopPath = Join-Path $script:ArpheDataDir 'stop.requested'
$script:ArpheSecretPath = Join-Path $script:ArpheDataDir 'runtime_api_key.dpapi'

function Copy-ArpheLegacySecretForWorkstation {
    if (Test-Path -LiteralPath $script:ArpheSecretPath -PathType Leaf) { return $false }
    if (-not (Test-Path -LiteralPath $script:ArpheLegacyConfigPath -PathType Leaf) -or
        -not (Test-Path -LiteralPath $script:ArpheLegacySecretPath -PathType Leaf)) { return $false }
    try {
        $legacyWorkstation = [string](Get-Content -Raw -LiteralPath $script:ArpheLegacyConfigPath | ConvertFrom-Json).workstation_id
    } catch {
        return $false
    }
    if ($legacyWorkstation -ne $script:ArpheWorkstationId) { return $false }
    New-Item -ItemType Directory -Path $script:ArpheDataDir -Force | Out-Null
    Copy-Item -LiteralPath $script:ArpheLegacySecretPath -Destination $script:ArpheSecretPath
    return $true
}

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
