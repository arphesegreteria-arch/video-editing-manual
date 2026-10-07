[CmdletBinding(SupportsShouldProcess)]
param(
    [Parameter(Mandatory)][ValidateSet('Creative03', 'SafeWrite02')][string]$Mode,
    [Parameter(Mandatory)][ValidatePattern('^PC_[A-Z0-9_]{2,48}$')][string]$WorkstationId,
    [Parameter(Mandatory)][string]$ProfilePath
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$lifecycleRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..\windows_bridge')).Path
. (Join-Path $lifecycleRoot 'common.ps1') -WorkstationId $WorkstationId -ProfilePath $ProfilePath
$runtimeConfig = $script:ArpheConfigPath

if (-not (Test-Path -LiteralPath $runtimeConfig -PathType Leaf)) { throw "Runtime config non trovata: $runtimeConfig" }
$config = Get-Content -Raw -LiteralPath $runtimeConfig | ConvertFrom-Json
if ($null -eq $config.bridge_commands -or $null -eq $config.bridge_commands.PSObject.Properties[$Mode]) {
    throw "Bridge command '$Mode' non registrato nel profilo $WorkstationId. Reinstallare il profilo con il bridge richiesto prima dello switch."
}
$targetCommand = [string]$config.bridge_commands.$Mode
if ([string]::IsNullOrWhiteSpace($targetCommand) -or $targetCommand -match '^(?i)\s*(py|python)(\.exe)?\s') {
    throw "Bridge command '$Mode' non valido: e' richiesto un interprete assoluto registrato nel profilo."
}
if ($targetCommand -notmatch '^"([^"]+)"\s+"([^"]+)"$') {
    throw "Bridge command '$Mode' non valido: formato atteso è interprete assoluto + target assoluto."
}
$targetPython = $Matches[1]
$targetEntrypoint = $Matches[2]
if (-not [IO.Path]::IsPathRooted($targetPython) -or -not (Test-Path -LiteralPath $targetPython -PathType Leaf)) {
    throw "Bridge command '$Mode' interpreter non trovato: $targetPython"
}
if (-not [IO.Path]::IsPathRooted($targetEntrypoint) -or -not (Test-Path -LiteralPath $targetEntrypoint -PathType Leaf)) {
    throw "Bridge command '$Mode' target non trovato: $targetEntrypoint"
}
Write-Host "Target command: $targetCommand"
if (-not $PSCmdlet.ShouldProcess($runtimeConfig, "Switch MCP_COMMAND to $Mode and restart runtime")) { return }

& (Join-Path $lifecycleRoot 'stop_bridge.ps1') -WorkstationId $script:ArpheWorkstationId
$config.mcp_command = $targetCommand
[IO.File]::WriteAllText($runtimeConfig, ($config | ConvertTo-Json -Depth 8), [Text.UTF8Encoding]::new($false))
& (Join-Path $lifecycleRoot 'start_bridge.ps1') -WorkstationId $script:ArpheWorkstationId
Write-Host "Runtime switched to $Mode. Verify status and ChatGPT ping."
