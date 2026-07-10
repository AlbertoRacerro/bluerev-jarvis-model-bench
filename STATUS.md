# Benchmark Status

This is the live roadmap for the benchmark repository.

Status vocabulary: `planned`, `blocked`, `ready`, `in_progress`, `in_review`, `merged`, `cancelled`.

| ID | Status | PR | Name | Dependencies | Scope |
|---|---|---:|---|---|---|
| BENCH-0 | merged | #1 | Foundation and runner contract | --- | Strict output extraction, manifests, local environment inventory, Windows self-hosted runner workflow, immutable artifacts, and safety rules. |
| BENCH-1 | in_progress | #18 | Synthetic orchestration battery | BENCH-0 | Strict case contracts, deterministic HO-STOP/HO-ROUTE fixtures, and the bounded direct execution pipeline are merged. Two Qwythos runs exposed truncation and hidden-oracle defects; an explicit candidate-visible response contract is pending replay. |
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
- Reproducibility note: Hermes reports that the pinned checkout is behind upstream. This remains non-blocking while the exact clean commit is retained; updating Hermes creates a new baseline and requires replay.

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

## First Qwythos-safe direct-smoke evidence

- GitHub Actions run: `29103995266`, attempt `1`.
- Trusted branch and SHA: `main` at `6fafcee357bde1e375924e428bff3b703daf7d27`.
- Artifact: `direct-smoke-29103995266-1`.
- Artifact digest: `sha256:dcf7ec4841869119ce6c577c7f0c513bec063e1d20a60545e47632da9ae0aa3e`.
- Deterministic tests: `75` passed; test exit code `0`.
- Candidate: `qwythos-hermes-safe`.
- Case: `ho-stop-reuse-001`.
- Execution completed: `true`; infrastructure exit code `0`.
- Ollama termination: `done_reason=length`, `eval_count=256`, configured `num_predict=256`.
- Raw output ended mid-reasoning before a contracted `FINAL:` could be emitted.
- Prior harness field: `candidate_passed=false`.
- Correct result status: `invalid`; the benchmark truncated the response, so this is not a semantic Qwythos failure.
- Manifest SHA-256: `b8881d0591d29899476bbe18fc28ec6140f81e963ff0281132a3b7cee75e0ce1`.

## Second Qwythos-safe direct-smoke evidence

- GitHub Actions run: `29104571461`, attempt `1`.
- Trusted branch and SHA: `main` at `50fc3b3c7b88c715c5f60b8538b6c8955ca99b1d`.
- Artifact: `direct-smoke-29104571461-1`.
- Artifact digest: `sha256:4af28ed332dd6f26551c33c0e7ddd3fd2c0a9f4a700b3ed909667ae812f88e74`.
- Deterministic tests: `81` passed; test exit code `0`.
- Candidate: `qwythos-hermes-safe`.
- Case: `ho-stop-reuse-001`.
- Execution completed: `true`; infrastructure exit code `0`.
- Ollama termination: `done_reason=stop`, `eval_count=399`, configured `num_predict=1024`.
- Harness result: `failed`; output used field `supplied_result` and action `return_supplied_result` without terminal `stop`.
- Case defect: candidate-visible data did not specify the required output field `final` or the exact required action sequence, while evaluator-only `expected` required both.
- Correct interpretation: invalidated by an underspecified case contract; this run must not be counted as a Qwythos failure.
- Manifest SHA-256: `8eeaa46e7a1b293fe4ef237403af7679451ce2bd91d2d9ef92c767ac0e065200`.

## Current operating order

1. Replace real-model use of `ho-stop-reuse-001` with `ho-stop-reuse-explicit-002`; keep the old run artifacts immutable.
2. Require exact evaluator expectations to match candidate-visible `inputs.response_contract` before any model call.
3. Preserve the full evaluator-only case as `case_definition.json`, bind its SHA-256 into the environment fingerprint and manifest, and fail the infrastructure gate if the digest is absent.
4. Replay the same `qwythos-hermes-safe` smoke with the new case; candidate, seed, temperature, context, generation limit, timeout, endpoint, and validator remain unchanged.
5. Do not compare candidates until complete valid results exist and each candidate-capability pair has at least three repetitions under an unchanged environment fingerprint.

`planned` means an outline exists. It is not an implementation instruction and does not authorize unattended expansion of scope.
