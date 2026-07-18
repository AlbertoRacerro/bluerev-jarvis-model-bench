# Benchmark Status

This is the live roadmap for the benchmark repository.

Status vocabulary: `planned`, `blocked`, `ready`, `in_progress`, `in_review`, `merged`, `cancelled`.

| ID | Status | PR | Name | Dependencies | Evidence-backed state |
|---|---|---:|---|---|---|
| BENCH-0 | merged | #1 | Foundation and runner contract | — | Strict extraction, manifests, local inventory, self-hosted Windows boundaries, immutable artifacts, and local-only safety controls. |
| BENCH-1 | merged | #96 | Direct synthetic orchestration battery | BENCH-0 | 60 accepted direct runs across 10 candidates; 36 pass, 24 fail, 0 invalid; five candidates tied across HO-STOP and corrected HO-ROUTE. |
| H4 | merged | #104 | Hermes minimum 64K admission | H3 | All ten Lane 1 candidates attempted: 8 qualified, 1 CPU offload, 1 context mismatch. Hardware/runtime admission only. |
| BENCH-2 | merged | #134 | Stock-Hermes full matrix | H4 | 48/48 planned runs completed for the eight H4-qualified candidates. No candidate was admitted from the stock full matrix. |
| BENCH-2R/S1 | merged | #146 | Profile-and-skill diagnostic | BENCH-2 | 32 runs: 7 pass, 18 fail, 7 invalid infrastructure. No fixed candidate/arm passed both diagnostic cases; three candidates advanced. |
| BENCH-2R/S2 | merged | #150 | Held-out governed-stack admission | S1 | 36/36 infrastructure-valid. The governed `gemma4-12b-it-qat` stack passed 12/12 and was admitted for further shadow testing; no production promotion. |
| BENCH-2R/S3A | merged | #166 | Governed-stack shadow soak | S2 | 50/50 infrastructure-valid, but the stack failed negative controls. Skill v1.1 remained non-promoted. |
| BENCH-2R/S3A-R1 | merged | #175 | Skill v1.2 bounded repair | S3A | First batch completed 9/9 infrastructure-valid and was early-stopped as failed: semantic/tool behavior improved, but strict ledger-only JSON was 0/4 because outputs were Markdown-fenced. |
| BENCH-2R/S3A-R2 | merged | #177 | Skill v1.3 static design | S3A-R1 | Runner history audited; candidate v1.3 and an 18-run fresh-seed canary are statically designed. No canary workflow, R2 marker, Ollama call, skill adoption, or promotion exists yet. |
| BENCH-3 | planned | — | Tool and coding fixtures | Stable governed orchestrator | Windows/cmd, file edits, patching, deterministic tests, and bounded worker/critic/adjudicator loops. |
| BENCH-4 | blocked | — | Adaptive local model routing | Stable governed orchestrator, BENCH-3 | Route among eligible local stacks by capability, reliability, latency, and resource cost. External APIs remain out of scope. |
| BENCH-5 | planned | — | Controlled self-improvement | BENCH-4 | Evaluate memory, skill, routing, replay, overfitting, and promotion boundaries. |

## Current operating state

- Current audit/design merge: `b4c28117496b075b9b1b42b93d96277c910e5871` from PR #177.
- Production status: **`not_promoted`**.
- The admitted unit is a governed stack, not a standalone checkpoint.
- S3A and S3A-R1 markers are disabled.
- No S3A-R2 execution marker exists.
- No S3A-R2 self-hosted canary workflow exists.
- No current merge authorizes Ollama, the Windows self-hosted runner, external providers, model-weight changes, skill replacement, routing changes, or production promotion.
- The next allowed execution work is a separately reviewed, canonical 18-run S3A-R2 canary implementation followed by a separate marker-only activation.

## Runtime qualification baseline

### H4 Hermes minimum 64K

