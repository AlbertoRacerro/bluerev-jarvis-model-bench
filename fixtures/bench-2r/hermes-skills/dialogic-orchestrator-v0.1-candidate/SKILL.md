---
name: dialogic-orchestrator
description: Coordinate memory, context, tasks, routines, and model routing
version: 0.1.0
metadata:
  hermes:
    tags: [orchestration, memory, context, routing, routines]
    category: reasoning
---

# Dialogic Orchestrator

## Purpose

Use Hermes as a conversational control plane. Build shared understanding, retrieve the right context, choose the right execution path, and improve reusable memory and procedures from completed work.

This skill does not require byte-exact output during normal interaction. Exact schemas apply only when the user or a terminal task explicitly requires them.

## Operating Loop

1. Understand the actual outcome the user wants.
2. Inspect available context before asking for information that may already exist.
3. Maintain a visible task graph for work with multiple dependent steps.
4. Choose whether the next action belongs in the parent session, a delegated agent, a mechanical code pipeline, or a durable scheduled routine.
5. Execute the smallest useful next step, observe the result, and revise the plan through dialogue.
6. At completion, decide whether the result should become persistent memory, a reusable skill, a scheduled routine, or only session history.

## Memory and Recall

Use the smallest durable store that fits the information:

- Put compact, high-value facts, corrections, preferences, and environment conventions in persistent memory.
- Search prior sessions for detailed historical context instead of copying long transcripts into memory.
- Store reusable procedures as skills rather than filling persistent memory with step-by-step instructions.
- Do not save raw logs, large code blocks, transient paths, or unverified claims as durable memory.
- When new evidence contradicts a stored fact, update or remove the stale entry.
- Consolidate overlapping entries before memory capacity becomes a blocker.

## Context Selection

Construct context progressively:

1. current user request and explicit constraints;
2. active project context files;
3. compact persistent memory and user profile;
4. targeted session search for relevant prior decisions or corrections;
5. only the skills needed for the current task;
6. focused source files, diffs, logs, or documents;
7. a compact context pack for every delegated agent.

Do not stuff every available source into the prompt. Record which context sources were selected and why. When context is too large, preserve goals, decisions, unresolved blockers, evidence pointers, and current task state before compressing narrative detail.

## Task Graph and Clarification

Use a task graph when the work has dependencies, multiple artifacts, or more than one plausible execution path.

- Ask a clarifying question only when the missing answer materially changes the plan, safety, cost, or expected result.
- Do not ask again for information available in memory, session history, project context, or tool output.
- Convert corrections into updated task state immediately.
- Keep exploration reversible until enough evidence exists to commit to a path.

## Delegation and Routing

Delegate judgment-heavy, parallel, or context-isolating work. Use code execution for deterministic mechanical pipelines.

Before delegation, create a context pack containing:

- concrete goal and acceptance condition;
- relevant facts and evidence;
- exact files, paths, or identifiers;
- allowed toolsets and prohibited actions;
- current blockers and known failed approaches;
- expected return structure.

Choose the route using task capability, required context length, tool needs, reliability evidence, latency, compute residency, and cost. Record the selected route and the alternatives rejected. A model name alone is not a routing policy.

Keep the parent responsible for synthesis, conflict resolution, user dialogue, memory decisions, and final side effects.

## Skills and Learning

After a successful non-trivial workflow, a user correction, or recovery from a dead end:

1. identify the generalizable procedure;
2. separate stable technique from case-specific data;
3. create or patch a skill using the smallest targeted change;
4. retain evidence linking the skill change to the trajectory that motivated it;
5. test the skill on fresh tasks before promotion.

Do not rewrite a shared production skill merely because one episode succeeded.

## Tasks and Routines

Use the immediate task graph for work inside the current interaction.

Use a scheduled routine when work must recur, survive the current turn, or run independently later. Create or edit routines through dialogue, preserving:

- purpose and expected deliverable;
- schedule or trigger;
- project work directory when needed;
- attached skills;
- provider and model binding;
- delivery destination;
- pause, edit, and removal path.

Do not create recursive scheduling loops. Routine executions may report or propose follow-up work, but they must not autonomously create more routines.

## Side-Effect Boundary

Exploration, planning, retrieval, routing, and reflection may remain conversational. Apply hard approval or deterministic checks before irreversible or externally visible actions such as sending, publishing, deleting, spending, exposing secrets, changing production routing, or promoting memory and skills outside the isolated training profile.

## Episode Completion

At the end of an episode, produce a normal user-facing answer and a machine-readable evaluation artifact derived from actual traces. The artifact should capture task outcome, context sources, memory changes, skill changes, routine changes, route decisions, tool traces, costs, corrections, and unresolved risks.

Do not force the conversational response into the evaluation schema. Evaluation is post-hoc and must not replace the native Hermes trajectory.
