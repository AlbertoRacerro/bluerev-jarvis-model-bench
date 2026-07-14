from __future__ import annotations

import argparse
import ctypes
import os
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from scripts import run_bench2r_hermes_s1 as base

ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001
ES_DISPLAY_REQUIRED = 0x00000002


class KeepAwakeError(RuntimeError):
    pass


def _set_thread_execution_state(flags: int) -> int:
    """Set the Windows execution-state flags for the current Python thread."""
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    function = kernel32.SetThreadExecutionState
    function.argtypes = [ctypes.c_uint32]
    function.restype = ctypes.c_uint32
    result = int(function(ctypes.c_uint32(flags)))
    if result == 0:
        error = ctypes.get_last_error()
        raise KeepAwakeError(f"SetThreadExecutionState failed: winerror={error}")
    return result


@contextmanager
def keep_windows_awake() -> Iterator[dict[str, object]]:
    """Prevent system/display sleep while the long-running capture process lives."""
    if os.name != "nt":
        yield {"platform": os.name, "active": False, "reason": "non_windows"}
        return

    requested = ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED
    previous = _set_thread_execution_state(requested)
    state = {
        "platform": os.name,
        "active": True,
        "requested_flags": requested,
        "previous_flags": previous,
    }
    print(
        "BENCH-2R keep-awake active "
        f"(requested=0x{requested:08X}, previous=0x{previous:08X}).",
        flush=True,
    )
    try:
        yield state
    finally:
        restored_previous = _set_thread_execution_state(ES_CONTINUOUS)
        print(
            "BENCH-2R keep-awake released "
            f"(restore_result=0x{restored_previous:08X}).",
            flush=True,
        )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run BENCH-2R Hermes S1 capture while preventing Windows sleep."
    )
    parser.add_argument("mode", choices=("capture",))
    parser.add_argument("--artifact-dir", type=Path, default=base.DEFAULT_ARTIFACTS)
    args = parser.parse_args()
    try:
        with keep_windows_awake():
            return base.capture(args.artifact_dir)
    except Exception as exc:
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
