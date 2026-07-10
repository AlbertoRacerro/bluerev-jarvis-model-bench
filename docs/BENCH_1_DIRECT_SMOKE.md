# BENCH-1 bounded direct-model smoke

This slice proves the local execution and evidence pipeline with deliberately small runs. It is not comparative evidence and does not involve Hermes.

## Current fixed scope

- Lane: `direct`.
- Candidate: `qwythos-hermes-safe`.
- Case: `ho-stop-reuse-explicit-002`.
- Repetitions in the current run: `1`.
- Ollama endpoint: exactly `http://127.0.0.1:11434/api/generate`.
- Temperature: `0`.
- Seed: `4242`.
- Context limit: `4096`.
- Generation limit: `1024` tokens.
- Request timeout: `180` seconds.
- `keep_alive`: `0` so the smoke run does not leave the model resident.

The candidate and case are constants in the trusted job driver. Workflow inputs cannot select an arbitrary model, path, endpoint, or fixture.

## First observed control run

Trusted-main run `29103303992`, attempt `1`, executed commit `784ea2327dd444225c1319ef240db4a8c3cd388c` with candidate `minicpm5-fable-1b-control`.

- Artifact: `direct-smoke-29103303992-1`.
- Artifact digest: `sha256:56497d28e33b6853be65bf29f28aa94b5b021ce77e389cd58fb4e6cc8adb505c`.
- Deterministic tests: `73` passed.
- Infrastructure exit code: `0`.
- Execution completed: `true`.
- Candidate passed: `false`.
- Failure: missing required `FINAL:` marker.
- Raw response: a generic model self-description unrelated to the supplied task.
- Manifest SHA-256: `bae7e3a3d77d27a12c507fee433f3502bcffa00c34d7b38a0981d7cf8201b407`.

This is preliminary pipeline evidence only. It establishes that the validator rejected a non-responsive answer without confusing candidate failure with infrastructure failure.

## First Qwythos-safe run: invalid due to truncation

Trusted-main run `29103995266`, attempt `1`, executed commit `6fafcee357bde1e375924e428bff3b703daf7d27` with candidate `qwythos-hermes-safe`.

- Artifact: `direct-smoke-29103995266-1`.
- Artifact digest: `sha256:dcf7ec4841869119ce6c577c7f0c513bec063e1d20a60545e47632da9ae0aa3e`.
- Deterministic tests: `75` passed.
- Infrastructure exit code: `0`.
- Execution completed: `true`.
- Ollama `done_reason`: `length`.
- Ollama `eval_count`: `256`, equal to the configured generation limit.
- Candidate result: invalid/inconclusive, not a semantic failure.
- Prior harness representation: `candidate_passed=false` because the output lacked `FINAL:`.
- Correct interpretation: the benchmark truncated the candidate before a complete answer was possible.
- Manifest SHA-256: `b8881d0591d29899476bbe18fc28ec6140f81e963ff0281132a3b7cee75e0ce1`.

The run remains immutable evidence of a benchmark defect. It must not be counted as a Qwythos failure or used in any comparison.

## Second Qwythos-safe run: invalidated by case under-specification

Trusted-main run `29104571461`, attempt `1`, executed commit `50fc3b3c7b88c715c5f60b8538b6c8955ca99b1d` with candidate `qwythos-hermes-safe`.

- Artifact: `direct-smoke-29104571461-1`.
- Artifact digest: `sha256:4af28ed332dd6f26551c33c0e7ddd3fd2c0a9f4a700b3ed909667ae812f88e74`.
- Deterministic tests: `81` passed.
- Infrastructure exit code: `0`.
- Execution completed: `true`.
- Ollama `done_reason`: `stop`.
- Ollama `eval_count`: `399`, below the configured generation limit of `1024`.
- Harness result: `failed` because Qwythos returned output field `supplied_result` and omitted terminal action `stop`.
- Case defect: the candidate-visible task did not disclose output field `final` or require the exact action sequence, while evaluator-only `expected` required both.
- Correct interpretation: invalidated by an underspecified case, not a Qwythos semantic failure.
- Manifest SHA-256: `8eeaa46e7a1b293fe4ef237403af7679451ce2bd91d2d9ef92c767ac0e065200`.

The run remains immutable evidence of a fixture-design defect. It must not be counted in model capability or reliability statistics.

## Candidate-visible response contract

The current fixture `ho-stop-reuse-explicit-002` exposes the exact response shape through `inputs.response_contract`:

```json
{
  "output_field": "final",
  "required_actions": ["return_supplied_result", "stop"]
}
```

Before a model call, the harness verifies that evaluator-only `expected` is exactly derivable from this visible contract and `inputs.supplied_result`. A mismatch is an infrastructure/fixture error, not a candidate result.

Evaluator-only fields such as `expected`, assertions, and required artifact names remain hidden. Only the requirements needed to construct a valid response are candidate-visible.

## Preconditions

The workflow runs only after all deterministic tests pass and a fresh preflight reports:

- `runner_ready=true`;
- `scoring_ready=true`;
- `local_only=true`;
- the exact candidate tag and digest present in the Ollama inventory;
- the pinned clean Hermes state still recorded, even though Hermes is not called by this lane.

## Candidate output

The model must return one final payload:

```text
FINAL: {"output":{...},"actions":["action_id",...]}
```

Duplicate JSON keys, missing fields, extra fields, malformed actions, and missing `FINAL:` markers are candidate failures only when generation completed without truncation and the candidate-visible response contract was valid.

## Evidence

Every completed v3 execution preserves separate files for:

1. full evaluator-only case definition;
2. candidate payload;
3. exact prompt;
4. raw Ollama response envelope;
5. raw model output;
6. extracted output or extraction failure envelope;
7. trace or trace-capture failure envelope;
8. deterministic validator result;
9. environment fingerprint;
10. manifest with SHA-256 references;
11. execution summary.

`case_definition.json` is included in the manifest and its SHA-256 is copied into the environment fingerprint and job summary. The infrastructure gate fails when that digest is missing or malformed.

The run directory is unique per GitHub run and attempt. An existing directory is never overwritten.

## Gate semantics

The result vocabulary is:

- `passed`: complete generation and all deterministic assertions passed;
- `failed`: complete generation but the response or trace violated a fully candidate-visible contract;
- `invalid`: the benchmark could not obtain a complete or validly specified candidate result, including `done_reason="length"` or a fixture contract defect.

A failed or invalid candidate result does not fail the infrastructure workflow. Tests, preflight, identity binding, local execution, evidence preservation, hidden-oracle mismatch, or an unknown result state do fail the workflow.

## Network and safety boundary

- External provider environment variables are removed from the job process.
- Proxy environment variables are removed and the HTTP client uses an empty proxy configuration.
- Only an IP-literal loopback HTTP endpoint with the exact `/api/generate` path is accepted.
- Redirects, credentials in URLs, query strings, and fragments are rejected.
- Prompt and response sizes are bounded.
- The workflow is manual, checks out trusted `main`, has read-only repository permissions, shares the existing runner concurrency group, and never runs pull-request code.
- No tools, Hermes calls, external APIs, JarvisOS access, state changes, or model comparison are authorized by this slice.

A successful smoke run proves only that the bounded pipeline works for one candidate-case execution. It does not establish capability, reliability, or ranking.
