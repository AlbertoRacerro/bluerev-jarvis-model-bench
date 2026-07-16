# BENCH-2R Hermes S3A-R1 closeout

## Decision

S3A-R1 is closed as **failed after the first authoritative batch**. Candidate skill v1.2 is not adopted, production remains `not_promoted`, and no model weights or routing are changed.

## Runner availability audit

No authoritative test failed because the self-hosted runner was not listening.

Attempt 2 of workflow run `29364133435` executed on `bluerev-bench-win` / `PC_DI_ALBERTO`:

- checkout: success;
- preflight: success;
- preflight upload: success;
- capture: success;
- artifact upload: success;
- enforce: failure.

The enforce failure occurred only after all nine batch-0 runs completed. It is therefore a semantic acceptance failure, not a runner-availability failure.

## Authoritative evidence

- execution SHA: `414c5ac259d3ac892f5ca2046c23d9074ae86a27`;
- workflow run: `29364133435`, attempt `2`;
- job: `87278458894` (`paired-repair (0)`);
- seed: `371872`;
- main artifact: `8335243161`;
- artifact digest: `sha256:4f9d5ecad31d8e422e804a64f270137551a6381b01753358288c99179c6b942c`;
- internal manifest: 145 entries, zero missing files and zero digest/size mismatches;
- marker closed in `bc72bfa719d74a257f447d091f388cdcbd0c8f4d`.

## Batch-0 results

| Metric | Control v1.1 | Repair v1.2 |
|---|---:|---:|
| Runs | 4 | 5 |
| Infrastructure valid | 4/4 | 5/5 |
| Negative tool sequence exact | 4/4 | 4/4 |
| Negative fail-closed pass | 4/4 | 4/4 |
| Negative ledger-only exact | 0/4 | 0/4 |
| Timeout tool invocation | 2/2 | 2/2 |
| Nominal sentinel | — | 1/1 |
| Shadow pass | 0/4 | 1/5 |

## What v1.2 improved

The control arm returned the metadata-shaped field `required_actions`. The repair arm instead produced the correct semantic object:

```json
{"actions":["call_tool","stop"]}
```

However, all four repair negative outputs wrapped that object in Markdown JSON fences. The reviewed contract requires a strict raw JSON object with no prose or fencing. Consequently:

- `raw_output_strict_json`: 0/4;
- `negative_output_ledger_only`: 0/4;
- repair batch pass: false.

The timeout tool was genuinely invoked in both repair timeout runs, and the nominal sentinel passed. These are useful partial improvements but do not satisfy R1.

## Why batches 1 and 2 were not rescheduled

R1 acceptance requires `12/12` negative ledger-only passes across three batches. After batch 0, v1.2 had `0/4`; even perfect remaining batches could reach only `8/12`. Additional runs could not reverse the decision and would only consume local compute.

The two remaining jobs were therefore intentionally left cancelled. This is an early-stop decision, not a missing-runner retry omission.

## Next allowed work

A new skill candidate may explicitly require raw JSON with no Markdown fences. It must be tested as a new experiment with fresh seeds. Repeating v1.2 with the same configuration is not allowed.
