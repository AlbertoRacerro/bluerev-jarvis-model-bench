# BENCH-1 synthetic case contract

`bench.case.v1` describes one deterministic orchestration fixture. It validates case data only. It does not call Ollama, Hermes, tools, external APIs, or JarvisOS.

## Required fields

- `schema_version`: exactly `bench.case.v1`.
- `case_id`: canonical kebab-case and prefixed by the lower-case capability, for example `ho-stop-reuse-001`.
- `capability`: one identifier from the benchmark capability vocabulary.
- `prompt`: the exact prompt presented to the evaluated lane.
- `inputs`: non-empty JSON-compatible fixture inputs.
- `expected`: non-empty JSON-compatible deterministic oracle data.
- `allowed_actions`: non-empty allowlisted action identifiers.
- `forbidden_actions`: non-empty allowlisted action identifiers.
- `success_assertions`: non-empty allowlisted positive assertion identifiers.
- `negative_assertions`: non-empty allowlisted negative assertion identifiers.
- `limits`: exact non-negative integer limits for model calls, tool calls, and retries.
- `required_artifacts`: exactly the raw output, extracted output, trace, validator result, and environment fingerprint artifact identifiers.

Unknown fields are rejected. Arrays must be JSON arrays, must not contain duplicates, and allowed and forbidden actions must be disjoint.

## Global boundaries

The following actions may appear in `forbidden_actions` but can never appear in `allowed_actions`:

- `call_external_provider`;
- `modify_jarvisos`;
- `promote_learning`;
- `write_external_state`.

This keeps the initial battery local-only and prevents a synthetic fixture from weakening repository invariants.

## Limit consistency

A case is invalid when it allows an action while setting the corresponding limit to zero:

- `call_local_model` with `max_model_calls = 0`;
- `call_tool` with `max_tool_calls = 0`;
- `retry` with `max_retries = 0`.

Limits are upper bounds. A positive limit does not require the action to occur.

## Evidence separation

Every future execution of a valid case must preserve these artifacts separately:

1. `raw_output`;
2. `extracted_output`;
3. `trace`;
4. `validator_result`;
5. `environment_fingerprint`.

A valid case contract is not evidence that a model passed the case. Execution and scoring remain separate later slices.
