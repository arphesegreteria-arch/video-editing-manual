[CmdletBinding(SupportsShouldProcess, ConfirmImpact = 'High')]
param(
    [switch]$PurgeLocalData,
    [string]$InstallRoot = 'C:\ARPHE\MCP\ARPHE_WINDOWS_BRIDGE_RUNTIME_V1'
)
. (Join-Path $PSScriptRoot 'common.ps1')

if (-not $PSCmdlet.ShouldProcess("$script:ArpheTaskPath$script:ArpheTaskName", 'Stop and unregister scheduled task')) { return }
& (Join-Path $PSScriptRoot 'stop_bridge.ps1')
$task = Get-ArpheTask
if ($task) {
    Unregister-ScheduledTask -TaskName $script:ArpheTaskName -TaskPath $script:ArpheTaskPath -Confirm:$false
}
Write-Host 'Scheduled task removed. Runtime files, DPAPI secret, config, state and logs were preserved.'

if ($PurgeLocalData) {
    if ($PSCmdlet.ShouldProcess("$script:ArpheDataDir and $InstallRoot", 'Permanently delete local runtime data and deployed code')) {
        $resolvedData = [IO.Path]::GetFullPath($script:ArpheDataDir)
        $resolvedInstall = [IO.Path]::GetFullPath($InstallRoot)
        if ($resolvedData -notlike ([IO.Path]::GetFullPath($env:LOCALAPPDATA) + '*')) { throw 'Refusing unsafe data path.' }
        if ($resolvedInstall -notlike 'C:\ARPHE\MCP\ARPHE_WINDOWS_BRIDGE_RUNTIME_V1*') { throw 'Refusing unsafe install path.' }
        Remove-Item -LiteralPath $resolvedData -Recurse -Force -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath $resolvedInstall -Recurse -Force -ErrorAction SilentlyContinue
        Write-Warning 'Local config, encrypted secret, state, and deployed runtime files were permanently removed. Logs outside these paths were preserved.'
    }
}
