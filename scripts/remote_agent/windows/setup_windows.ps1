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

function Read-Default([string] $Prompt, [string] $Default, [scriptblock] $PromptReader) {
    if ($null -ne $PromptReader) {
        $value = & $PromptReader $Prompt $Default
    } else {
        $value = Read-Host "$Prompt [$Default]"
    }
    if ([string]::IsNullOrWhiteSpace($value)) { return $Default }
    return $value.Trim()
}

function Read-Confirmation([string] $Prompt, [scriptblock] $PromptReader) {
    return (Read-Default $Prompt 'N' $PromptReader) -match '^[Yy]$'
}

function Assert-LastExitCode([string] $Step) {
    if ($LASTEXITCODE -ne 0) {
        throw "Failed while $Step (exit code $LASTEXITCODE)."
    }
}

function Initialize-NewConfig(
    [string] $AgentDirectory,
    [string] $ConfigPath,
    [string] $ExampleConfigPath,
    [scriptblock] $ConfigValidator,
    [scriptblock] $PromptReader
) {
    if ([string]::IsNullOrWhiteSpace($AgentDirectory) -or [string]::IsNullOrWhiteSpace($ConfigPath) -or [string]::IsNullOrWhiteSpace($ExampleConfigPath) -or $null -eq $ConfigValidator) {
        throw 'The configuration transaction requires an agent directory, config paths, and strict validator.'
    }
    if (Test-Path -LiteralPath $ConfigPath) {
        throw 'Refusing to overwrite an existing local configuration.'
    }
    $resolvedAgentDirectory = [IO.Path]::GetFullPath($AgentDirectory)
    $resolvedConfigParent = [IO.Path]::GetDirectoryName([IO.Path]::GetFullPath($ConfigPath))
    if ($resolvedConfigParent -ne $resolvedAgentDirectory) {
        throw 'The configuration transaction must remain inside the agent directory.'
    }
    $temporaryConfigPath = Join-Path $resolvedAgentDirectory ('.config.json.{0}.tmp' -f [guid]::NewGuid().ToString('N'))
    try {
    $config = Get-Content -LiteralPath $exampleConfigPath -Raw | ConvertFrom-Json
    $config.machine_id = Read-Default 'Machine ID (uppercase letters, digits, underscores)' $config.machine_id $PromptReader
    Assert-ConfigValue 'machine ID' $config.machine_id '^[A-Z][A-Z0-9_]{0,63}$'
    $config.github.owner = Read-Default 'Private runtime/job GitHub owner or organization' $config.github.owner $PromptReader
    Assert-ConfigValue 'GitHub owner' $config.github.owner '^[A-Za-z0-9_.-]{1,128}$'
    $config.github.repository = Read-Default 'Private runtime/job GitHub repository (for example arphe-remote-jobs)' $config.github.repository $PromptReader
    Assert-ConfigValue 'GitHub repository' $config.github.repository '^[A-Za-z0-9_.-]{1,128}$'
    $config.github.branch = Read-Default 'Private runtime/job GitHub branch' $config.github.branch $PromptReader
    Assert-ConfigValue 'GitHub branch' $config.github.branch '^.{1,256}$'
    $config.resolve.executable_path = Read-Default 'Resolve Studio executable path' $config.resolve.executable_path $PromptReader
    if (-not [IO.Path]::IsPathFullyQualified($config.resolve.executable_path)) { throw 'Resolve executable path must be absolute.' }
    foreach ($folderName in @('incoming', 'test_media', 'workspace', 'exports')) {
        $config.folders.$folderName = Read-Default "Folder path for $folderName" $config.folders.$folderName $PromptReader
        if (-not [IO.Path]::IsPathFullyQualified($config.folders.$folderName)) { throw "Folder path for $folderName must be absolute." }
    }
    if (Read-Confirmation 'Enable controlled source-code synchronization on this HOME_DEV machine? [y/N]' $PromptReader) {
        $config.allowed_actions = @($config.allowed_actions) + 'SYNC_APPROVED_CODE'
        $checkoutPath = Read-Default 'Local source checkout path for controlled synchronization' '' $PromptReader
        if (-not [IO.Path]::IsPathFullyQualified($checkoutPath)) { throw 'Local source checkout path must be absolute.' }
        $sourceOwner = Read-Default 'Source repository owner or organization' '' $PromptReader
        Assert-ConfigValue 'source repository owner' $sourceOwner '^[A-Za-z0-9_.-]{1,128}$'
        $sourceRepository = Read-Default 'Source repository name' '' $PromptReader
        Assert-ConfigValue 'source repository name' $sourceRepository '^[A-Za-z0-9_.-]{1,128}$'
        $sourceBranch = Read-Default 'Source repository branch' 'main' $PromptReader
        Assert-ConfigValue 'source repository branch' $sourceBranch '^.{1,256}$'
        $config | Add-Member -NotePropertyName 'local_checkout_path' -NotePropertyValue $checkoutPath
        $config | Add-Member -NotePropertyName 'code_sync' -NotePropertyValue ([pscustomobject]@{
            source_repository = [pscustomobject]@{
                owner = $sourceOwner
                repository = $sourceRepository
                branch = $sourceBranch
            }
        })
    }
    $config | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $temporaryConfigPath -Encoding utf8 -NoNewline
    $global:LASTEXITCODE = 0
    & $ConfigValidator $temporaryConfigPath
    if ($global:LASTEXITCODE -ne 0) {
        throw 'Strict validation rejected the new local configuration.'
    }
    if (Test-Path -LiteralPath $ConfigPath) {
        throw 'Refusing to overwrite an existing local configuration.'
    }
    [IO.File]::Move($temporaryConfigPath, $ConfigPath)
    } finally {
        if (Test-Path -LiteralPath $temporaryConfigPath) {
            Remove-Item -LiteralPath $temporaryConfigPath -Force -ErrorAction SilentlyContinue
        }
    }
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

function Invoke-Setup {
Write-Host 'ARPHE Remote Agent — manual HOME_DEV setup'
$pythonCommand = @(Get-Python311Command)
if (-not (Test-Path -LiteralPath $venvDirectory)) {
    if ($pythonCommand.Length -gt 1) {
        & $pythonCommand[0] $pythonCommand[1] -m venv $venvDirectory
    } else {
        & $pythonCommand[0] -m venv $venvDirectory
    }
    Assert-LastExitCode 'creating the dedicated virtual environment'
}
$venvPython = Join-Path $venvDirectory 'Scripts\python.exe'
if (-not (Test-Path -LiteralPath $venvPython)) { throw 'The dedicated virtual environment was not created.' }
& $venvPython -m pip install --upgrade pip
Assert-LastExitCode 'upgrading pip in the dedicated virtual environment'
& $venvPython -m pip install -r (Join-Path $agentDirectory 'requirements.txt')
Assert-LastExitCode 'installing the ARPHE Remote Agent runtime dependencies'

if ($CreateDefaultFolders) {
    foreach ($folder in @('D:\ARPHE\Incoming', 'D:\ARPHE\TestMedia', 'D:\ARPHE\Workspace', 'D:\ARPHE\Exports')) {
        New-Item -ItemType Directory -LiteralPath $folder -Force | Out-Null
    }
}

if (-not (Test-Path -LiteralPath $configPath)) {
    $configValidator = {
        param([string] $CandidatePath)
        & $venvPython -c "import sys; from pathlib import Path; sys.path.insert(0, str(Path(sys.argv[2]).resolve())); from scripts.remote_agent.config import AgentConfig; AgentConfig.load(sys.argv[1])" $CandidatePath $projectDirectory
        Assert-LastExitCode 'validating the new local config.json'
    }
    Initialize-NewConfig -AgentDirectory $agentDirectory -ConfigPath $configPath -ExampleConfigPath $exampleConfigPath -ConfigValidator $configValidator
} else {
    Write-Host "Keeping the existing local configuration: $configPath"
}

# Validate the strict, secret-free config before creating a launch shortcut.
& $venvPython -c "import sys; from pathlib import Path; sys.path.insert(0, str(Path(sys.argv[2]).resolve())); from scripts.remote_agent.config import AgentConfig; AgentConfig.load(sys.argv[1])" $configPath $projectDirectory
Assert-LastExitCode 'validating the local config.json'

New-DesktopShortcut
if (-not $SkipTokenSetup) {
    $setToken = Read-Host 'Set or update the GitHub token in Windows Credential Manager now? [Y/n]'
    if ([string]::IsNullOrWhiteSpace($setToken) -or $setToken -match '^[Yy]') {
        & $venvPython (Join-Path $agentDirectory 'start_agent.py') --config $configPath --set-github-token
        Assert-LastExitCode 'storing the GitHub token in Windows Credential Manager'
    }
}

Write-Host 'Setup complete. Use the ARPHE Remote Agent desktop shortcut to start the visible app.'
Write-Host 'This setup creates no service, scheduled task, startup entry, tray process, or automatic background launch.'
}

if ($MyInvocation.InvocationName -ne '.') {
    Invoke-Setup
}
