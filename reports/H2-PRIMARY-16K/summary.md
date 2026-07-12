# H2 primary 16K qualification

Status: **complete**.

- Source H1 artifact: `6458a0fcce21bf74850ced340f0172089c67143955af2c6177696d1e45045540`
- Bound H2 plan: `cce4863f87520dae70ea97fcd75a88d4ada0dff874202376cc9223ea6c29868a`
- Execution commit: `8c6b73d8263c0603dfd286debec3bd4c3377746f`
- Workflow run: `29106127334`, attempts `7`–`10`
- Result: **10 qualified for primary 32K**, **2 moved to secondary offload**

| # | Model | 16K status | VRAM ratio | Gen tok/s |
|---:|---|---|---:|---:|
| 1 | `deepseek-coder-v2:16b` | `cpu_offload` | 73.1% | 16.747 |
| 2 | `gemma4:12b-it-qat` | `qualified_16k` | 100.0% | 25.648 |
| 3 | `hf.co/empero-ai/Qwable-9B-Claude-Fable-5-GGUF:Q4_K_M` | `qualified_16k` | 100.0% | 33.225 |
| 4 | `hf.co/empero-ai/Qwythos-9B-Claude-Mythos-5-1M-GGUF:Q4_K_M` | `qualified_16k` | 100.0% | 32.546 |
| 5 | `hf.co/GnLOLot/MiniCPM5-1B-Claude-Opus-Fable5-Thinking-GGUF:Q4_K_M` | `qualified_16k` | 100.0% | 97.693 |
| 6 | `hf.co/tvall43/Qwen3.6-14B-A3B-FableVibes-GGUF:Q4_K_M` | `qualified_16k` | 100.0% | 41.610 |
| 7 | `hf.co/yuxinlu1/gemma-4-12B-agentic-fable5-composer2.5-v2-3.5x-tau2-GGUF:Q4_K_M` | `qualified_16k` | 100.0% | 23.014 |
| 8 | `hf.co/yuxinlu1/gemma-4-12B-coder-fable5-composer2.5-v1-GGUF:Q4_K_M` | `qualified_16k` | 100.0% | 23.171 |
| 9 | `qwen3:14b` | `cpu_offload` | 84.5% | 11.094 |
| 10 | `qwen3:8b` | `qualified_16k` | 100.0% | 82.255 |
| 11 | `qwythos-hermes-64k:latest` | `qualified_16k` | 100.0% | 72.726 |
| 12 | `qwythos-hermes-safe:latest` | `qualified_16k` | 100.0% | 72.551 |

## Gate outcome

Primary 32K candidates are exactly the ten entries classified `qualified_16k` in `summary.json`. The two `cpu_offload` entries remain available for a separate secondary lane but are not promoted.

## Evidence boundary

All four archives matched the GitHub artifact SHA-256 values byte-for-byte. Each report was bound to `refs/heads/main`, checked out commit `8c6b73d8263c0603dfd286debec3bd4c3377746f`, a clean tracked tree, the immutable H1 source, and the fixed H2 plan. All candidate cleanup attestations and artifact manifests passed.

This is hardware/runtime qualification only; it is not a semantic quality ranking.
