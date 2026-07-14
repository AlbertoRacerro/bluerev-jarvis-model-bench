# BENCH-2R Hermes S3A — disabled workflow gate

## Status

`runtime_ready_execution_disabled`

This slice adds the self-hosted workflow needed to execute the reviewed S3A runtime, but leaves the execution marker disabled.

## Workflow boundary

- Trigger: push to `main` changing only `config/bench2r-hermes-s3a-marker.json`.
- No `workflow_dispatch`.
- Activation message prefix: `Activate BENCH-2R Hermes S3A shadow soak`.
- Runner: `[self-hosted, Windows, X64, bluerev-bench]`.
- Five seed batches: `0` through `4`.
- `max-parallel: 1`; batches remain serial.
- `fail-fast: false`; one semantic failure does not erase later evidence.
- `cancel-in-progress: true`; a reviewed replacement activation cancels stale work.
- Checkout is bound to the triggering SHA with persisted credentials disabled.
- Capture uses the in-process Windows keep-awake wrapper.
- Enforce and upload run under `if: always()` so invalid evidence remains visible.
- Artifact retention: 45 days.

## Transition boundary

The historical design validator intentionally rejects a live runtime workflow because it represents the original design-only state. The runtime validator now evaluates that historical design inside a temporary sentinel boundary, restores the real path in `finally`, and then validates the actual workflow separately.

This prevents either of two false states:

1. pretending the historical design included an executable workflow;
2. bypassing design validation merely because the workflow now exists.

## Authorization

The marker remains:

```json
{"enabled": false}
```

Hosted CI validates both:

- the live disabled workflow state;
- a temporary `enabled=true` marker against the exact reviewed workflow.

No model call or GPU work is authorized by this merge. Activation requires a later marker-only commit with the exact reviewed prefix.

## Promotion boundary

Even a fully passing S3A run cannot automatically update model weights, alter the production router or promote the stack. S3A closeout requires human review and leaves production status `not_promoted`.
