# Final benchmark objective

## Decision to support

Select local models that can plausibly deliver professional-grade, reliable work on the available Windows workstation in two primary areas:

1. orchestration inside the pinned local Hermes runtime;
2. coding, both as a direct model and as a Hermes-driven model.

A fast smoke result is not sufficient evidence. Final recommendations require severe, repeated, held-out evaluation with deterministic authority wherever possible.

## Primary evaluation lanes

### Hermes orchestration

Evaluate the model while it actually drives Hermes in a disposable local workspace. Required capability families include:

- planning and task decomposition;
- route and worker selection;
- bounded delegation;
- critic use and disagreement handling;
- tool selection and sequencing;
- recovery after failed commands or tests;
- budget, timeout, and retry discipline;
- sensitivity and local-only boundaries;
- correct stopping behaviour;
- final synthesis grounded in worker and tool evidence.

Direct structured-response tests remain useful only as harness calibration and controls. They do not establish orchestration quality.

### Coding

Evaluate both direct-model coding and Hermes-mediated coding. Priority stacks are those used by JarvisOS and its operational environment:

1. Python;
2. PowerShell and Windows automation;
3. TypeScript / JavaScript;
4. YAML, JSON, GitHub Actions, and configuration contracts;
5. SQL where relevant.

C, C++, and MATLAB are secondary expansion lanes after the primary benchmark is stable.

Coding tasks must include bug diagnosis, bounded multi-file changes, tests, code review, failure recovery, regression avoidance, and refusal to claim success when tests or evidence are incomplete.

## Candidate policy

- Consider every locally installed model, including candidates currently marked disabled in the registry.
- Explicitly exclude Gemma 4 27B from the initial matrix.
- Do not infer suitability from parameter count or model-file size alone.
- Measure actual Ollama GPU residency and operational behaviour on the benchmark runner.
- Models that do not fit fully in the 12 GB VRAM envelope are deferred from the primary all-GPU comparison, not permanently discarded.
- A later secondary lane may measure promising partial-offload models if the expected capability gain appears worth the latency and comparability cost.

## Hardware qualification stages

### H1 — residency inventory

For every installed model except explicit exclusions:

- unload other Ollama models;
- load one candidate at a time;
- use a fixed local prompt and fixed 4K context profile;
- record Ollama `size`, `size_vram`, residency ratio, load duration, termination data, and NVIDIA memory snapshots;
- unload and verify cleanup before continuing;
- preserve per-model evidence and a manifest.

Classification:

- `full_vram`: at least 98% of Ollama-reported loaded size is resident in VRAM;
- `partial_vram`: some but less than 98% is resident in VRAM;
- `cpu_only`: no reported VRAM residency;
- `load_failed`: the bounded load or probe did not complete;
- `excluded`: explicit user exclusion.

### H2 — operational context qualification

Run only after H1. Probe shortlisted models at realistic contexts, initially 16K and then 32K where useful. Record throughput, VRAM residency, CPU offload, timeout behaviour, and stability. Context qualification is separate from weight-residency qualification.

## Benchmark construction

### Calibration

Build small adversarial slices first to identify harness defects. Calibration results are never used for final ranking.

### Core benchmark

Use task families rather than many cosmetic prompt variants. Include normal, ambiguous, adversarial, recovery, and correct-no-action cases. Preserve exact workspace snapshots and deterministic validators.

### Held-out validation

Reserve unseen tasks and repositories for the shortlist. Do not tune prompts, parsers, or validators against held-out outputs. Final professional-grade claims require held-out success.

## Professional-grade evidence standard

No single aggregate score is sufficient. Report at least:

- task success rate;
- critical safety violation count;
- invalid-output rate;
- unnecessary action and tool-call rate;
- recovery success rate;
- regression rate;
- latency and token throughput;
- consistency across repetitions;
- results separated by capability, language, direct lane, and Hermes lane.

A model cannot be labelled professional-grade when it has an unresolved critical safety violation, fabricated success, uncontrolled loop, or material regression, even if its average score is high.

## Repetition and reliability

- Use deterministic or low-variance settings where the lane permits it.
- Run multiple repetitions for every candidate-task family used in comparative claims.
- Use checkpointed sequential campaigns on the single-GPU runner.
- A semantic model failure does not stop the remaining campaign.
- An infrastructure-integrity failure stops or quarantines affected results.

## Hermes sandbox authorization

Hermes may operate only in disposable benchmark workspaces. It may:

- read and modify benchmark fixture files;
- run local Python, PowerShell, test, and git-diff commands;
- use bounded local worker and critic roles;
- create patches and reports.

It may not access JarvisOS, external providers, credentials, secrets, paid services, or unrelated user state.

## Self-improvement

Self-improvement is not part of the first professional-grade decision. A later isolated lane may evaluate proposals through independent criticism, deterministic replay, held-out regression testing, and explicit promotion boundaries. A model receives no credit merely for proposing or claiming an improvement.

## Completion criterion

The first benchmark milestone is complete when it provides severe, reproducible, held-out evidence sufficient to choose models for reliable Hermes orchestration and reliable coding on the measured hardware. The number of tasks is secondary to task-family coverage, validator quality, repetitions, and held-out integrity.
