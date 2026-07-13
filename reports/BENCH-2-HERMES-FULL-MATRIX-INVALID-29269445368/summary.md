# BENCH-2 Hermes full matrix — invalid infrastructure closeout

Run `29269445368` attempted the complete reviewed matrix: eight H4-qualified Lane 1 candidates, two cases, and three repetitions per pair.

## Decision

The entire run is invalid infrastructure evidence. It must not be used for semantic scoring, capability ranking, or candidate exclusion.

All 48 run records failed before model inference because `_run_once` attempted to write `raw-output.txt` before creating the per-run output directory. The common missing operation is:

```python
output_dir.mkdir(parents=True, exist_ok=True)
```

## Verified evidence

- All four GitHub artifact archives were downloaded and their SHA-256 digests matched GitHub.
- All top-level and per-run internal manifests matched their files byte-for-byte.
- Every report is bound to activation commit `554ea07482fe3755ee2fb5219d7e91040a9a65c0`, run `29269445368`, attempt `1`, and the reviewed BENCH-2 plan.
- All eight candidate aliases were created with `num_ctx 65536` and subsequently removed.
- No run produced valid model-inference or semantic evidence.

## Next action

Disable the one-shot marker, create all per-run output directories before the first artifact write, validate the regression on GitHub-hosted runners, and then launch a fresh one-shot run. Do not rerun the failed jobs against the old activation commit.
