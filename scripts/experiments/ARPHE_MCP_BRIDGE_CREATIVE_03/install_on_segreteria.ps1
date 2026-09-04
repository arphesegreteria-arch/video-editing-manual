[CmdletBinding(SupportsShouldProcess)]
param(
    [string]$Destination = 'C:\ARPHE\MCP\ARPHE_MCP_BRIDGE_CREATIVE_03',
    [string]$AssetRoot = 'C:\ARPHE\MCP\assets\creative',
    [string]$RenderRoot = 'C:\ARPHE\MCP\renders\creative'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$configDir = Join-Path $env:LOCALAPPDATA 'ARPHE\CreativeBridge03'
$configPath = Join-Path $configDir 'creative_config.json'
$examplePath = Join-Path $PSScriptRoot 'creative_config.example.json'

if (-not $PSCmdlet.ShouldProcess($Destination, 'Install creative bridge beside validated bridges')) { return }

New-Item -ItemType Directory -Path $Destination -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'ARPHE_MCP_BRIDGE_CREATIVE_03.py') -Destination $Destination -Force
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'bridge') -Destination $Destination -Recurse -Force
New-Item -ItemType Directory -Path $AssetRoot -Force | Out-Null
New-Item -ItemType Directory -Path $RenderRoot -Force | Out-Null
New-Item -ItemType Directory -Path $configDir -Force | Out-Null

if (-not (Test-Path -LiteralPath $configPath)) {
    $config = Get-Content -Raw -LiteralPath $examplePath | ConvertFrom-Json
    $config.asset_root = $AssetRoot.Replace('\', '/')
    $config.render_root = $RenderRoot.Replace('\', '/')
    [IO.File]::WriteAllText($configPath, ($config | ConvertTo-Json -Depth 8), [Text.UTF8Encoding]::new($false))
    Write-Host "Created local config: $configPath"
} else {
    Write-Host "Preserved existing local config: $configPath"
}

Write-Host "Installed ARPHE_MCP_BRIDGE_CREATIVE_03 beside existing bridges."
Write-Host 'Runtime MCP_COMMAND was NOT changed.'
