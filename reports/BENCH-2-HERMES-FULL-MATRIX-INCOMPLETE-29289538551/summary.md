# BENCH-2 Hermes full matrix v4 — incomplete closeout

Workflow run `29289538551`, attempt `1`, was bound to activation commit `0078c74a22bc1943c4188018923d14b4b8211b5e`.

## Final state

- Batch 0 was interrupted by runner disconnection and produced no artifact.
- Batch 1 was cancelled during capture and published one partial artifact.
- Batches 2 and 3 were cancelled before execution.
- The matrix is incomplete and must not be used for candidate comparison, ranking, or exclusion.

## Preserved partial observation

The batch-1 archive SHA-256 matched GitHub and its internal per-run manifest verified byte-for-byte. It contains one completed run:

- Candidate: `qwythos-mythos-9b`
- Case: `ho-tools-hermes-lookup-001`
- Repetition: `1`
- Infrastructure: valid at context `65536`, full VRAM, ratio `1.0`
- Tool call and trace: exact
- Semantic result: fail
- Reason: output schema mismatch; the model returned `{"status":"complete","final":"62915387","code":"BRAVO-08"}` instead of the required exact actions/final contract.

This observation is retained for audit only and is not a substitute for the fresh complete matrix.

## Decision

Reset the one-shot marker to disabled and launch a new single-attempt matrix covering all eight H4-qualified candidates.
