# H4 Hermes minimum 64K closeout

## Decision

H4 is **closed** on trusted workflow run `29260032005`, attempt `1`, execution commit `a2926cc93abb1a64874352c4508e8c97b0b6007f`.

All ten H3-qualified Lane 1 candidates were attempted. BENCH-1 direct semantic outcomes were not used as an admission gate.

- **8** candidates are `qualified_64k` and may enter the stock Hermes Agent 0.18.2 runtime canary.
- **1** candidate is `cpu_offload` and is excluded by the reviewed no-offload policy.
- **1** candidate is `context_mismatch` and exposes only 40 960 tokens, below Hermes' 64 000-token hard minimum.
- **0** candidates failed to load.

## Results

| Seq. | Candidate | H4 status | Observed context | GPU residency |
|---:|---|---|---:|---:|
| 0 | `gemma4-12b-it-qat` | `qualified_64k` | 65 536 | 100.00% |
| 1 | `qwable-9b-fable5` | `qualified_64k` | 65 536 | 100.00% |
| 2 | `qwythos-mythos-9b` | `qualified_64k` | 65 536 | 100.00% |
| 3 | `minicpm5-fable-1b-control` | `qualified_64k` | 65 536 | 100.00% |
| 4 | `qwen3.6-fablevibes-14b-a3b` | `cpu_offload` | 65 536 | 95.50% |
| 5 | `gemma4-fable-agentic-12b` | `qualified_64k` | 65 536 | 100.00% |
| 6 | `gemma4-fable-coder-12b` | `qualified_64k` | 65 536 | 100.00% |
| 7 | `qwen3-8b` | `context_mismatch` | 40 960 | — |
| 8 | `qwythos-hermes-64k` | `qualified_64k` | 65 536 | 100.00% |
| 9 | `qwythos-hermes-safe` | `qualified_64k` | 65 536 | 100.00% |

## Evidence integrity

All five jobs completed successfully. The five downloaded archives matched GitHub's SHA-256 metadata byte-for-byte. Their internal manifests, candidate identities, source bindings, exact workflow SHA, test/probe exit codes, cleanup attestations, and local-only boundaries were verified.

The accepted evidence is bound to:

- workflow run `29260032005`, attempt `1`;
- execution commit `a2926cc93abb1a64874352c4508e8c97b0b6007f`;
- H4 plan SHA-256 `b94032a9104316f2e05cb4c1b8934772fee66804dd609d84a570d4f4e940e146`;
- Hermes Agent `0.18.2`, commit `73b611ad19720d70308dad6b0fb64648aaadc216`.

## Invalid prerequisite run

Run `29257990674` is retained only as infrastructure-failure evidence. Windows PowerShell policy blocked temporary `.ps1` scripts before Python or any model executed. It contributes no candidate result.

## BENCH-2 consequence

The historical BENCH-2 v1 plan remains non-executable because it requires 32 768 tokens and assumes all ten models can enter stock Hermes. BENCH-2 v2 must:

1. retain evidence that all ten Lane 1 models were attempted at H4;
2. admit only the eight `qualified_64k` candidates;
3. require an actual 65 536-token runtime context;
4. keep BENCH-1 outcomes post-hoc and non-gating;
5. preserve capability-specific results and forbid a global composite score.
