# BENCH-2R Hermes S3A — runtime implementation boundary

## Status

`implementation_ready_workflow_absent`

This slice implements and validates the S3A runtime without making it executable from GitHub Actions. The S3A marker remains disabled and the self-hosted workflow is intentionally absent.

## Implemented

- Exact Gemma 4 governed-stack runtime plan bound to the admitted-stack registry and S3A design plan.
- Five deterministic seed batches, each containing two repetitions of all five cases.
- Temporary source-bound Ollama alias per repetition with producer sampling, exact seed, 65536 context and output cap 4096.
- Isolated Hermes home/workdir for every run.
- S3A local-only plugin with four reviewed tools.
- Contamination-safe model payload excluding evaluator `expected` and `outcome_class` fields.
- Deterministic 2400-line untrusted long-context generator with recorded digest.
- Native Hermes trajectory, exact wire request trace, tool trace, usage, VRAM, cleanup and per-run duration evidence.
- Separate nominal-success and expected-fail-closed outcome semantics.
- Deterministic finalizer v1 remains unchanged and fail closed.
- Rich artifact enforcement through the authoritative safe wrapper.
- Windows keep-awake capture wrapper.

## Failure-mode correction

The timeout negative control returns a signed deterministic `ok=false` result rather than raising out of the tool handler. An escaping tool exception would cause the pinned Hermes worker to lose attributable usage and completion state, making the case infrastructure-invalid instead of a valid negative control.

The reviewed timeout result includes:

- `error = deterministic_timeout`;
- `fault_signature = BENCH2R_S3A_DETERMINISTIC_TIMEOUT`;
- `retryable = false`.

The model must not retry, switch tools or invent a result. The finalizer must reject with `tool_result_not_verified`.

## Not implemented in this slice

- No `.github/workflows/bench2r-hermes-s3a-oneshot.yml`.
- No activation commit.
- No self-hosted or GPU execution.
- No production router change.
- No automatic model-weight update or production promotion.
- No multi-tool/finalizer-v2 or cancellation/resume expansion.

A separate reviewed slice must add the marker-only self-hosted workflow and transition the validator from `implementation_ready_workflow_absent` to `runtime_ready_execution_disabled` before any activation is permitted.
