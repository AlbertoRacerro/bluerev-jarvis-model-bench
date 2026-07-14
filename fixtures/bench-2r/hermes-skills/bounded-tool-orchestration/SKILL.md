---
name: bounded-tool-orchestration
description: Execute bounded tool tasks with exact stop and output rules
version: 1.1.0
metadata:
  hermes:
    tags: [orchestration, tools, stopping, structured-output]
    category: reasoning
---

# Bounded Tool Orchestration

## When to Use

Use this skill when a task supplies an explicit tool registry, allowed and forbidden actions, an output contract, or a strict call budget.

## Procedure

1. Read the entire task contract before acting. Treat the supplied registry, limits, response contract, and literal values as authoritative.
2. Separate two concepts that may use similar words:
   - **runtime behavior**: whether to call a tool, return, or stop;
   - **output ledger**: literal action labels that the response contract requires as data.
   A runtime stop does not permit deleting, shortening, or inventing the required output ledger.
3. Determine whether the required result is already present and verified in the task input.
   - When it is present, do not call a tool. Preserve the supplied result verbatim.
   - When it is absent, select only a registered tool whose documented purpose directly provides the missing information.
4. Never invent, alias, or infer an unavailable tool name. A familiar tool from another framework is not available unless it appears in the current registry.
5. Make the minimum number of tool calls allowed by the task. Do not call a distractor, repeat a successful lookup, or perform an unrequested verification.
6. After a sufficient tool result is returned, re-read the response contract before composing the answer. Do not return the raw tool object unless the required value type explicitly calls for that object.
7. Build the final answer exactly once:
   - emit every required field and no unrequested field;
   - preserve each required field name and value type;
   - when the contract supplies `actions`, `required_actions`, or an equivalent literal list, copy every item exactly once and in the original order;
   - do not replace a required action list with a description of the tool call or with only the final stop action;
   - preserve supplied values verbatim unless transformation is explicitly required;
   - include no prose, markdown fence, wrapper, commentary, or extra nesting when a strict object is requested.
8. Stop immediately after emitting the valid final answer. Do not continue reasoning, call another tool, or restate the answer.

## Pitfalls

- Calling a tool even though the answer is already supplied.
- Choosing a tool because its name is familiar rather than because its registered description matches the task.
- Treating a successful tool result as permission to perform follow-up checks.
- Confusing actions already performed with literal action labels required in the output.
- Omitting earlier ledger items because the runtime is now at the stop state.
- Returning the complete tool response when the contract requires only one scalar value from it.
- Returning a correct value inside the wrong wrapper or with the wrong type.
- Continuing after the terminal state has already been reached.

## Verification

Before the final response, verify internally:

1. Was every called tool present in the active registry?
2. Was each call necessary and within the task budget?
3. Is the required result now available?
4. Did I re-read the response contract after the last tool result?
5. Does the final value have exactly the requested type rather than the tool response type?
6. Does the response contain every required field and no additional wrapper?
7. If an action ledger is supplied, did I copy all labels exactly and in order?
8. Will the response end immediately after the final structured output?

Do not print this checklist or any reasoning in the final response.
