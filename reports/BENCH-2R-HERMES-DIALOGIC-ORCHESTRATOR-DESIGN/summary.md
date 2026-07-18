# Hermes dialogic memory-context-routing orchestrator

## Decision

The benchmark has been optimizing the wrong layer.

S3A and S3A-R1 correctly exposed protocol defects, but byte-exact JSON is a terminal protocol property. It must not become the dominant training objective for Hermes as an orchestrator. S3A-R2 remains useful as a protocol regression side gate; the primary program now targets Hermes as a dialogic control plane for memory, context, task graphs, routines, delegation, and model routing.

No historical closeout is reclassified. Production remains `not_promoted`.

## Official Hermes capabilities confirmed

This design is bound to Hermes Agent `0.18.2` at commit `73b611ad19720d70308dad6b0fb64648aaadc216`.

### Memory and historical recall

Hermes already separates:

- compact persistent `MEMORY.md` and `USER.md`, injected as a frozen session-start snapshot;
- on-demand `session_search` over the full SQLite session history;
- agent-managed add, replace, remove, and consolidation behavior.

The implication is architectural: persistent memory should hold only high-value facts that must always be available. Detailed history belongs in session search. Raw logs, full transcripts, and large code blocks should not be promoted into always-on memory.

### Context

Hermes already supports:

- project context files with explicit priority;
- progressive discovery of subdirectory context;
- security scanning and bounded truncation;
- on-demand skills with progressive disclosure.

The orchestrator must therefore select and stage context rather than concatenate every source into one prompt.

### Procedural learning

Hermes skills are procedural memory. The agent can learn from local sources, URLs, the current conversation, user corrections, successful complex tasks, and recovered dead ends. Skill writes can be staged for later review.

Training should exercise this native loop:

1. complete or recover a workflow;
2. identify the generalizable procedure;
3. create or patch a skill;
4. test it on a fresh scenario;
5. promote only after post-hoc review.

### Tasks and routines

Hermes supports natural-language scheduled tasks, attached skills, project work directories, provider/model binding, pause, resume, edit, run, and remove operations.

Immediate work and durable work are different:

- current-turn dependencies belong in a task graph;
- recurring or interrupt-resistant work belongs in cron;
- cron executions cannot recursively create more cron jobs.

### Delegation and routing

Delegated agents have completely isolated context. They know only the `goal` and `context` explicitly supplied by the parent, and only their final summary returns to the parent. Delegation is synchronous and is cancelled when the parent turn is interrupted; cron is the durable alternative.

This makes a context packer load-bearing. Every delegation must carry the goal, acceptance condition, evidence, paths, toolsets, prohibitions, known failures, and expected return structure.

Hermes also supports child-model override and restricted toolsets. Routing can therefore choose among:

- parent agent;
- delegated leaf;
- delegated orchestrator;
- deterministic code execution;
- cron agent session;
- cron no-agent script.

A model name alone is not a routing policy. The decision must account for capability, context length, tools, reliability evidence, latency, compute residency, cost, and side-effect risk.

## Architecture

### 1. Dialogue and learning plane

Hermes may reason, ask material clarifying questions, revise the task graph, search prior sessions, propose memory, create sandbox skills, and create sandbox routines through normal dialogue.

Normal intermediate responses are not forced into exact JSON.

### 2. Context plane

Context is selected progressively:

1. current request and constraints;
2. project context;
3. compact memory and user profile;
4. targeted session search;
5. relevant skills only;
6. focused files, diffs, logs, or documents;
7. delegation context packs;
8. compression or a future context engine.

Compression must preserve goals, decisions, blockers, evidence pointers, task state, and user corrections.

### 3. Routing plane

The parent orchestrator initially stays bound to the S2-admitted governed Gemma stack. Adaptive routing is explored only for child and auxiliary tasks until evidence exists.

Every route decision records:

- chosen target and model;
- required toolsets;
- evidence supporting the choice;
- rejected alternatives;
- expected context, latency, and cost;
- result and route revision if it fails.

### 4. Procedural memory and routine plane

After useful trajectories Hermes may propose or stage:

- compact memory changes;
- new or patched skills;
- cron routines;
- task templates.

All training writes occur in an isolated Hermes profile. Shared or production promotion is a later decision.

### 5. Governance plane

Deterministic controls remain strict at:

- irreversible or externally visible side effects;
- secret and external-provider boundaries;
- trace and artifact integrity;
- post-episode scoring;
- promotion of memories, skills, routines, routing policies, or models.

They do not replace native dialogue or native Hermes trajectories.

## Curriculum

The initial curriculum contains nine capability families:

- D0 recall and correction;
- D1 context selection and compression;
- D2 task graph and dialogue;
- D3 delegation context packing;
- D4 procedural learning;
- D5 routine creation and lifecycle;
- D6 adaptive routing;
- D7 multi-session continuity;
- D8 failure recovery.

Episodes permit corrections and new constraints. The evaluated object is the complete trajectory and resulting state changes, not only the final text.

## Evidence and scoring

Each episode must retain the native Hermes trajectory plus a post-hoc artifact containing:

- semantic outcome;
- selected context sources;
- memory, skill, routine, and task-graph diffs;
- route decisions and delegation context packs;
- actual tool traces;
- tokens, latency, and estimated cost;
- user corrections;
- unresolved risks.

Primary scores are semantic task success, context relevance, memory precision, recall quality, task-graph quality, correction incorporation, routing utility, routine correctness, skill generalization, and continuity.

Exact protocol conformance remains a separate terminal regression gate. It is not a global intelligence score.

## Failure modes addressed first

1. **Memory poisoning or bloat** — isolate training memory, reject raw dumps, require consolidation and evidence-linked promotion.
2. **Stale frozen memory** — use live tool responses and session search during the session; do not assume a write changes the frozen prompt snapshot.
3. **Subagent amnesia** — require complete context packs; never delegate with references such as “fix the error”.
4. **Context stuffing** — progressive disclosure and relevance logging; no indiscriminate prompt concatenation.
5. **Compression loss** — preserve task state and evidence pointers before summarizing narrative turns.
6. **Runaway delegation cost** — bounded depth and concurrency; route mechanical work to code execution.
7. **Non-durable delegated work** — use cron for work that must survive the parent turn.
8. **Routine recursion** — cron runs cannot create more cron jobs.
9. **Skill overfitting** — fresh-scenario tests before promotion.
10. **Routing by reputation** — route from observed task-specific evidence and runtime state, not a single global winner.
11. **Finalizer masking** — preserve raw trajectory and separately score final artifacts.
12. **Premature production mutation** — isolated profile and explicit promotion boundary.

## Scope of this slice

This is a static architecture and curriculum slice only.

It adds no self-hosted workflow, activation marker, Ollama call, external provider, production memory write, skill adoption, cron job, routing change, or model-weight update.
