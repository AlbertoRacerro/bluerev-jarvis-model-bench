# BENCH-2R Hermes S3A Windows runner audit

## Decision

No historical job is eligible for rerun.

The audit found five jobs with no runner assignment and no steps, but each belongs either to a superseded, preflight-invalid activation or to S3A-R1 batches made mathematically useless by the authoritative batch-0 failure. No Ollama-unavailable failure was found.

No workflow, marker, skill, finalizer, acceptance criterion, model setting, or production route was changed by this audit. Both S3A markers remain disabled and production remains `not_promoted`.

## Scope and method

The audit covered the observer-published S3A activation sequence, the authoritative S3A soak, both S3A-R1 activation SHAs, the latest authoritative R1 attempt, and both recovery workflows.

Classification is two-dimensional because the requested classes overlap:

- `A` or `B` records runner availability evidence.
- `C`, `D`, or `E` records the failure subtype.
- Therefore `A+D` and `A+E` are intentional classifications.

## Aggregate

| Classification | Jobs | Meaning |
|---|---:|---|
| A+D | 26 | Runner assigned; infrastructure/workflow failed before valid semantic result |
| A+E | 3 | Runner assigned; valid capture and artifact; semantic gate failed |
| A+pass | 4 | Runner assigned; relevant job completed successfully |
| B | 5 | Cancelled without runner assignment or steps |
| C | 0 | No evidence of Ollama being unavailable after runner startup |

Total jobs with full observer or Actions metadata: **38**.

## Run inventory

| Run | Attempt | SHA / role | Classification | Result |
|---:|---:|---|---|---|
| 29342851925 | 1 | `d4516d1` S3A activation | 5× A+D | All jobs reached runner; preflight failed; no capture |
| 29343772998 | 1 | `810400f` S3A activation | 5× A+D | All jobs reached runner; preflight failed; no capture |
| 29349268377 | 1 | `b2d7755` S3A activation | 4× A+D, 1× B | Four preflight failures; batch 4 never assigned |
| 29349791304 | 1 | `c30cf7f` S3A activation | 4× A+D, 1× B | PowerShell `PSSecurityException`; batch 4 never assigned |
| 29350222618 | 1 | `e522b3e` S3A activation | 4× A+D, 1× B | Marker validation drift; no capture |
| 29350762330 | 1 | `43fdd22` authoritative S3A | 2× A+E, 3× A+pass | Five valid captures and five main artifacts; semantic closeout remains failed |
| 29363488845 | 1 | `0aefc372` first R1 activation | 3× A+D | Closeout blob drift or cancellation during checkout; superseded |
| 29364133435 | 2 | `414c5ac` authoritative R1 | 1× A+E, 2× B | Batch 0 semantic failure; batches 1–2 unnecessary after early stop |
| 29364729407 | 1 | recovery v1 | 1× A+D | Runner active; expected workspace path absent |
| 29391937836 | 1 | recovery v2 | 1× A+pass | Full root scan succeeded; zero residual evidence found |

## Class-B jobs

The five jobs satisfying the raw class-B signature are recorded in `summary.json`. None is rerunnable:

1. Three are matrix batch-4 jobs from superseded S3A activations whose sibling jobs had already proved the activation invalid before capture.
2. Two are R1 batches 1 and 2. After batch 0 scored `0/4` on the strict negative ledger gate, the maximum possible final score was `8/12`, below the frozen `12/12` requirement.

## Evidence limitation

GitHub still exposes the attempt-1 preflight artifact for run `29364133435`, but the available connector returns only latest-attempt job metadata and no persisted observer snapshot for attempt 1 was found. This is recorded as a historical evidence gap, not silently inferred.

It does not change the decision: attempt 2 is the authoritative, fully captured execution, and rerunning the failed v1.2 configuration is expressly forbidden by the closeout.

## Next work

Proceed only with a non-executive v1.3 design slice:

- no marker activation;
- no self-hosted workflow;
- no Ollama call;
- no production adoption;
- fresh deterministic seeds;
- static rejection of Markdown fences;
- exact raw-JSON boundary;
- a later canary only after the static design is merged and reviewed.
