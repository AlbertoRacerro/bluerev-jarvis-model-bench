# BENCH-1 bounded direct-model smoke

This slice proves the local execution and evidence pipeline with one deliberately small run. It is not comparative evidence and does not involve Hermes.

## Fixed scope

- Lane: `direct`.
- Candidate: `minicpm5-fable-1b-control`.
- Case: `ho-stop-reuse-001`.
- Repetitions: `1`.
- Ollama endpoint: exactly `http://127.0.0.1:11434/api/generate`.
- Temperature: `0`.
- Seed: `4242`.
- Context limit: `4096`.
- Generation limit: `256` tokens.
- Request timeout: `180` seconds.
- `keep_alive`: `0` so the smoke run does not leave the model resident.

The candidate and case are constants in the trusted job driver. Workflow inputs cannot select an arbitrary model, path, endpoint, or fixture.

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

Duplicate JSON keys, missing fields, extra fields, malformed actions, and missing `FINAL:` markers are candidate failures.

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

A malformed answer or wrong answer produces `candidate_passed=false` but does not fail the workflow. That is valid benchmark evidence.

The workflow fails when tests, preflight, model identity binding, local execution, or artifact preservation fail. Infrastructure failure must never be confused with candidate quality.

## Network and safety boundary

- External provider environment variables are removed from the job process.
- Only an IP-literal loopback HTTP endpoint with the exact `/api/generate` path is accepted.
- Redirects, credentials in URLs, query strings, and fragments are rejected.
- Prompt and response sizes are bounded.
- The workflow is manual, checks out trusted `main`, has read-only repository permissions, shares the existing runner concurrency group, and never runs pull-request code.
- No tools, Hermes calls, external APIs, JarvisOS access, state changes, or model comparison are authorized by this slice.

A successful smoke run proves only that the bounded pipeline works for one candidate-case execution. It does not establish capability, reliability, or ranking.
