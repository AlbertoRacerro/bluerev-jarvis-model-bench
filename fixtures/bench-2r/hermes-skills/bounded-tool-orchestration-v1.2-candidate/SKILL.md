---
name: bounded-tool-orchestration
description: Execute bounded tool tasks with exact calls, stopping, and final-output rules
version: 1.2.0
metadata:
  hermes:
    tags: [orchestration, tools, stopping, structured-output]
    category: reasoning
---

# Bounded Tool Orchestration

## When to Use

Use this skill when a task supplies an explicit tool registry, a `tool_contract`, allowed or forbidden actions, a response contract, or a strict call budget.

## Contract Precedence

Read the entire task before acting. Apply these sources in this order:

1. The task prompt's explicit final-answer instruction or literal output template.
2. An explicit final-output schema supplied by the task.
3. `inputs.response_contract` as metadata describing where values come from and which ledger values are required.
4. General defaults from this skill.

Metadata property names are not automatically final-response field names. In particular, a metadata key such as `required_actions` describes required ledger values; it must not be emitted as a field unless the task prompt or final-output schema explicitly names `required_actions` as an output field.

## Procedure

1. Separate three concepts:
   - **runtime action**: an actual tool invocation or stop;
   - **contract metadata**: fields such as `tool_contract`, `response_contract`, `output_field`, and `required_actions`;
   - **final output**: the exact object requested by the task prompt.
2. Inspect `inputs.tool_contract` before producing any final answer.
   - If `exact_calls` is a positive integer, invoke the named registered tool exactly that many times with exactly the supplied arguments.
   - A string label such as `"call_tool"` in the final ledger is not a tool invocation and never satisfies `exact_calls`.
   - Do not emit a final answer until the required tool response count has been observed.
3. If the required result is already present and verified in the task input and the tool contract permits zero calls, do not call a tool. Preserve the supplied result verbatim.
4. Never invent, alias, or infer an unavailable tool name. Use only a tool present in the active registry whose documented purpose matches the contract.
5. Respect all budgets. Do not call a distractor, repeat a call, retry a non-retryable failure, switch tools after a reviewed failure, or use an external provider.
6. After the final required tool response:
   - determine whether the requested value is verified;
   - if it is verified, extract only the value and field requested by the task;
   - if it is unverified, omit the task's `output_field`; do not emit `null`, the raw tool result, an error wrapper, or an invented value.
7. Construct the final answer from the task prompt, not from metadata key names.
   - If the prompt requests an object containing only an `actions` ledger, the only field is `actions`.
   - Copy the ledger values from `response_contract.required_actions` exactly once and in order.
   - Emit every requested field and no unrequested field.
   - Include no prose, Markdown fence, commentary, or extra nesting.
8. Stop immediately after the exact final object. Do not reason aloud, call another tool, retry, or restate the answer.

## Generic Example

Given metadata containing:

```json
{
  "response_contract": {
    "output_field": "value",
    "required_actions": ["call_tool", "stop"]
  }
}
```

and a task prompt that requires an object containing only the `actions` ledger while omitting an unverified `value`, the final response is:

```json
{"actions":["call_tool","stop"]}
```

The field name is `actions` because the task prompt names it. The metadata key `required_actions` is not an output field. This final object may be emitted only after any positive `tool_contract.exact_calls` requirement has been satisfied by real tool invocation.

## Pitfalls

- Treating `required_actions` or `output_field` metadata keys as final-response keys.
- Writing `"call_tool"` in a ledger without actually invoking the required tool.
- Returning `null` for an unverified value instead of omitting the value field.
- Returning the complete tool response or nesting the ledger under the omitted value field.
- Retrying or switching tools after a deterministic non-retryable failure.
- Continuing after the terminal state.

## Verification

Before the final response, verify internally:

1. Did the number, name, and arguments of actual tool calls exactly match `tool_contract`?
2. If `exact_calls` is positive, was at least one real tool response observed before final output?
3. Were all forbidden calls, retries, providers, and state changes absent?
4. Did I use the task prompt or explicit final schema to choose final field names?
5. Did I treat `response_contract` keys as metadata rather than output keys?
6. If the result is unverified, did I omit the output field and avoid `null` or wrappers?
7. Does the final object contain every requested field and no other field?
8. Are ledger labels copied exactly once and in order?
9. Will the response end immediately after the final structured output?

Do not print this checklist or any reasoning in the final response.
