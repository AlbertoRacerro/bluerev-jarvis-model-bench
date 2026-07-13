# BENCH-1 direct semantic closeout

Status: **complete**.

BENCH-1 now has evidence-gated direct local results for both approved synthetic capabilities:

- HO-STOP: 10 candidates × 3 repetitions, retained from run `29225755398`;
- HO-ROUTE: 10 candidates × 3 repetitions, repaired replay run `29232014623`;
- total accepted evidence: **60 runs**, **36 pass**, **24 fail**, **0 invalid**.

## Capability matrix

| # | Candidate | HO-STOP | HO-ROUTE | Passed both |
|---:|---|---:|---:|---:|
| 1 | `gemma4-12b-it-qat` | 3/3 | 3/3 | yes |
| 2 | `qwable-9b-fable5` | 0/3 | 3/3 | no |
| 3 | `qwythos-mythos-9b` | 3/3 | 3/3 | yes |
| 4 | `minicpm5-fable-1b-control` | 0/3 | 0/3 | no |
| 5 | `qwen3.6-fablevibes-14b-a3b` | 3/3 | 3/3 | yes |
| 6 | `gemma4-fable-agentic-12b` | 0/3 | 0/3 | no |
| 7 | `gemma4-fable-coder-12b` | 0/3 | 0/3 | no |
| 8 | `qwen3-8b` | 3/3 | 0/3 | no |
| 9 | `qwythos-hermes-64k` | 3/3 | 3/3 | yes |
| 10 | `qwythos-hermes-safe` | 3/3 | 3/3 | yes |

Five candidates passed all three repetitions on both cases:

- `gemma4-12b-it-qat`
- `qwythos-mythos-9b`
- `qwen3.6-fablevibes-14b-a3b`
- `qwythos-hermes-64k`
- `qwythos-hermes-safe`

They remain tied. BENCH-1 does not authorize an overall winner.

## Important asymmetry

- `qwable-9b-fable5` passed HO-ROUTE 3/3 but failed HO-STOP 0/3.
- `qwen3-8b` passed HO-STOP 3/3 but failed HO-ROUTE 0/3.

This is precisely why capability-specific routing evidence must remain separate rather than being collapsed into one score.

## Evidence boundary

The original 30 HO-ROUTE outputs from run `29225755398` are excluded: the old fixture did not make the expected route mechanically derivable. Only the HO-STOP half of that run is retained. HO-ROUTE is sourced exclusively from the explicit replay run `29232014623`.

All retained archives matched GitHub SHA-256 metadata. Checkout, plan, case, candidate identity, manifest, artifact hash and cleanup bindings passed. Execution remained local-only with no Hermes, JarvisOS, external providers or secrets.

## Closure decision

BENCH-1 direct semantic scope is closed. The next stage is BENCH-2 Hermes orchestrator isolation, but it requires a new immutable plan that freezes workers, tools, context, prompts and runtime conditions. No BENCH-2 model execution is authorized by this closeout.
