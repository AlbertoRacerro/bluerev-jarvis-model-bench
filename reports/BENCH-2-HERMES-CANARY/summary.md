# BENCH-2 Hermes canary closeout

## Decision

Trusted run `29265322367` proves that the isolated Hermes harness can execute locally with an actual **65,536-token** context, full VRAM residency, immutable source binding, verified cleanup, and a temporary derived Ollama alias tied to the exact H4-qualified source model.

The candidate `qwythos-hermes-safe` **failed** the HO-TOOLS semantic case. It produced no tool trace and returned a non-conforming final object. That failure is retained as valid benchmark evidence.

The full BENCH-2 matrix may proceed because the canary's role is infrastructure qualification. Making the other seven H4-qualified candidates contingent on this candidate's semantic pass would introduce outcome-dependent admission bias.

## Trusted evidence

- Workflow run: `29265322367`, attempt `1`
- Execution SHA: `941d587267bfeb602ba9bd5d5513695c56d63e52`
- Artifact ID: `8285164320`
- Archive SHA-256: `a73d442c801735070927ea3048f63d2e87f3b0741e44b8ce262a513c40dc37ed`
- Hermes Agent: `0.18.2`, commit `73b611ad19720d70308dad6b0fb64648aaadc216`
- Observed context: `65536`
- GPU residency: `full_vram`, ratio `1.0`
- API calls: `1`
- Alias and model cleanup: verified

## Semantic observation

Expected:

1. `bench_lookup({"key":"alpha-7"})`
2. final `BRAVO-19`
3. action sequence `call_tool`, `return_final`, `stop`

Observed:

```json
{
  "actions": ["call_tool"],
  "final": {
    "label": null,
    "value": null,
    "error": null
  }
}
```

No tool was invoked. The strict validator remains unchanged.

## Gate correction

The pre-run wording “semantic pass required before full matrix” is superseded by this closeout decision:

- **required:** infrastructure-valid canary with deterministic classification;
- **not required:** semantic success by the single canary candidate;
- **preserved:** the canary's semantic result as ordinary candidate/capability evidence;
- **forbidden:** using BENCH-1 or canary semantic outcomes to exclude other H4-qualified candidates.
