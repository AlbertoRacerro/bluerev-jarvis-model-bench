# BENCH-2 Hermes orchestrator isolation — Phase A

## Decision

BENCH-2 admits all ten models qualified by H3 Lane 1. BENCH-1 direct semantic outcomes are retained as capability evidence, but they are not an admission gate for Hermes orchestration tests.

The immutable plan is bound by SHA-256:

`d6fa093c7950113e5776dc3d4f6c942d86f29b1e4a33f8191c6c1bdd160c3c19`

## Candidate set

1. `gemma4-12b-it-qat`
2. `qwable-9b-fable5`
3. `qwythos-mythos-9b`
4. `minicpm5-fable-1b-control`
5. `qwen3.6-fablevibes-14b-a3b`
6. `gemma4-fable-agentic-12b`
7. `gemma4-fable-coder-12b`
8. `qwen3-8b`
9. `qwythos-hermes-64k`
10. `qwythos-hermes-safe`

This deliberately includes the five candidates that did not pass both BENCH-1 direct capabilities.

## Phase A cases

- `HO-TOOLS`: call `bench_lookup` exactly once with the supplied key, reject the distractor tool, and return the immutable fixture value.
- `HO-STOP`: reuse a supplied verified result without calling any tool.

The planned campaign is five serial batches of two candidates, two cases, and three repetitions: **60 runs**.

## Hermes isolation contract

- Hermes Agent version `0.18.2`, commit `73b611ad19720d70308dad6b0fb64648aaadc216`.
- Local custom provider only: `http://127.0.0.1:11434/v1`.
- Isolated `HERMES_HOME` and working directory for every run.
- Empty fallback chain.
- Ignore rules enabled so host memory, project instructions, and user configuration cannot change the task.
- Explicit toolset `bench2_fixture`; no inherited CLI toolsets.
- Local deterministic plugin only. It has no network or subprocess access and may write only the per-run append-only tool trace.
- JarvisOS and external providers remain out of scope.

## Blocking runtime admission gate

H3 established full-VRAM residency at an actual 32768-token context through the direct Ollama path. That does not prove that Hermes' OpenAI-compatible path will request or preserve the same context.

Before scoring any model, the self-hosted admission canary must observe the effective runtime context and prove `num_ctx = 32768`. A mismatch is `invalid_infrastructure`, not a model failure.

The canary must also prove:

- exact Hermes commit and version;
- exact candidate tag and digest;
- isolated profile and empty fallback chain;
- exact plugin and toolset inventory;
- local-only environment after secret sanitization;
- clean model state before and after the run;
- immutable raw output, tool trace, usage report, environment fingerprint, and runtime-context evidence.

## Authorization state

The execution marker is present but disabled. This PR defines and validates the plan only; it cannot invoke Hermes or a model.

The next separately reviewed slice is the self-hosted admission canary and campaign runner. Only after that slice proves the runtime contract may the marker be enabled for the 60-run campaign.
