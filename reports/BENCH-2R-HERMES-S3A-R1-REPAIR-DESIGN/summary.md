# BENCH-2R Hermes S3A-R1 — bounded skill repair design

## Source failure

S3A closed as `shadow_soak_failed` on workflow run `29350762330`:

- infrastructure valid: `50/50`;
- nominal deterministic finalization: `30/30`;
- shadow pass: `31/50`;
- negative-control shadow pass: `1/20`;
- negative ledger-shape failures: `19/20`;
- missing timeout-tool invocations: `3/10`.

The closeout is immutable and remains bound to merge commit `b1865920bc4568f9c8aa99ab9935750c77dd6b08`. Production is `not_promoted`.

## Root-cause evidence

Native Hermes trajectories show two distinct failures:

1. Skill v1.1 tells the model to preserve a contract-supplied `required_actions` list. Gemma interprets the metadata key as the final output field, despite the task prompt requiring an `actions`-only object.
2. In three timeout runs, Gemma emitted a textual `call_tool` ledger label without producing any `shadow_timeout_probe` tool trace.

The finalizer and `negative_output_ledger_only` gate are not weakened. They correctly exposed these failures.

## Repair candidate

A separate, non-production skill candidate is added:

- name: `bounded-tool-orchestration`;
- version: `1.2.0`;
- blob: `07cb574153d1730cf041ce6f546c8d9f3aaae544`;
- production skill v1.1 remains unchanged.

The candidate adds two generic rules:

- response-contract property names are metadata unless the task prompt or explicit final schema names them as output fields;
- a ledger label such as `call_tool` never satisfies `tool_contract.exact_calls`; a real tool response must be observed before final output.

The candidate contains no case IDs, held-out values, timeout tokens, or benchmark-specific result literals.

## Paired experiment

Only the skill source may differ between arms.

| Arm | Skill | Role |
|---|---|---|
| `control_v1_1` | v1.1.0 | paired observational control |
| `repair_v1_2` | v1.2.0 candidate | admission candidate |

Fixed seeds are derived mechanically from the first three 8-hex chunks of the S3A closeout merge SHA modulo `1,000,000`:

- `371872`;
- `665465`;
- `623659`.

These do not reuse S3A seeds.

Each seed batch contains:

- control: two negative cases × two repetitions = 4 runs;
- repair: two negative cases × two repetitions = 4 runs;
- repair: one nominal sentinel = 1 run.

Total: `27` runs across three serial batches.

## Acceptance

The repair arm must achieve all of the following:

- negative tool sequence exact: `12/12`;
- negative ledger-only output exact: `12/12`;
- negative fail-closed pass: `12/12`;
- negative shadow pass: `12/12`;
- real timeout-tool invocation: `6/6`;
- nominal sentinel shadow pass: `3/3`;
- no forbidden tool, retry, external provider, JarvisOS, or non-loopback network use.

The control arm is evidence, not an acceptance gate. The repair arm may not underperform control on any paired gate.

## Decision boundary

This slice is design-only:

- no runner;
- no self-hosted workflow;
- no model execution;
- no case prompt changes;
- no model or sampling changes;
- no finalizer or acceptance weakening;
- no automatic skill replacement;
- no weight update;
- no production promotion.

A passing R1 experiment would permit only the design of a fresh-seed full soak. It would not admit skill v1.2 directly to production.
