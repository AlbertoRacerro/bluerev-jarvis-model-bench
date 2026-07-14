param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('start', 'stop')]
    [string]$Mode
)

$ErrorActionPreference = 'Stop'
$PidFile = Join-Path $env:RUNNER_TEMP 'bench2r-s1-keep-awake.pid'

if ($Mode -eq 'stop') {
    if (Test-Path $PidFile) {
        $KeepAwakePid = [int](Get-Content $PidFile -Raw).Trim()
        $Process = Get-Process -Id $KeepAwakePid -ErrorAction SilentlyContinue
        if ($null -ne $Process) {
            Stop-Process -Id $KeepAwakePid -Force
            Wait-Process -Id $KeepAwakePid -ErrorAction SilentlyContinue
        }
        Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
    }
    exit 0
}

if (Test-Path $PidFile) {
    & $PSCommandPath stop
}

$ChildScript = @'
Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class Bench2RPowerState {
    [DllImport("kernel32.dll", SetLastError = true)]
    public static extern uint SetThreadExecutionState(uint esFlags);
}
"@

$ES_CONTINUOUS = 0x80000000
$ES_SYSTEM_REQUIRED = 0x00000001
$ES_DISPLAY_REQUIRED = 0x00000002
$Required = $ES_CONTINUOUS -bor $ES_SYSTEM_REQUIRED -bor $ES_DISPLAY_REQUIRED
$Reset = $ES_CONTINUOUS

try {
    $Result = [Bench2RPowerState]::SetThreadExecutionState($Required)
    if ($Result -eq 0) {
        throw "SetThreadExecutionState failed"
    }
    while ($true) {
        Start-Sleep -Seconds 30
    }
}
finally {
    [void][Bench2RPowerState]::SetThreadExecutionState($Reset)
}
'@

$Encoded = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($ChildScript))
$PreviousTrackingId = $env:RUNNER_TRACKING_ID
try {
    $env:RUNNER_TRACKING_ID = ''
    $Process = Start-Process powershell.exe -ArgumentList @(
        '-NoLogo',
        '-NoProfile',
        '-NonInteractive',
        '-EncodedCommand',
        $Encoded
    ) -WindowStyle Hidden -PassThru
}
finally {
    $env:RUNNER_TRACKING_ID = $PreviousTrackingId
}

$Process.Id | Set-Content -Path $PidFile -Encoding ascii -NoNewline
Start-Sleep -Seconds 2
if ($Process.HasExited) {
    Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
    throw "keep-awake process exited immediately with code $($Process.ExitCode)"
}

Write-Host "BENCH-2R keep-awake active (PID $($Process.Id))."
