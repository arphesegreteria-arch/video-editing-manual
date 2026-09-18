[CmdletBinding(SupportsShouldProcess)]
param(
    [Parameter(Mandatory)][ValidatePattern('^tunnel_[A-Za-z0-9_-]+$')][string]$TunnelId,
    [Parameter(Mandatory)][string]$TunnelClientPath,
    [Parameter(Mandatory)][string]$PythonPath,
    [Parameter(Mandatory)][string]$PythonwPath
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$creativeSource = Join-Path $PSScriptRoot 'experiments\ARPHE_MCP_BRIDGE_CREATIVE_03'
$creativeDestination = 'C:\ARPHE\MCP\ARPHE_MCP_BRIDGE_CREATIVE_03'

if (-not $PSCmdlet.ShouldProcess('PC_PERSONALE', 'Install creative bridge and Windows autostart runtime')) { return }

& (Join-Path $creativeSource 'install_on_segreteria.ps1') -WorkstationId 'PC_PERSONALE' -Destination $creativeDestination

$entryPoint = (Join-Path $creativeDestination 'ARPHE_MCP_BRIDGE_CREATIVE_03.py').Replace('\', '/')
$mcpCommand = '"{0}" "{1}"' -f $PythonPath.Replace('\', '/'), $entryPoint
& (Join-Path $PSScriptRoot 'windows_bridge\install_autostart.ps1') `
    -WorkstationId 'PC_PERSONALE' -TunnelId $TunnelId -TunnelClientPath $TunnelClientPath `
    -McpCommand $mcpCommand -PythonPath $PythonPath -PythonwPath $PythonwPath

Write-Host 'Installazione locale completata. Ora eseguire status_bridge.ps1 e collegare il tunnel a una app ChatGPT Business dedicata.'