- Workflow run: `29260032005`, attempt `1`.
- Trusted execution SHA: `a2926cc93abb1a64874352c4508e8c97b0b6007f`.
- Candidate set: all ten H3-qualified Lane 1 models, regardless of BENCH-1 direct outcomes.
- Result: **8 `qualified_64k`, 1 `cpu_offload`, 1 `context_mismatch`, 0 `load_failed`**.
- All five archives matched GitHub SHA-256 metadata; internal manifests, source bindings, candidate identity, cleanup, context observation, and local-only boundaries passed.
- H4 is hardware/runtime admission only and does not rank semantic quality.

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

- `qwen3.6-fablevibes-14b-a3b`: actual context 65536, but GPU residency below the reviewed no-CPU-offload threshold.
- `qwen3-8b`: actual loaded context 40960, below Hermes Agent 0.18.2's 64000-token minimum.

Detailed evidence: `reports/H4-HERMES-MINIMUM-64K/`.

### H3 primary 32K

- Workflow run: `29106127334`, valid attempts `14`–`18`.
- Trusted execution SHA: `202214c45a9a6952600bbd2d621697fcf349db25`.
- Result: **10/10 candidates fully resident in VRAM at an actual 32768-token context**.
- H3 is retained as a lower-context runtime baseline, not semantic ranking.

## BENCH-1 direct semantic evidence

### HO-STOP

- Workflow run: `29225755398`, attempt `1`.
- Retained case: `ho-stop-reuse-explicit-002`.
- Accepted evidence: **30 runs — 18 pass, 12 fail, 0 invalid**.

### HO-ROUTE explicit replay

- Workflow run: `29232014623`, attempt `1`.
- Case: `ho-route-local-coder-explicit-002`.
- Accepted evidence: **30 runs — 18 pass, 12 fail, 0 invalid**.

### Combined capability matrix

- Accepted evidence: **60 runs — 36 pass, 24 fail, 0 invalid**.
- Five candidates passed all repetitions on both capabilities: `gemma4-12b-it-qat`, `qwythos-mythos-9b`, `qwen3.6-fablevibes-14b-a3b`, `qwythos-hermes-64k`, and `qwythos-hermes-safe`.
- They remain tied. BENCH-1 declares no aggregate score or global winner.
- BENCH-1 outcomes are post-hoc explanatory evidence and are not a Hermes admission gate.

Detailed evidence: `reports/BENCH-1-HO-ROUTE-EXPLICIT-REPLAY/` and `reports/BENCH-1-DIRECT-SEMANTIC-CLOSEOUT/`.

## BENCH-2 and BENCH-2R progression

### BENCH-2 stock-Hermes full matrix

- Trusted full-matrix run: `29309289661`.
- Matrix: 8 H4-qualified candidates × 2 cases × 3 repetitions = **48 runs**.
- All planned runs completed and were closed with attributable evidence.
- No candidate was admitted as a stock-Hermes orchestrator.
- Capability-specific outcomes remain authoritative; no global composite score is permitted.

### S1 profile-and-skill diagnostic

- Matrix: 8 candidates × 2 cases × 2 arms = **32 runs**.
- Result: **7 pass, 18 fail, 7 invalid infrastructure**.
- No fixed candidate/arm passed both diagnostic cases.
- Advanced to held-out S2: `gemma4-12b-it-qat`, `qwythos-mythos-9b`, and `qwythos-hermes-64k`.
- S1 was diagnostic and admitted no stack.

### S2 held-out admission

- Workflow run: `29335974597`, attempt `1`.
- Matrix: 3 candidates × 4 held-out cases × 3 seeds = **36 runs**.
- Infrastructure: **36/36 valid**.
- `gemma4-12b-it-qat` governed stack: **12/12 admission**, **12/12 raw orchestration**, **12/12 finalized output**, **3/12 raw-presentation**.
- `qwythos-mythos-9b`: **9/12 admission**.
- `qwythos-hermes-64k`: **10/12 admission**.
- The admitted object includes the exact model digest and sampling profile, 65536 context, Hermes Agent 0.18.2 at the pinned commit, skill v1.1, deterministic fail-closed finalizer, reviewed tools/budgets, native trajectories, and wire traces.
- Admission allowed only later shadow testing. It did not authorize production.

