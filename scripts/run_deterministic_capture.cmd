@echo off
setlocal

set "ARTIFACT_DIR=artifacts\deterministic-ci"
if not exist "%ARTIFACT_DIR%" mkdir "%ARTIFACT_DIR%"
> "%ARTIFACT_DIR%\workflow-step-started.txt" echo started

python -m scripts.run_deterministic_ci capture
set "CAPTURE_EXIT=%ERRORLEVEL%"

if not exist "%ARTIFACT_DIR%" mkdir "%ARTIFACT_DIR%"
> "%ARTIFACT_DIR%\launcher.exit" echo %CAPTURE_EXIT%

exit /b %CAPTURE_EXIT%
