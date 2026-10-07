[CmdletBinding(SupportsShouldProcess)]
param(
    [ValidatePattern('^PC_[A-Z0-9_]{2,48}$')][string]$WorkstationId = 'PC_SEGRETERIA',
    [string]$Destination = 'C:\ARPHE\MCP\ARPHE_MCP_BRIDGE_CREATIVE_03',
    [string]$AssetRoot = 'C:\ARPHE\MCP\assets\creative',
    [string]$RenderRoot = 'C:\ARPHE\MCP\renders\creative',
    [Parameter(Mandatory)][string]$ConfigPath
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$configPath = [IO.Path]::GetFullPath($ConfigPath)
$configDir = Split-Path -Parent $configPath
$examplePath = Join-Path $PSScriptRoot 'creative_config.example.json'
$legacyConfigPath = Join-Path $env:LOCALAPPDATA 'ARPHE\CreativeBridge03\creative_config.json'
$legacyConfig = $null
if (-not (Test-Path -LiteralPath $configPath -PathType Leaf) -and
    (Test-Path -LiteralPath $legacyConfigPath -PathType Leaf)) {
    $legacyConfig = Get-Content -Raw -LiteralPath $legacyConfigPath | ConvertFrom-Json
    if ([string]$legacyConfig.workstation_id -ne $WorkstationId) {
        throw "La config Creative legacy appartiene a '$($legacyConfig.workstation_id)', non a '$WorkstationId'. Migrazione rifiutata senza modifiche."
    }
}

Write-Host "Creative config: $configPath"

function Set-ConfigProperty {
    param([Parameter(Mandatory)]$Config, [Parameter(Mandatory)][string]$Name, $Value)
    if ($null -eq $Config.PSObject.Properties[$Name]) {
        $Config | Add-Member -NotePropertyName $Name -NotePropertyValue $Value
    } else {
        $Config.$Name = $Value
    }
}

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
    $config = if ($null -ne $legacyConfig) { $legacyConfig } else { Get-Content -Raw -LiteralPath $examplePath | ConvertFrom-Json }
    $legacyStatePath = [string]$config.state_path
    $legacyAuditPath = [string]$config.audit_log_path
    Set-ConfigProperty -Config $config -Name workstation_id -Value $WorkstationId
    Set-ConfigProperty -Config $config -Name asset_root -Value $AssetRoot.Replace('\', '/')
    Set-ConfigProperty -Config $config -Name render_root -Value $RenderRoot.Replace('\', '/')
    Set-ConfigProperty -Config $config -Name state_path -Value (Join-Path $configDir 'creative_state.json').Replace('\', '/')
    Set-ConfigProperty -Config $config -Name audit_log_path -Value (Join-Path $configDir 'audit.jsonl').Replace('\', '/')
    if ($null -ne $legacyConfig) {
        foreach ($migration in @(
            @{ Source = $legacyStatePath; Destination = [string]$config.state_path },
            @{ Source = $legacyAuditPath; Destination = [string]$config.audit_log_path }
        )) {
            if (-not [string]::IsNullOrWhiteSpace($migration.Source) -and
                (Test-Path -LiteralPath $migration.Source -PathType Leaf) -and
                -not (Test-Path -LiteralPath $migration.Destination -PathType Leaf)) {
                Copy-Item -LiteralPath $migration.Source -Destination $migration.Destination
            }
        }
        [IO.File]::WriteAllText($configPath, ($config | ConvertTo-Json -Depth 8), [Text.UTF8Encoding]::new($false))
        Write-Host "Migrated matching legacy Creative config into profile path: $configPath"
    } else {
        [IO.File]::WriteAllText($configPath, ($config | ConvertTo-Json -Depth 8), [Text.UTF8Encoding]::new($false))
        Write-Host "Created local config: $configPath"
    }
} else {
    Write-Host "Preserved existing local config: $configPath"
    $config = Get-Content -Raw -LiteralPath $configPath | ConvertFrom-Json
    if ([string]$config.workstation_id -ne $WorkstationId) {
        throw "La config esistente appartiene a '$($config.workstation_id)', non a '$WorkstationId'. Non viene modificata automaticamente."
    }
    $changed = $false
    $profileStatePath = (Join-Path $configDir 'creative_state.json').Replace('\', '/')
    $profileAuditPath = (Join-Path $configDir 'audit.jsonl').Replace('\', '/')
    if ([string]$config.state_path -ne $profileStatePath) {
        $config.state_path = $profileStatePath
        $changed = $true
    }
    if ([string]$config.audit_log_path -ne $profileAuditPath) {
        $config.audit_log_path = $profileAuditPath
        $changed = $true
    }
    if ($null -eq $config.PSObject.Properties['media_roots']) {
        $config | Add-Member -NotePropertyName media_roots -NotePropertyValue @((Join-Path $env:USERPROFILE 'Downloads').Replace('\', '/'))
        $changed = $true
    }
    if ($null -eq $config.PSObject.Properties['transcript_root']) {
        $config | Add-Member -NotePropertyName transcript_root -NotePropertyValue ((Join-Path $env:LOCALAPPDATA 'ARPHE\Longform04\transcripts').Replace('\', '/'))
        $changed = $true
    }
    if ($null -eq $config.PSObject.Properties['audio_root']) {
        $config | Add-Member -NotePropertyName audio_root -NotePropertyValue ((Join-Path $env:LOCALAPPDATA 'ARPHE\Longform04\audio').Replace('\', '/'))
        $changed = $true
    }
    if ($null -eq $config.PSObject.Properties['audio_jobs_root']) {
        $config | Add-Member -NotePropertyName audio_jobs_root -NotePropertyValue ((Join-Path $env:LOCALAPPDATA 'ARPHE\Longform04\audio_jobs').Replace('\', '/'))
        $changed = $true
    }
    if ($null -eq $config.feature_flags.PSObject.Properties['CAP_LONGFORM']) {
        $config.feature_flags | Add-Member -NotePropertyName CAP_LONGFORM -NotePropertyValue $false
        $changed = $true
    }
    if ($null -eq $config.feature_flags.PSObject.Properties['CAP_CLEANUP']) {
        $config.feature_flags | Add-Member -NotePropertyName CAP_CLEANUP -NotePropertyValue $false
        $changed = $true
    }
    if ($changed) {
        [IO.File]::WriteAllText($configPath, ($config | ConvertTo-Json -Depth 16), [Text.UTF8Encoding]::new($false))
        Write-Host 'Migrated existing config with missing gated longform fields; existing flag values preserved.'
    }
}

Write-Host "Installed ARPHE_MCP_BRIDGE_CREATIVE_03 beside existing bridges."
Write-Host 'Runtime MCP_COMMAND was NOT changed.'
