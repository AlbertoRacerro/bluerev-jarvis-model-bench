# Benchmark Status

This is the live roadmap for the benchmark repository.

Status vocabulary: `planned`, `blocked`, `ready`, `in_progress`, `in_review`, `merged`, `cancelled`.

| ID | Status | PR | Name | Dependencies | Scope |
|---|---|---:|---|---|---|
| BENCH-0 | in_review | #1 | Foundation and runner contract | --- | Strict output extraction, manifests, local environment inventory, Windows self-hosted runner workflow, immutable artifacts, and safety rules. |
| BENCH-1 | planned | --- | Synthetic orchestration battery | BENCH-0 | Deterministic planning, routing, escalation, budget, sensitivity, recovery, critic, and stop/no-op cases. |
| BENCH-2 | planned | --- | Hermes orchestrator isolation | BENCH-1 | Hold worker pool and tools fixed while varying only the local model driving Hermes. |
| BENCH-3 | planned | --- | Tool and coding fixtures | BENCH-2 | Windows/PowerShell, file edits, patching, test execution, bounded worker/critic/adjudicator loops. |
| BENCH-4 | blocked | --- | Adaptive local model routing | BENCH-2, BENCH-3 | Hermes chooses among eligible local models by capability, latency, reliability, and resource cost. External APIs remain out of scope. |
| BENCH-5 | planned | --- | Controlled self-improvement | BENCH-4 | Evaluate memory/skill/routing proposals, replay gates, overfitting, and promotion boundaries. |

## Current operating order

1. Merge BENCH-0 after human review.
2. Register the dedicated Windows runner.
3. Run inventory/preflight and map actual Ollama tags to candidate aliases.
4. Correct any harness or extraction defects before scoring models.
5. Build BENCH-1 synthetic cases.
6. Start repeated Hermes orchestration runs only after deterministic fixtures are green.

`planned` means an outline exists. It is not an implementation instruction and does not authorize unattended expansion of scope.
