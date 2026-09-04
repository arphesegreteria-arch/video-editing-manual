[CmdletBinding()]
param([ValidateRange(1, 60)][int]$GraceSeconds = 15)
. (Join-Path $PSScriptRoot 'common.ps1')

New-Item -ItemType Directory -Path $script:ArpheDataDir -Force | Out-Null
New-Item -ItemType File -Path $script:ArpheStopPath -Force | Out-Null
$deadline = [DateTime]::UtcNow.AddSeconds($GraceSeconds)
do {
    $running = $false
    if (Test-Path -LiteralPath $script:ArpheStatePath) {
        try {
            $state = Get-Content -Raw -LiteralPath $script:ArpheStatePath | ConvertFrom-Json
            $running = Test-ArpheProcess -ProcessId $state.supervisor_pid
        } catch { $running = $true }
    }
    if ($running) { Start-Sleep -Milliseconds 500 }
} while ($running -and [DateTime]::UtcNow -lt $deadline)

$task = Get-ArpheTask
if ($task -and $task.State -eq 'Running') {
    Stop-ScheduledTask -TaskName $script:ArpheTaskName -TaskPath $script:ArpheTaskPath
    Write-Warning 'Grace period expired or task state lagged; Task Scheduler stop was issued. The Job Object closes child processes.'
}
Write-Host 'ARPHE bridge stop requested.'
