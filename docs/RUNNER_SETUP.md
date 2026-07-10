# Windows self-hosted runner setup

The benchmark requires a dedicated Windows x64 runner because Ollama models and the local Hermes checkout are on the workstation.

## Security boundary

- Use this runner only for the private `bluerev-jarvis-model-bench` repository.
- Do not install it at organization scope.
- Do not attach it to `JarvisOS_v1`.
- Prefer a non-administrator Windows account with access only to the benchmark, Ollama, and Hermes directories.
- The workflow never runs on `pull_request`; scheduled execution checks out the trusted `main` branch explicitly.
- Do not place API keys or provider credentials in runner environment variables.

## Prerequisites

Verify in PowerShell:

```powershell
python --version
ollama --version
ollama list
Test-Path C:\AI\hermes-agent
Test-Path C:\AI\hermes-agent\.venv\Scripts\python.exe
```

Python 3.11 or newer is recommended. Ollama must remain reachable on `127.0.0.1:11434` while jobs run.

## Register the runner

1. Open the repository on GitHub.
2. Go to **Settings → Actions → Runners → New self-hosted runner**.
3. Select **Windows** and **x64**.
4. Create a dedicated directory:

```powershell
New-Item -ItemType Directory -Force C:\AI\bluerev-bench-runner
Set-Location C:\AI\bluerev-bench-runner
```

5. Execute the download and extraction commands shown by GitHub. The registration token is temporary; never paste it into chat or commit it.
6. Run GitHub's configuration command, adding the custom label `bluerev-bench`. When prompted, use:

```text
Runner name: bluerev-bench-win
Additional labels: bluerev-bench
Work folder: _work
```

7. Set the Hermes checkout for the runner process:

```powershell
[Environment]::SetEnvironmentVariable('HERMES_REPO', 'C:\AI\hermes-agent', 'User')
```

8. Close and reopen PowerShell so the environment variable is visible, then start the runner:

```powershell
Set-Location C:\AI\bluerev-bench-runner
.\run.cmd
```

Keep that window open for the initial validation. Installing the runner as a Windows service can be considered after the first successful preflight; it is not required for BENCH-0.

## First validation

After BENCH-0 is merged, open **Actions → Local benchmark preflight → Run workflow**.

Expected behavior:

1. The runner accepts the job.
2. Contract unit tests pass.
3. `artifacts/preflight.json` records the OS, Python version, Hermes commit, and Ollama model inventory.
4. The workflow uploads a `preflight-<run>-<attempt>` artifact.

A blocked preflight is useful evidence. Do not bypass it. Fix the reported environment condition and replay the job.

## Stop or remove

Stop an interactive runner with `Ctrl+C`. To permanently detach it, follow GitHub's runner removal instructions and delete `C:\AI\bluerev-bench-runner` only after confirming no job is active.
