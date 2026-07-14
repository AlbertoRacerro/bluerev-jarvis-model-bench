# BENCH-2R Hermes S3A — Windows source-digest preflight fix

## Failure evidence

The first S3A activation, workflow run `29343117187`, failed in the authorized runtime validation step on the real self-hosted Windows runner before capture. No model call was made and no run artifact was produced, so the failed workflow contributes no semantic model evidence.

The same runtime contract had passed hosted Ubuntu validation. The remaining platform-specific boundary was source binding: S3A computed Git blob identifiers from raw checked-out file bytes, while Windows may materialize repository text with CRLF line endings. Git blob identities are based on repository LF content, so a raw-byte calculation can reject an otherwise exact checkout.

## Minimal correction

A separate Windows validation boundary now:

- decodes UTF-8 repository text;
- normalizes CRLF and lone CR to LF;
- computes the Git blob SHA from the normalized bytes;
- preserves raw bytes for non-UTF-8 files;
- applies the same normalized hash function to both the runtime plan bindings and the historical S3A design bindings;
- replaces the live workflow validator with a semantic validator bound to the new authoritative command;
- restores all monkeypatches in `finally`.

The self-hosted workflow now calls:

```text
python -m scripts.validate_bench2r_hermes_s3a_windows --require-enabled
```

The keep-awake capture wrapper enters the same Windows boundary before invoking capture, so the internal runtime preflight cannot regress to the raw-byte validator after the workflow step passes.

## Regression coverage

Hosted CI now verifies:

- LF and CRLF variants produce the same Git blob SHA;
- runtime and design hash functions are both patched and restored;
- the live disabled workflow validates through the Windows boundary;
- the old non-normalized validator command is absent;
- the complete existing S3A runtime test suite passes while nested inside the Windows boundary;
- Python compilation and validation evidence remain persisted on failure.

## Safety state

- The S3A marker is reset to `enabled=false`.
- The invalid run is not retried automatically.
- Model, profile, cases, skill, finalizer, tool fixture and acceptance criteria are unchanged.
- No production router or model-weight change is introduced.
- Production remains `not_promoted`.
- A new marker-only activation commit is required after this fix is merged.