### S3A governed-stack shadow soak

- Workflow run: `29350762330`, attempt `1`.
- Execution SHA: `43fdd22252d89c1b83b5190e6ef41dbf0bfac625`.
- Infrastructure: **50/50 valid**, with all five main and five preflight artifacts present and verified.
- Nominal deterministic finalization: **30/30**.
- Long-context measured-token gate: **10/10**.
- Full shadow pass: **31/50**.
- Negative-control shadow pass: **1/20**.
- Negative outputs used the wrong ledger shape in **19/20** runs.
- The timeout tool was not actually invoked in **3/10** timeout runs.
- Conclusion: a real semantic failure, not runner unavailability. Skill v1.1 and production remained unchanged.

### S3A-R1 bounded repair with skill v1.2

- Authoritative workflow run: `29364133435`, attempt `2`.
- Executed first batch: **9/9 infrastructure-valid**.
- Repair negative tool sequence: **4/4 exact**.
- Repair negative fail-closed behavior: **4/4**.
- Real timeout-tool invocation: **2/2**.
- Nominal sentinel: **1/1**.
- Strict negative ledger-only output: **0/4** because all four semantically correct action objects were wrapped in Markdown JSON fences.
- After batch 0, the best possible final ledger score was 8/12 against a frozen 12/12 gate; batches 1 and 2 could not restore acceptance and were not run.
- Skill v1.2 was not adopted. Production remained `not_promoted`.

### Windows runner audit

- Audited jobs with full observer or Actions metadata: **38**.
- Classification: **26 `A+D`, 3 `A+E`, 4 `A+pass`, 5 `B`, 0 `C`**.
- `A+D`: runner assigned; failure was workflow/preflight/infrastructure after assignment.
- `A+E`: valid preflight/capture/artifact followed by a semantic gate failure.
- `B`: cancelled before runner assignment and before steps.
- `C`: runner started but Ollama unavailable; no such job was found.
- Rerunnable historical jobs: **0**. The five class-B jobs belong either to superseded invalid activations or to mathematically unnecessary R1 batches.
- Residual gap: attempt 1 of run `29364133435` retains a preflight artifact but no persisted attempt-specific job snapshot. Attempt 2 is authoritative; the gap does not change the decision.

Detailed evidence: `reports/BENCH-2R-HERMES-S3A-RUNNER-AUDIT/`.

### S3A-R2 skill v1.3 static design

- Candidate skill version: `1.3.0`; v1.2 remains the paired observational control.
- Hypothesis: the remaining R1 failure was caused by Markdown-fence/example mimicry rather than by tool or ledger semantics.
- Candidate rule: byte-exact raw JSON, first character `{`, final character `}`, zero backticks, no fence/prefix/suffix, observed real tool response before a positive-call ledger, and exact terminal `stop`.
- Governed model/runtime stack is pinned to the S3A-R1 stack.
- Fresh canary seeds: `849690` and `603823`; prior S3A/R1 seeds are forbidden.
- Future canary arithmetic: 2 negative cases × 2 seeds × 2 arms × 2 repetitions = **16 paired negative runs**, plus 2 candidate nominal sentinels = **18 total runs**.
- Static validation covers exact stack, exact case order, exact repetitions, derived counts, skill blobs, seed reuse, marker state, forbidden canary workflow/marker paths, and absence of self-hosted execution.
- Regression suite: **15 tests** on the merged design head.
- This is design evidence only. v1.3 has not executed against Ollama or Hermes.

## Most promising findings

