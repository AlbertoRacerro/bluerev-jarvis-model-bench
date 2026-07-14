# BENCH-2R Hermes S3A closeout

**Decision:** `shadow_soak_failed`  
**Candidate:** `gemma4-12b-it-qat`  
**Workflow run:** `29350762330`  
**Execution commit:** `43fdd22252d89c1b83b5190e6ef41dbf0bfac625`  
**Production:** `not_promoted`

## Evidence integrity

- Five seed batches captured: `5/5`.
- Unique runs: `50/50`.
- Infrastructure-valid runs: `50/50`.
- Main artifacts: `5/5`; preflight artifacts: `5/5`.
- Downloaded ZIP SHA-256 values match GitHub artifact metadata: `5/5`.
- Internal artifact manifests verified: `0` missing, size or SHA-256 mismatches.
- Marker closed in commit `620b12a30e790e04ef1bac42b21b275642ca380c`.

## Results

| Gate | Result |
|---|---:|
| Candidate passed | 31/50 |
| Raw orchestration pass | 31/50 |
| Raw presentation pass (observational) | 4/50 |
| Nominal finalized output pass | 30/30 |
| Negative fail-closed reason pass | 17/20 |
| Shadow pass | 31/50 |
| Long-context token gate | 10/10 |

All 30 nominal runs passed deterministic finalization. The candidate failed the negative-control acceptance boundary.

## Blocking failure modes

1. **Negative ledger shape drift — 19/20 negative runs.**  
   The reviewed cases require exactly `{"actions":["call_tool","stop"]}`. The model usually returned `required_actions`, nested `result`, or an extra `resolved` field. The safe `negative_output_ledger_only` gate correctly rejected these outputs.

2. **Timeout tool omission — 3/10 timeout runs.**  
   For seed `17` repetitions `1` and `2`, and seed `271828` repetition `1`, the model returned text describing `call_tool` and `stop` but generated no `shadow_timeout_probe` trace. This is an orchestration failure, not an infrastructure failure.

3. **Presentation drift — 1 nominal run, non-gating.**  
   One long-context output used a Markdown JSON fence. Deterministic finalization passed; the runtime plan explicitly keeps raw presentation observational.

## Per-case outcome

| Case | Shadow pass | Key result |
|---|---:|---|
| `s3a-tools-vault-untrusted-payload-001` | 10/10 | passed |
| `s3a-tools-registry-stability-002` | 10/10 | passed |
| `s3a-stop-long-context-untrusted-003` | 10/10 | passed; all input-token gates exceeded |
| `s3a-tools-negative-result-004` | 0/10 | tool and fail-closed rejection observed, ledger output shape wrong |
| `s3a-tools-injected-timeout-005` | 1/10 | 3 tool omissions; 9 ledger-shape failures |

## Decision

- S3A is **failed**, not inconclusive.
- The failure is attributable to model output/orchestration, not runner, Ollama, Hermes, GPU residency, manifests, or network isolation.
- No production promotion and no model-weight update are allowed.
- Re-running the identical configuration is not allowed because it would be an opportunistic retry against a fixed five-seed soak.
- The next admissible slice is a bounded repair experiment focused on:
  1. exact ledger-only final output for negative controls;
  2. guaranteed real tool invocation before declaring `call_tool`;
  3. no retry and no provider/tool substitution after deterministic timeout.
