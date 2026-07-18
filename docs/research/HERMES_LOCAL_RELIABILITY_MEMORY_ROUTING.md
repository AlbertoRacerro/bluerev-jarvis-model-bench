# Hermes + Local AI Reliability: Memory and Routing Design

## Scope

This note converts public Hermes Agent guidance into a bounded architecture for reliable local-model orchestration in JarvisOS and the BlueRev model benchmark.

It is bound to the benchmarked Hermes runtime:

- Hermes Agent version `0.18.2`;
- pinned commit `73b611ad19720d70308dad6b0fb64648aaadc216`;
- local OpenAI-compatible endpoint backed by Ollama;
- minimum actual context `65536`;
- no external provider in this design slice.

Current Hermes `main` may contain newer behavior. No newer feature is treated as available until a compatibility qualification is completed against a pinned commit.

## Primary Hermes sources

All normative claims below are tied to files at the pinned commit.

| Source | Blob SHA | Reliability implication |
|---|---|---|
| [`website/docs/user-guide/features/memory.md`](https://github.com/NousResearch/hermes-agent/blob/73b611ad19720d70308dad6b0fb64648aaadc216/website/docs/user-guide/features/memory.md) | `20c37afa12f7be99831c37744ddf07039f48491e` | Bounded curated memory, frozen session snapshot, session search, write approval. |
| [`tools/memory_tool.py`](https://github.com/NousResearch/hermes-agent/blob/73b611ad19720d70308dad6b0fb64648aaadc216/tools/memory_tool.py) | `08eeaa470ea493480e6095a3f04063466a31ee7e` | Atomic and locked writes, threat scanning, drift rejection, bounded consolidation retries. |
| [`website/docs/user-guide/features/skills.md`](https://github.com/NousResearch/hermes-agent/blob/73b611ad19720d70308dad6b0fb64648aaadc216/website/docs/user-guide/features/skills.md) | `19fffb1f1b23727f8d13cd42ac7986716ad1cf93` | Skills are procedural memory loaded through progressive disclosure; bundles combine focused skills; writes can be approval-gated. |
| [`website/docs/user-guide/features/delegation.md`](https://github.com/NousResearch/hermes-agent/blob/73b611ad19720d70308dad6b0fb64648aaadc216/website/docs/user-guide/features/delegation.md) | `037c2e806ae1d883c21026405a96a5dbd5f76596` | Children start with no parent context, have restricted toolsets, cannot write memory, and use one globally configured delegation model. |
| [`website/docs/user-guide/features/provider-routing.md`](https://github.com/NousResearch/hermes-agent/blob/73b611ad19720d70308dad6b0fb64648aaadc216/website/docs/user-guide/features/provider-routing.md) | `3dd6e69787e6a98e3761dcce753e063741d2591b` | Provider routing controls OpenRouter sub-providers; it is not local task routing for Ollama. |
| [`toolsets.py`](https://github.com/NousResearch/hermes-agent/blob/73b611ad19720d70308dad6b0fb64648aaadc216/toolsets.py) | `03e64fdba4c012a792c2139f5d39ffc110f60d78` | Pins the exact `memory`, `session_search`, `skills`, and `delegation` toolset names used by the candidate skills. |
| [`website/docs/user-guide/profiles.md`](https://github.com/NousResearch/hermes-agent/blob/73b611ad19720d70308dad6b0fb64648aaadc216/website/docs/user-guide/profiles.md) | `904d3ec3d1ee9da64e18ef9515f9eb66a25c7575` | Profiles isolate Hermes config and state, but do not sandbox filesystem access. |

## Findings that constrain the design

### 1. Memory is bounded trusted prompt context

Hermes injects `MEMORY.md` and `USER.md` into the system prompt at session start. The official defaults are 2200 and 1375 characters. This store must remain compact because every entry consumes prompt budget and is trusted by future turns.

The snapshot is frozen for the session. A mid-session write is durable on disk, but it is not newly injected into the current prompt. A skill that assumes immediate prompt refresh will behave inconsistently.

The memory implementation scans writes and loaded entries for threat patterns, locks files, rejects non-round-trippable external drift, and stops repeated consolidation attempts from consuming the whole turn.

### 2. Episodic recall is not persistent memory

Hermes stores sessions in SQLite and exposes FTS5-backed `session_search`. Past decisions, detailed discussions, and debugging history should remain in session history and be retrieved on demand. Copying them into bounded memory wastes prompt budget and creates stale summaries.

### 3. Procedures belong in skills

Hermes skills are procedural memory loaded only when needed. Memory should hold compact facts; skills should hold multi-step methods, pitfalls, and verification rules.

The public skill format supports conditional tool requirements, reference files, write approval, stacking, and bundles. Memory orchestration and routing orchestration should therefore be separate focused skills loaded together through a bundle.

### 4. Subagents start empty and cannot write shared memory

A delegated child receives only the explicit `goal` and `context` packet. It has no parent conversation history. A route that delegates with phrases such as “fix the error” or “continue what we discussed” is invalid.

Leaf subagents cannot use the shared memory tool. Any child learning must return as a proposal to the parent, which verifies and optionally promotes it.

### 5. Stock Hermes does not provide reviewed per-task local-model routing

At the pinned commit, `delegation.model` and `delegation.provider` select one model/provider pair for subagents. The model is not selected per task through `delegate_task`.

Hermes `provider_routing` applies to OpenRouter provider selection. It does not resolve `local:fast`, `local:code`, or other Ollama lanes.

A routing skill can classify and request a route, but a deterministic dispatcher must enforce the selected profile and stack. A prose decision alone is not routing evidence.

## Reliability architecture

### Memory plane

Use six distinct stores:

1. `USER.md`: stable user identity and preferences.
2. `MEMORY.md`: stable project/environment facts and verified lessons.
3. `session_search`: detailed episodic recall.
4. Skills: procedures and reusable methods.
5. Project context files: repository policy and current instructions.
6. Performance ledger: route, model digest, latency, tool traces, failures, benchmark outcomes, and qualification state.

The performance ledger must be machine-readable and append-only. Model performance must never be promoted into free-form memory, where it could become stale and self-reinforcing.

### Routing plane

A route decision must be derived from:

- required capability;
- task risk and reversibility;
- context requirement;
- required tools and side effects;
- completion contract;
- current governed-stack eligibility;
- hardware availability and residency;
- iteration and latency budget.

The initial logical lanes are:

- `local:fast`;
- `local:general`;
- `local:code`;
- `local:strong`;
- `local:orchestrator`.

The lane is an alias, not evidence. The dispatcher must resolve it to an immutable profile containing endpoint, model tag and digest, context, sampling, Hermes commit, skills, finalizer, and toolset policy.

### Dispatch plane

The recommended implementation is a JarvisOS `route_task` boundary that:

1. validates a strict route request;
2. resolves the lane against a capability registry;
3. rejects ineligible or unavailable stacks;
4. creates a complete child context packet;
5. launches the selected Hermes profile or governed adapter;
6. captures provider/model/context/tool/usage evidence;
7. returns a structured result without rewriting failures.

Separate Hermes profiles are an acceptable first implementation because the pinned Hermes runtime supports isolated config, memory, skills, and a globally configured delegation model per profile. Profiles are not filesystem sandboxes: each routed profile must pin an absolute `terminal.cwd` and remain behind an independently enforced filesystem/tool boundary.

A future Hermes upgrade may expose better per-call routing. It must first pass compatibility tests for context, tool calls, memory isolation, finalization, and evidence capture.

## Recommended initial Hermes configuration

```yaml
memory:
  memory_enabled: true
  user_profile_enabled: true
  memory_char_limit: 2200
  user_char_limit: 1375
  write_approval: true

skills:
  write_approval: true

delegation:
  max_iterations: 50
  max_concurrent_children: 1
  max_spawn_depth: 1
  orchestrator_enabled: false
  child_timeout_seconds: 0
```

Rationale:

- approval gates prevent a small local model from poisoning future sessions or rewriting procedures without review;
- one child at a time avoids uncontrolled VRAM contention on a single consumer GPU;
- flat delegation prevents recursive fan-out before routing itself is qualified;
- no hard child timeout avoids killing slow but progressing local inference; every dispatch still carries an explicit `max_iterations` value and the external JarvisOS dispatcher supplies a wall-clock watchdog with durable timeout evidence.
- profile separation prevents state mixing but does not sandbox files; use an absolute `terminal.cwd` plus explicit tool/filesystem policy.

Provider fallback should remain disabled during qualification. Later, one infrastructure-only fallback may be allowed before side effects for reversible work. Semantic failure must never trigger an invisible stronger-model retry.

## Memory promotion policy

| Information | Destination |
|---|---|
| Stable user preference | `USER.md` |
| Stable environment or project convention | `MEMORY.md` |
| Detailed previous discussion | `session_search` |
| Reusable multi-step method | Skill |
| Current repository instruction | Project context file |
| Model quality, route result, latency, failure | Performance ledger |
| Raw logs, code dumps, temporary paths | Do not persist in memory |

Conflict precedence:

1. current explicit user statement;
2. verified current project state;
3. approved persistent memory;
4. session history.

## Routing and fallback policy

1. Route by capability-specific evidence, never by a single aggregate score.
2. Reject a lane when the registered stack lacks the required context, tools, residency, or capability admission.
3. Build every child packet as though the child knows nothing.
4. Grant least-privilege toolsets.
5. Permit at most one infrastructure fallback before side effects, only when explicitly allowed by the registry.
6. Never reroute automatically after a patch, send, write, or other state change.
7. Treat malformed output, wrong tool choice, failed tests, and failed completion contracts as semantic failures, not provider outages.
8. Return `no_eligible_route` rather than guessing.

## First benchmark family

The first memory-routing benchmark should remain synthetic and deterministic.

### Memory cases

- stable user preference → `USER.md`;
- stable project fact → `MEMORY.md`;
- prior detailed discussion → `session_search`;
- reusable procedure → skill;
- benchmark result → performance ledger;
- raw log and temporary state → skip;
- stale memory conflict → replace;
- subagent memory proposal → parent verification;
- capacity above 80 percent → consolidation;
- injected or secret-bearing text → reject;
- mid-session write → no assumed prompt refresh;
- unsupported recollection → explicit uncertainty.

### Routing cases

- short reversible lookup → `local:fast`;
- ordinary synthesis → `local:general`;
- patch and test task → `local:code`;
- complex high-ambiguity reasoning → `local:strong`;
- exact tool contract → admitted `local:orchestrator` stack;
- insufficient context → reject or choose a qualified larger-context stack;
- omitted child context → reject before dispatch;
- provider outage before side effects → one registered infrastructure fallback;
- semantic failure → no automatic reroute;
- state change already started → no automatic fallback;
- aggregate-score-only recommendation → reject;
- no eligible stack → fail closed.

## Promotion boundary

This design does not:

- execute Ollama or a self-hosted runner;
- add a routing dispatcher;
- change JarvisOS routing;
- modify memory files;
- install or adopt either candidate skill;
- enable automatic skill or memory writes;
- upgrade Hermes;
- authorize cloud providers;
- promote any stack to production.

A later runtime experiment must separately qualify memory classification, retrieval, route selection, actual dispatch identity, side-effect boundaries, and completion evidence.
