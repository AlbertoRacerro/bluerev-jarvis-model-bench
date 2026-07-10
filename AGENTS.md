# AGENTS.md

## Purpose

This repository evaluates local AI models directly and as orchestrators inside Hermes Agent. It is an experimental benchmark, not a production subsystem of JarvisOS.

## Hard invariants

1. Local models only until the maintainer explicitly changes this rule. Do not configure or call external model APIs, provider fallbacks, cloud tool gateways, or auxiliary cloud models.
2. Never modify, execute against, push to, or merge into `JarvisOS_v1`. Use synthetic fixtures or isolated copies only.
3. Deterministic validators, executable tests, and recorded artifacts are the mechanical authority. Model self-assessment is advisory.
4. Preserve raw outputs immutably. Derived scores and summaries must reference the raw artifact and validator version.
5. Do not silently accept malformed output. Missing `FINAL:` markers, invalid schemas, missing units, and incomplete traces are failures.
6. Separate orchestrator quality from worker, critic, scientific-reasoning, and direct-model quality.
7. Prefer the smallest sufficient change. Before adding infrastructure, verify whether an existing script, contract, or workflow can be extended.
8. Supervised automatic merge is allowed only in this repository after deterministic tests, diff-scope review, and explicit verification that the change does not weaken local-only, trusted-main, artifact, credential, or JarvisOS boundaries. Changes involving external providers, credentials, repository permissions, untrusted workflow triggers, destructive state changes, or JarvisOS remain maintainer-confirmation gates.
9. Never commit credentials, tokens, private prompts, personal files, model weights, or host-specific secrets.
10. Self-hosted workflows must not run untrusted pull-request code and must use explicit concurrency and timeout limits.

## Experimental discipline

- Pin the Hermes commit/version and record it in every run.
- Record candidate model tags, digests when available, runtime versions, hardware fingerprint, parameters, seed when supported, and context limits.
- Use at least three repetitions before treating stochastic results as comparative evidence.
- Report per-capability metrics; do not collapse all evidence into one global score.
- Mark results `preliminary`, `validated`, `invalid`, or `superseded`.
- A benchmark case must contain an explicit success contract and negative assertions.
- A finding that depends on a permissive validator is invalid until the validator is corrected and the affected runs are replayed.

## Initial scope

BENCH-0 establishes contracts, strict output extraction, environment inventory, Windows self-hosted execution, artifact provenance, and queue safety. It does not yet claim a winning model.
