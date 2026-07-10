# Benchmark Status

This is the live roadmap for the benchmark repository.

Status vocabulary: `planned`, `blocked`, `ready`, `in_progress`, `in_review`, `merged`, `cancelled`.

| ID | Status | PR | Name | Dependencies | Scope |
|---|---|---:|---|---|---|
| BENCH-0 | merged | #1 | Foundation and runner contract | --- | Strict output extraction, manifests, local environment inventory, Windows self-hosted runner workflow, immutable artifacts, and safety rules. |
| BENCH-1 | in_progress | #13 | Synthetic orchestration battery | BENCH-0 | The strict `bench.case.v1` case-data boundary is merged. Executable deterministic fixtures and validator dispatch remain pending. |
| BENCH-2 | planned | --- | Hermes orchestrator isolation | BENCH-1 | Hold worker pool and tools fixed while varying only the local model driving Hermes. |
| BENCH-3 | planned | --- | Tool and coding fixtures | BENCH-2 | Windows/PowerShell, file edits, patching, test execution, bounded worker/critic/adjudicator loops. |
| BENCH-4 | blocked | --- | Adaptive local model routing | BENCH-2, BENCH-3 | Hermes chooses among eligible local models by capability, latency, reliability, and resource cost. External APIs remain out of scope. |
| BENCH-5 | planned | --- | Controlled self-improvement | BENCH-4 | Evaluate memory/skill/routing proposals, replay gates, overfitting, and promotion boundaries. |

## Latest trusted preflight evidence

- GitHub Actions run: `29100302596`, attempt `1`.
- Trusted branch and SHA: `main` at `27d2ca544f44772d4a2720620c5cde3c05532e6d`.
- Artifact: `preflight-29100302596-1`.
- Artifact digest: `sha256:08b54b90be663395bb34d11cbf82d1681d6fdcac4ef5a99b94e0f92d35c7e977`.
- Deterministic tests: `44` passed; test exit code `0`.
- Runtime inventory: exit code `0`, `status=ready`, `runner_ready=true`, `scoring_ready=true`, `local_only=true`, and no blocking reasons.
- Hermes: version `0.18.2`, branch `main`, clean worktree, pinned commit `73b611ad19720d70308dad6b0fb64648aaadc216`.
- Ollama: loopback endpoint, version `0.31.2`, and `15` model tags with digests recorded.
- Candidate mapping: every tag and digest listed in `candidates/models.local.json` remained present and matched the trusted artifact inventory.
- Reproducibility note: Hermes reports that the pinned checkout is `106` commits behind upstream. This is not a scoring-readiness blocker while the exact clean commit remains recorded; updating Hermes would create a new environment baseline and require a replay.

## Current operating order

1. Keep the clean Hermes commit and Ollama model digests fixed while implementing the first BENCH-1 fixtures.
2. Add a small executable fixture slice and deterministic validator dispatch without calling models, Hermes, tools, external APIs, or JarvisOS.
3. Replay the trusted-main suite after that slice is merged and preserve the resulting artifact.
4. Only then add bounded local-model execution and repeated runs; raw output, trace, extraction, validation, and environment evidence must remain separate.
5. Start comparative claims only after at least three repetitions per candidate and capability under an unchanged environment fingerprint.

`planned` means an outline exists. It is not an implementation instruction and does not authorize unattended expansion of scope.
