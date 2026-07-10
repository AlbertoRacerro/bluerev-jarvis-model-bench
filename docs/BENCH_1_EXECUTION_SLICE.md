# BENCH-1 first executable fixture slice

This slice executes deterministic fixture validation only. It does not call Ollama, Hermes,
tools, external APIs, or JarvisOS.

## Included cases

- `ho-stop-reuse-001`: reuse a supplied verified result without additional work.
- `ho-route-local-coder-001`: select the smallest eligible local route for a bounded Python
  patch.

These cases are deliberately simple. Their purpose is to prove that the evaluator rejects
false passes before model behavior is introduced.

## Candidate visibility boundary

`build_candidate_payload` exposes only:

- case identity and capability;
- prompt and inputs;
- allowed and forbidden actions;
- call and retry limits.

The evaluator-only `expected` oracle, positive assertions, negative assertions, and required
artifact list are not exposed. The returned payload is deep-copied so candidate-side mutation
cannot alter the source case.

## Trace authority

A `bench.trace.v1` trace contains only ordered events:

```json
{
  "schema_version": "bench.trace.v1",
  "case_id": "ho-stop-reuse-001",
  "events": [
    {"index": 1, "action_id": "return_supplied_result", "details": {}},
    {"index": 2, "action_id": "stop", "details": {}}
  ]
}
```

Model-call, tool-call, and retry counts are derived from events. Aggregate counters supplied by
a candidate are unsupported fields and therefore contract failures.

## Failure semantics

Malformed case data, traces, or extracted outputs raise `ContractError`. A well-formed but wrong
submission returns `bench.validator-result.v1` with `passed=false` and individual failed checks.

For the two initial fixtures, output objects and action sequences are exact. Correct key values
with extra output fields, duplicate actions, forbidden actions, external-provider attempts, or
limit violations do not pass.

## Remaining boundary

This slice does not yet execute a local model and does not create the five run artifacts. The
next slice may wire bounded local-model execution only after these fixtures and evaluator tests
pass on trusted `main` and the resulting preflight artifact remains scoring-ready.
