# BENCH-2R Hermes S3A — Windows cmd shell boundary

## Failure evidence

Activation `c30cf7f35022bfede5835e72acbcf7d4355ebf69` reached `bluerev-bench-win`, but GitHub Actions invoked each `run:` step through a temporary PowerShell script. The machine execution policy rejected that `.ps1` before Python started:

`PSSecurityException: l'esecuzione di script è disabilitata nel sistema in uso`.

The durable Python wrapper therefore never ran, no preflight files were created, capture was skipped and no model call occurred.

## Correction

The three Python-bearing workflow steps now declare `shell: cmd` explicitly:

- durable preflight wrapper;
- Windows keep-awake capture;
- safe artifact enforcement.

Upload actions are unchanged. The hosted validator requires exactly three `shell: cmd` declarations and continues to reject PowerShell, direct validator invocation and unsafe runner entrypoints.

## Safety state

- Marker remains `enabled=false` during this slice.
- No Windows execution-policy change is required.
- No model, runtime case, skill, finalizer, router, provider or weight change.
- Production remains `not_promoted`.
