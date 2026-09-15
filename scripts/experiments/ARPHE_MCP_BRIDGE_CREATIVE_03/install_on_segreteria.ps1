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
$bridgeSource = Join-Path $PSScriptRoot 'bridge'
$bridgeDestination = Join-Path $Destination 'bridge'
New-Item -ItemType Directory -Path $bridgeDestination -Force | Out-Null
Get-ChildItem -LiteralPath $bridgeSource -File | ForEach-Object {
    Copy-Item -LiteralPath $_.FullName -Destination $bridgeDestination -Force
}
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
    $config = Get-Content -Raw -LiteralPath $configPath | ConvertFrom-Json
    $changed = $false
    if ($null -eq $config.PSObject.Properties['media_roots']) {
        $config | Add-Member -NotePropertyName media_roots -NotePropertyValue @((Join-Path $env:USERPROFILE 'Downloads').Replace('\', '/'))
        $changed = $true
    }
    if ($null -eq $config.PSObject.Properties['transcript_root']) {
        $config | Add-Member -NotePropertyName transcript_root -NotePropertyValue ((Join-Path $env:LOCALAPPDATA 'ARPHE\Longform04\transcripts').Replace('\', '/'))
        $changed = $true
    }
    if ($null -eq $config.feature_flags.PSObject.Properties['CAP_LONGFORM']) {
        $config.feature_flags | Add-Member -NotePropertyName CAP_LONGFORM -NotePropertyValue $false
        $changed = $true
    }
    if ($changed) {
        [IO.File]::WriteAllText($configPath, ($config | ConvertTo-Json -Depth 16), [Text.UTF8Encoding]::new($false))
        Write-Host 'Migrated existing config with gated longform paths and CAP_LONGFORM=false.'
    }
}

Write-Host "Installed ARPHE_MCP_BRIDGE_CREATIVE_03 beside existing bridges."
Write-Host 'Runtime MCP_COMMAND was NOT changed.'
