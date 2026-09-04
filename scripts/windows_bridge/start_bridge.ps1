[CmdletBinding()]
param()
. (Join-Path $PSScriptRoot 'common.ps1')

$task = Get-ArpheTask
if (-not $task) { throw 'ARPHE bridge task is not installed.' }
Remove-Item -LiteralPath $script:ArpheStopPath -Force -ErrorAction SilentlyContinue
Start-ScheduledTask -TaskName $script:ArpheTaskName -TaskPath $script:ArpheTaskPath
Write-Host 'Start requested. Use status_bridge.ps1 to check /readyz.'
