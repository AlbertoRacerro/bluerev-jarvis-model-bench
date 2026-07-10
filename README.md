# BlueRev / Jarvis Model Benchmark

Private benchmark repository for evaluating local AI models directly and as orchestrators inside Hermes Agent.

The benchmark is independent from `JarvisOS_v1`. It must not modify or execute against the production JarvisOS repository unless a later, explicitly approved fixture boundary is introduced.

## Current scope

BENCH-0 establishes:

- strict output and run-manifest contracts;
- deterministic negative tests;
- local Ollama and Hermes inventory;
- a dedicated Windows self-hosted runner;
- scheduled preflight every 20 minutes;
- immutable GitHub Actions artifacts;
- local-model-only and no-auto-merge safety rules.

No model winner is claimed during BENCH-0.

## Candidate families

Initial aliases include Qwythos, Qwable, Gemma4 Fable, Gemma4 12B IT QAT, Qwen3-Coder 30B, and one lightweight control. Actual Ollama tags are mapped only after the runner inventory records them.

## Repository map

```text
.github/workflows/       trusted self-hosted workflows
candidates/              stable aliases and runtime tag mapping
docs/                    benchmark and runner contracts
scripts/                 environment and execution utilities
src/bench/               deterministic harness code
tests/                   reviewer-owned contract tests
STATUS.md                 live benchmark roadmap
AGENTS.md                 operating invariants
```

## Local contract tests

```powershell
$env:PYTHONPATH = "$PWD\src"
python -m unittest discover -s tests -v
```

## Runner bootstrap

Follow [`docs/RUNNER_SETUP.md`](docs/RUNNER_SETUP.md). The workflow runs only from trusted `main`, uses a repository-specific self-hosted runner with the `bluerev-bench` label, and uploads preflight evidence instead of pushing generated files.

## Evidence rules

Read [`docs/BENCHMARK_CONTRACT.md`](docs/BENCHMARK_CONTRACT.md). Raw output, extracted final content, traces, validator results, and environment metadata remain separate. Missing `FINAL:` markers and malformed manifests are failures rather than silently accepted output.

## Status

See [`STATUS.md`](STATUS.md). Pull requests remain subject to human merge.
