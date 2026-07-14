# BENCH-2R Hermes optimization design

## Objective

Find at least one of the eight H4-qualified Lane 1 models that can serve as a bounded Hermes orchestrator after model-specific optimization. Stock BENCH-2 remains frozen as baseline evidence; this slice does not rerun it and does not modify model weights.

## Corrections to the original setup

1. Sampling is model-specific. Temperature zero is not a universal requirement and is forbidden as a blanket policy.
2. Each profile is bound to the exact BENCH-2 candidate tag and digest. Newer or differently quantized variants cannot silently replace a candidate.
3. Hermes `max_turns` is derived from each case's `max_model_calls`, rather than fixed at four.
4. The global 256-token output cap is removed. Every candidate receives a documented or explicitly bounded output allowance.
5. Native Hermes trajectory capture is required.
6. Admission requires wire-level request tracing before the execution marker may be enabled.

## Treatment arms

- `profile_only`: documented candidate-specific runtime profile.
- `profile_plus_skill`: the same profile with the generic `bounded-tool-orchestration` skill explicitly expanded through Hermes' pinned skill machinery.

The skill contains no values, tool names, or expected answers from the frozen benchmark. It teaches only transferable invariants: use supplied results, select only registered tools, minimize calls, recognize terminal state, satisfy exact schemas, and stop.

## Candidate priority

The initial priority is diagnostic rather than exclusionary:

1. `gemma4-12b-it-qat`: strongest BENCH-2 tool-use result; HO-STOP appears dominated by excess continuation.
2. `qwythos-mythos-9b`: partial success on both capabilities; likely sensitive to exact finalization and stop guidance.
3. `gemma4-fable-coder-12b`: correct tool behavior appeared in several failed runs, but final formatting leaked prose or wrappers.
4. `qwable-9b-fable5`: tool choice was often plausible, with output typing and unnecessary continuation as dominant symptoms.
5. Remaining models stay in preflight. MiniCPM is protocol-gated before semantic attribution.

## Gates

- Design validation is hosted-only and cannot invoke Ollama or Hermes runtime work.
- The execution marker remains disabled.
- A separate reviewed activation commit is required for preflight.
- No model may enter admission without valid protocol traces.
- No candidate may be promoted without unseen equivalent holdouts and variable tool registries.
