$ErrorActionPreference = 'Stop'

$artifactDir = Join-Path (Get-Location).Path 'artifacts\deterministic-ci'
$launcherDir = Join-Path $env:RUNNER_TEMP ("bluerev-deterministic-{0}-{1}" -f $env:GITHUB_RUN_ID, $env:GITHUB_RUN_ATTEMPT)

if (Test-Path -LiteralPath $launcherDir) {
    Remove-Item -LiteralPath $launcherDir -Recurse -Force
}
New-Item -ItemType Directory -Path $launcherDir -Force | Out-Null

$stdoutPath = Join-Path $launcherDir 'launcher.stdout.log'
$stderrPath = Join-Path $launcherDir 'launcher.stderr.log'
$errorPath = Join-Path $launcherDir 'launcher.powershell-error.log'
$captureExit = 127

try {
    $pythonCommand = Get-Command python -ErrorAction Stop
    $arguments = @('-m', 'scripts.run_deterministic_ci', 'capture')
    $startParameters = @{
        FilePath = $pythonCommand.Source
        ArgumentList = $arguments
        WorkingDirectory = (Get-Location).Path
        NoNewWindow = $true
        Wait = $true
        PassThru = $true
        RedirectStandardOutput = $stdoutPath
        RedirectStandardError = $stderrPath
    }
    $process = Start-Process @startParameters
    $captureExit = $process.ExitCode
}
catch {
    $_ | Out-String | Set-Content -LiteralPath $errorPath -Encoding UTF8
}

New-Item -ItemType Directory -Path $artifactDir -Force | Out-Null
Set-Content -LiteralPath (Join-Path $artifactDir 'launcher.exit') -Value $captureExit -Encoding ASCII

foreach ($sourcePath in @($stdoutPath, $stderrPath, $errorPath)) {
    if (Test-Path -LiteralPath $sourcePath) {
        Copy-Item -LiteralPath $sourcePath -Destination $artifactDir -Force
        Get-Content -LiteralPath $sourcePath | ForEach-Object { Write-Host $_ }
    }
}

exit $captureExit
