# BENCH-2R Hermes S3A-R1 — paired repair runtime implementation

## State

- Runtime implementation: present.
- Self-hosted workflow: absent.
- Dedicated repair marker: `enabled=false`.
- Model execution in this slice: none.
- Production skill v1.1: unchanged.
- Repair skill v1.2: candidate only.
- Production status: `not_promoted`.

## Runtime contract

The implementation executes three serial seed batches. Each batch contains exactly nine runs:

- control v1.1: two negative cases × two repetitions = four runs;
- repair v1.2: the same two negative cases × two repetitions = four runs;
- repair v1.2: one nominal sentinel = one run.

Total planned inventory: `27` runs.

The only allowed paired-arm difference is the installed skill path and its Git blob. Candidate model, seed, repetition, task prompt, cases, sampling, Hermes commit, tool registry, finalizer, proxy and runtime limits remain fixed.

## Execution boundary

The runner reuses the reviewed S3A producer and safe validator boundary:

- local Ollama loopback only;
- no external providers;
- no JarvisOS access;
- full native trajectory and wire trace required;
- full-VRAM and cleanup attestations required;
- deterministic finalizer unchanged;
- negative `actions`-only ledger gate unchanged;
- per-run timeout `900 s`;
- Windows keep-awake wrapper;
- durable Python preflight that always writes JSON and log evidence.

The runner installs the selected skill inside an isolated Hermes home through a bounded monkeypatch and restores the original installer in `finally`.

## Artifact attribution

Every run stores:

- selected `arm_id`;
- skill version, path and Git blob;
- task prompt and native trajectory;
- tool and wire traces;
- validator and environment fingerprints;
- run manifest with SHA-256 and byte sizes.

The enforcer requires the selected skill version to appear in the native trajectory and verifies that paired arms received byte-identical task prompts.

## Acceptance enforcement

For each repair batch:

- all four repair negative runs must pass tool sequence, ledger-only, fail-closed and shadow gates;
- both timeout runs must contain the real reviewed timeout-tool invocation;
- the nominal sentinel must pass shadow validation;
- repair may not underperform the paired control on any gate that control passed.

Across three batches this yields the design acceptance target:

- negative tool sequence: `12/12`;
- negative ledger-only: `12/12`;
- negative fail-closed: `12/12`;
- negative shadow pass: `12/12`;
- timeout real tool invocation: `6/6`;
- nominal sentinels: `3/3`.

Control failures remain observational. Repair failures are enforcement failures.

## Safety decision

A passing experiment cannot:

- replace the current skill automatically;
- update model weights;
- promote a production route;
- reclassify the failed S3A closeout;
- reuse the failed S3A seed inventory.

It permits only a later design for a fresh-seed full soak.

## Activation boundary

This PR must not include `.github/workflows/bench2r-hermes-s3a-r1-repair.yml`. A later activation slice must add the reviewed self-hosted workflow while the marker remains disabled, pass hosted validation, and only then activate through a marker-only commit.
