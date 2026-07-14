---
name: bounded-tool-orchestration
description: Execute bounded tool tasks with exact stop and output rules
version: 1.0.0
metadata:
  hermes:
    tags: [orchestration, tools, stopping, structured-output]
    category: reasoning
---

# Bounded Tool Orchestration

## When to Use

Use this skill when a task supplies an explicit tool registry, allowed and forbidden actions, an output contract, or a strict call budget.

## Procedure

1. Read the task contract before acting. Treat the supplied registry and limits as authoritative.
2. Determine whether the required result is already present and verified in the task input.
   - When it is present, do not call a tool. Return that result using the requested schema.
   - When it is absent, select only a registered tool whose documented purpose directly provides the missing information.
3. Never invent, alias, or infer an unavailable tool name. A familiar tool from another framework is not available unless it appears in the current registry.
4. Make the minimum number of tool calls allowed by the task. Do not call a distractor, repeat a successful lookup, or perform an unrequested verification.
5. After a sufficient tool result is returned, treat the task as terminal unless the contract explicitly requires another action.
6. Build the final answer exactly once:
   - preserve requested field names and value types;
   - preserve supplied values verbatim unless transformation is explicitly required;
   - include no prose, markdown fence, wrapper, commentary, or additional field when a strict object is requested.
7. Stop immediately after emitting the valid final answer. Do not continue reasoning, call another tool, or restate the answer.

## Pitfalls

- Calling a tool even though the answer is already supplied.
- Choosing a tool because its name is familiar rather than because its registered description matches the task.
- Treating a successful tool result as permission to perform follow-up checks.
- Reporting intended actions instead of satisfying the actual output schema.
- Returning a correct value inside the wrong wrapper or with the wrong type.
- Continuing after the terminal state has already been reached.

## Verification

Before the final response, verify internally:

1. Was every called tool present in the active registry?
2. Was each call necessary and within the task budget?
3. Is the required result now available?
4. Does the final value exactly match the supplied or observed value?
5. Does the response contain exactly the required fields and types?
6. Will the response end immediately after the final structured output?

Do not print this checklist or any reasoning in the final response.
