# BENCH-1 bounded direct-model smoke

This slice proves the local execution and evidence pipeline with deliberately small runs. It is not comparative evidence and does not involve Hermes.

## Current fixed scope

- Lane: `direct`.
- Candidate: `qwythos-hermes-safe`.
- Case: `ho-stop-reuse-001`.
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

## Preconditions

The workflow runs only after all deterministic tests pass and a fresh preflight reports:

- `runner_ready=true`;
- `scoring_ready=true`;
- `local_only=true`;
- the exact candidate tag and digest present in the Ollama inventory;
- the pinned clean Hermes state still recorded, even though Hermes is not called by this lane.

## Candidate-visible data

The prompt contains only `bench.candidate-task.v1` fields. Evaluator-only fields such as `expected`, assertions, and required artifact names are rejected if they leak into the payload.

The model must return one final payload:

```text
FINAL: {"output":{...},"actions":["action_id",...]}
```

Duplicate JSON keys, missing fields, extra fields, malformed actions, and missing `FINAL:` markers are candidate failures only when generation completed without truncation.

## Evidence

Every completed execution preserves separate files for:

1. candidate payload;
2. exact prompt;
3. raw Ollama response envelope;
4. raw model output;
5. extracted output or extraction failure envelope;
6. trace or trace-capture failure envelope;
7. deterministic validator result;
8. environment fingerprint;
9. manifest with SHA-256 references;
10. execution summary.

The run directory is unique per GitHub run and attempt. An existing directory is never overwritten.

## Gate semantics

The result vocabulary is:

- `passed`: complete generation and all deterministic assertions passed;
- `failed`: complete generation but the response or trace violated the contract;
- `invalid`: the benchmark could not obtain a complete candidate result, including `done_reason="length"`.

A failed or invalid candidate result does not fail the infrastructure workflow. Tests, preflight, identity binding, local execution, evidence preservation, or an unknown result state do fail the workflow.

## Network and safety boundary

- External provider environment variables are removed from the job process.
- Proxy environment variables are removed and the HTTP client uses an empty proxy configuration.
- Only an IP-literal loopback HTTP endpoint with the exact `/api/generate` path is accepted.
- Redirects, credentials in URLs, query strings, and fragments are rejected.
- Prompt and response sizes are bounded.
- The workflow is manual, checks out trusted `main`, has read-only repository permissions, shares the existing runner concurrency group, and never runs pull-request code.
- No tools, Hermes calls, external APIs, JarvisOS access, state changes, or model comparison are authorized by this slice.

A successful smoke run proves only that the bounded pipeline works for one candidate-case execution. It does not establish capability, reliability, or ranking.
