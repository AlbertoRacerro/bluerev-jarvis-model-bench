# BENCH-2 Hermes orchestrator isolation plan

Status: **review-ready, execution not authorized**.

Canonical plan: `fixtures/bench-plans/bench2-hermes-orchestrator-isolation-v1.json`  
Canonical SHA-256: `9d6a3ea722b536a2a535186f5ef10632c34a0817bad0a511a250721c100a8ddd`

## Decision

BENCH-2 asks which local model most reliably drives a **fixed** Hermes environment. Only the orchestrator model may vary. Hermes commit/configuration, prompts, skills, worker pool, tools, disposable workspace, cases, validators, limits, cleanup, and evidence layout must remain unchanged.

BENCH-1 does not nominate a winner. Five models passed both direct HO-STOP and HO-ROUTE cases; they form the primary BENCH-2 shortlist. The MiniCPM 1B model remains a negative control so that the Hermes layer cannot hide a weak candidate.

## Why execution remains blocked

The last visible Hermes preflight evidence is not recent enough to freeze as the BENCH-2 baseline. The plan therefore leaves preflight artifact, benchmark SHA, Hermes commit, version, and platform mode unresolved. A later revision may set `execution_authorized=true` only after a fresh `required_gate=hermes` preflight is produced on the same trusted `main` SHA that would execute the campaign.

No workflow, marker, CLI invocation, model call, or Hermes mutation is introduced by this plan.

## Stage gates

### B2-PRE-0 — fresh baseline binding

Run only inventory/preflight. Require:

- Hermes gate selected and `scoring_ready=true`;
- local-only environment after sanitization;
- clean Hermes worktree;
- exact Hermes commit and version;
- Windows Git Bash readiness when applicable;
- exact preflight artifact ID and SHA-256;
- preflight and future execution bound to the same benchmark SHA.

### B2-PRE-1 — deterministic adapter contract

Construct the future Hermes command and environment without executing Hermes or a model. Tests must prove:

- isolated Hermes home;
- trusted executable and repository paths;
- disposable workspace containment;
- exact orchestrator tag/digest injection;
- external-provider variables removed;
- no arbitrary shell interpolation;
- stdout, stderr, exit, timeout, command, and environment metadata are separately materialized.

### B2-CAL — deterministic-worker calibration

Use real Hermes, but fixed deterministic fixture workers rather than AI workers. This isolates orchestration from worker quality and exposes validator or trace defects before comparative evidence.

Calibration matrix: six candidates × three cases × one repetition = 18 non-comparative runs.

Cases:

1. `b2-ho-stop-noop-001`: no worker/tool call; reuse supplied verified result.
2. `b2-ho-delegate-single-worker-001`: exactly one bounded delegation to a deterministic success worker.
3. `b2-ho-critic-disagreement-001`: reject a deterministic wrong worker result after independent critic evidence.

Outputs seen during calibration may not be used to edit prompts, cases, or validators and then counted as evidence. Any correction requires a fresh replay.

### B2-CORE — fixed-local-worker comparison

This stage remains blocked. It requires:

- green calibration;
- separately qualified fixed local worker/critic pool;
- locked held-out cases;
- a new reviewed plan revision with `execution_authorized=true`.

The fixed worker pool must be identical for every orchestrator candidate. At least three repetitions per candidate-case pair are required. Results remain capability-specific; no global composite score is allowed.

## Candidate set

Primary shortlist:

- `gemma4-12b-it-qat`
- `qwythos-mythos-9b`
- `qwen3.6-fablevibes-14b-a3b`
- `qwythos-hermes-64k`
- `qwythos-hermes-safe`

Negative control:

- `minicpm5-fable-1b-control`

Each identity is pinned by exact Ollama tag and digest in the JSON plan.

## Evidence and safety

Every future run must preserve raw Hermes output, traces, final extraction, deterministic validator output, configuration/workspace snapshots, environment fingerprint, cleanup evidence, and a SHA-256 manifest.

The campaign remains:

- local-model-only;
- external-network-disabled;
- credential- and secret-free;
- isolated from JarvisOS and unrelated user state;
- trusted-main-only on the self-hosted runner;
- serial at one active model;
- disposable-workspace-only.

BENCH-2 evidence may recommend a role. It may not automatically modify Hermes configuration, JarvisOS, routing policy, or model assignments.
