# BENCH-2R Hermes S2 closeout

## Decision

**A Hermes orchestrator has been found.**

The admitted configuration is the governed stack:

- model: `gemma4:12b-it-qat`;
- digest: `38044be4f923e5a55264ed7df4eaac2676651a905f735197c504045140c02bd3`;
- producer sampling: `temperature=1.0`, `top_k=64`, `top_p=0.95`;
- context: `65536`;
- Hermes Agent: `0.18.2` at `73b611ad19720d70308dad6b0fb64648aaadc216`;
- skill: `bounded-tool-orchestration` v1.1.0;
- deterministic finalizer: `bench.hermes-deterministic-finalizer.v1`;
- mandatory native trajectory, wire trace, tool allowlist and call-budget checks.

The standalone checkpoint is **not** admitted. Raw presentation passed only 3/12 held-out runs, while raw orchestration and finalized output passed 12/12. The finalizer is therefore a required governed component, not optional formatting.

Production promotion remains disabled pending a separate shadow-and-soak gate.

## Trusted execution

- Workflow run: `29335974597`
- Attempt: `1`
- Execution SHA: `8cb771cb140795198de0c38937b382a10054d867`
- Workflow conclusion: `success`
- Matrix: 3 candidates × 4 held-out cases × 3 seeds = 36 runs
- Infrastructure-valid: 36/36
- Admission passes: 31/36

All three serial jobs completed validation, capture, enforce and artifact upload successfully.

## Candidate results

| Candidate | Infra | Raw orchestration | Raw presentation | Finalized output | Admission | Decision |
|---|---:|---:|---:|---:|---:|---|
| `gemma4-12b-it-qat` | 12/12 | 12/12 | 3/12 | 12/12 | 12/12 | admitted governed stack |
| `qwythos-mythos-9b` | 12/12 | 9/12 | 6/12 | 9/12 | 9/12 | rejected |
| `qwythos-hermes-64k` | 12/12 | 10/12 | 6/12 | 10/12 | 10/12 | rejected |

### Qwythos Mythos failures

- Seed 17: both tool cases terminated without the required tool call.
- Seed 314159: the supplied-string case made an unexpected tool call and exceeded the one-call budget.

### Qwythos Hermes 64K failures

- Seed 17: the vault case used an invalid tool chain and exceeded both model and tool budgets.
- Seed 314159: the registry case used the wrong tool contract.

These are orchestration failures. The deterministic finalizer rejected them and did not convert them into passes.

## Artifact bindings

| Batch | Candidate | Artifact ID | Size | SHA-256 |
|---:|---|---:|---:|---|
| 0 | `gemma4-12b-it-qat` | `8312150578` | 297149 | `040783597136bb7c1211799db26d3421cfe4148201790c1449dbb17913d0dbc5` |
| 1 | `qwythos-mythos-9b` | `8312317137` | 291633 | `9296595b5c9c68f47bc9381c3bf16b6582b373eae323262e831c5593f0c1086d` |
| 2 | `qwythos-hermes-64k` | `8312496822` | 295705 | `42f8f1d6b25de60eb9f8eb06bc7497af7fd2e280a62e1c71005815245429fefa` |

## Wire and contamination checks

For every infrastructure-valid run:

- worker API-call count matched captured `/chat/completions` requests;
- all chat responses were HTTP 200;
- the runtime alias matched the request model;
- all held-out tools appeared in the wire registry and native trajectory;
- Authorization was redacted in stored traces;
- evaluator `expected` fields and held-out answers were excluded from initial model prompts.

## Next gate

The next gate is shadow-and-soak, not automatic production promotion. It must test longer sessions, multi-tool sequences, malformed and adversarial tool results, context pressure, cancellation, cleanup, latency and deterministic rollback while preserving the exact admitted stack.
