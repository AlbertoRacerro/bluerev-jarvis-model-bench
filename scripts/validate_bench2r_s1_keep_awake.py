from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for item in (ROOT, ROOT / "src"):
    if str(item) not in sys.path:
        sys.path.insert(0, str(item))

from scripts import validate_bench2r_hermes_s1 as s1

WRAPPER_PATH = ROOT / "scripts/run_bench2r_hermes_s1_awake.py"
WORKFLOW_PATH = ROOT / ".github/workflows/bench2r-hermes-s1-oneshot.yml"
FAILED_HELPER_PATH = ROOT / "scripts/bench2r_windows_keep_awake.ps1"


class KeepAwakeValidationError(RuntimeError):
    pass


def validate() -> dict[str, object]:
    _, marker, _, _ = s1.validate_execution(require_enabled=False)
    if marker.get("enabled") is not False:
        raise KeepAwakeValidationError("S1 marker must remain disabled during review")
    if not WRAPPER_PATH.is_file():
        raise KeepAwakeValidationError("in-process keep-awake wrapper is missing")
    if FAILED_HELPER_PATH.exists():
        raise KeepAwakeValidationError("failed PowerShell keep-awake helper remains present")

    wrapper = WRAPPER_PATH.read_text(encoding="utf-8")
    required_wrapper_tokens = {
        'ctypes.WinDLL("kernel32", use_last_error=True)',
        "SetThreadExecutionState",
        "ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED",
        "with keep_windows_awake():",
        "finally:",
        "_set_thread_execution_state(ES_CONTINUOUS)",
        "return base.capture(args.artifact_dir)",
    }
    missing = sorted(token for token in required_wrapper_tokens if token not in wrapper)
    if missing:
        raise KeepAwakeValidationError(f"keep-awake wrapper contract incomplete: {missing}")
    if "subprocess" in wrapper or "Start-Process" in wrapper:
        raise KeepAwakeValidationError("keep-awake wrapper spawns an external helper")

    workflow = WORKFLOW_PATH.read_text(encoding="utf-8")
    required_workflow_tokens = {
        "cancel-in-progress: true",
        "python -m scripts.run_bench2r_hermes_s1_awake capture",
        "python -m scripts.run_bench2r_hermes_s1 enforce",
        "if: always()",
    }
    missing_workflow = sorted(
        token for token in required_workflow_tokens if token not in workflow
    )
    if missing_workflow:
        raise KeepAwakeValidationError(
            f"S1 workflow keep-awake binding incomplete: {missing_workflow}"
        )
    forbidden_workflow_tokens = {
        "bench2r_windows_keep_awake.ps1",
        "Prevent Windows sleep during S1",
        "Restore Windows sleep policy",
    }
    present = sorted(token for token in forbidden_workflow_tokens if token in workflow)
    if present:
        raise KeepAwakeValidationError(f"obsolete PowerShell boundary remains: {present}")

    return {
        "schema_version": "bench.hermes-s1-keep-awake-validation.v1",
        "status": "ready",
        "execution_authorized": False,
        "marker_enabled": False,
        "in_process_keep_awake": True,
        "external_helper_process": False,
    }


def main() -> int:
    try:
        payload = validate()
        code = 0
    except (KeepAwakeValidationError, s1.HermesS1ValidationError, OSError) as exc:
        payload = {
            "schema_version": "bench.hermes-s1-keep-awake-validation.v1",
            "status": "invalid",
            "execution_authorized": False,
            "error_type": type(exc).__name__,
            "error": str(exc),
        }
        code = 2
    print(json.dumps(payload, indent=2, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
