[CmdletBinding(SupportsShouldProcess)]
param(
    [Parameter(Mandatory)][ValidateSet('Creative03', 'SafeWrite02')][string]$Mode,
    [ValidatePattern('^PC_[A-Z0-9_]{2,48}$')][string]$WorkstationId = '',
    [string]$CreativeMcpCommand = 'py -3 C:/ARPHE/MCP/ARPHE_MCP_BRIDGE_CREATIVE_03/ARPHE_MCP_BRIDGE_CREATIVE_03.py'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$lifecycleRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..\windows_bridge')).Path
. (Join-Path $lifecycleRoot 'common.ps1') -WorkstationId $WorkstationId
$runtimeConfig = $script:ArpheConfigPath
$commands = @{
    Creative03 = $CreativeMcpCommand
    SafeWrite02 = 'py -3 C:/ARPHE/MCP/ARPHE_MCP_BRIDGE_SAFE_WRITE_02/ARPHE_MCP_BRIDGE_SAFE_WRITE_02.py'
}
$entryPoints = @{
    Creative03 = 'C:\ARPHE\MCP\ARPHE_MCP_BRIDGE_CREATIVE_03\ARPHE_MCP_BRIDGE_CREATIVE_03.py'
    SafeWrite02 = 'C:\ARPHE\MCP\ARPHE_MCP_BRIDGE_SAFE_WRITE_02\ARPHE_MCP_BRIDGE_SAFE_WRITE_02.py'
}

if (-not (Test-Path -LiteralPath $runtimeConfig -PathType Leaf)) { throw "Runtime config non trovata: $runtimeConfig" }
if ($Mode -eq 'Creative03' -and -not (Test-Path -LiteralPath $entryPoints[$Mode] -PathType Leaf)) { throw "Bridge target non trovato: $($entryPoints[$Mode])" }
if (-not $PSCmdlet.ShouldProcess($runtimeConfig, "Switch MCP_COMMAND to $Mode and restart runtime")) { return }

& (Join-Path $lifecycleRoot 'stop_bridge.ps1') -WorkstationId $script:ArpheWorkstationId
$config = Get-Content -Raw -LiteralPath $runtimeConfig | ConvertFrom-Json
$config.mcp_command = $commands[$Mode]
[IO.File]::WriteAllText($runtimeConfig, ($config | ConvertTo-Json -Depth 8), [Text.UTF8Encoding]::new($false))
& (Join-Path $lifecycleRoot 'start_bridge.ps1') -WorkstationId $script:ArpheWorkstationId
Write-Host "Runtime switched to $Mode. Verify status and ChatGPT ping."
