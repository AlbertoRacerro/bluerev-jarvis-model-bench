---
name: bounded-tool-orchestration
description: Execute bounded tool tasks with exact calls and byte-exact final output
version: 1.3.0
metadata:
  hermes:
    tags: [orchestration, tools, stopping, structured-output]
    category: reasoning
---

# Bounded Tool Orchestration

## When to Use

Use this skill when a task supplies an explicit tool registry, a `tool_contract`, allowed or forbidden actions, a response contract, a literal output template, or a strict call budget.

## Contract Precedence

Read the entire task before acting. Apply sources in this order:

1. The task prompt's literal final-answer instruction.
2. An explicit final-output schema supplied by the task.
3. `inputs.response_contract` as metadata describing required values.
4. General defaults from this skill.

Metadata property names are not automatically output field names. A metadata key such as `required_actions` describes required ledger values; emit it only if the literal final schema names `required_actions`.

## Runtime Procedure

1. Separate runtime actions, contract metadata, and final output.
2. Inspect `inputs.tool_contract` before composing any answer.
3. If `exact_calls` is positive, invoke the named registered tool exactly that many times with exactly the supplied arguments.
4. A written label such as `call_tool` is data, not a tool invocation. It never satisfies `exact_calls`.
5. Do not emit the final object until every required tool response has actually been observed.
6. If a required result is unavailable or unverified after a reviewed non-retryable failure, omit the result field exactly as instructed. Do not invent a value, emit `null`, retry, switch tools, or expose the raw error.
7. Construct the final object from the literal prompt or explicit schema. Copy every action value exactly once, in order, and with the requested type.
8. Emit the final object once and stop.

## Byte-Exact Final Output Boundary

When the task requires strict JSON:

- Character 1 of the response MUST be `{`.
- The final character of the response MUST be `}`.
- Emit one JSON object and nothing else.
- Do not emit a Markdown fence.
- Do not emit a language label.
- Do not emit backticks.
- Do not emit an introduction, explanation, apology, newline-prefixed text, or trailing commentary.
- Do not wrap the object in another object, array, string, or code block.
- Do not replace an actual tool invocation with a textual claim that the tool was called.
- The terminal `stop` action must remain in the exact position required by the schema.

For a task that explicitly requires the following action-object schema and values, the response bytes are exactly:

{"actions":[{"type":"call_tool","tool":"registry.lookup","args":{"key":"missing"}},{"type":"stop"}]}

The line above is JSON data, not Markdown. Its surrounding document text is not part of the response. For tasks with a different explicit action representation, preserve that representation exactly rather than converting strings to objects or objects to strings.

## Fail-Closed Rules

- Any character before the opening brace is a failure.
- Any character after the closing brace is a failure.
- Any Markdown fence is a failure.
- Any extra key, missing key, changed key, extra nesting, reordered action, duplicate action, or changed action type is a failure.
- Any positive `exact_calls` contract without the required observed tool trace is a failure.
- A timeout or negative tool result does not waive the required tool invocation or terminal ledger.

## Internal Verification

Before emitting the final object, verify internally:

1. The tool name, arguments, count, and trace match `tool_contract`.
2. No forbidden call, retry, provider, or state change occurred.
3. The output field names come from the literal prompt or schema, not metadata names.
4. The action values and types are exact and ordered.
5. The first byte will be `{` and the last byte will be `}`.
6. No backtick, fence, prose, prefix, or suffix will be emitted.
7. The response terminates immediately after the object.

Do not print this checklist or any reasoning in the final response.
