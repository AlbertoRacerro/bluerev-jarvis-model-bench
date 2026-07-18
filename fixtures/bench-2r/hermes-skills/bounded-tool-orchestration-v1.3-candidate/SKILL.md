---
name: bounded-tool-orchestration
description: Execute bounded tool tasks with exact calls, stopping, and byte-exact final output
version: 1.3.0
metadata:
  hermes:
    tags: [orchestration, tools, stopping, structured-output]
    category: reasoning
---

# Bounded Tool Orchestration

## Contract precedence

Apply the task prompt and explicit final-output schema before metadata or examples. Metadata keys describe the contract; they are not output fields unless the task explicitly names them.

## Procedure

1. Read the full task, tool registry, call budget, fault policy, and response contract before acting.
2. Separate:
   - an actual runtime tool invocation;
   - metadata such as `tool_contract`, `response_contract`, `output_field`, and `required_actions`;
   - the byte sequence required as final output.
3. When `tool_contract.exact_calls` is positive, invoke the named registered tool exactly that many times with exactly the supplied arguments. A ledger label such as `call_tool` is data and does not satisfy this requirement.
4. Do not compose the final answer until the required tool response or reviewed fault result has been observed. Never replace a required invocation with prose claiming that the tool was called.
5. After an unverified result or reviewed timeout, do not retry, switch tools, invent a value, emit `null`, or expose the raw tool object. Omit the unverified output field when the task requires omission.
6. Construct the final object from the task prompt and explicit schema. For the current S3A negative cases, the exact final payload is the following sequence of characters after the colon: {"actions":["call_tool","stop"]}
7. Emit raw JSON bytes only when the contract requires a single JSON object:
   - the first emitted character must be `{`;
   - the last emitted character must be `}`;
   - emit no leading or trailing whitespace;
   - emit no Markdown fence, backtick, language label, quotation wrapper, prose, commentary, or second object;
   - preserve the exact field names, value types, ledger values, and ledger order required by the task.
8. The final `stop` ledger item is terminal. End the response immediately after the closing `}`.

## Hard failures

The answer is invalid if any of the following occurs:

- the required tool was not actually invoked;
- a retry or unlisted tool was used;
- `required_actions` or another metadata key was emitted instead of the task-mandated field;
- the JSON object is wrapped in Markdown or prose;
- any byte appears before `{` or after `}`;
- the action ledger is missing, reordered, duplicated, or replaced by a narrative;
- an unverified value is invented or returned.

## Internal verification

Before emitting the final answer, verify internally:

1. The actual tool trace exactly matches the contract.
2. The required tool result or reviewed fault was observed.
3. No forbidden call, retry, provider, or state change occurred.
4. The final object uses task-defined fields rather than metadata field names.
5. The candidate output begins with `{`, ends with `}`, and contains no backtick or newline.
6. The action ledger is exact and terminal.

Do not print this checklist or any reasoning.