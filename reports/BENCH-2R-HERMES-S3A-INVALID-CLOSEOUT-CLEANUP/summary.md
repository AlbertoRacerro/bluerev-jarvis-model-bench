# BENCH-2R Hermes S3A — invalid closeout cleanup

## Evidence

The temporary S3A closeout automation chain was bound to execution SHA `c1cce366128b1678fd6fc0e2a5718b97dad7a9fc`.

That SHA is not a commit in this repository. Consequently, the observer could not bind a real workflow run, and no valid closeout issue, closeout pull request or `reports/BENCH-2R-HERMES-S3A-CLOSEOUT/summary.json` was produced.

The real activation run bound to commit `810400f7b1e5b7659daa16e8ce3516682ce95ada` failed during Windows preflight on every batch. Capture was skipped and no semantic model evidence was produced.

## Corrected state

PR #157 was merged as commit `e2eb8e6ee7a66dece5930b62584ddd9a4dac8569` after S3A, BENCH-2 and H4 validation passed on its exact head.

It:

- resets `config/bench2r-hermes-s3a-marker.json` to `enabled=false`;
- persists preflight JSON and combined logs before capture;
- uploads preflight evidence under `if: always()`;
- validates multiline PowerShell commands after resolving continuation characters;
- keeps the Windows-normalized and safe runtime boundaries authoritative.

## Removed temporary workflows

- `.github/workflows/bench2r-hermes-s3a-observer.yml`
- `.github/workflows/bench2r-hermes-s3a-closeout-observer.yml`
- `.github/workflows/bench2r-hermes-s3a-closeout-pr.yml`
- `.github/workflows/bench2r-hermes-s3a-closeout-hardener.yml`
- `.github/workflows/bench2r-hermes-s3a-closeout-merger.yml`

The governed S3A runtime workflow and hosted S3A validation workflow remain present.

## Decision boundary

- S3A is not closed as PASS or FAIL because no complete attributable 50-run execution exists.
- Production remains `not_promoted`.
- No model weights, router, provider configuration or runtime contract are changed.
- The next operation is a fresh marker-only activation after confirming the self-hosted runner and Ollama are online.
