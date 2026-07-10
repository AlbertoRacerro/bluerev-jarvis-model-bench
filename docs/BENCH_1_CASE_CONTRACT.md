# BENCH-1 synthetic case contract

## Purpose

BENCH-1 defines deterministic synthetic orchestration cases before any comparative model scoring. A case is a self-contained fixture with an explicit success contract, negative assertions, and a bounded execution envelope.

This contract does not authorize model execution, external APIs, JarvisOS access, or changes to Hermes trusted skills.

## Required case fields

Each case must provide:

- `schema_version`: fixed to `bench.case.v1`;
- `case_id`: stable, unique identifier;
- `capability`: one capability ID from `docs/BENCHMARK_CONTRACT.md`;
- `title`: short human-readable name;
- `lane_eligibility`: allowed benchmark lanes;
- `input`: synthetic task content and supplied context;
- `execution_envelope`: local-only limits and permissions;
- `success_assertions`: deterministic conditions that must hold;
- `negative_assertions`: deterministic conditions that must not occur;
- `expected_stop_reason`: required when the correct behavior is clarification, refusal, reuse, or no-op;
- `fixture_refs`: repository-relative paths for any synthetic files;
- `validator_id`: deterministic validator name and version;
- `notes`: optional non-normative rationale.

Unknown fields are rejected in `bench.case.v1`. Missing required fields are invalid fixtures rather than skipped cases.

## Execution envelope

The execution envelope must explicitly define:

- `local_models_only: true`;
- `external_network_allowed: false`;
- `external_provider_allowed: false`;
- `jarvisos_access_allowed: false`;
- `max_model_calls`;
- `max_tool_calls`;
- `max_retries`;
- `max_parallel_workers`;
- `timeout_seconds`;
- `allowed_tools`;
- `writable_paths`.

A validator must fail closed when an envelope field is absent, malformed, or exceeded.

## Assertion rules

Success assertions must be mechanically testable. They may verify:

- required plan steps and ordering;
- selected local role or local candidate alias;
- exact tool choice and bounded arguments;
- emitted clarification or safe-stop reason;
- retry and escalation limits;
- preservation of supplied sensitivity and budget constraints;
- use of tool results in the final answer;
- required `FINAL:` extraction contract.

Negative assertions must cover the relevant failure modes, including:

- external-provider or network attempts;
- JarvisOS paths or identifiers;
- writes outside fixture-owned paths;
- secret-like values in output or artifacts;
- unnecessary model or tool calls;
- retry loops beyond the envelope;
- unsupported claims of success;
- silent acceptance of malformed tool results;
- model self-scoring treated as validator evidence.

Natural-language similarity, subjective quality judgments, and model self-assessment cannot be sole pass criteria.

## Initial battery coverage

The first battery must contain at least one positive and one adversarial or stop case for each of:

- `HO-PLAN`;
- `HO-ROUTE`;
- `HO-ESCALATE`;
- `HO-DELEGATE`;
- `HO-TOOLS`;
- `HO-RECOVER`;
- `HO-CRITIC`;
- `HO-BUDGET`;
- `HO-SENSITIVITY`;
- `HO-STOP`.

`HO-LEARN` remains fixture-only in BENCH-1: proposals may be evaluated, but nothing is promoted automatically.

## Fixture isolation

All files used by BENCH-1 must be synthetic and repository-owned. Fixtures must not contain copied personal data, credentials, private prompts, production files, or model-generated secrets. Cases that exercise sensitive-data handling use deterministic placeholders.

Each case runs in a fresh temporary workspace. The validator records created, modified, and deleted paths and fails the case if any path escapes the declared writable set.

## Determinism and repetitions

Case validation is deterministic even when model output is stochastic. Validator versions are recorded in run artifacts. Comparative evidence requires at least three repetitions per candidate/configuration; a single pass is only execution evidence.

A validator defect invalidates affected results until the validator is corrected and the cases are replayed.

## Promotion boundary

BENCH-1 outputs may identify fixture failures, validator defects, and candidate-specific behavior. They do not change JarvisOS, Hermes configuration, candidate mapping, routing, or trusted skills automatically.