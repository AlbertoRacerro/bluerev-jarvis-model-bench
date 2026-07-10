# Benchmark Status

This is the live roadmap for the benchmark repository.

Status vocabulary: `planned`, `blocked`, `ready`, `in_progress`, `in_review`, `merged`, `cancelled`.

| ID | Status | PR | Name | Dependencies | Scope |
|---|---|---:|---|---|---|
| BENCH-0 | merged | #1 | Foundation and runner contract | --- | Strict output extraction, manifests, local environment inventory, Windows self-hosted runner workflow, immutable artifacts, and safety rules. |
| BENCH-1 | in_progress | #18 | Synthetic orchestration battery | BENCH-0 | Strict case contracts, deterministic HO-STOP/HO-ROUTE fixtures, and the bounded direct execution pipeline are merged. The first control run completed and failed semantically as expected; a second fixed-candidate smoke is being prepared. |
| BENCH-2 | planned | --- | Hermes orchestrator isolation | BENCH-1 | Hold worker pool and tools fixed while varying only the local model driving Hermes. |
| BENCH-3 | planned | --- | Tool and coding fixtures | BENCH-2 | Windows/PowerShell, file edits, patching, test execution, bounded worker/critic/adjudicator loops. |
| BENCH-4 | blocked | --- | Adaptive local model routing | BENCH-2, BENCH-3 | Hermes chooses among eligible local models by capability, latency, reliability, and resource cost. External APIs remain out of scope. |
| BENCH-5 | planned | --- | Controlled self-improvement | BENCH-4 | Evaluate memory/skill/routing proposals, replay gates, overfitting, and promotion boundaries. |

## Latest trusted preflight evidence

- GitHub Actions run: `29101424988`, attempt `1`.
- Trusted branch and SHA: `main` at `4437ae74e229b4c168cfbe89691c6d85a5690def`.
- Artifact: `preflight-29101424988-1`.
- Artifact digest: `sha256:5f38b2e945be0fa12dfeacaa2d011389d7a579ce86622802fbf56089a34d5aab`.
- Deterministic tests: `61` passed; test exit code `0`.
- Runtime inventory: exit code `0`, `status=ready`, `runner_ready=true`, `scoring_ready=true`, `local_only=true`, and no blocking reasons.
- Hermes: version `0.18.2`, branch `main`, clean worktree, pinned commit `73b611ad19720d70308dad6b0fb64648aaadc216`.
- Ollama: loopback endpoint, version `0.31.2`, and `15` model tags with digests recorded.
- Candidate mapping: every enabled candidate tag and digest remained present and matched the trusted artifact inventory.
- Reproducibility note: Hermes reports that the pinned checkout is `106` commits behind upstream. This remains non-blocking while the exact clean commit is retained; updating Hermes creates a new baseline and requires replay.

## First trusted direct-smoke evidence

- GitHub Actions run: `29103303992`, attempt `1`.
- Trusted branch and SHA: `main` at `784ea2327dd444225c1319ef240db4a8c3cd388c`.
- Artifact: `direct-smoke-29103303992-1`.
- Artifact digest: `sha256:56497d28e33b6853be65bf29f28aa94b5b021ce77e389cd58fb4e6cc8adb505c`.
- Deterministic tests: `73` passed; test exit code `0`.
- Candidate: `minicpm5-fable-1b-control`.
- Case: `ho-stop-reuse-001`.
- Execution completed: `true`; infrastructure exit code `0`.
- Candidate passed: `false`.
- Deterministic failure: missing required `FINAL:` marker; the raw response was a generic self-description unrelated to the task.
- Manifest SHA-256: `bae7e3a3d77d27a12c507fee433f3502bcffa00c34d7b38a0981d7cf8201b407`.
- Interpretation: valid preliminary pipeline evidence and a semantic failure for the lightweight control, not a comparative ranking.

## Current operating order

1. Keep the fixture, prompt contract, generation parameters, environment fingerprint rules, and validator unchanged.
2. Run the same single HO-STOP smoke with fixed candidate `qwythos-hermes-safe`.
3. Inspect the immutable artifact and record `candidate_passed` without claiming a ranking.
4. Add repetitions only after the second candidate confirms that the direct execution boundary behaves consistently.
5. Comparative claims require at least three repetitions per candidate and capability under an unchanged environment fingerprint.

`planned` means an outline exists. It is not an implementation instruction and does not authorize unattended expansion of scope.
