[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$PackagePath,
    [Parameter(Mandatory)][string]$ProfilePath,
    [ValidateSet('DryRun','Install','Rollback')][string]$Mode = 'DryRun',
    [string]$BackupPath
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Read-Json([string]$Path) { Get-Content -Raw -LiteralPath $Path | ConvertFrom-Json }
function Hash-File([string]$Path) {
    if (Test-Path -LiteralPath $Path -PathType Leaf) { return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant() }
    return $null
}
function Confined([string]$Root,[string]$Relative) {
    if ([IO.Path]::IsPathRooted($Relative) -or $Relative -match '(^|[\\/])\.\.([\\/]|$)') { throw 'Invalid manifest path' }
    $base = [IO.Path]::GetFullPath($Root).TrimEnd('\','/')
    $path = [IO.Path]::GetFullPath((Join-Path $base $Relative))
    if (-not $path.StartsWith($base + [IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)) { throw 'Path outside target root' }
    $walk = $path
    while ($walk) {
        if (Test-Path -LiteralPath $walk) {
            if ((Get-Item -LiteralPath $walk -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Reparse target refused' }
        }
        $walk = Split-Path -Parent $walk
    }
    return $path
}
function Save-Receipt($Receipt,[string]$Path) {
    $Receipt | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath ($Path+'.tmp') -Encoding UTF8
    Move-Item -LiteralPath ($Path+'.tmp') -Destination $Path -Force
}

$package = (Resolve-Path -LiteralPath $PackagePath).Path
$profile = Read-Json ((Resolve-Path -LiteralPath $ProfilePath).Path)
if ([string]$profile.workstation_id -notmatch '^PC_[A-Z0-9_]{2,48}$') { throw 'Invalid workstation identity' }
$destinationProperty = $profile.PSObject.Properties['creative_destination']
if ($destinationProperty) {
    $target = [IO.Path]::GetFullPath([string]$destinationProperty.Value)
} else {
    $command = [string]$profile.bridge_commands.Creative03
    if ($command -notmatch '^"[^"]+"\s+"([^"]+[/\\]ARPHE_MCP_BRIDGE_CREATIVE_03\.py)"$') { throw 'Cannot resolve creative destination from runtime profile' }
    $target = Split-Path -Parent $Matches[1]
}
if (-not (Test-Path -LiteralPath $target -PathType Container)) { throw 'Target must already exist' }
$creativeProperty = $profile.PSObject.Properties['creative_config_path']
if ($creativeProperty) { $creativeConfigPath = [string]$creativeProperty.Value }
else { $creativeConfigPath = Join-Path (Split-Path -Parent ((Resolve-Path -LiteralPath $ProfilePath).Path)) 'creative_config.json' }
$creative = Read-Json $creativeConfigPath
if ([string]$creative.workstation_id -ne [string]$profile.workstation_id) { throw 'Creative/profile ownership mismatch' }
$configHash = Hash-File $creativeConfigPath
$pendingPath = Join-Path $target '.arphe-install-pending.json'
if ($Mode -ne 'Rollback' -and (Test-Path -LiteralPath $pendingPath)) { throw 'Partial installation detected; verified rollback is required' }
$manifestPath = Join-Path $package 'release-manifest.json'
$manifest = Read-Json $manifestPath
if ($manifest.schema_version -ne 1 -or [string]$manifest.release_id -notmatch '^[a-f0-9]{64}$') { throw 'Invalid release manifest' }
$files = @($manifest.files.PSObject.Properties)
if ($files.Count -eq 0) { throw 'Empty release' }
$seen = @{}
foreach ($file in $files) {
    if ($seen.ContainsKey($file.Name.ToLowerInvariant())) { throw 'Duplicate manifest file' }
    $seen[$file.Name.ToLowerInvariant()] = $true
    $source = Confined (Join-Path $package 'payload') $file.Name
    $null = Confined $target $file.Name
    if ((Hash-File $source) -ne [string]$file.Value) { throw "Payload hash mismatch: $($file.Name)" }
}
$actualPayload = @(Get-ChildItem -LiteralPath (Join-Path $package 'payload') -Recurse -File)
if ($actualPayload.Count -ne $files.Count) { throw 'Unexpected package payload files' }
# A sidecar SHA256 pins the complete deterministic manifest, including baseline rules.
$manifestHashPath = Join-Path $package 'release-manifest.sha256'
if (-not (Test-Path -LiteralPath $manifestHashPath) -or (Get-Content -Raw -LiteralPath $manifestHashPath).Trim() -ne (Hash-File $manifestPath)) { throw 'Manifest hash mismatch' }

if ($Mode -eq 'Rollback') {
    if (-not $BackupPath) { throw 'Rollback requires BackupPath' }
    $backup = (Resolve-Path -LiteralPath $BackupPath).Path
    if ((Test-Path -LiteralPath $pendingPath) -and (Get-Content -Raw -LiteralPath $pendingPath) -ne $backup) { throw 'Pending transaction belongs to another backup' }
    $receiptPath = Join-Path $backup 'receipt.json'
    $receipt = Read-Json $receiptPath
    if ($receipt.target -ne $target -or $receipt.workstation_id -ne $profile.workstation_id -or $receipt.release_id -ne $manifest.release_id) { throw 'Rollback identity mismatch' }
    if ($receipt.state -eq 'rolled_back') { Write-Output 'Already rolled back'; return }
    foreach ($entry in $receipt.files) {
        $expectedAfter = if ($entry.path -eq 'release-manifest.json') { Hash-File $manifestPath } else { $manifest.files.PSObject.Properties[$entry.path].Value }
        if ($entry.after -ne $expectedAfter) { throw 'Rollback receipt does not match release' }
        $path = Confined $target $entry.path
        $hash = Hash-File $path
        if ($hash -ne $entry.after -and $hash -ne $entry.before) { throw "Rollback target drift: $($entry.path)" }
        if ($null -ne $entry.before -and (Hash-File (Confined (Join-Path $backup 'files') $entry.path)) -ne $entry.before) { throw 'Rollback backup hash mismatch' }
    }
    foreach ($entry in $receipt.files) {
        $path = Confined $target $entry.path
        if ($null -eq $entry.before) { if (Test-Path -LiteralPath $path) { Remove-Item -LiteralPath $path } }
        else { Copy-Item -LiteralPath (Confined (Join-Path $backup 'files') $entry.path) -Destination $path -Force }
        if ((Hash-File $path) -ne $entry.before) { throw 'Rollback readback mismatch' }
        $temporary = $path+'.arphe-install.tmp'
        if (Test-Path -LiteralPath $temporary) {
            if ((Hash-File $temporary) -ne $entry.after) { throw 'Unexpected partial temporary file' }
            Remove-Item -LiteralPath $temporary
        }
    }
    $receipt.state = 'rolled_back'; Save-Receipt $receipt $receiptPath
    if (Test-Path -LiteralPath $pendingPath) { Remove-Item -LiteralPath $pendingPath }
    Write-Output 'Verified rollback complete'; return
}

foreach ($existing in @(Get-ChildItem -LiteralPath (Join-Path $target 'bridge') -Filter '*.py' -File)) {
    if (-not $seen.ContainsKey(('bridge/'+$existing.Name).ToLowerInvariant())) { throw "Unbound target module: $($existing.Name)" }
}
$changes = @()
$newOnlyMatches = @()
foreach ($file in $files) {
    $path = Confined $target $file.Name
    $before = Hash-File $path
    $accepted = @($manifest.accepted_baselines.PSObject.Properties[$file.Name].Value)
    if ($before -eq [string]$file.Value) {
        if ($accepted -notcontains $before) { $newOnlyMatches += $file.Name }
        continue
    }
    if ($accepted -notcontains $before) { throw "Target baseline drift: $($file.Name)" }
    $changes += [pscustomobject]@{path=$file.Name;before=$before;after=[string]$file.Value}
}
$identityTarget = Join-Path $target 'release-manifest.json'
if (Test-Path -LiteralPath $identityTarget) {
    $installed = Read-Json $identityTarget
    if ($changes.Count -eq 0 -and $installed.release_id -eq $manifest.release_id -and (Hash-File $identityTarget) -eq (Hash-File $manifestPath)) { Write-Output 'Already installed and verified'; return }
}
if ($newOnlyMatches.Count -gt 0) { throw 'Mixed or partial release detected; verified rollback/reconciliation required' }
if ($Mode -eq 'DryRun') { Write-Output "Validated $($profile.workstation_id): $($changes.Count) changed files; release $($manifest.release_id)"; return }
if (-not $BackupPath) { throw 'Install requires a new BackupPath' }
$backup = [IO.Path]::GetFullPath($BackupPath)
if ($backup -eq $target -or $backup.StartsWith($target.TrimEnd('\')+'\',[StringComparison]::OrdinalIgnoreCase) -or (Test-Path -LiteralPath $backup)) { throw 'Backup must be new and outside target' }
$null = New-Item -ItemType Directory -Path $backup
# Identity manifest participates in backup and rollback like payload files.
$changes += [pscustomobject]@{path='release-manifest.json';before=(Hash-File $identityTarget);after=(Hash-File $manifestPath)}
foreach ($entry in $changes) {
    if ($null -ne $entry.before) {
        $saved = Confined (Join-Path $backup 'files') $entry.path
        $null = New-Item -ItemType Directory -Force -Path (Split-Path -Parent $saved)
        Copy-Item -LiteralPath (Confined $target $entry.path) -Destination $saved
        if ((Hash-File $saved) -ne $entry.before) { throw 'Backup verification failed' }
    }
}
$receipt = [pscustomobject]@{schema_version=1;workstation_id=$profile.workstation_id;target=$target;release_id=$manifest.release_id;state='prepared';files=@($changes)}
$receiptPath = Join-Path $backup 'receipt.json'
Save-Receipt $receipt $receiptPath
$null = New-Item -ItemType File -Path $pendingPath -Value $backup
try {
    $receipt.state = 'writing'; Save-Receipt $receipt $receiptPath
    foreach ($entry in $changes) {
        $path = Confined $target $entry.path
        if ((Hash-File $path) -ne $entry.before) { throw 'Target changed since preflight' }
        $source = if ($entry.path -eq 'release-manifest.json') { $manifestPath } else { Confined (Join-Path $package 'payload') $entry.path }
        if ((Hash-File $source) -ne $entry.after) { throw 'Payload changed since preflight' }
        $null = New-Item -ItemType Directory -Force -Path (Split-Path -Parent $path)
        Copy-Item -LiteralPath $source -Destination ($path+'.arphe-install.tmp') -Force
        if ((Hash-File ($path+'.arphe-install.tmp')) -ne $entry.after) { throw 'Staged payload readback mismatch' }
        Move-Item -LiteralPath ($path+'.arphe-install.tmp') -Destination $path -Force
        if ((Hash-File $path) -ne $entry.after) { throw 'Installed payload readback mismatch' }
    }
    if ((Hash-File $creativeConfigPath) -ne $configHash) { throw 'Configuration changed during installation' }
    $receipt.state='installed'; Save-Receipt $receipt $receiptPath
    Remove-Item -LiteralPath $pendingPath
    Write-Output "Installed and verified $($manifest.release_id); rollback: $backup"
} catch {
    $receipt.state='rollback_required'; Save-Receipt $receipt $receiptPath
    throw "Install interrupted; runtime must remain stopped. Use verified Rollback with BackupPath '$backup'. $($_.Exception.Message)"
}
