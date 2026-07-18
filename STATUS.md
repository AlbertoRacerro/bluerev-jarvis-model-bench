# Benchmark Status

Live roadmap and evidence summary for this repository.

Status vocabulary: `planned`, `blocked`, `ready`, `in_progress`, `in_review`, `merged`, `cancelled`.

| ID | Status | PR | Name | Evidence-backed state |
|---|---|---:|---|---|
| BENCH-0 | merged | #1 | Foundation and runner contract | Strict extraction, manifests, local inventory, immutable artifacts, and local-only safety controls. |
| BENCH-1 | merged | #96 | Direct orchestration battery | 60 accepted runs; 36 pass, 24 fail, 0 invalid; five candidates tied across the two retained capabilities. |
| H4 | merged | #104 | Hermes minimum 64K admission | 8 qualified, 1 CPU offload, 1 context mismatch. Hardware/runtime admission only. |
| BENCH-2 | merged | #134 | Stock-Hermes full matrix | 48/48 completed; no stock-Hermes candidate admitted. |
| BENCH-2R/S1 | merged | #146 | Profile-and-skill diagnostic | 32 runs; no fixed candidate/arm passed both cases; three candidates advanced. |
| BENCH-2R/S2 | merged | #150 | Held-out governed-stack admission | 36/36 infrastructure-valid; the governed Gemma stack passed 12/12 and advanced only to shadow testing. |
| BENCH-2R/S3A | merged | #166 | Governed-stack shadow soak | 50/50 infrastructure-valid, but negative controls failed. |
| BENCH-2R/S3A-R1 | merged | #175 | Skill v1.2 bounded repair | Tool and timeout behavior improved; strict raw ledger JSON remained 0/4 because of Markdown fences. |
| BENCH-2R/S3A-R2 | merged | #177 | Skill v1.3 static design | An 18-run fresh-seed canary is statically designed. No workflow, marker, execution, adoption, or promotion. |
| BENCH-3 | merged | #179 | Hermes memory and local-routing reliability contract | Two candidate skills, one bundle, 12 memory cases, 12 routing cases, exact source/blob bindings, and fail-closed static validators. No runtime or JarvisOS change. |
| BENCH-3R | planned | — | Memory/routing runtime qualification | Future local-only synthetic canary. No executor, self-hosted workflow, marker, or run arithmetic is authorized. |
| BENCH-3B | planned | — | Tool and coding fixtures | Starts only after the memory/routing runtime contract is stable. |
| BENCH-4 | blocked | — | Adaptive local model routing | Requires qualified governed stacks and dispatcher evidence. External APIs remain out of scope. |
| BENCH-5 | planned | — | Controlled self-improvement | Memory, skill, routing, replay, overfitting, and promotion boundaries. |

## Current operating state

- Current merge: `731de9de429589f468d6cb577bdeab11932c2bc8` from PR #179.
- Production status: **`not_promoted`**.
- Evaluated units are governed stacks, not standalone checkpoint names.
- S3A and S3A-R1 markers are disabled.
- No S3A-R2 runtime workflow or marker exists.
- BENCH-3 skills and bundle are candidate fixtures only; they are not installed or adopted.
- BENCH-3 contains no runtime executor, marker, self-hosted workflow, Ollama call, persistent-memory mutation, routing activation, or JarvisOS integration.
- No merge authorizes external providers, model-weight changes, unattended skill replacement, production routing, or production promotion.

## Authoritative experimental progression

### Runtime and direct baselines

- H4 run `29260032005`, attempt 1: 8 `qualified_64k`, 1 `cpu_offload`, 1 `context_mismatch`.
- BENCH-1: 60 accepted direct runs, 36 pass, 24 fail, 0 invalid. No global winner.
- Detailed evidence: `reports/H4-HERMES-MINIMUM-64K/`, `reports/BENCH-1-HO-ROUTE-EXPLICIT-REPLAY/`, and `reports/BENCH-1-DIRECT-SEMANTIC-CLOSEOUT/`.

### Stock Hermes and governed-stack admission

- BENCH-2 run `29309289661`: 8 candidates × 2 cases × 3 repetitions = 48 completed runs; no stock candidate admitted.
- S1: 32 diagnostic runs; three candidates advanced, no stack admitted.
- S2 run `29335974597`: 36/36 infrastructure-valid. The governed `gemma4-12b-it-qat` stack achieved 12/12 admission, 12/12 raw orchestration, 12/12 finalized output, and 3/12 raw presentation.
- The admitted object includes model digest, sampling, 65536 context, Hermes commit, skill, finalizer, tools, budgets, trajectories, and traces.
- Admission allowed later shadow testing only.

### S3A shadow soak and repairs

- S3A run `29350762330`: 50/50 infrastructure-valid; 31/50 full shadow pass; 1/20 negative-control pass; wrong ledger shape in 19/20 negatives; timeout not invoked in 3/10 timeout runs.
- S3A-R1 run `29364133435`, attempt 2: 9/9 infrastructure-valid; 4/4 exact negative tool sequence; 4/4 fail closed; 2/2 timeout invocation; 1/1 nominal sentinel; 0/4 strict raw ledger because outputs were fenced.
- Skill v1.2 was not adopted.
- S3A-R2 keeps v1.2 as control and designs v1.3 with fresh seeds `849690` and `603823` for 16 paired negative runs plus 2 nominal sentinels.
- v1.3 has not executed against Hermes or Ollama.
- Runner audit evidence: `reports/BENCH-2R-HERMES-S3A-RUNNER-AUDIT/`.

## BENCH-3 memory and routing static contract

