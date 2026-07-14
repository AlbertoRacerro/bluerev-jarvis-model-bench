# BENCH-2R Hermes S3A-R1 — reviewed Windows workflow

## State

- Self-hosted workflow: present.
- Dedicated repair marker: `enabled=false`.
- Model execution in this slice: none.
- Manual dispatch: absent.
- Production status: `not_promoted`.

## Trigger boundary

The workflow runs only when all conditions hold:

1. a push reaches `main`;
2. the changed path is `config/bench2r-hermes-s3a-r1-repair-marker.json`;
3. the commit message starts with `Activate BENCH-2R Hermes S3A-R1 repair experiment`;
4. the runtime validator accepts the marker as enabled and all source bindings remain exact.

Adding or merging the workflow while the marker remains disabled cannot launch the experiment.

## Windows execution

The three Python execution steps explicitly use `cmd.exe`:

- durable preflight;
- keep-awake capture;
- artifact enforcement.

PowerShell is not used, so the runner's script execution policy is unchanged.

## Batch policy

- matrix batches: `[0, 1, 2]`;
- `max-parallel: 1`;
- `fail-fast: false`;
- concurrency group: `bench2r-hermes-s3a-r1-repair`;
- an updated activation cancels an older in-progress experiment;
- job timeout: `180 min` per batch.

Each batch executes nine paired repair runs from the frozen runtime plan.

## Evidence boundaries

Preflight evidence is uploaded under `if: always()` before capture. Enforcement and final artifact upload also run under `if: always()`.

- preflight retention: `21 days`;
- run evidence retention: `45 days`;
- missing evidence directories are errors;
- capture uses the exact triggering SHA;
- checkout credentials are not persisted.

## Safety decision

The workflow does not:

- replace skill v1.1;
- modify model weights;
- change cases, prompts, sampling or finalizer;
- permit external providers or non-loopback networking;
- promote production;
- expose manual dispatch.

A separate marker-only activation is required after hosted validation and merge of this workflow slice.
