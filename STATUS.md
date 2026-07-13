# Benchmark Status

This is the live roadmap for the benchmark repository.

Status vocabulary: `planned`, `blocked`, `ready`, `in_progress`, `in_review`, `merged`, `cancelled`.

| ID | Status | PR | Name | Dependencies | Scope |
|---|---|---:|---|---|---|
| BENCH-0 | merged | #1 | Foundation and runner contract | — | Strict extraction, manifests, local inventory, self-hosted Windows workflows, immutable artifacts, and safety boundaries. |
| BENCH-1 | merged | #96 | Direct synthetic orchestration battery | BENCH-0 | Evidence-gated local direct results for explicit HO-STOP and HO-ROUTE contracts: 60 accepted runs across 10 candidates. |
| H4 | in_review | #104 | Hermes minimum 64K admission | H3 | All ten Lane 1 candidates attempted on trusted run `29260032005`: 8 qualified, 1 CPU offload, 1 context mismatch. |
| BENCH-2 | in_review | #104 | Hermes orchestrator isolation | H4 | H4-bound v2 plan: eight infrastructure-qualified candidates, two capabilities, three repetitions, 48 total runs at an actual 65536-token context. |
| BENCH-3 | planned | — | Tool and coding fixtures | BENCH-2 | Windows/cmd, file edits, patching, deterministic tests, and bounded worker/critic/adjudicator loops. |
| BENCH-4 | blocked | — | Adaptive local model routing | BENCH-2, BENCH-3 | Route among eligible local models by capability, reliability, latency, and resource cost. External APIs remain out of scope. |
| BENCH-5 | planned | — | Controlled self-improvement | BENCH-4 | Evaluate memory, skill, routing, replay, overfitting, and promotion boundaries. |

## Latest trusted runtime qualification

### H4 Hermes minimum 64K

- Workflow run: `29260032005`, attempt `1`.
- Trusted execution SHA: `a2926cc93abb1a64874352c4508e8c97b0b6007f`.
- Candidate set: **all ten H3-qualified Lane 1 models**, regardless of BENCH-1 direct outcomes.
- Result: **8 `qualified_64k`, 1 `cpu_offload`, 1 `context_mismatch`, 0 `load_failed`**.
- All five jobs completed with capture, artifact upload, evidence enforcement, and issue publication green.
- All five archives matched GitHub SHA-256 metadata; internal manifests, source bindings, exact candidate identity, cleanup, context observation, and local-only boundaries passed.
- The initial run `29257990674` is infrastructure-invalid: Windows PowerShell policy blocked execution before Python or any model ran.
- H4 is hardware/runtime admission only. It does not rank semantic model quality.

Stock-Hermes eligible candidates:

- `gemma4-12b-it-qat`
- `qwable-9b-fable5`
- `qwythos-mythos-9b`
- `minicpm5-fable-1b-control`
- `gemma4-fable-agentic-12b`
- `gemma4-fable-coder-12b`
- `qwythos-hermes-64k`
- `qwythos-hermes-safe`

H4 nonqualifications:

- `qwen3.6-fablevibes-14b-a3b`: actual context 65536, but GPU residency `0.9549681545549448`; excluded by the reviewed no-CPU-offload policy.
- `qwen3-8b`: actual loaded context 40960; below Hermes Agent 0.18.2's hard 64000-token minimum.

Detailed evidence is stored in `reports/H4-HERMES-MINIMUM-64K/`.

### H3 primary 32K

- Workflow run: `29106127334`, valid attempts `14`–`18`.
- Trusted execution SHA: `202214c45a9a6952600bbd2d621697fcf349db25`.
- Result: **10/10 candidates fully resident in VRAM at an actual 32768-token context**.
- H3 is retained as the lower-context runtime baseline and is not semantic ranking.

## BENCH-1 trusted semantic evidence

### HO-STOP

- Workflow run: `29225755398`, attempt `1`.
- Trusted SHA: `5d527a10e7e49140647a7475b2aebc35c4177078`.
- Retained case: `ho-stop-reuse-explicit-002`.
- Accepted evidence: **30 runs — 18 pass, 12 fail, 0 invalid**.

### HO-ROUTE explicit replay

- Workflow run: `29232014623`, attempt `1`.
- Trusted SHA: `057c33ccbcb40acff3f840f642b5165f396df7f8`.
- Case: `ho-route-local-coder-explicit-002`.
- Accepted evidence: **30 runs — 18 pass, 12 fail, 0 invalid**.

### Combined capability matrix

- Accepted evidence: **60 runs — 36 pass, 24 fail, 0 invalid**.
- Five candidates passed all repetitions on both capabilities: `gemma4-12b-it-qat`, `qwythos-mythos-9b`, `qwen3.6-fablevibes-14b-a3b`, `qwythos-hermes-64k`, and `qwythos-hermes-safe`.
- They remain tied. BENCH-1 declares no aggregate score or global winner.
- BENCH-1 outcomes are post-hoc explanatory evidence only for BENCH-2 and are not an admission gate.

Detailed evidence is stored in `reports/BENCH-1-HO-ROUTE-EXPLICIT-REPLAY/` and `reports/BENCH-1-DIRECT-SEMANTIC-CLOSEOUT/`.

## BENCH-2 v2 contract

- The historical v1 plan remains immutable evidence of the invalid 32768-token assumption and must not execute.
- The v2 plan is bound to the H4 closeout summary and manifest.
- It includes all eight and only the eight `qualified_64k` candidates.
- Four candidates that failed at least one BENCH-1 direct capability remain admitted, proving direct semantic outcomes are non-gating.
- Required runtime context: actual `num_ctx = 65536`.
- Matrix: 8 candidates × 2 cases × 3 repetitions = **48 runs**, four serial batches.
- Comparison remains capability-specific; global composite scores are forbidden and ties remain ties.
- The execution marker remains disabled. PR validation cannot run Hermes, Ollama, external providers, or JarvisOS.

## Excluded evidence

- The original 30 HO-ROUTE outputs from run `29225755398` remain invalidated by the underspecified route fixture.
- Run `29231060170` failed before model execution because the replay entrypoint lacked the `src` bootstrap.
- Run `29231447924` produced six outputs, but its evidence gate was red because the manifest validator was patched in the wrong module; those outputs are not counted.
- H4 run `29257990674` failed before model execution because PowerShell scripts were blocked; it contributes no candidate evidence.

## Current operating order

1. Merge PR #104 only after both hosted validation workflows are green.
2. Implement a single-candidate isolated Hermes canary against the v2 plan, without enabling the full marker.
3. Verify Hermes initialization, isolated home/workdir, local custom provider, plugin loading, tool trace, usage file, context observation, cleanup, and immutable artifact binding.
4. Only after a valid canary, enable and dispatch the four serial BENCH-2 batches for all eight H4-qualified candidates.
5. Close BENCH-2 capability-by-capability; preserve invalid infrastructure separately and do not calculate a global winner.

`planned` means an outline exists. It is not an implementation instruction and does not authorize unattended expansion of scope.
