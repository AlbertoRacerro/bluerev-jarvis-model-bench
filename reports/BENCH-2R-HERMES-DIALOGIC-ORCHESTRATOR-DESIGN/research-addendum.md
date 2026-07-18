# External research addendum

## Evidence status

This addendum separates two evidence classes:

1. primary research preprints used to derive transferable architecture hypotheses;
2. Hermes community issue reports used only as failure-mode signals.

Issue reports are not treated as proof that the pinned Hermes `0.18.2` runtime exhibits the reported behavior. Each signal must be reproduced or rejected inside the isolated benchmark profile before it affects admission.

## Context evolution

Agentic Context Engineering suggests maintaining a structured, evolving playbook through incremental generation, reflection, and curation rather than repeatedly compressing all experience into one short rewritten summary.

Applied to Hermes:

- memory and skills receive append, refine, merge, and deprecate operations with provenance;
- each learned strategy retains links to the trajectories and outcomes that motivated it;
- context compression preserves detailed state and evidence pointers;
- stale or contradicted entries are explicitly deprecated rather than silently overwritten;
- context growth, duplication, and stale-strategy rate become measured outputs.

## Routing from experience

BoundaryRouter provides a stronger pattern than routing by model reputation: execute direct and agentic routes on a compact seed set, store the paired experience, retrieve similar cases, and use a task-boundary rubric to decide whether escalation is justified.

Applied to Hermes:

- the route memory stores task features, selected target, alternatives, result, cost, latency, and failure class;
- route selection retrieves similar prior cases before choosing parent, child, code execution, or routine execution;
- route regret compares the chosen route against paired evidence where available;
- no single global model ranking is permitted.

## Graph memory for workflows

Trainable graph-memory and GraphPlanner research support representing more than flat text memories. The useful abstraction is a graph linking task states, agent roles, models, tools, decisions, and outcomes.

Applied to Hermes:

- raw trajectories remain immutable evidence;
- task transitions become structured decision paths;
- reusable strategies are distilled separately from case facts;
- strategy utility is updated from downstream outcomes;
- model and role are selected jointly at workflow steps;
- graph retrieval complements, rather than replaces, compact memory and session search.

## Hermes-specific risk signals

### Historical retrieval

Community reports indicate two risks worth testing:

- keyword session search and semantic memory-provider retrieval may be separate paths;
- expanding a very long matched session may create latency and context cost.

The benchmark therefore requires bounded discovery, local scrolling around matches, backend attribution, and a future hybrid keyword-plus-semantic comparison. Whole-session loading is forbidden by default.

### Delegation durability

Official documentation and community reports agree that `delegate_task` is synchronous. It must not be treated as a durable queue. Current-turn parallel analysis may use delegation; work that must survive interruption belongs in cron or a durable background process.

### Routine continuity

Cron routines start fresh sessions and may not expose the same memory behavior as interactive sessions across Hermes versions and configurations. Every routine therefore carries an explicit context capsule containing purpose, state pointers, workdir, skills, provider/model, and delivery target. The runtime must not assume that the originating conversation or interactive memory is available.

### Profile isolation

A community bug report raises the possibility of session or memory contamination when multiple instances share state. Regardless of whether the pinned runtime reproduces it, the prevention is cheap and mandatory: every experiment receives a unique profile identity, `HERMES_HOME`, state database, memory directory, skills directory, and cron store.

## New runtime acceptance questions

The dialogic runtime must answer, with traces rather than prose:

1. Did targeted historical retrieval find the relevant prior decision without loading unrelated history?
2. Did context updates preserve provenance and avoid duplicate or stale strategies?
3. Did the selected route outperform or justify itself against available paired experience?
4. Did every delegated child receive a sufficient context pack?
5. Did every routine execute from an explicit context capsule?
6. Did any state leak across isolated profiles?
7. Did a failure update task state and route policy without corrupting durable memory?

These are curriculum and evaluation requirements. They do not authorize runtime execution in this PR.