- PR: #179.
- Reviewed head: `1f7746362a8ae147f82ab355e9452b200f8bb2e8`.
- Merge: `731de9de429589f468d6cb577bdeab11932c2bc8`.
- Hermes: version `0.18.2`, commit `73b611ad19720d70308dad6b0fb64648aaadc216`.
- Hosted validation run: `29658898042`.
- Artifact: `8433709862`.
- Artifact digest: `sha256:dedca6bca97e07f92176dad057b8e9db79a318f0bced7c1fe04eaff6f0d2fbab`.
- Artifact schema: `bench3.static-contract-validation.v1`.

Candidate fixtures:

- `memory-orchestration` v0.1.0, blob `48b3c07168aa143ecfa2fb63ebbbb0da070c1a1e`.
- `routing-orchestration` v0.1.0, blob `cb0b9b348cacd5f014e70790fd6410e120b5a7ba`.
- `jarvis-orchestration-core`, blob `59bc83ff4079e2e956237c4097ba0d7472f06e09`.
- Case contracts, blob `65072ade82917f97055a7eba4726bc2796e1ba91`.

Contracted behavior:

- 12 ordered memory cases and 12 ordered routing cases.
- Every case has deterministic inputs, exact decision and target, required output fields, required evidence, allowed side effects, and at least two negative assertions.
- Memory stores are separated into user profile, curated memory, session search, procedural skills, project context, and performance ledger.
- Persistent writes are parent-only and approval-gated; children may propose but not commit shared memory.
- Conflict precedence is exact: current user statement, verified current project state, approved persistent memory, then session history.
- Routing uses capability-registry and performance-ledger evidence, not checkpoint reputation or a global model score.
- Initial orchestration is limited to one child, depth one, least-privilege tools, explicit iteration ceilings, and an external wall-clock watchdog.
- One infrastructure fallback may occur before side effects for reversible tasks. Semantic failures are not auto-rerouted. Fallback after side effects is forbidden.
- Hermes delegation is globally configured at the pinned commit; it is not a reviewed per-task local-model switch.
- OpenRouter provider routing is not Ollama routing. Actual local dispatch requires a deterministic dispatcher or separately pinned profiles.
- Hermes profiles isolate state but are not filesystem sandboxes.

Mechanical boundaries:

- Complete contract, acceptance, memory precedence, fixture bindings, case contracts, workflow/config/script namespaces, Unix shell helpers, and action namespace all validate green.
- Python, PowerShell, cmd, bat, and shell runtime paths are guarded.
- Any file under `.github/actions` is rejected during this static slice.
- Signed text fixtures are pinned to LF.
- `execution_implemented=false` and `production_status=not_promoted` are authoritative.

## Main findings

1. Governed-stack admission is possible when model, sampling, context, Hermes, skill, finalizer, tools, and evidence are one immutable unit.
2. Skill-only changes produced directional improvement in tool sequence, fail-closed behavior, and timeout invocation; presentation fencing remains the observed R1 blocker.
3. Memory and routing can be specified as deterministic contracts before runtime work begins.
4. Hermes can classify and delegate, but a deterministic external dispatcher must prove the actual local profile, model digest, context, tools, and limits.
5. Raw protocol, native trajectories, tool traces, and immutable artifacts remain independent gates; finalizers cannot replace them.

## Open hypotheses and risks

- Skill v1.3 may remove fencing without losing the R1 semantic improvements.
- The memory skill must still prove correct classification, retrieval, consolidation, injection rejection, and parent-only writes at runtime.
- The routing skill must still prove exact lane selection, resolved profile/model evidence, fallback discipline, and failure preservation at runtime.
- No deterministic dispatcher implementation exists yet.
- No BENCH-3 memory or routing case has model-run evidence yet.
- Profiles are not filesystem sandboxes; filesystem and side-effect policy require separate enforcement.
- Concurrency remains unqualified; BENCH-3 deliberately freezes one child and depth one.
- Harness complexity across Windows, PowerShell, CRLF, paths, shells, composite actions, and artifacts requires hosted simulation before activation.
- External providers remain excluded.

## Current operating order

### Track A — complete S3A-R2

1. Implement the canonical 18-run canary workflow in a separate reviewed PR while the marker remains absent.
2. Bind exact stack, skills, cases, repetitions, fresh seeds, traces, VRAM, keep-awake behavior, and immutable artifacts.
3. Validate on hosted CI before any marker-only activation commit.
4. A pass permits only a later fresh-seed full-soak design; it does not adopt the skill or promote production.

### Track B — qualify memory and routing

1. Freeze a BENCH-3R runtime plan containing evaluator schema, synthetic stores, capability registry, performance ledger, dispatcher trace, governed stacks, repetitions, seeds, stop rules, and artifact layout.
2. Implement hosted simulations and deterministic validators first; keep runtime workflow and marker absent.
3. Add a bounded local canary workflow only in a separate reviewed PR.
4. Require separate explicit confirmation before any self-hosted marker or Ollama call.
5. Keep cases synthetic and side-effect-free until memory classification, route selection, resolved model evidence, failure preservation, and no-write boundaries pass consistently.
6. A BENCH-3R pass may authorize a later dispatcher-integration design. It does not authorize JarvisOS routing changes or production use.
7. Start BENCH-3B coding fixtures only after the memory/routing runtime contract is stable.

## Excluded evidence

- Original HO-ROUTE outputs from run `29225755398` are invalidated by the underspecified fixture.
- H3 attempts 11–13 and H4 run `29257990674` failed before model execution.
- Hermes canary runs `29263590189` and `29264163081` are infrastructure-invalid.
- S3A activation attempts before `29350762330` contribute no semantic evidence.
- S3A-R1 run `29363488845` failed source binding before capture.

`planned` means a bounded outline exists. It does not authorize unattended scope expansion, model execution, external calls, memory mutation, skill adoption, routing activation, or production promotion.
