# BENCH-2R Hermes S1 closeout

- Workflow run: `29332828621`
- Execution SHA: `c6960b3dc10cb5cbd3bcb2363ad7c83bc3939466`
- Runs: 32/32
- Statuses: 7 passed, 18 failed, 7 invalid infrastructure

## Decision

No fixed candidate/arm passed both diagnostic cases. No orchestrator is admitted from S1.

S2 advances three candidates under `profile_plus_skill_with_deterministic_finalizer`:

1. `gemma4-12b-it-qat`
2. `qwythos-mythos-9b`
3. `qwythos-hermes-64k`

## Evidence

All four batch jobs completed capture, enforce and artifact upload successfully. Native trajectories and both tool definitions were observed for every infrastructure-valid run. The seven invalid-infrastructure runs are confined to MiniCPM protocol failures and Gemma Fable Agentic incomplete-response paths.

## Configuration results

| Candidate | Arm | Semantic passes | Infra-valid | Tool exact | Final exact | Actions exact | Budget valid |
|---|---:|---:|---:|---:|---:|---:|---:|
| `gemma4-12b-it-qat` | `profile_only` | 1/2 | 2/2 | 2/2 | 2/2 | 1/2 | 2/2 |
| `gemma4-12b-it-qat` | `profile_plus_skill` | 1/2 | 2/2 | 2/2 | 2/2 | 1/2 | 2/2 |
| `gemma4-fable-agentic-12b` | `profile_only` | 0/2 | 1/2 | 2/2 | 0/2 | 0/2 | 0/2 |
| `gemma4-fable-agentic-12b` | `profile_plus_skill` | 0/2 | 0/2 | 1/2 | 0/2 | 0/2 | 0/2 |
| `gemma4-fable-coder-12b` | `profile_only` | 1/2 | 2/2 | 1/2 | 1/2 | 1/2 | 2/2 |
| `gemma4-fable-coder-12b` | `profile_plus_skill` | 1/2 | 2/2 | 1/2 | 1/2 | 1/2 | 2/2 |
| `minicpm5-fable-1b-control` | `profile_only` | 0/2 | 0/2 | 1/2 | 0/2 | 0/2 | 0/2 |
| `minicpm5-fable-1b-control` | `profile_plus_skill` | 0/2 | 0/2 | 1/2 | 0/2 | 0/2 | 0/2 |
| `qwable-9b-fable5` | `profile_only` | 0/2 | 2/2 | 2/2 | 1/2 | 0/2 | 2/2 |
| `qwable-9b-fable5` | `profile_plus_skill` | 1/2 | 2/2 | 2/2 | 1/2 | 1/2 | 2/2 |
| `qwythos-hermes-64k` | `profile_only` | 0/2 | 2/2 | 2/2 | 1/2 | 0/2 | 2/2 |
| `qwythos-hermes-64k` | `profile_plus_skill` | 1/2 | 2/2 | 2/2 | 2/2 | 1/2 | 2/2 |
| `qwythos-hermes-safe` | `profile_only` | 0/2 | 2/2 | 2/2 | 0/2 | 0/2 | 2/2 |
| `qwythos-hermes-safe` | `profile_plus_skill` | 0/2 | 2/2 | 1/2 | 0/2 | 2/2 | 1/2 |
| `qwythos-mythos-9b` | `profile_only` | 1/2 | 2/2 | 1/2 | 1/2 | 1/2 | 1/2 |
| `qwythos-mythos-9b` | `profile_plus_skill` | 0/2 | 2/2 | 2/2 | 1/2 | 1/2 | 2/2 |

## S2 boundary

The deterministic finalizer may normalize only the presentation layer from the task contract and verified tool/supplied-result data. It must not:

- change tool names, arguments, call count or ordering;
- erase budget violations, retries, model failure or incomplete turns;
- invent a value when the contract and verified trace do not provide one;
- use evaluator expected values.

Admission still requires held-out cases, all three admission seeds, wire-level request capture and no raw orchestration failure.
