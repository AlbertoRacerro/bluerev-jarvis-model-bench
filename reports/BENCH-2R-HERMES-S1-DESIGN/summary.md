# BENCH-2R Hermes S1 observed preflight design

## Scope

S1 executes every H4-qualified candidate on both frozen diagnostic cases under two arms:

- model-specific profile only;
- the same profile with `bounded-tool-orchestration` explicitly expanded through Hermes' pinned skill mechanism.

Eight candidates, two cases, two arms and one tuning seed produce 32 diagnostic runs. S1 cannot admit a model and cannot update weights.

## New evidence

Each run preserves:

- raw final output;
- parsed output;
- real plugin tool trace;
- Hermes worker result including message history, API-call count and `turn_exit_reason`;
- native Hermes trajectory JSONL;
- effective config;
- model profile and alias parameter attestation;
- GPU residency and cleanup evidence.

The worker calls pinned Hermes internals directly so the skill arm is genuinely expanded before `run_conversation`; a slash command is never passed through as ordinary task text.

## Classification correction

Model-call budget violations, incomplete completion and invalid tool choices are semantic failures. They do not invalidate infrastructure when the Hermes/Ollama protocol completed and the evidence was captured. Protocol exceptions such as the MiniCPM HTTP 400 remain infrastructure/protocol invalidity.

## Execution gate

The self-hosted workflow is push-only on `main`, commit-prefix guarded, serial, and bound to a disabled marker. This design PR cannot execute models. A separate reviewed activation commit is required after hosted validation passes.
