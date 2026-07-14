# BENCH-2 Hermes full matrix — closeout

Workflow run `29309289661`, attempt `1`, completed the reviewed stock-Hermes matrix at activation commit `deb7ae4c6ccbd80b1c14f65d3722c6cc2268fa70`.

## Scope and integrity

- All ten Lane 1 candidates remained in the benchmark record.
- All ten were previously attempted at the H4 65,536-token infrastructure gate.
- Eight H4-qualified candidates were executable with stock Hermes 0.18.2 and were included here.
- BENCH-1 direct outcomes were not used as an admission gate.
- The matrix captured 48/48 runs: eight candidates, two capabilities, three repetitions.
- All four GitHub archives matched their published SHA-256 digests.
- Every top-level and per-run manifest verified byte-for-byte.
- Every run used context 65,536, full VRAM residency, the local `custom` provider, and verified cleanup.
- No external provider or JarvisOS access was observed.

## Raw runner result

| Status | Runs |
|---|---:|
| Passed | 6 |
| Failed | 24 |
| `invalid_infrastructure` | 18 |
| Total | 48 |

The raw `invalid_infrastructure` count mixes two different classes. The closeout preserves the raw artifacts and separates them without rewriting history:

| Closeout class | Runs |
|---|---:|
| Passed | 6 |
| Semantic failure | 24 |
| Model-call budget violation | 9 |
| Genuine runtime invalidity | 9 |

The taxonomy defect is that `usage_api_calls_bounded` is included in the runner's infrastructure checks. A model that over-calls is behaving incorrectly, but the machine and Hermes runtime may still be valid.

## Capability-specific outcomes

No global composite score is calculated.

| Candidate | HO-TOOLS passes | HO-STOP passes | Stable 2/3 on both | Decision |
|---|---:|---:|---:|---|
| `gemma4-12b-it-qat` | 2/3 | 0/3 | No | Not admitted |
| `qwable-9b-fable5` | 0/3 | 0/3 | No | Not admitted |
| `qwythos-mythos-9b` | 1/3 | 1/3 | No | Not admitted |
| `minicpm5-fable-1b-control` | 0/3 | 0/3 | No | Runtime incompatible |
| `gemma4-fable-agentic-12b` | 0/3 | 0/3 | No | Not admitted |
| `gemma4-fable-coder-12b` | 0/3 | 1/3 | No | Not admitted |
| `qwythos-hermes-64k` | 0/3 | 1/3 | No | Not admitted |
| `qwythos-hermes-safe` | 0/3 | 0/3 | No | Not admitted |

`gemma4-12b-it-qat` is the only model stable at 2/3 on one capability, HO-TOOLS. No candidate meets the repeated threshold on both capabilities, so no Hermes orchestrator candidate is admitted.

## Important failure signatures

- `minicpm5-fable-1b-control`: six runtime failures with `HTTP 400: Cannot have 2 or more assistant messages at the end of the list`.
- `gemma4-fable-agentic-12b`: three runtime failures caused by invalid tool calls (`hermes_skill`, `Bash`, `return_final`).
- Several otherwise complete runs exceeded the permitted model-call budget.
- Most semantic failures were exact-schema failures: invalid JSON, missing `actions`, non-string `final`, verbose final text, or incomplete action sequences.
- `qwable-9b-fable5` called the distractor tool four times in one HO-STOP repetition.
- `qwythos-hermes-safe` called distractors despite explicit stop/reuse instructions.

## Decision

- The full matrix is valid evidence and does not need to be repeated unchanged.
- No candidate is admitted for Hermes orchestration.
- All capability-specific outcomes and ties remain preserved.
- The execution marker is disabled.
- The next slice is BENCH-2R diagnostic testing: first correct the status taxonomy, then isolate strict JSON/finalization behavior from tool-selection behavior before another admission matrix.
