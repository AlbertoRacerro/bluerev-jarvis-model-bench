# H3 primary 32K qualification

Status: **complete**.

- H3 plan: `0bf7838ef0199be1dcf89122bbdedaf17ca4253223eafd0b89472bdcba3d7c12`
- Execution commit: `202214c45a9a6952600bbd2d621697fcf349db25`
- Workflow run: `29106127334`, valid attempts `14`–`18`
- Result: **10/10 qualified full-VRAM at 32K**

| # | Model | 32K status | VRAM | Gen tok/s |
|---:|---|---|---:|---:|
| 1 | `gemma4:12b-it-qat` | `qualified_32k` | 100.0% | 58.725 |
| 2 | `hf.co/empero-ai/Qwable-9B-Claude-Fable-5-GGUF:Q4_K_M` | `qualified_32k` | 100.0% | 71.194 |
| 3 | `hf.co/empero-ai/Qwythos-9B-Claude-Mythos-5-1M-GGUF:Q4_K_M` | `qualified_32k` | 100.0% | 73.489 |
| 4 | `hf.co/GnLOLot/MiniCPM5-1B-Claude-Opus-Fable5-Thinking-GGUF:Q4_K_M` | `qualified_32k` | 100.0% | 277.189 |
| 5 | `hf.co/tvall43/Qwen3.6-14B-A3B-FableVibes-GGUF:Q4_K_M` | `qualified_32k` | 100.0% | 101.336 |
| 6 | `hf.co/yuxinlu1/gemma-4-12B-agentic-fable5-composer2.5-v2-3.5x-tau2-GGUF:Q4_K_M` | `qualified_32k` | 100.0% | 51.595 |
| 7 | `hf.co/yuxinlu1/gemma-4-12B-coder-fable5-composer2.5-v1-GGUF:Q4_K_M` | `qualified_32k` | 100.0% | 52.077 |
| 8 | `qwen3:8b` | `qualified_32k` | 100.0% | 84.434 |
| 9 | `qwythos-hermes-64k:latest` | `qualified_32k` | 100.0% | 72.705 |
| 10 | `qwythos-hermes-safe:latest` | `qualified_32k` | 100.0% | 71.174 |

## Gate outcome

All ten candidates that passed H2 at 16K remained fully resident in VRAM at an actual 32768-token Ollama context. No candidate was moved to an offload or failure lane.

## Evidence boundary

All five archives matched GitHub artifact SHA-256 metadata byte-for-byte. Each runtime report was bound to `refs/heads/main`, checked-out commit `202214c45a9a6952600bbd2d621697fcf349db25`, a clean tracked tree, the immutable H2 closeout, and the fixed H3 plan. Runtime artifact manifests and cleanup attestations passed.

Attempts 11–13 are prerequisite-failure evidence only; they executed no model.

This is hardware/runtime qualification, not semantic ranking.
