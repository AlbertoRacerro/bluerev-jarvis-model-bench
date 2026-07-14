# BENCH-2R Hermes S3A — durable Python preflight boundary

## Failure evidence

Activation `b2d775541ef3617ab4226e7ca922bc5a8f0272f7` reached the real Windows runner, but the PowerShell preflight step failed before producing `s3a-preflight.json` or `s3a-preflight.log`. The subsequent `if: always()` upload therefore had no files to publish.

The runner was online and checkout completed. Capture was skipped, so no model call or semantic run evidence was produced.

## Root failure mode

A shell block cannot be the authority for preserving its own parser/process-launch failures. If PowerShell terminates before the redirection and exit-code handling complete, the diagnostic boundary disappears with the failing step.

## Correction

`scripts/run_bench2r_hermes_s3a_preflight.py` now owns the boundary:

- creates `artifacts/preflight/` before launching the validator;
- launches the Windows-normalized validator as a child process;
- captures stdout and stderr without shell redirection;
- always writes `s3a-preflight.log`;
- preserves validator JSON when produced;
- writes a fail-closed fallback JSON when the child cannot launch or exits before producing JSON;
- returns the child exit code so capture remains skipped on failure.

The workflow calls only the Python wrapper. Direct PowerShell and direct validator invocation are forbidden by the hosted contract validator.

## Tests

- successful child validation preserves its JSON and writes a log;
- launch exceptions always produce fallback JSON and log;
- non-zero child exit without JSON remains attributable;
- workflow binding requires the wrapper, three `if: always()` evidence boundaries and safe capture/enforce entrypoints;
- existing runtime regression tests remain nested inside the Windows boundary.

## Safety state

- Marker remains `enabled=false`.
- No model execution in this slice.
- No runtime case, skill, finalizer, router, provider or model-weight change.
- Production remains `not_promoted`.
