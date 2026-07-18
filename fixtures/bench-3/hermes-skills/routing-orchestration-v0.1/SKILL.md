---
name: routing-orchestration
description: Select and verify an eligible local execution stack
version: 0.1.0
metadata:
  hermes:
    tags: [routing, delegation, local-models, orchestration]
    category: reasoning
    requires_toolsets: [delegation]
---

# Routing Orchestration

## When to Use

Use this skill before delegating or dispatching work among local AI stacks.

A routing decision is not execution. Do not claim that a route was used until a deterministic dispatcher or child trace confirms the actual profile, model digest, context, toolsets, and result.

## Required Inputs

Classify the task using explicit facts:

1. Capability: lookup, general, code, strong reasoning, or governed orchestration.
2. Risk: low, medium, or high.
3. Reversibility: reversible, reviewable, or state-changing.
4. Context requirement: estimated tokens and required source files.
5. Tools: exact toolsets and side effects required.
6. Budget: iteration, latency, and resource limits.
7. Completion contract: evidence that proves the task is done.

Use the capability registry and machine-readable performance ledger as the routing source of truth. Never route from a global model score, reputation, memory entry, or unsupported intuition.

## Local Lanes

The registry may expose these logical lanes:

- local:fast for low-risk, short-context, reversible work.
- local:general for ordinary synthesis and conversation.
- local:code for repository, patch, test, and debugging tasks.
- local:strong for ambiguous or high-complexity reasoning.
- local:orchestrator for exact tool contracts using a separately admitted governed stack.

A lane is eligible only for capabilities supported by current benchmark evidence. A checkpoint name alone is not an eligible route.

## Pinned Hermes Constraint

In the pinned Hermes Agent runtime, delegation.model and delegation.provider configure one model for all subagents. Stock delegate_task does not provide a reviewed per-task local-model switch.

Therefore this skill must not pretend that naming a lane changes the child model.

Actual per-task routing must be enforced by one of these deterministic mechanisms:

1. A JarvisOS route tool that resolves a lane to an immutable profile and governed stack.
2. Separate Hermes profiles with pinned provider, endpoint, model digest, context, skills, and toolsets.
3. A later Hermes upgrade only after compatibility qualification proves the required routing semantics.

OpenRouter provider_routing is not a local Ollama router and must not be used as evidence of local lane selection.

## Context Packet

Hermes subagents know nothing about the parent conversation. Before dispatch, construct a complete context packet containing:

- exact goal;
- relevant verified facts and source paths;
- constraints and forbidden actions;
- expected output schema;
- allowed toolsets;
- iteration and resource budget;
- completion evidence;
- stop and escalation conditions.

Reject delegation when the packet contains unresolved references such as this error, the file, or as discussed earlier without the underlying facts.

## Tool and Concurrency Boundary

Grant least-privilege toolsets.

For a single consumer GPU, set max_concurrent_children to 1 until a hardware experiment proves safe concurrency. Keep max_spawn_depth at 1 and disable nested orchestrators during the first routing qualification.

Subagents must not write persistent memory. The parent adjudicates child summaries and any memory proposals.

## Fallback Policy

Infrastructure failover and semantic rerouting are different:

- Before any side effect, one deterministic fallback may be allowed for a reversible task when the registry explicitly permits it.
- After a state change, tool side effect, partial patch, or external send, automatic fallback is forbidden.
- A malformed answer, wrong tool, failed completion contract, or low-quality result is a semantic failure. Do not silently send the same task to a stronger model.
- When no eligible route exists, fail closed and return an escalation requirement.

Fallback decisions must preserve an audit trail and never erase the original failure.

## Verification

Require dispatcher or child evidence for:

1. Selected lane and resolved profile.
2. Exact provider endpoint and model digest.
3. Actual context length and residency policy.
4. Toolsets and iteration budget.
5. Completion-contract evidence.
6. Whether a fallback occurred and why.
7. Absence of forbidden side effects or retries.

Record route evidence in the performance ledger. Persistent memory may store only stable user preferences such as local-only operation, never model performance conclusions.
