# BENCH-2R Windows runner audit

## Decision

No historical job is justified for rerun.

The audit found jobs with the transport signature of an offline or unavailable runner, but every such job was either cancelled by an already-invalid matrix run, superseded by a later corrected activation, or intentionally left unexecuted after a mathematically terminal early stop. No missing job can change an accepted closeout or reconstruct evidence that is still required.

Production remains `not_promoted`. S3A and S3A-R1 markers remain disabled. No skill, model weight, routing, finalizer, case, or acceptance criterion is changed by this audit.

## Classification rules

- **A — runner certainly available:** runner assigned, setup succeeded, checkout or another operational step started.
- **B — possible runner unavailable:** no runner, no steps, and cancellation while queued.
- **C — runner available, Ollama absent:** preflight reached and loopback Ollama/model access failed.
- **D — infrastructure failure after start:** runner available but checkout, preflight, shell, artifact, validator, or recovery boundary failed.
- **E — semantic failure:** preflight and capture succeeded, evidence artifact is valid, and the semantic enforcer rejected the result.

## Audited inventory

| Workflow run | Head SHA / purpose | Jobs and classification | Verifiable outcome | Rerun decision |
|---|---|---|---|---|
| `29342851925` | `d4516d167527c24a41ada8f72233d730b8ddfb42` S3A activation | `87118864263` b0 D; `87118864458` b1 D; `87118864224` b2 D; `87118864192` b3 D; `87118864279` b4 D | Every job had `bluerev-bench-win`, setup and checkout succeeded, preflight failed, capture was skipped, and no main artifact existed. The following fix normalized Windows Git/text digests. | No: superseded infrastructure-invalid activation. |
| `29343772998` | `810400f7b1e5b7659daa16e8ce3516682ce95ada` S3A activation | `87122027481` b0 D; `87122027510` b1 D; `87122027499` b2 D; `87122027492` b3 D; `87122027446` b4 D | Runner assigned and operational for all jobs. Preflight failed before capture; evidence at the time was insufficient to recover a narrower cause. | No: obsolete opaque preflight attempt, followed by evidence-persistence fixes. |
| `29349268377` | `b2d775541ef3617ab4226e7ca922bc5a8f0272f7` S3A activation | b0 `87140999529` D; b1 `87140999417` D; b2 `87140999498` D; b3 `87140999484` D; b4 `87140999505` B | Four jobs reached setup/checkout and failed preflight. Batch 4 had no runner and no steps, but was cancelled inside the already-invalid matrix run. | No: the B job cannot repair the failed activation and later activations supersede it. |
| `29349791304` | `c30cf7f35022bfede5835e72acbcf7d4355ebf69` S3A activation | b0 `87142766946` D; b1 `87142766845` D; b2 `87142766863` D; b3 `87142766874` D; b4 `87142766802` B | Started jobs failed because GitHub Actions generated PowerShell scripts were blocked by `PSSecurityException`. Batch 4 had no runner or steps. | No: shell boundary was corrected to `cmd`; this activation is obsolete. |
| `29350222618` | `e522b3ec455faf4a563118cf96df65f62f16656a` S3A activation | b0 `87144249610` D; b1 `87144249487` D; b2 `87144249447` D; b3 `87144249455` D; b4 `87144249471` B | Started jobs reached preflight; validation reported marker drift/enabled-state mismatch. Batch 4 had no steps. | No: invalid activation, superseded by the authoritative corrected run. |
| `29350762330` | `43fdd22252d89c1b83b5190e6ef41dbf0bfac625` authoritative S3A | b0 `87146093843` E; b1 `87146093847` A; b2 `87146093752` E; b3 `87146093781` A; b4 `87146093787` A | All five jobs had runner, setup, checkout, preflight, capture and artifact upload success. All 50 runs were infrastructure-valid. Two jobs failed only at semantic enforcement; three passed their per-batch enforcer. | No: authoritative semantic closeout; identical rerun forbidden. |
| `29363488845` | `0aefc372fc2ac95bc1467877d2bca68dc1abcbb5` first S3A-R1 activation | b0 `87189174164` D; b1 `87189174183` D; b2 `87189174166` D | Runner assigned. Batches 0 and 1 failed preflight with S3A closeout blob/EOL drift; batch 2 began setup and was cancelled during checkout. Capture did not run. | No: source-binding fix produced a new activation SHA; old run is obsolete. |
| `29364133435`, attempt 2 | `414c5ac259d3ac892f5ca2046c23d9074ae86a27` authoritative S3A-R1 | b0 `87278458894` E; b1 `87278459381` early-stop; b2 `87278480900` early-stop | Batch 0 ran on `bluerev-bench-win` / `PC_DI_ALBERTO`: setup, checkout, preflight, capture and both uploads succeeded; enforcer failed after 9/9 runs. Artifact `8335243161` and its 145-entry manifest were valid. Batches 1–2 were intentionally cancelled because the maximum possible score had fallen to 8/12 against a 12/12 gate. | No: semantic failure for b0; intentional mathematical early-stop for b1–b2. |
| `29364729407` | read-only batch-0 recovery | `87193346234` D | Runner available. Recovery looked for a workspace-relative report that no longer existed; artifact upload correctly failed on no files. | No: obsolete recovery, later replaced by exhaustive scan. |
| `29391937836` | exhaustive read-only recovery v2 | `87277121166` A | Runner available; scan and upload succeeded. It found zero residual artifact directories, temporary directories, or diagnostic files. | No: successful diagnostic with no evidence to recover. |

## Additional observer finding

The closeout observer was once bound to `c1cce366128b1678fd6fc0e2a5718b97dad7a9fc`. That SHA does not resolve to a repository commit, so it cannot identify a lost benchmark run. This is an obsolete observer-binding defect, not evidence of runner or model failure.

## Rescheduling result

- Class B signatures found: three historical S3A matrix jobs (`29349268377` b4, `29349791304` b4, `29350222618` b4).
- Class C jobs found: zero.
- Class D jobs found: several preflight/shell/recovery failures, all superseded or diagnostic-only.
- Class E jobs found: authoritative S3A semantic batches and authoritative S3A-R1 batch 0.
- Jobs rerun: zero.

A rerun would either repeat a forbidden semantic configuration, execute an obsolete preflight boundary, or spend compute after an irrecoverable acceptance failure. The correct next action is a new design slice with a distinct skill candidate and fresh seeds.

## Residual limitations

The GitHub connector exposes the latest job list for a workflow run rather than an arbitrary historical-attempt endpoint. Attempt-specific conclusions above are therefore restricted to persisted observer/closeout evidence and the authoritative attempt-2 job logs. This limitation does not affect the rerun decision: every unresolved older attempt is superseded by a complete authoritative artifact or by a later corrected activation.
