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
4. Create the root-level directory recommended by GitHub:

```powershell
New-Item -ItemType Directory -Force C:\actions-runner
Set-Location C:\actions-runner
```

5. Execute the download and extraction commands shown by GitHub. The registration token is temporary; never paste it into chat or commit it.
6. Run GitHub's configuration command, adding the custom label `bluerev-bench`. When prompted, use:

```text
Runner name: bluerev-bench-win
Additional labels: bluerev-bench
Work folder: _work
```

7. Set the Hermes checkout for future runner processes:

```powershell
[Environment]::SetEnvironmentVariable('HERMES_REPO', 'C:\AI\hermes-agent', 'User')
```

8. Close the runner and every PowerShell window that may have inherited the old environment. Open a new PowerShell and verify:

```powershell
$env:HERMES_REPO
Test-Path $env:HERMES_REPO
Test-Path "$env:HERMES_REPO\.venv\Scripts\python.exe"
```

9. Start the runner from the new process:

```powershell
Set-Location C:\actions-runner
.\run.cmd
```

The runner snapshots its environment when `run.cmd` starts. Changing a user environment variable while the runner is already active does not update that process; stop and restart it. The preflight also recognizes `C:\AI\hermes-agent` as the documented Windows fallback when `HERMES_REPO` is absent.

Keep that window open for the initial validation. Installing the runner as a Windows service can be considered after the first successful preflight; it is not required for BENCH-0.

## First validation

After BENCH-0 is merged, open **Actions → Local benchmark preflight → Run workflow**.

Expected behavior:

1. The runner accepts the job.
2. Contract unit tests pass.
3. `artifacts/preflight.json` records the OS, Python version, Hermes commit, Hermes branch/dirty state, Ollama version, and Ollama model inventory.
4. The report separates `runner_ready` from `scoring_ready` and records dedicated blocking reasons for each boundary.
5. The workflow uploads a `preflight-<run>-<attempt>` artifact.

`status=ready` and `runner_ready=true` mean that the local execution infrastructure is available. They do not authorize comparative scoring.

`scoring_ready=true` additionally requires:

- local-only execution with no external API environment variables;
- complete workflow identity and runner identity;
- an available Ollama version;
- model names and digests for the observed inventory;
- a detected Hermes commit;
- a clean, known Hermes working-tree state.

A dirty Hermes checkout therefore leaves the infrastructure preflight green but produces `scoring_ready=false` with `hermes_worktree_dirty`. Comparative model runs must not start until the scoring blockers are removed and a new immutable artifact records `scoring_ready=true`.

A blocked preflight is useful evidence. Do not bypass it. Fix the reported environment condition and replay the job.

## Stop or remove

Stop an interactive runner with `Ctrl+C`. To permanently detach it, follow GitHub's runner removal instructions and delete `C:\actions-runner` only after confirming no job is active.
