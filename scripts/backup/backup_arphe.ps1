[CmdletBinding(SupportsShouldProcess)]
param(
    [Parameter(Mandatory)]
    [string]$DestinationRoot,
    [switch]$IncludeCurrentResolveProject,
    [switch]$AllowSystemDrive,
    [string]$PythonPath = 'C:\Users\auras\AppData\Local\Python\pythoncore-3.14-64\python.exe'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$repoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..')).Path
$destinationFull = [IO.Path]::GetFullPath($DestinationRoot)
$destinationDrive = [IO.Path]::GetPathRoot($destinationFull)
$systemDrive = [IO.Path]::GetPathRoot($env:SystemRoot)
if (-not $AllowSystemDrive -and $destinationDrive -eq $systemDrive) {
    throw "Destinazione sul disco di sistema rifiutata. Usare un disco esterno oppure -AllowSystemDrive consapevolmente."
}
if (-not (Test-Path -LiteralPath $destinationDrive -PathType Container)) {
    throw "Unità di destinazione non disponibile: $destinationDrive"
}

$dirty = @(& git -C $repoRoot status --porcelain)
if ($LASTEXITCODE -ne 0) { throw 'Impossibile leggere lo stato Git.' }
if ($dirty.Count -gt 0) {
    throw 'Repository non pulita: fare commit oppure annullare le modifiche prima del backup verificabile.'
}

$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$backupDir = Join-Path $destinationFull "ARPHE_BACKUP_$stamp"
if (-not $PSCmdlet.ShouldProcess($backupDir, 'Create verified ARPHE backup')) { return }
New-Item -ItemType Directory -Path $backupDir -Force | Out-Null

$bundlePath = Join-Path $backupDir 'video-editing-manual.bundle'
& git -C $repoRoot bundle create $bundlePath --all
if ($LASTEXITCODE -ne 0) { throw 'Creazione Git bundle fallita.' }
$snapshotPath = Join-Path $backupDir 'video-editing-manual-HEAD.zip'
& git -C $repoRoot archive --format=zip --output=$snapshotPath HEAD
if ($LASTEXITCODE -ne 0) { throw 'Creazione snapshot Git fallita.' }

$stateDir = Join-Path $backupDir 'creative-state'
New-Item -ItemType Directory -Path $stateDir -Force | Out-Null
$creativeDir = Join-Path $env:LOCALAPPDATA 'ARPHE\CreativeBridge03'
foreach ($name in @('creative_state.json', 'audit.jsonl')) {
    $source = Join-Path $creativeDir $name
    if (Test-Path -LiteralPath $source -PathType Leaf) {
        Copy-Item -LiteralPath $source -Destination $stateDir
    }
}

$creativeConfig = Join-Path $creativeDir 'creative_config.json'
if (Test-Path -LiteralPath $creativeConfig -PathType Leaf) {
    $creative = Get-Content -Raw -LiteralPath $creativeConfig | ConvertFrom-Json
    $safeCreative = [ordered]@{}
    foreach ($property in $creative.PSObject.Properties) {
        if ($property.Name -notmatch '(?i)secret|token|key|auth|credential') {
            $safeCreative[$property.Name] = $property.Value
        }
    }
    [IO.File]::WriteAllText(
        (Join-Path $stateDir 'creative_config.redacted.json'),
        ($safeCreative | ConvertTo-Json -Depth 8),
        [Text.UTF8Encoding]::new($false)
    )
}

$runtimeConfig = Join-Path $env:LOCALAPPDATA 'ARPHE\WindowsBridgeRuntimeV1\bridge_config.json'
if (Test-Path -LiteralPath $runtimeConfig -PathType Leaf) {
    $runtime = Get-Content -Raw -LiteralPath $runtimeConfig | ConvertFrom-Json
    $safeRuntime = [ordered]@{}
    foreach ($property in $runtime.PSObject.Properties) {
        if ($property.Name -notmatch '(?i)secret|token|key|auth|credential') {
            $safeRuntime[$property.Name] = $property.Value
        }
    }
    [IO.File]::WriteAllText(
        (Join-Path $stateDir 'bridge_config.redacted.json'),
        ($safeRuntime | ConvertTo-Json -Depth 8),
        [Text.UTF8Encoding]::new($false)
    )
}

if ($IncludeCurrentResolveProject) {
    if (-not (Test-Path -LiteralPath $PythonPath -PathType Leaf)) {
        throw "Python non trovato: $PythonPath"
    }
    $resolveDir = Join-Path $backupDir 'resolve-projects'
    New-Item -ItemType Directory -Path $resolveDir -Force | Out-Null
    & $PythonPath (Join-Path $PSScriptRoot 'export_current_arphe_project.py') $resolveDir
    if ($LASTEXITCODE -ne 0) { throw 'Export del progetto Resolve corrente fallito.' }
}

$files = Get-ChildItem -LiteralPath $backupDir -File -Recurse | Sort-Object FullName
$manifest = [ordered]@{
    schema_version = 1
    created_at = (Get-Date).ToString('o')
    source_repository = $repoRoot
    git_commit = (& git -C $repoRoot rev-parse HEAD).Trim()
    includes_dpapi_secret = $false
    files = @($files | ForEach-Object {
        [ordered]@{
            path = [IO.Path]::GetRelativePath($backupDir, $_.FullName).Replace('\', '/')
            size_bytes = $_.Length
            sha256 = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash
        }
    })
}
[IO.File]::WriteAllText(
    (Join-Path $backupDir 'MANIFEST.json'),
    ($manifest | ConvertTo-Json -Depth 8),
    [Text.UTF8Encoding]::new($false)
)

Write-Host "Backup completato e verificabile: $backupDir"
Write-Host 'La runtime API key DPAPI non è stata copiata.'
