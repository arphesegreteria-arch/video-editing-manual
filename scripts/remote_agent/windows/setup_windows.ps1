[CmdletBinding()]
param(
    [switch] $CreateDefaultFolders,
    [switch] $SkipTokenSetup
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$agentDirectory = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$projectDirectory = (Resolve-Path -LiteralPath (Join-Path $agentDirectory '..\..')).Path
$venvDirectory = Join-Path $agentDirectory '.venv'
$configPath = Join-Path $agentDirectory 'config.json'
$exampleConfigPath = Join-Path $agentDirectory 'config.example.json'
$launcherPath = Join-Path $PSScriptRoot 'start_agent.bat'
$desktopShortcutPath = Join-Path ([Environment]::GetFolderPath('Desktop')) 'ARPHE Remote Agent.lnk'

function Get-Python311Command {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        & py -3.11 -c "import sys; raise SystemExit(0 if sys.version_info[:2] >= (3, 11) else 1)"
        if ($LASTEXITCODE -eq 0) { return @('py', '-3.11') }
    }
    if (Get-Command python -ErrorAction SilentlyContinue) {
        & python -c "import sys; raise SystemExit(0 if sys.version_info[:2] >= (3, 11) else 1)"
        if ($LASTEXITCODE -eq 0) { return @('python') }
    }
    throw 'Python 3.11 or newer is required. Install it from python.org, then run this setup again.'
}

function Assert-ConfigValue([string] $Label, [string] $Value, [string] $Pattern) {
    if ([string]::IsNullOrWhiteSpace($Value) -or $Value -notmatch $Pattern) {
        throw "Invalid $Label."
    }
}

function Read-Default([string] $Prompt, [string] $Default) {
    $value = Read-Host "$Prompt [$Default]"
    if ([string]::IsNullOrWhiteSpace($value)) { return $Default }
    return $value.Trim()
}

function Initialize-NewConfig {
    $config = Get-Content -LiteralPath $exampleConfigPath -Raw | ConvertFrom-Json
    $config.machine_id = Read-Default 'Machine ID (uppercase letters, digits, underscores)' $config.machine_id
    Assert-ConfigValue 'machine ID' $config.machine_id '^[A-Z][A-Z0-9_]{0,63}$'
    $config.github.owner = Read-Default 'Private GitHub owner or organization' $config.github.owner
    Assert-ConfigValue 'GitHub owner' $config.github.owner '^[A-Za-z0-9_.-]{1,128}$'
    $config.github.repository = Read-Default 'Private GitHub repository' $config.github.repository
    Assert-ConfigValue 'GitHub repository' $config.github.repository '^[A-Za-z0-9_.-]{1,128}$'
    $config.github.branch = Read-Default 'GitHub branch' $config.github.branch
    Assert-ConfigValue 'GitHub branch' $config.github.branch '^.{1,256}$'
    $config.resolve.executable_path = Read-Default 'Resolve Studio executable path' $config.resolve.executable_path
    if (-not [IO.Path]::IsPathFullyQualified($config.resolve.executable_path)) { throw 'Resolve executable path must be absolute.' }
    foreach ($folderName in @('incoming', 'test_media', 'workspace', 'exports')) {
        $config.folders.$folderName = Read-Default "Folder path for $folderName" $config.folders.$folderName
        if (-not [IO.Path]::IsPathFullyQualified($config.folders.$folderName)) { throw "Folder path for $folderName must be absolute." }
    }
    $config | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $configPath -Encoding utf8 -NoNewline
}

function New-DesktopShortcut {
    $shell = New-Object -ComObject WScript.Shell
    if (Test-Path -LiteralPath $desktopShortcutPath) {
        $existing = $shell.CreateShortcut($desktopShortcutPath)
        if ($existing.TargetPath -and $existing.TargetPath -ne $launcherPath) {
            throw "Refusing to replace unrelated desktop shortcut: $desktopShortcutPath"
        }
    }
    $shortcut = $shell.CreateShortcut($desktopShortcutPath)
    $shortcut.TargetPath = $launcherPath
    $shortcut.WorkingDirectory = $agentDirectory
    $shortcut.IconLocation = $launcherPath
    $shortcut.Description = 'Manually launch ARPHE Remote Agent'
    $shortcut.Save()
}

Write-Host 'ARPHE Remote Agent — manual HOME_DEV setup'
$pythonCommand = @(Get-Python311Command)
if (-not (Test-Path -LiteralPath $venvDirectory)) {
    if ($pythonCommand.Length -gt 1) {
        & $pythonCommand[0] $pythonCommand[1] -m venv $venvDirectory
    } else {
        & $pythonCommand[0] -m venv $venvDirectory
    }
}
$venvPython = Join-Path $venvDirectory 'Scripts\python.exe'
if (-not (Test-Path -LiteralPath $venvPython)) { throw 'The dedicated virtual environment was not created.' }
& $venvPython -m pip install --upgrade pip
& $venvPython -m pip install -r (Join-Path $agentDirectory 'requirements.txt')

if ($CreateDefaultFolders) {
    foreach ($folder in @('D:\ARPHE\Incoming', 'D:\ARPHE\TestMedia', 'D:\ARPHE\Workspace', 'D:\ARPHE\Exports')) {
        New-Item -ItemType Directory -LiteralPath $folder -Force | Out-Null
    }
}

if (-not (Test-Path -LiteralPath $configPath)) {
    Copy-Item -LiteralPath $exampleConfigPath -Destination $configPath -ErrorAction Stop
    Initialize-NewConfig
} else {
    Write-Host "Keeping the existing local configuration: $configPath"
}

# Validate the strict, secret-free config before creating a launch shortcut.
& $venvPython -c "import sys; from pathlib import Path; sys.path.insert(0, str(Path(sys.argv[2]).resolve())); from scripts.remote_agent.config import AgentConfig; AgentConfig.load(sys.argv[1])" $configPath $projectDirectory
if ($LASTEXITCODE -ne 0) { throw 'The local config.json did not pass ARPHE Remote Agent validation.' }

New-DesktopShortcut
if (-not $SkipTokenSetup) {
    $setToken = Read-Host 'Set or update the GitHub token in Windows Credential Manager now? [Y/n]'
    if ([string]::IsNullOrWhiteSpace($setToken) -or $setToken -match '^[Yy]') {
        & $venvPython (Join-Path $agentDirectory 'start_agent.py') --config $configPath --set-github-token
    }
}

Write-Host 'Setup complete. Use the ARPHE Remote Agent desktop shortcut to start the visible app.'
Write-Host 'This setup creates no service, scheduled task, startup entry, tray process, or automatic background launch.'
