# Benchmark Status

This is the live roadmap for the benchmark repository.

Status vocabulary: `planned`, `blocked`, `ready`, `in_progress`, `in_review`, `merged`, `cancelled`.

| ID | Status | PR | Name | Dependencies | Scope |
|---|---|---:|---|---|---|
| BENCH-0 | merged | #1 | Foundation and runner contract | — | Strict extraction, manifests, local inventory, self-hosted Windows workflows, immutable artifacts, and safety boundaries. |
| BENCH-1 | merged | #96 | Direct synthetic orchestration battery | BENCH-0 | Evidence-gated local direct results for explicit HO-STOP and HO-ROUTE contracts: 60 accepted runs across 10 candidates. |
| H4 | merged | #104 | Hermes minimum 64K admission | H3 | All ten Lane 1 candidates attempted on trusted run `29260032005`: 8 qualified, 1 CPU offload, 1 context mismatch. |
| BENCH-2 | in_review | #111 | Hermes orchestrator isolation | H4 | H4-bound v2 plan; two canaries exposed separate context-wiring defects and the full 48-run matrix remains unauthorized. |
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
- The full execution marker remains disabled.

### Isolated Hermes canary

- PR #105 prepared exactly **1 candidate × 1 case × 1 repetition**; PRs #106 and #109 enabled the first two trusted activations.
- Candidate: `qwythos-hermes-safe`; selection is an infrastructure canary, not a ranking or admission preference.
- Case: `ho-tools-hermes-lookup-001`.
- Hermes Agent is pinned to version `0.18.2`, commit `73b611ad19720d70308dad6b0fb64648aaadc216`.
- Run `29263590189`, execution SHA `5901761c0a02097f80e7d6b34e326c13e766e7c4`, is **invalid infrastructure**: zero model API calls because only `model.context_length` was configured and Hermes observed Ollama's default 4096-token context.
- Run `29264163081`, execution SHA `d32de0cb05473139dab2903bf423191555627c1d`, is also **invalid infrastructure**: `ollama_num_ctx=65536` allowed Hermes to execute two local API calls and one exact `bench_lookup` call, but the OpenAI-compatible Ollama path still loaded the model at an observed context of 4096.
- The second artifact matched GitHub's ZIP digest and its internal manifest. It recorded full VRAM residency, `api_calls=2`, the exact tool call/result, and a strict-output mismatch, but none of those observations are admitted as model-quality evidence because the actual runtime context was invalid.
- PR #111 creates a temporary Ollama alias from the exact H4-qualified source model with `PARAMETER num_ctx 65536`, binds the derived alias back to the source name/digest, verifies the alias parameters and loaded digest, and removes the alias after execution.
- The strict final-output validator remains unchanged. If the model again returns the extra `{"final": {...}}` wrapper under valid 64K infrastructure, that result will be retained as a genuine semantic failure rather than silently unwrapped.
- Required evidence remains: clean pinned Hermes checkout, isolated home/workdir, custom loopback provider, deterministic plugin trace, usage file, strict final JSON, actual 65536 context, full VRAM residency, temporary-alias cleanup, immutable repository binding, and manifest verification.
- Credential-bearing environment variables are removed and non-loopback proxy traffic is sinked to `127.0.0.1:9`.

## Excluded evidence

- The original 30 HO-ROUTE outputs from run `29225755398` remain invalidated by the underspecified route fixture.
- Run `29231060170` failed before model execution because the replay entrypoint lacked the `src` bootstrap.
- Run `29231447924` produced six outputs, but its evidence gate was red because the manifest validator was patched in the wrong module; those outputs are not counted.
- H4 run `29257990674` failed before model execution because PowerShell scripts were blocked; it contributes no candidate evidence.
- Hermes canary run `29263590189` made zero API calls because `ollama_num_ctx` was absent; it contributes no model-quality evidence.
- Hermes canary run `29264163081` executed the tool path but loaded only 4096 context; it contributes no model-quality evidence.

## Current operating order

1. Merge PR #111 only after H4, BENCH-2 v2, and canary hosted validators are green on the user-authored head.
2. Enable only the dedicated canary marker in a new activation commit; keep the full BENCH-2 marker disabled.
3. Execute and verify the temporary-alias canary artifact, including GitHub digest, internal manifest, source-to-alias binding, Hermes identity, local-only boundary, tool trace, usage, actual context, VRAM residency, alias removal, and model cleanup.
4. Preserve any strict-output failure as semantic model evidence once infrastructure is valid; do not weaken the parser after observing the answer.
5. Decide the full-matrix gate from the demonstrated canary evidence and the benchmark's all-candidate fairness requirement, not from BENCH-1 outcomes or a global score.
6. Close BENCH-2 capability-by-capability; preserve invalid infrastructure separately and do not calculate a global winner.

`planned` means an outline exists. It is not an implementation instruction and does not authorize unattended expansion of scope.
