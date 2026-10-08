[CmdletBinding(SupportsShouldProcess)]
param(
    [Parameter(Mandatory)]
    [ValidatePattern('^PC_[A-Z0-9_]{2,48}$')]
    [string]$WorkstationId,

    [Parameter(Mandatory)]
    [string]$ProfilePath,

    [Parameter(Mandatory)]
    [ValidateSet('CAP_PROJECT', 'CAP_TIMELINE', 'CAP_FUSION', 'CAP_REVIEW',
                 'CAP_MOTION', 'CAP_ASSETS', 'CAP_RENDER', 'CAP_LONGFORM', 'CAP_CLEANUP',
                 'CAP_ARTIFACT_MAINTENANCE', 'CAP_RESOLVE_RETIREMENT', 'CAP_READABILITY_GUARD',
                 'CAP_EDITORIAL_SELECTION')]
    [string]$Name,

    [Parameter(Mandatory)]
    [bool]$Enabled
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$lifecycleRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..\windows_bridge')).Path
. (Join-Path $lifecycleRoot 'common.ps1') -WorkstationId $WorkstationId -ProfilePath $ProfilePath
if (-not (Test-Path -LiteralPath $script:ArpheConfigPath -PathType Leaf)) {
    throw "Runtime config non trovata per ${WorkstationId}: $script:ArpheConfigPath"
}
$runtimeConfig = Get-Content -Raw -LiteralPath $script:ArpheConfigPath | ConvertFrom-Json
if ([string]$runtimeConfig.workstation_id -ne $WorkstationId) {
    throw "Runtime config appartiene a $($runtimeConfig.workstation_id), non a $WorkstationId."
}
$creativeConfigPath = [string]$runtimeConfig.creative_config_path
if (-not (Test-Path -LiteralPath $creativeConfigPath -PathType Leaf)) {
    throw "Config Creative03 non trovata: $creativeConfigPath"
}
Write-Host "Creative config: $creativeConfigPath"
Write-Host "Workstation: $WorkstationId"

$creativeConfig = Get-Content -Raw -LiteralPath $creativeConfigPath | ConvertFrom-Json
if (-not $creativeConfig.feature_flags) {
    throw 'feature_flags assente dalla config Creative03.'
}

$flagProperty = $creativeConfig.feature_flags.PSObject.Properties[$Name]
if ($null -eq $flagProperty -or $flagProperty.Value -isnot [bool]) {
    throw "Flag non booleano o assente: $Name"
}

$previousValue = [bool]$flagProperty.Value
if ($previousValue -eq $Enabled) {
    Write-Host "$Name è già impostato a $Enabled. Nessuna modifica."
    return
}

if (-not $PSCmdlet.ShouldProcess($creativeConfigPath, "Set $Name=$Enabled")) {
    return
}

$flagProperty.Value = $Enabled
$temporaryPath = $creativeConfigPath + '.tmp'
$json = $creativeConfig | ConvertTo-Json -Depth 16
try {
    [IO.File]::WriteAllText($temporaryPath, $json, [Text.UTF8Encoding]::new($false))
    Move-Item -LiteralPath $temporaryPath -Destination $creativeConfigPath -Force
} finally {
    if (Test-Path -LiteralPath $temporaryPath -PathType Leaf) {
        Remove-Item -LiteralPath $temporaryPath -Force
    }
}

Write-Host "Creative03: $Name $previousValue -> $Enabled"
Write-Host 'Riavviare il runtime ARPHE per applicare la modifica.'
