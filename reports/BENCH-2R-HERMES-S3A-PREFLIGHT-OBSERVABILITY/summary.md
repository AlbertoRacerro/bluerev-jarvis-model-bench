# BENCH-2R Hermes S3A — persistent preflight evidence

## Failure evidence

After the Windows source-digest correction, activation run `29343942867` still failed during the authorized preflight before capture. No model call was made and no semantic artifact was produced.

GitHub's decoded job-log response truncated the final validator error, and the workflow uploaded only the run artifact directory created after capture. Because capture was correctly skipped after preflight failure, no diagnostic file survived.

A third diagnosis without the exact validator payload would be speculation. This slice therefore changes observability only.

## Correction

The self-hosted preflight now always creates:

- `artifacts/preflight/s3a-preflight.json` from the validator `--output` option;
- `artifacts/preflight/s3a-preflight.log` containing combined stdout and stderr.

The native validator exit code is captured immediately, the log is printed to the job console, and the same non-zero code is returned after evidence creation.

A dedicated `if: always()` artifact step uploads the preflight directory whether validation succeeds or fails. Capture remains skipped after a failed preflight.

## Contract enforcement

The Windows workflow validator now requires:

- the JSON output path;
- the persistent log path;
- the preflight evidence upload step and artifact name;
- three `if: always()` boundaries for preflight evidence, run enforcement and run evidence.

Tests verify these requirements together with the existing LF/CRLF normalization and nested runtime regression suite.

## Safety state

- Marker reset to `enabled=false`.
- No model/profile/case/plugin/skill/finalizer change.
- No automatic retry or activation.
- No production promotion.
- The next activation is permitted only after hosted validation and merge of this observability slice.