1. **Governed-stack admission is possible.** Gemma 4 reached 12/12 held-out S2 admission when model, sampling, context, Hermes, skill, finalizer, tools, and evidence boundaries were treated as one immutable unit.
2. **Skill-only changes produced directional causal improvement.** From S3A to R1, the repair moved the output field to `actions`, restored all four negative tool sequences, preserved fail-closed behavior, and produced both required timeout invocations. The remaining observed blocker narrowed to presentation fencing.
3. **The harness now distinguishes model failure from infrastructure failure.** Invalid source bindings, shells, sleep/disconnection, artifact paths, and workflow cancellation were not silently converted into semantic failures.
4. **Deterministic finalization is useful but can hide raw-output weakness.** S2 finalized output was 12/12 while raw presentation was only 3/12; later fencing failures confirm that raw presentation must remain an independent gate.
5. **Fresh-seed paired experiments are more informative than opportunistic reruns.** The R1 early-stop prevented 18 unnecessary runs, and R2 preserves a control arm while changing only the skill.

## Open hypotheses

- Removing every backtick and fenced example from v1.3 will eliminate Markdown fencing on fresh seeds.
- v1.3 will preserve the tool-sequence and real timeout-invocation improvements observed with v1.2.
- The S2-admitted Gemma governed stack can pass negative controls consistently once the output-boundary defect is removed.
- The v1.2 improvement is generic orchestration learning rather than overfitting to the two negative cases.
- Strict raw-output conformance should become a stronger nominal admission requirement rather than remaining mostly observational behind the finalizer.
- Multi-tool orchestration and cancellation/resume require a separate S3B design and likely a finalizer v2; current S3A evidence does not answer those questions.

## Primary risks and unresolved gaps

- **No runtime evidence for v1.3.** Static checks prove only that the intended delta is encoded and bounded.
- **Small repair sample.** R1 executed one fresh-seed batch; 4 negative candidate runs are enough for deterministic early-stop but not broad generalization.
- **Harness complexity.** The history contains repeated Windows/Actions defects involving CRLF, PowerShell policy, sleep, concurrency, path filtering, artifact directories, and source binding. Pre-activation simulation must remain a first-class gate.
- **Finalizer masking.** A finalized pass is not evidence that the model emitted the required raw protocol.
- **No production-ready orchestrator.** S2 admission and later repair progress do not equal production promotion.
- **No evidence for S3B.** Multi-tool chains, cancellation, resume, and broader coding workflows remain untested.

## Current operating order

1. Implement the canonical S3A-R2 canary workflow in a separate reviewed PR while keeping the future R2 marker disabled.
2. Bind that workflow to the exact merged design, governed stack, skill blobs, cases, repetitions, fresh seeds, serial batches, native trajectories, wire/tool traces, full-VRAM requirement, keep-awake behavior, and immutable artifacts.
3. Validate the workflow on hosted CI, including Windows-specific contract simulations, before adding any activation commit.
4. Activate only through a separate marker-only commit with the reviewed message prefix and with the Windows runner confirmed ready.
5. Execute at most 18 runs in two serial seed batches. Early-stop after the first candidate backtick/fence or any candidate negative-gate failure.
6. Require candidate v1.3 to achieve 8/8 strict raw negative outputs, 8/8 exact tool sequences, 8/8 fail-closed passes, 4/4 real timeout-tool invocations, 2/2 nominal sentinels, zero retries, zero forbidden tools, and all infrastructure-valid.
7. A canary pass permits only a later fresh-seed full-soak design. It does not adopt the skill or promote production.
8. Design S3B separately for multi-tool and cancellation/resume behavior after the one-tool contract is stable.

## Excluded or non-authoritative evidence

- The original HO-ROUTE outputs from run `29225755398` are invalidated by the underspecified route fixture and are not model failures.
- H3 attempts 11–13 failed prerequisite/source-binding checks before model execution.
- H4 run `29257990674` failed before model execution because Windows PowerShell scripts were blocked.
- Hermes canary runs `29263590189` and `29264163081` are infrastructure-invalid and contribute no model-quality evidence.
- S3A activation attempts preceding `29350762330` failed preflight/workflow boundaries and contribute no semantic evidence.
- S3A-R1 run `29363488845` failed source binding before capture and contributes no repair-model evidence.
- Recovery scans found no residual R1 workspace evidence beyond the already uploaded authoritative artifact.

`planned` means an outline exists. It is not an implementation instruction and does not authorize unattended expansion of scope, model execution, external calls, skill adoption, or production promotion.
