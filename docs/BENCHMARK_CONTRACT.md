# Benchmark contract

## Questions the benchmark must answer

1. Which local model is best for each capability?
2. Which local model is best as the model driving Hermes orchestration?
3. Which Hermes configuration improves reliability without hiding failures or multiplying work unnecessarily?
4. Which combinations should be used as orchestrator, worker, critic, scientific reviewer, or lightweight classifier?

The benchmark must not infer these roles from subjective impressions.

## Lanes

### `direct`

The candidate receives the task without Hermes. This measures intrinsic model capability.

### `hermes_single`

Hermes uses the same candidate as orchestrator and worker. This measures the effect of the Hermes runtime on that candidate.

### `orchestrator_isolated`

Only the model driving Hermes changes. Worker pool, tools, cases, limits, and validators remain fixed. This is the primary orchestration comparison.

### `adaptive_local`

Hermes selects among eligible local models by capability and prior evidence. External providers remain unavailable.

## Capabilities

- `HO-PLAN`: decomposition and smallest-sufficient-work judgment.
- `HO-ROUTE`: selection among allowed local model roles.
- `HO-ESCALATE`: justified transition to a stronger local model or safe stop.
- `HO-DELEGATE`: complete bounded subagent goal/context construction.
- `HO-TOOLS`: correct tool selection, arguments, ordering, and result use.
- `HO-RECOVER`: strategy change after injected errors.
- `HO-CRITIC`: use of independent criticism without blindly accepting findings.
- `HO-BUDGET`: token, call, retry, parallelism, latency, and hardware discipline.
- `HO-SENSITIVITY`: respect for the supplied eligibility envelope.
- `HO-STOP`: clarification, no-op, or reuse when additional work is unnecessary.
- `HO-LEARN`: evidence-based improvement proposals that remain unpromoted until replayed.

## Evidence rules

- Every run has a manifest conforming to `bench.run.v1`.
- Raw model output, tool trace, final extraction, validator result, and environment fingerprint are separate artifacts.
- Missing `FINAL:` is a failure, not a reason to score arbitrary trailing text.
- Tests and deterministic validators outrank model self-assessment.
- At least three repetitions are required before comparative claims.
- Ties remain ties; do not invent a total ordering.
- Results invalidated by a validator defect are replayed after correction.
- Reports expose pass rate, variance, failure modes, unnecessary calls, latency, and resource usage per capability.
- There is no global composite score in BENCH-0.

## Candidate aliases

Candidate IDs are stable benchmark identities. Local runtime tags are discovered from Ollama and mapped explicitly after preflight. Never guess that an alias equals an installed model tag.

Initial aliases:

- `qwythos`
- `qwable`
- `gemma4-fable`
- `gemma4-12b-it-qat`
- `qwen3-coder-30b`
- one lightweight negative/control candidate selected from the installed inventory

## Promotion boundary

Benchmark evidence may recommend a JarvisOS role or Hermes configuration. It does not modify JarvisOS, Hermes trusted skills, routing policy, or model assignments automatically.
