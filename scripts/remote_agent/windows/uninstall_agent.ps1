[CmdletBinding(SupportsShouldProcess)]
param()

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$agentDirectory = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$venvDirectory = Join-Path $agentDirectory '.venv'
$configPath = Join-Path $agentDirectory 'config.json'
$launcherPath = Join-Path $PSScriptRoot 'start_agent.bat'
$desktopShortcutPath = Join-Path ([Environment]::GetFolderPath('Desktop')) 'ARPHE Remote Agent.lnk'

function Remove-ExactChild([string] $Path, [string] $ExpectedLeaf, [switch] $Recursive) {
    if (-not (Test-Path -LiteralPath $Path)) { return }
    $item = Get-Item -LiteralPath $Path
    if ($item.Name -ne $ExpectedLeaf -or $item.Directory.FullName -ne $agentDirectory -or
        ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
        throw "Refusing an unsafe uninstall target: $Path"
    }
    if ($PSCmdlet.ShouldProcess($Path, 'Remove ARPHE Remote Agent state')) {
        if ($Recursive) { Remove-Item -LiteralPath $Path -Recurse -Force }
        else { Remove-Item -LiteralPath $Path -Force }
    }
}

if (Test-Path -LiteralPath $desktopShortcutPath) {
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($desktopShortcutPath)
    if ($shortcut.TargetPath -eq $launcherPath -and $PSCmdlet.ShouldProcess($desktopShortcutPath, 'Remove ARPHE shortcut')) {
        Remove-Item -LiteralPath $desktopShortcutPath -Force
    }
}

Remove-ExactChild -Path $venvDirectory -ExpectedLeaf '.venv' -Recursive
Remove-ExactChild -Path $configPath -ExpectedLeaf 'config.json'

Write-Host 'Uninstall complete. Media folders, exports, and local logs are preserved by default.'
Write-Host 'No service, scheduled task, startup entry, or background process is created or removed by this script.'
