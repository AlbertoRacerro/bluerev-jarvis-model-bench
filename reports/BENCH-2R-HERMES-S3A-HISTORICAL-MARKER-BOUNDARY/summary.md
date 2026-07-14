# BENCH-2R Hermes S3A — historical/live marker boundary

## Failure evidence

Activation `e522b3ec455faf4a563118cf96df65f62f16656a` reached the real Windows runner through `cmd.exe`. The durable preflight wrapper executed, wrote and uploaded both diagnostic files, then rejected before capture with:

`HermesS3AValidationError: S3A marker drifted or became enabled`.

No model call occurred.

## Root cause

The live runtime validator first invokes the immutable design validator. The design contract correctly requires its historical marker to remain `enabled=false`, but both validators were reading the same checkout file. During a reviewed activation that file is necessarily `enabled=true`.

The existing authorized test patched only `runtime.MARKER_PATH`; the design module continued reading the repository's disabled marker, so the real shared-file failure was not represented.

## Correction

The authoritative Windows boundary now replaces `runtime._historical_design_boundary` with a bounded context that:

- masks the runtime workflow for immutable design validation;
- supplies an exact temporary historical marker with `enabled=false`;
- restores the design workflow and marker paths in `finally`;
- leaves `runtime.MARKER_PATH` unchanged.

After immutable design validation completes, the live runtime gate reads the real marker and still requires `enabled=true` for execution.

## Regression coverage

- historical workflow and marker paths restore after exceptions;
- the historical marker exactly matches the reviewed disabled contract;
- a checkout where both runtime and design initially see the same enabled marker validates historical design first and live authorization second;
- all prior runtime tests remain nested inside the Windows boundary.

## Safety state

- Marker remains `enabled=false` in this slice.
- No model execution in this slice.
- No case, skill, finalizer, router, provider or model-weight change.
- Production remains `not_promoted`.
