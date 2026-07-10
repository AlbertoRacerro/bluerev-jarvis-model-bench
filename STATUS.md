# Benchmark Status

This is the live roadmap for the benchmark repository.

Status vocabulary: `planned`, `blocked`, `ready`, `in_progress`, `in_review`, `merged`, `cancelled`.

| ID | Status | PR | Name | Dependencies | Scope |
|---|---|---:|---|---|---|
| BENCH-0 | merged | #1 | Foundation and runner contract | --- | Strict output extraction, manifests, local environment inventory, Windows self-hosted runner workflow, immutable artifacts, and safety rules. |
| BENCH-1 | in_review | #18 | Synthetic orchestration battery | BENCH-0 | Strict case contracts and the first deterministic HO-STOP/HO-ROUTE fixtures are merged. PR #18 adds one bounded direct Ollama smoke execution for the lightweight control; it does not add Hermes execution or comparative scoring. |
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

## Current operating order

1. Review and merge PR #18 only if its trusted-main, local-only, fixed-candidate, fixed-case, timeout, and artifact boundaries remain intact.
2. Manually dispatch `Local direct-model smoke` on `main`; the workflow has no arbitrary model, endpoint, path, or fixture inputs.
3. Inspect the immutable artifact and distinguish infrastructure success from `candidate_passed`.
4. Treat the single smoke result as preliminary pipeline evidence only, whether the control passes or fails.
5. Add repetitions or additional candidates only after the direct artifact contract is verified; comparative claims require at least three repetitions under an unchanged environment fingerprint.

`planned` means an outline exists. It is not an implementation instruction and does not authorize unattended expansion of scope.
