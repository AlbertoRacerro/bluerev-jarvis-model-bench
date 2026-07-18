# Benchmark Status

This repository is an experimental qualification harness. It records model and Hermes
evidence; it does not own JarvisOS architecture or product priorities.

## Program status

| ID | Status | PR | Evidence-backed state |
|---|---|---:|---|
| BENCH-0 | merged | #1 | Foundation, manifests, inventory, and artifact controls. |
| BENCH-1 | merged | #96 | 60 accepted direct runs: 36 pass, 24 fail, 0 invalid. |
| H4 | merged | #104 | 8 candidates qualified at the required context; 2 did not. |
| BENCH-2 | merged | #134 | 48 completed stock-Hermes runs; no candidate admitted. |
| BENCH-2R/S1 | merged | #146 | Diagnostic stage completed; three candidates advanced. |
| BENCH-2R/S2 | merged | #150 | Governed Gemma stack passed 12/12 and advanced to shadow testing only. |
| BENCH-2R/S3A | merged | #166 | Infrastructure completed, but negative controls failed. |
| BENCH-2R/S3A-R1 | merged | #175 | Tool behavior improved; strict raw output remained 0/4. |
| BENCH-2R/S3A-R2 | blocked | #177 | Static design preserved. No further work is currently scheduled. |
| BENCH-3 | merged | #179 | Memory and routing test fixtures plus 24 explicit cases. Benchmark material only. |
| BENCH-2R/dialogic | cancelled | #180 | Closed without merge; branch retained for selective reuse in JarvisOS-owned work. |
| BENCH-3R/MR0 | cancelled | #182 | Closed without merge; incomplete branch retained as historical material. |
| BENCH-3B | blocked | — | Resume only for a specific evidence gap raised by active product work. |
| BENCH-4 | blocked | — | Resume only when a concrete routing decision lacks evidence. |
| BENCH-5 | blocked | — | Deferred until the first useful JarvisOS/BlueRev loop exists. |

## Current operating mode: maintenance

Effective after PRs #180 and #182 were closed on 2026-07-18:

1. No new benchmark architecture, design-hardening, runtime, or repair line starts by
   default.
2. Work resumes only when an active JarvisOS or BlueRev implementation names a specific
   decision, the missing evidence, and the smallest experiment that can resolve it.
3. The benchmark may test contracts decided elsewhere; it does not create JarvisOS ADRs,
   product policy, memory authority, routing authority, or production decisions.
4. Each experiment receives a fixed run budget or a two-day timebox and ends with one
   verdict: continue, pivot, or stop.
5. A second consecutive design-only PR in the same line requires runtime evidence, a
   terminal closeout, or an explicit parking decision from the prior PR.
6. New strict guards must identify the irreversible product risk they address. Other
   checks should remain diagnostic.
7. Any future model execution requires a separate explicit maintainer decision.

## Current evidence

- Current benchmark merge: `731de9de429589f468d6cb577bdeab11932c2bc8`
  from PR #179.
- Production status: **`not_promoted`**.
- H4 run `29260032005`: 8 qualified, 1 CPU offload, 1 context mismatch.
- BENCH-2 run `29309289661`: 48 completed runs; no stock candidate admitted.
- S2 run `29335974597`: 36/36 infrastructure-valid; the governed Gemma stack passed
  its 12/12 admission set and advanced only to shadow testing.
- S3A run `29350762330`: 50/50 infrastructure-valid; 31/50 full shadow pass and
  1/20 negative-control pass.
- S3A-R1 run `29364133435`, attempt 2: 9/9 infrastructure-valid; strict raw output
  remained 0/4 because responses were fenced.

## BENCH-3 static contract

- Reviewed head: `1f7746362a8ae147f82ab355e9452b200f8bb2e8`.
- Hermes version `0.18.2`, commit
  `73b611ad19720d70308dad6b0fb64648aaadc216`.
- Validation run `29658898042`; artifact `8433709862`; digest
  `sha256:dedca6bca97e07f92176dad057b8e9db79a318f0bced7c1fe04eaff6f0d2fbab`.
- Candidate blobs:
  - memory skill `48b3c07168aa143ecfa2fb63ebbbb0da070c1a1e`;
  - routing skill `cb0b9b348cacd5f014e70790fd6410e120b5a7ba`;
  - bundle `59bc83ff4079e2e956237c4097ba0d7472f06e09`;
  - case contracts `65072ade82917f97055a7eba4726bc2796e1ba91`.
- These remain test fixtures and have not been adopted.

## Findings retained

- Memory, session history, skills, project context, and performance evidence have
  different roles and authority.
- Child agents may propose shared-memory changes but should not commit them.
- Routing evidence must be capability- and task-specific, not a global model score.
- Logical lanes do not imply one resident checkpoint per lane; hardware residency and
  swap cost are separate constraints.
- Native dialogue and trajectories are primary orchestration evidence. Exact output
  belongs at explicit terminal protocol boundaries.
- Hermes profiles isolate state but are not filesystem sandboxes.

## Reactivation template

A future benchmark request must state:

- the active JarvisOS or BlueRev decision being blocked;
- the evidence already available and the exact missing evidence;
- the smallest candidate/control experiment;
- the run budget or two-day timebox;
- the terminal outcomes: continue, pivot, or stop;
- the separate confirmation boundary for model execution.