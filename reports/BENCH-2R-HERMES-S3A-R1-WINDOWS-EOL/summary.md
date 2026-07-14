# BENCH-2R Hermes S3A-R1 — Windows text blob normalization

## Failure evidence

Activation commit `0aefc372fc2ac95bc1467877d2bca68dc1abcbb5` created workflow run `29363488845` on `bluerev-bench-win`.

Batch 0 reached the durable preflight and uploaded both diagnostic files. The runtime validator returned:

- status: `invalid`;
- error type: `HermesS3ARepairDesignError`;
- error: `S3A closeout blob drifted`.

Capture was skipped. No model call or semantic experiment artifact was produced.

The marker was closed in commit `e0c69f2029e2f38d59d3ce0c4afba5e4befcd215`.

## Root cause

The R1 design and runtime validators computed Git blob SHA-1 directly from checkout bytes. The Windows checkout converted repository text from LF to CRLF, so immutable text files no longer matched their canonical Git blob hashes even though their semantic content was unchanged.

Expected digests were correct. The validator boundary was platform-dependent.

## Correction

`git_blob_sha` now:

1. reads raw bytes;
2. decodes UTF-8 text when possible;
3. normalizes CRLF and lone CR to LF;
4. computes the canonical Git blob SHA-1 over normalized bytes;
5. leaves non-UTF-8 binary bytes unchanged.

During R1 design validation, the runtime validator temporarily replaces the design validator's hash function with the same normalized implementation and restores the original function in `finally`.

## Regression coverage

- LF and CRLF forms of the same text produce the same Git blob SHA.
- The design hash monkeypatch is active only inside the Windows text boundary.
- The original design hash function is restored after an exception.
- Hosted Linux validation continues to use the same canonical expected digests.

## Safety

- No expected digest changed.
- No case, prompt, skill, model, sampling, finalizer, runner or workflow changed.
- Marker remains disabled.
- No automatic retry.
- No production promotion or skill replacement.
