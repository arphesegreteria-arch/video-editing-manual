[CmdletBinding(SupportsShouldProcess)]
param(
    [ValidatePattern('^PC_[A-Z0-9_]{2,48}$')][string]$WorkstationId = 'PC_SEGRETERIA',
    [string]$Destination = 'C:\ARPHE\MCP\ARPHE_MCP_BRIDGE_CREATIVE_03',
    [string]$AssetRoot = 'C:\ARPHE\MCP\assets\creative',
    [string]$RenderRoot = 'C:\ARPHE\MCP\renders\creative',
    [string]$RuntimeLogRoot = '',
    [Parameter(Mandatory)][string]$ConfigPath
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$configPath = [IO.Path]::GetFullPath($ConfigPath)
$configDir = Split-Path -Parent $configPath
$artifactRegistryPath = Join-Path $configDir 'artifact_registry.json'
$resolveArchiveRoot = Join-Path $configDir 'resolve-retirement-archives'
$resolveRetirementRegistryPath = Join-Path $configDir 'resolve_retirement_registry.json'
$editorialJobsPath = Join-Path $configDir 'editorial_jobs.json'
$editorialJournalPath = Join-Path $configDir 'editorial_journal.jsonl'
$editorialOverlayPath = Join-Path $configDir 'editorial_profile_overlay.json'
$editorialProposalsPath = Join-Path $configDir 'editorial_profile_proposals.json'
if (-not $RuntimeLogRoot) {
    $RuntimeLogRoot = Join-Path 'C:\ARPHE\MCP\logs\ARPHE_WINDOWS_BRIDGE_RUNTIME_V1' $WorkstationId
}
$RuntimeLogRoot = [IO.Path]::GetFullPath($RuntimeLogRoot)
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
if (Test-Path -LiteralPath $configPath -PathType Leaf) {
    $existingConfigIdentity = Get-Content -Raw -LiteralPath $configPath | ConvertFrom-Json
    if ([string]$existingConfigIdentity.workstation_id -ne $WorkstationId) {
        throw "La config esistente appartiene a '$($existingConfigIdentity.workstation_id)', non a '$WorkstationId'. Installazione rifiutata senza modifiche."
    }
}

if (Test-Path -LiteralPath $artifactRegistryPath -PathType Leaf) {
    $existingArtifactRegistry = Get-Content -Raw -LiteralPath $artifactRegistryPath | ConvertFrom-Json
    if ([string]$existingArtifactRegistry.workstation_id -ne $WorkstationId) {
        throw "Il registry artefatti appartiene a '$($existingArtifactRegistry.workstation_id)', non a '$WorkstationId'. Installazione rifiutata senza modifiche."
    }
}
if (Test-Path -LiteralPath $resolveRetirementRegistryPath -PathType Leaf) {
    $existingResolveRegistry = Get-Content -Raw -LiteralPath $resolveRetirementRegistryPath | ConvertFrom-Json
    if ([string]$existingResolveRegistry.workstation_id -ne $WorkstationId) {
        throw "Il registry retirement Resolve appartiene a '$($existingResolveRegistry.workstation_id)', non a '$WorkstationId'. Installazione rifiutata senza modifiche."
    }
}
foreach ($editorialState in @($editorialJobsPath, $editorialOverlayPath, $editorialProposalsPath)) {
    if (Test-Path -LiteralPath $editorialState -PathType Leaf) {
        $existingEditorialState = Get-Content -Raw -LiteralPath $editorialState | ConvertFrom-Json
        if ([string]$existingEditorialState.workstation_id -ne $WorkstationId) {
            throw "Lo stato editoriale '$editorialState' appartiene a '$($existingEditorialState.workstation_id)', non a '$WorkstationId'. Installazione rifiutata senza modifiche."
        }
    }
}
if (Test-Path -LiteralPath $editorialJournalPath -PathType Leaf) {
    $firstEditorialRecord = Get-Content -LiteralPath $editorialJournalPath | Where-Object { $_.Trim() } | Select-Object -First 1
    if ($firstEditorialRecord) {
        $existingEditorialJournal = $firstEditorialRecord | ConvertFrom-Json
        if ([string]$existingEditorialJournal.workstation_id -ne $WorkstationId) {
            throw "Il journal editoriale appartiene a '$($existingEditorialJournal.workstation_id)', non a '$WorkstationId'. Installazione rifiutata senza modifiche."
        }
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
foreach ($registryName in @('editorial_workflows.json', 'render_profiles.json', 'artifact_retention.json', 'review_readability_contract.json', 'editorial_selection_contract.json', 'editorial_preferences.json')) {
    $registrySource = Join-Path $PSScriptRoot $registryName
    if (-not (Test-Path -LiteralPath $registrySource -PathType Leaf)) {
        throw "Creative registry not found: $registrySource"
    }
    Copy-Item -LiteralPath $registrySource -Destination (Join-Path $Destination $registryName) -Force
}
New-Item -ItemType Directory -Path $AssetRoot -Force | Out-Null
New-Item -ItemType Directory -Path $RenderRoot -Force | Out-Null
New-Item -ItemType Directory -Path $RuntimeLogRoot -Force | Out-Null
New-Item -ItemType Directory -Path $configDir -Force | Out-Null
New-Item -ItemType Directory -Path $resolveArchiveRoot -Force | Out-Null
$carrierSource = Join-Path $PSScriptRoot 'assets\arphe_fusion_carrier_5m.mp4'
if (-not (Test-Path -LiteralPath $carrierSource)) {
    throw "Asset tecnico di durata non trovato: $carrierSource"
}
Copy-Item -LiteralPath $carrierSource -Destination (Join-Path $AssetRoot 'arphe_fusion_carrier_5m.mp4') -Force

if (-not (Test-Path -LiteralPath $configPath)) {
    $config = if ($null -ne $legacyConfig) { $legacyConfig } else { Get-Content -Raw -LiteralPath $examplePath | ConvertFrom-Json }
    $legacyStatePath = [string]$config.state_path
    $legacyAuditPath = [string]$config.audit_log_path
    Set-ConfigProperty -Config $config -Name workstation_id -Value $WorkstationId
    Set-ConfigProperty -Config $config -Name asset_root -Value $AssetRoot.Replace('\', '/')
    Set-ConfigProperty -Config $config -Name render_root -Value $RenderRoot.Replace('\', '/')
    Set-ConfigProperty -Config $config -Name state_path -Value (Join-Path $configDir 'creative_state.json').Replace('\', '/')
    Set-ConfigProperty -Config $config -Name audit_log_path -Value (Join-Path $configDir 'audit.jsonl').Replace('\', '/')
    Set-ConfigProperty -Config $config -Name artifact_policy_path -Value (Join-Path $Destination 'artifact_retention.json').Replace('\', '/')
    Set-ConfigProperty -Config $config -Name artifact_registry_path -Value $artifactRegistryPath.Replace('\', '/')
    Set-ConfigProperty -Config $config -Name runtime_log_root -Value $RuntimeLogRoot.Replace('\', '/')
    Set-ConfigProperty -Config $config -Name resolve_archive_root -Value $resolveArchiveRoot.Replace('\', '/')
    Set-ConfigProperty -Config $config -Name resolve_retirement_registry_path -Value $resolveRetirementRegistryPath.Replace('\', '/')
    Set-ConfigProperty -Config $config -Name editorial_jobs_path -Value $editorialJobsPath.Replace('\', '/')
    Set-ConfigProperty -Config $config -Name editorial_journal_path -Value $editorialJournalPath.Replace('\', '/')
    Set-ConfigProperty -Config $config -Name editorial_profile_overlay_path -Value $editorialOverlayPath.Replace('\', '/')
    Set-ConfigProperty -Config $config -Name editorial_profile_proposals_path -Value $editorialProposalsPath.Replace('\', '/')
    if ($null -eq $config.feature_flags.PSObject.Properties['CAP_ARTIFACT_MAINTENANCE']) {
        $config.feature_flags | Add-Member -NotePropertyName CAP_ARTIFACT_MAINTENANCE -NotePropertyValue $false
    }
    if ($null -eq $config.feature_flags.PSObject.Properties['CAP_RESOLVE_RETIREMENT']) {
        $config.feature_flags | Add-Member -NotePropertyName CAP_RESOLVE_RETIREMENT -NotePropertyValue $false
    }
    if ($null -eq $config.feature_flags.PSObject.Properties['CAP_READABILITY_GUARD']) {
        $config.feature_flags | Add-Member -NotePropertyName CAP_READABILITY_GUARD -NotePropertyValue $false
    }
    if ($null -eq $config.feature_flags.PSObject.Properties['CAP_EDITORIAL_SELECTION']) {
        $config.feature_flags | Add-Member -NotePropertyName CAP_EDITORIAL_SELECTION -NotePropertyValue $false
    }
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
    $profileArtifactPolicyPath = (Join-Path $Destination 'artifact_retention.json').Replace('\', '/')
    $profileArtifactRegistryPath = $artifactRegistryPath.Replace('\', '/')
    $profileRuntimeLogRoot = $RuntimeLogRoot.Replace('\', '/')
    $profileResolveArchiveRoot = $resolveArchiveRoot.Replace('\', '/')
    $profileResolveRetirementRegistryPath = $resolveRetirementRegistryPath.Replace('\', '/')
    if ([string]$config.state_path -ne $profileStatePath) {
        $config.state_path = $profileStatePath
        $changed = $true
    }
    if ([string]$config.audit_log_path -ne $profileAuditPath) {
        $config.audit_log_path = $profileAuditPath
        $changed = $true
    }
    foreach ($pathField in @(
        @{ Name = 'artifact_policy_path'; Value = $profileArtifactPolicyPath },
        @{ Name = 'artifact_registry_path'; Value = $profileArtifactRegistryPath },
        @{ Name = 'runtime_log_root'; Value = $profileRuntimeLogRoot },
        @{ Name = 'resolve_archive_root'; Value = $profileResolveArchiveRoot },
        @{ Name = 'resolve_retirement_registry_path'; Value = $profileResolveRetirementRegistryPath },
        @{ Name = 'editorial_jobs_path'; Value = $editorialJobsPath.Replace('\', '/') },
        @{ Name = 'editorial_journal_path'; Value = $editorialJournalPath.Replace('\', '/') },
        @{ Name = 'editorial_profile_overlay_path'; Value = $editorialOverlayPath.Replace('\', '/') },
        @{ Name = 'editorial_profile_proposals_path'; Value = $editorialProposalsPath.Replace('\', '/') }
    )) {
        if ($null -eq $config.PSObject.Properties[$pathField.Name]) {
            $config | Add-Member -NotePropertyName $pathField.Name -NotePropertyValue $pathField.Value
            $changed = $true
        } elseif ([string]$config.($pathField.Name) -ne $pathField.Value) {
            $config.($pathField.Name) = $pathField.Value
            $changed = $true
        }
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
    if ($null -eq $config.feature_flags.PSObject.Properties['CAP_ARTIFACT_MAINTENANCE']) {
        $config.feature_flags | Add-Member -NotePropertyName CAP_ARTIFACT_MAINTENANCE -NotePropertyValue $false
        $changed = $true
    }
    if ($null -eq $config.feature_flags.PSObject.Properties['CAP_RESOLVE_RETIREMENT']) {
        $config.feature_flags | Add-Member -NotePropertyName CAP_RESOLVE_RETIREMENT -NotePropertyValue $false
        $changed = $true
    }
    if ($null -eq $config.feature_flags.PSObject.Properties['CAP_READABILITY_GUARD']) {
        $config.feature_flags | Add-Member -NotePropertyName CAP_READABILITY_GUARD -NotePropertyValue $false
        $changed = $true
    }
    if ($null -eq $config.feature_flags.PSObject.Properties['CAP_EDITORIAL_SELECTION']) {
        $config.feature_flags | Add-Member -NotePropertyName CAP_EDITORIAL_SELECTION -NotePropertyValue $false
        $changed = $true
    }
    if ($changed) {
        [IO.File]::WriteAllText($configPath, ($config | ConvertTo-Json -Depth 16), [Text.UTF8Encoding]::new($false))
        Write-Host 'Migrated existing config with missing gated longform fields; existing flag values preserved.'
    }
}

Write-Host "Installed ARPHE_MCP_BRIDGE_CREATIVE_03 beside existing bridges."
Write-Host 'Runtime MCP_COMMAND was NOT changed.'
