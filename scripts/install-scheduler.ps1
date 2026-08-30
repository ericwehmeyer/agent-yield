<#
.SYNOPSIS
    Register, inspect or remove the Windows Task Scheduler entry that runs
    scripts/run-unattended.py on an interval.

.DESCRIPTION
    The fourth quarter of the loop. #28 established that nothing inside a
    session can restart it -- the loop closes as boundary -> handoff ->
    SessionStart -> a human types the restart -- and this is what replaces the
    keystroke. It is deliberately thin: every guard lives in
    run-unattended.py, where pytest can reach it. A scheduler entry that
    carried policy would be policy nothing can test.

    Registration is per-user and needs no elevation. The task runs whether or
    not the operator is logged on is NOT set: it runs in the interactive
    session, so it inherits the same PATH, the same `claude` install and the
    same hooks an interactive run gets. That is the point -- #28's first open
    question is whether a scheduled `claude -p` inherits hooks and the status
    line, and a task configured to run in an isolated session would answer a
    different question than the one asked.

.PARAMETER IntervalMinutes
    How often to fire. Default 60. A run with nothing eligible costs one `gh`
    call and exits 0, so a short interval is cheap; the cost is in the runs
    that find work, and those are capped at one issue each.

.PARAMETER TaskName
    Default 'agent-yield unattended'.

.PARAMETER SigningKey
    Fingerprint of the key the loop signs its own commits with -- never the
    operator's (#171). A scheduled task cannot carry environment variables, so
    this goes on the argument line, where -Status shows it. It is a public
    fingerprint, not a secret. Without one the loop still runs and simply does
    not commit, which is the correct behaviour for a clone that has no identity
    of its own.

.PARAMETER SigningEmail
    Author and committer address for those commits, so `git log` separates the
    two actors without anybody reading a signature.

.PARAMETER NoCommit
    Register the task with --no-commit: the run leaves its work in the tree for
    a human. Committing is otherwise the default, gated on -SigningKey.

.PARAMETER Status
    Print the registered task and its last result, change nothing.

.PARAMETER Uninstall
    Remove the task.

.EXAMPLE
    pwsh scripts/install-scheduler.ps1 -WhatIf
    pwsh scripts/install-scheduler.ps1 -IntervalMinutes 60
    pwsh scripts/install-scheduler.ps1 -Status
    pwsh scripts/install-scheduler.ps1 -Uninstall

.OUTPUTS
    Exit 0 on success, 1 on a refusal that names its reason, 2 when -Status
    finds no registered task.
#>
[CmdletBinding(SupportsShouldProcess)]
param(
    [int]$IntervalMinutes = 60,
    [string]$TaskName = 'agent-yield unattended',
    [switch]$NoCommit,
    [string]$SigningKey = $env:AGENT_YIELD_SIGNING_KEY,
    [string]$SigningEmail = $env:AGENT_YIELD_SIGNING_EMAIL,
    [switch]$Status,
    [switch]$Uninstall
)

$ErrorActionPreference = 'Stop'

$repo = Split-Path -Parent $PSScriptRoot
$python = Join-Path $repo '.venv\Scripts\python.exe'
$runner = Join-Path $repo 'scripts\run-unattended.py'

function Fail($message) { Write-Host "refused: $message"; exit 1 }

if ($Status) {
    $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if (-not $task) { Write-Host "no task named '$TaskName' is registered"; exit 2 }
    $info = Get-ScheduledTaskInfo -TaskName $TaskName
    $task | Select-Object TaskName, State | Format-List
    $info | Select-Object LastRunTime, LastTaskResult, NextRunTime | Format-List
    Write-Host "action: $($task.Actions[0].Execute) $($task.Actions[0].Arguments)"
    exit 0
}

if ($Uninstall) {
    if (-not (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue)) {
        Write-Host "nothing to remove: no task named '$TaskName'"
        exit 0
    }
    if ($PSCmdlet.ShouldProcess($TaskName, 'Unregister-ScheduledTask')) {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        Write-Host "removed '$TaskName'"
    }
    exit 0
}

# Refuse rather than register something that cannot run. A task that fires
# hourly against a missing interpreter is a silent failure with a schedule.
if (-not (Test-Path $python)) { Fail "$python does not exist" }
if (-not (Test-Path $runner)) { Fail "$runner does not exist" }
if ($IntervalMinutes -lt 5) { Fail "an interval under 5 minutes is a loop, not a schedule" }

$claude = (Get-Command claude -ErrorAction SilentlyContinue)
if (-not $claude) {
    Write-Host "warning: 'claude' is not on this shell's PATH. The task inherits the"
    Write-Host "         interactive session's PATH, so this may still work -- but"
    Write-Host "         run the task once and read LastTaskResult before trusting it."
}

$arguments = "`"$runner`""
if ($NoCommit) { $arguments += ' --no-commit' }
if ($SigningKey)   { $arguments += " --signing-key $SigningKey" }
if ($SigningEmail) { $arguments += " --signing-email $SigningEmail" }

if (-not $NoCommit -and -not $SigningKey) {
    Write-Host "warning: no -SigningKey, so this task will not commit. Its runs will"
    Write-Host "         leave work in the tree and the next one refuses on the"
    Write-Host "         dirty-tree guard. See #171."
}

$action = New-ScheduledTaskAction -Execute $python -Argument $arguments -WorkingDirectory $repo
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(2) `
    -RepetitionInterval (New-TimeSpan -Minutes $IntervalMinutes)
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -StartWhenAvailable -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2)

$existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
$verb = if ($existing) { 'replace' } else { 'register' }

if ($PSCmdlet.ShouldProcess($TaskName, "$verb, every $IntervalMinutes min")) {
    if ($existing) { Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false }
    Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
        -Settings $settings -Description (
            "Runs scripts/run-unattended.py every $IntervalMinutes minutes. " +
            "Guards live in that script; stop the loop with .agent-yield/STOP.") | Out-Null
    Write-Host "${verb}ed '$TaskName': $python $arguments"
    Write-Host "every $IntervalMinutes minutes, first run in ~2 minutes"
    Write-Host "commit mode: $(if ($NoCommit) { 'off' } elseif ($SigningKey) { "ON, signed by $SigningKey" } else { 'off -- no signing key' })"
    Write-Host ""
    Write-Host "stop it any time:  New-Item -ItemType File '$repo\.agent-yield\STOP'"
    Write-Host "check on it:       pwsh scripts/install-scheduler.ps1 -Status"
    Write-Host "read what it did:  Get-Content '$repo\.agent-yield\unattended.jsonl' -Tail 5"
}
exit 0
