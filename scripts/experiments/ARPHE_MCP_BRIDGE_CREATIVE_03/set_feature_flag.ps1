[CmdletBinding(SupportsShouldProcess)]
param(
    [Parameter(Mandatory)]
    [ValidateSet('CAP_PROJECT', 'CAP_TIMELINE', 'CAP_FUSION', 'CAP_REVIEW',
                 'CAP_MOTION', 'CAP_ASSETS', 'CAP_RENDER')]
    [string]$Name,

    [Parameter(Mandatory)]
    [bool]$Enabled
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$creativeRoot = Join-Path $env:LOCALAPPDATA 'ARPHE\CreativeBridge03'
$creativeConfigPath = Join-Path $creativeRoot 'creative_config.json'
if (-not (Test-Path -LiteralPath $creativeConfigPath -PathType Leaf)) {
    throw "Config Creative03 non trovata: $creativeConfigPath"
}

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
$temporaryPath = Join-Path $creativeRoot 'creative_config.json.tmp'
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
