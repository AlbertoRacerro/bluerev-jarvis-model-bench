# BENCH-2 Hermes full matrix v3 — invalid infrastructure closeout

Run `29288354274` was activated from commit `51071ed211d23bf28b5804adfb2bca8d6d50df59`.

## Final state

- Batch 0 completed capture and published one artifact, but all 12 records were `invalid_infrastructure`.
- Batch 1 lost or interrupted the self-hosted runner during capture and published no artifact.
- Batches 2 and 3 were cancelled before execution.
- No result from this run is semantically evaluable.

## Root cause

The first wrapper created the 12 per-run directories before calling the frozen `capture()` function. `capture()` immediately deleted the complete artifact root with `shutil.rmtree(output_dir)`. The subsequent `_run_once` call therefore still attempted to write `raw-output.txt` without an existing parent directory.

## Verified artifact evidence

The batch 0 archive SHA-256 matches GitHub. Its top-level manifest and all 12 per-run manifests were verified byte-for-byte. The report is bound to the run ID, attempt, activation SHA, reviewed plan, H4 closeout, canary closeout, and pinned Hermes identity.

## Decision

This run is invalid infrastructure evidence only. It must not affect model admission, capability scoring, ties, or ranking. The marker was disabled and the corrected wrapper now creates each directory immediately at the `_run_once` boundary, after capture cleanup.
