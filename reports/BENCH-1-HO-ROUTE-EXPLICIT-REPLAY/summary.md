# BENCH-1 HO-ROUTE explicit replay

Status: **complete and evidence-gated**.

- Workflow run: `29232014623`, attempt `1`
- Trusted branch and SHA: `main` at `057c33ccbcb40acff3f840f642b5165f396df7f8`
- Plan SHA-256: `b4853987a8aa3a2d3c6ed0b334a6e98c04871b3725cb2931fbd69dd08f716166`
- Case: `ho-route-local-coder-explicit-002`
- Canonical case SHA-256: `122050ceb6d5b198a079142e131829f0cafe5520eff38bcef4bffb80c5dfd706`
- Execution: 10 local candidates × 3 repetitions = **30 runs**
- Result: **18 passed, 12 failed, 0 invalid**
- Candidate-level result: **6 passed 3/3; 4 failed 3/3**

## Candidate outcomes

| # | Candidate | Outcome | Median total s | Eval tokens | Failure mode |
|---:|---|---:|---:|---:|---|
| 1 | `gemma4-12b-it-qat` | 3/3 pass | 19.309 | 537 | — |
| 2 | `qwable-9b-fable5` | 3/3 pass | 13.878 | 378 | — |
| 3 | `qwythos-mythos-9b` | 3/3 pass | 15.514 | 516 | — |
| 4 | `minicpm5-fable-1b-control` | 0/3 pass | 5.081 | 28 | missing_final_marker |
| 5 | `qwen3.6-fablevibes-14b-a3b` | 3/3 pass | 12.752 | 313 | — |
| 6 | `gemma4-fable-agentic-12b` | 0/3 pass | 13.455 | 162 | tool_call_without_final |
| 7 | `gemma4-fable-coder-12b` | 0/3 pass | 13.582 | 196 | nonparseable_final_marker |
| 8 | `qwen3-8b` | 0/3 pass | 11.139 | 301 | incomplete_action_sequence |
| 9 | `qwythos-hermes-64k` | 3/3 pass | 15.678 | 520 | — |
| 10 | `qwythos-hermes-safe` | 3/3 pass | 15.757 | 508 | — |

The six candidates with `3/3 pass` are tied for this case. Duration is diagnostic only and is not a semantic tie-breaker.

## Deterministic failure modes

- `minicpm5-fable-1b-control`: returned a generic self-description and no `FINAL:` marker.
- `gemma4-fable-agentic-12b`: reasoned to `local_coder`, then emitted a model-specific route tool call without a parseable final submission.
- `gemma4-fable-coder-12b`: reasoned to the correct route and emitted the correct JSON, but prefixed `FINAL:` with a channel token; the strict extractor therefore rejected it.
- `qwen3-8b`: returned `selected_route=local_coder`, but omitted the required terminal `stop` action.

These are contract failures under the published candidate-visible response contract. They are not infrastructure failures.

## Evidence gate

All five matrix jobs completed successfully. Capture and enforce passed for every batch. The five main archives and five enforce archives matched GitHub SHA-256 metadata byte-for-byte. Independent verification found:

- 30 unique run IDs and exactly three repetitions per candidate;
- clean checkout binding to the same `main` SHA;
- fixed plan, registry, H3 source, case identity and serialized case snapshot bindings;
- complete campaign and per-run manifests with matching hashes and sizes;
- cleanup attested before and after every run;
- no external providers, secrets, Hermes execution or JarvisOS access.

## Excluded evidence

- The 30 HO-ROUTE results in run `29225755398` remain invalidated because the original route fixture did not make the expected choice mechanically derivable.
- Run `29231060170` failed before model execution because the replay entrypoint lacked the `src` bootstrap.
- Run `29231447924` produced six outputs, but its evidence gate was red because the manifest validator was patched in the wrong module. Those outputs are not counted.

## Interpretation boundary

This establishes repeatable evidence for one synthetic direct HO-ROUTE case. It is not a general model ranking, does not exercise Hermes orchestration or tools, and does not measure coding quality. The valid 30-run HO-STOP evidence from the earlier campaign remains separate; combining the two capabilities supports BENCH-1 closure but not a global winner.
