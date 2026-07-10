# Benchmark Status

This is the live roadmap for the benchmark repository.

Status vocabulary: `planned`, `blocked`, `ready`, `in_progress`, `in_review`, `merged`, `cancelled`.

| ID | Status | PR | Name | Dependencies | Scope |
|---|---|---:|---|---|---|
| BENCH-0 | merged | #1 | Foundation and runner contract | --- | Strict output extraction, manifests, local environment inventory, Windows self-hosted runner workflow, immutable artifacts, and safety rules. |
| BENCH-1 | in_progress | #13 | Synthetic orchestration battery | BENCH-0 | Deterministic planning, routing, escalation, budget, sensitivity, recovery, critic, and stop/no-op cases. PR #13 establishes the strict case-data boundary only; executable fixtures remain pending. |
| BENCH-2 | planned | --- | Hermes orchestrator isolation | BENCH-1 | Hold worker pool and tools fixed while varying only the local model driving Hermes. |
| BENCH-3 | planned | --- | Tool and coding fixtures | BENCH-2 | Windows/PowerShell, file edits, patching, test execution, bounded worker/critic/adjudicator loops. |
| BENCH-4 | blocked | --- | Adaptive local model routing | BENCH-2, BENCH-3 | Hermes chooses among eligible local models by capability, latency, reliability, and resource cost. External APIs remain out of scope. |
| BENCH-5 | planned | --- | Controlled self-improvement | BENCH-4 | Evaluate memory/skill/routing proposals, replay gates, overfitting, and promotion boundaries. |

## Latest trusted preflight evidence

- GitHub Actions run: `29096446631`, attempt `1`.
- Trusted branch and SHA: `main` at `73a06a20ef60bdcab55a53fcd80eda6249ecff5a`.
- Artifact: `preflight-29096446631-1`.
- Artifact digest: `sha256:48769db01a9cccee0ded90978360c60001ac8b52ff27942a654d1f02fe377d40`.
- Deterministic tests: `11` passed; exit code `0`.
- Runtime inventory: exit code `0`, `status=ready`, `local_only=true`, no blocking reasons, and `15` Ollama tags observed.
- Candidate mapping: every tag and digest listed in `candidates/models.local.json` matched the artifact inventory.
- Reproducibility caveat: Hermes was detected at commit `73b611ad19720d70308dad6b0fb64648aaadc216` with a dirty working tree. Comparative scoring remains blocked until that state is cleaned or explicitly snapshotted and pinned.

## Current operating order

1. Clean or explicitly snapshot and pin the Hermes working tree before comparative scoring.
2. Review PR #13 as the replacement for stale draft PR #2; do not merge PR #2.
3. Replay the trusted-main deterministic suite after PR #13 is merged.
4. Add the first executable synthetic cases only after the case contract is green on trusted `main`.
5. Start repeated Hermes orchestration runs only after deterministic fixtures and validators are green.

`planned` means an outline exists. It is not an implementation instruction and does not authorize unattended expansion of scope.
