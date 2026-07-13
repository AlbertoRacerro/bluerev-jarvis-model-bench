# Benchmark Status

This is the live roadmap for the benchmark repository.

Status vocabulary: `planned`, `blocked`, `ready`, `in_progress`, `in_review`, `merged`, `cancelled`.

| ID | Status | PR | Name | Dependencies | Scope |
|---|---|---:|---|---|---|
| BENCH-0 | merged | #1 | Foundation and runner contract | — | Strict extraction, manifests, local inventory, self-hosted Windows workflows, immutable artifacts, and safety boundaries. |
| BENCH-1 | merged | #96 | Direct synthetic orchestration battery | BENCH-0 | Evidence-gated local direct results for explicit HO-STOP and HO-ROUTE contracts: 60 accepted runs across 10 candidates. |
| BENCH-2 | planned | — | Hermes orchestrator isolation | BENCH-1 | Hold workers, tools, prompts, context, and runtime fixed while varying only the local model driving Hermes. |
| BENCH-3 | planned | — | Tool and coding fixtures | BENCH-2 | Windows/PowerShell, file edits, patching, deterministic tests, and bounded worker/critic/adjudicator loops. |
| BENCH-4 | blocked | — | Adaptive local model routing | BENCH-2, BENCH-3 | Route among eligible local models by capability, reliability, latency, and resource cost. External APIs remain out of scope. |
| BENCH-5 | planned | — | Controlled self-improvement | BENCH-4 | Evaluate memory, skill, routing, replay, overfitting, and promotion boundaries. |

## Latest trusted runtime qualification

- H3 workflow run: `29106127334`, valid attempts `14`–`18`.
- Trusted execution SHA: `202214c45a9a6952600bbd2d621697fcf349db25`.
- Result: **10/10 candidates fully resident in VRAM at an actual 32768-token context**.
- All five archives matched GitHub SHA-256 metadata; checkout, manifest, cleanup, context length, candidate identity, and local-only boundaries passed.
- H3 is hardware/runtime qualification only. It is not semantic ranking.

## BENCH-1 trusted semantic evidence

### HO-STOP

- Workflow run: `29225755398`, attempt `1`.
- Trusted SHA: `5d527a10e7e49140647a7475b2aebc35c4177078`.
- Retained case: `ho-stop-reuse-explicit-002`.
- Accepted evidence: **30 runs — 18 pass, 12 fail, 0 invalid**.
- The HO-ROUTE half of this original campaign is excluded because its fixture did not make the expected route mechanically derivable.

### HO-ROUTE explicit replay

- Workflow run: `29232014623`, attempt `1`.
- Trusted SHA: `057c33ccbcb40acff3f840f642b5165f396df7f8`.
- Case: `ho-route-local-coder-explicit-002`.
- Accepted evidence: **30 runs — 18 pass, 12 fail, 0 invalid**.
- All five jobs completed with capture and enforce success. Main and enforce archives matched GitHub digests; per-run manifests, serialized case snapshots, checkout bindings, and cleanup attestations passed.
- The replay workflow is manual-only and the completed one-shot marker is disabled. A future replay requires a separately reviewed marker change and explicit dispatch.

### Combined capability matrix

- Accepted evidence: **60 runs — 36 pass, 24 fail, 0 invalid**.
- Five candidates passed all three repetitions on both capabilities:
  - `gemma4-12b-it-qat`
  - `qwythos-mythos-9b`
  - `qwen3.6-fablevibes-14b-a3b`
  - `qwythos-hermes-64k`
  - `qwythos-hermes-safe`
- They remain tied. BENCH-1 declares no aggregate score or global winner.
- Capability-specific asymmetry is retained: `qwable-9b-fable5` passed HO-ROUTE but failed HO-STOP; `qwen3-8b` passed HO-STOP but failed HO-ROUTE.

Detailed evidence is stored in:

- `reports/BENCH-1-HO-ROUTE-EXPLICIT-REPLAY/`
- `reports/BENCH-1-DIRECT-SEMANTIC-CLOSEOUT/`

## Excluded evidence

- The original 30 HO-ROUTE outputs from run `29225755398` remain invalidated by the underspecified route fixture.
- Run `29231060170` failed before model execution because the replay entrypoint lacked the `src` bootstrap.
- Run `29231447924` produced six outputs, but its evidence gate was red because the manifest validator was patched in the wrong module; those outputs are not counted.

## Current operating order

1. Prepare a separately reviewed immutable BENCH-2 plan; do not execute Hermes models yet.
2. Freeze worker pool, tools, prompt, context, generation parameters, timeout, cleanup, and evidence bindings before any BENCH-2 run.
3. Preserve capability-specific outcomes and ties; do not collapse them into an unsupported global score.
4. Keep the BENCH-1 replay marker disabled unless a new, explicit replay plan is reviewed and authorized.

`planned` means an outline exists. It is not an implementation instruction and does not authorize unattended expansion of scope.
