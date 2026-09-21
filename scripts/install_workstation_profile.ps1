[CmdletBinding(SupportsShouldProcess)]
param(
    [Parameter(Mandatory)][string]$ProfilePath,
    [switch]$PreflightOnly,
    [switch]$KeepExistingSecret,
    [switch]$AllowTunnelChange,
    [switch]$DoNotStart
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $PSScriptRoot
$validator = Join-Path $PSScriptRoot 'windows_bridge\profile_config.py'
$profilePathResolved = (Resolve-Path -LiteralPath $ProfilePath -ErrorAction Stop).Path
$rawProfile = Get-Content -Raw -LiteralPath $profilePathResolved | ConvertFrom-Json
$profilePython = (Resolve-Path -LiteralPath ([string]$rawProfile.python_path) -ErrorAction Stop).Path

if ($profilePython -like '*\Microsoft\WindowsApps\*') {
    throw 'python_path cannot use a WindowsApps alias.'
}
if (-not (Test-Path -LiteralPath $validator -PathType Leaf)) {
    throw "Profile validator not found: $validator"
}

$normalizedJson = & $profilePython $validator validate --profile $profilePathResolved --emit-json
if ($LASTEXITCODE -ne 0) {
    throw "Profile validation failed with exit code $LASTEXITCODE."
}
$profile = $normalizedJson | ConvertFrom-Json

$pythonw = (Resolve-Path -LiteralPath ([string]$profile.pythonw_path) -ErrorAction Stop).Path
$tunnelClient = (Resolve-Path -LiteralPath ([string]$profile.tunnel_client_path) -ErrorAction Stop).Path
$requirements = (Resolve-Path -LiteralPath ([string]$profile.requirements_path) -ErrorAction Stop).Path
$actualPythonVersion = (& $profilePython -c 'import platform; print(platform.python_version())').Trim()
if ($LASTEXITCODE -ne 0 -or $actualPythonVersion -ne [string]$profile.python_version) {
    throw "Python version mismatch: profile requires $($profile.python_version), executable reports $actualPythonVersion."
}

$runtimeConfigPath = Join-Path $env:LOCALAPPDATA 'ARPHE\WindowsBridgeRuntimeV1\bridge_config.json'
if (Test-Path -LiteralPath $runtimeConfigPath -PathType Leaf) {
    $existing = Get-Content -Raw -LiteralPath $runtimeConfigPath | ConvertFrom-Json
    if ([string]$existing.workstation_id -ne [string]$profile.workstation_id) {
        throw "Existing runtime config belongs to $($existing.workstation_id), not $($profile.workstation_id)."
    }
    if ([string]$existing.tunnel_id -ne [string]$profile.tunnel_id -and -not $AllowTunnelChange) {
        throw 'Existing runtime uses a different tunnel. Re-run with -AllowTunnelChange only after verifying the new workstation-specific tunnel.'
    }
}

$tunnelId = [string]$profile.tunnel_id
$redactedTunnelId = if ($tunnelId.Length -gt 14) { $tunnelId.Substring(0, 14) + '...' } else { 'tunnel_...' }
Write-Host "Workstation : $($profile.workstation_id)"
Write-Host "Tunnel name : $($profile.tunnel_name)"
Write-Host "Tunnel ID   : $redactedTunnelId"
Write-Host "Python      : $actualPythonVersion ($profilePython)"
Write-Host "Venv        : $($profile.venv_root)"
Write-Host "Install root: $($profile.install_root)"
Write-Host "Creative    : $($profile.creative_destination)"

if ($PreflightOnly) {
    Write-Host 'Preflight PASS. No files, tasks or secrets were changed.'
    return
}

if (-not $PSCmdlet.ShouldProcess([string]$profile.workstation_id, 'Install isolated ARPHE Resolve bridge profile')) {
    return
}

$venvRoot = [string]$profile.venv_root
if (-not (Test-Path -LiteralPath (Join-Path $venvRoot 'Scripts\python.exe') -PathType Leaf)) {
    & $profilePython -m venv $venvRoot
    if ($LASTEXITCODE -ne 0) { throw "Virtual environment creation failed with exit code $LASTEXITCODE." }
}
$venvPython = (Resolve-Path -LiteralPath (Join-Path $venvRoot 'Scripts\python.exe') -ErrorAction Stop).Path
$venvPythonw = (Resolve-Path -LiteralPath (Join-Path $venvRoot 'Scripts\pythonw.exe') -ErrorAction Stop).Path
& $venvPython -m pip install --disable-pip-version-check -r $requirements
if ($LASTEXITCODE -ne 0) { throw "Dependency installation failed with exit code $LASTEXITCODE." }

$creativeInstaller = Join-Path $PSScriptRoot 'experiments\ARPHE_MCP_BRIDGE_CREATIVE_03\install_on_segreteria.ps1'
& $creativeInstaller -WorkstationId ([string]$profile.workstation_id) -Destination ([string]$profile.creative_destination)

$creativeConfigPath = Join-Path $env:LOCALAPPDATA 'ARPHE\CreativeBridge03\creative_config.json'
$creativeConfig = Get-Content -Raw -LiteralPath $creativeConfigPath | ConvertFrom-Json
foreach ($flag in $profile.feature_flags.PSObject.Properties) {
    if ($null -eq $creativeConfig.feature_flags.PSObject.Properties[$flag.Name]) {
        $creativeConfig.feature_flags | Add-Member -NotePropertyName $flag.Name -NotePropertyValue ([bool]$flag.Value)
    } else {
        $creativeConfig.feature_flags.($flag.Name) = [bool]$flag.Value
    }
}
[IO.File]::WriteAllText($creativeConfigPath, ($creativeConfig | ConvertTo-Json -Depth 16), [Text.UTF8Encoding]::new($false))

$mcpCommand = '"{0}" "{1}"' -f $venvPython.Replace('\', '/'), ([string]$profile.mcp_entrypoint).Replace('\', '/')
$runtimeInstaller = Join-Path $PSScriptRoot 'windows_bridge\install_autostart.ps1'
$runtimeArgs = @{
    WorkstationId = [string]$profile.workstation_id
    TunnelId = [string]$profile.tunnel_id
    TunnelClientPath = $tunnelClient
    McpCommand = $mcpCommand
    InstallRoot = [string]$profile.install_root
    LogDir = [string]$profile.log_dir
    PythonPath = $venvPython
    PythonwPath = $venvPythonw
    DoNotStart = $DoNotStart
}
if ($KeepExistingSecret) { $runtimeArgs.KeepExistingSecret = $true }
& $runtimeInstaller @runtimeArgs

Write-Host "Profile installation completed for $($profile.workstation_id)."
