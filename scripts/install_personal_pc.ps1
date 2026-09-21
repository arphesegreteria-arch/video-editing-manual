[CmdletBinding(SupportsShouldProcess)]
param(
    [Parameter(Mandatory)][string]$ProfilePath,
    [switch]$PreflightOnly,
    [switch]$KeepExistingSecret,
    [switch]$AllowTunnelChange,
    [switch]$DoNotStart
)

$installer = Join-Path $PSScriptRoot 'install_workstation_profile.ps1'
& $installer -ProfilePath $ProfilePath -PreflightOnly:$PreflightOnly `
    -KeepExistingSecret:$KeepExistingSecret -AllowTunnelChange:$AllowTunnelChange `
    -DoNotStart:$DoNotStart -WhatIf:$WhatIfPreference
