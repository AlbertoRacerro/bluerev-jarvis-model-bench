from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for item in (ROOT, ROOT / "src"):
    if str(item) not in sys.path:
        sys.path.insert(0, str(item))

from scripts import validate_bench2r_hermes_s2 as base

SAFE_RUNNER_PATH = ROOT / "scripts/run_bench2r_hermes_s2_safe.py"
AWAKE_RUNNER_PATH = ROOT / "scripts/run_bench2r_hermes_s2_awake.py"
RUNTIME_WORKFLOW_PATH = ROOT / ".github/workflows/bench2r-hermes-s2-oneshot.yml"


class HermesS2SafeValidationError(RuntimeError):
    pass


def validate() -> dict[str, object]:
    plan, marker, candidates, cases = base.validate_execution(require_enabled=False)
    for path in (SAFE_RUNNER_PATH, AWAKE_RUNNER_PATH):
        if not path.is_file():
            raise HermesS2SafeValidationError(f"required safe S2 source is missing: {path.name}")

    safe_text = SAFE_RUNNER_PATH.read_text(encoding="utf-8")
    required_safe_tokens = {
        "_MODEL_FIELDS",
        "_build_model_prompt",
        "_parse_generic_object",
        "base.canary._build_prompt = _build_model_prompt",
        "base.canary._parse_output = _parse_generic_object",
        "finally:",
        "base.canary._build_prompt = original_builder",
        "base.canary._parse_output = original_parser",
        "wire-trace.jsonl",
        "native trajectory is missing",
    }
    missing = sorted(token for token in required_safe_tokens if token not in safe_text)
    if missing:
        raise HermesS2SafeValidationError(f"safe S2 boundary is incomplete: {missing}")
    if '"expected"' in safe_text.split("_MODEL_FIELDS", 1)[1].split(")", 1)[0]:
        raise HermesS2SafeValidationError("expected field entered the S2 model-field allowlist")

    workflow = RUNTIME_WORKFLOW_PATH.read_text(encoding="utf-8")
    required_workflow_tokens = {
        "python -m scripts.run_bench2r_hermes_s2_awake capture",
        "python -m scripts.run_bench2r_hermes_s2_safe enforce",
        "python -m scripts.validate_bench2r_hermes_s2_safe --require-enabled",
        "cancel-in-progress: true",
    }
    missing_workflow = sorted(
        token for token in required_workflow_tokens if token not in workflow
    )
    if missing_workflow:
        raise HermesS2SafeValidationError(
            f"S2 workflow does not use the safe boundary: {missing_workflow}"
        )
    forbidden_commands = {
        "python -m scripts.run_bench2r_hermes_s2 capture",
        "python -m scripts.run_bench2r_hermes_s2 enforce",
        "workflow_dispatch",
    }
    present = sorted(token for token in forbidden_commands if token in workflow)
    if present:
        raise HermesS2SafeValidationError(f"unsafe S2 workflow command present: {present}")

    return {
        "schema_version": "bench.hermes-s2-safe-validation.v1",
        "status": "ready",
        "execution_authorized": marker["enabled"],
        "candidate_count": len(candidates),
        "case_count": len(cases),
        "total_runs": plan["counts"]["total_runs"],
        "model_prompt_allowlisted": True,
        "generic_output_parser": True,
        "safe_runner_authoritative": True,
    }


def main() -> int:
    require_enabled = "--require-enabled" in sys.argv[1:]
    try:
        if require_enabled:
            base.validate_execution(require_enabled=True)
        payload = validate()
        if require_enabled:
            payload["execution_authorized"] = True
        code = 0
    except (
        HermesS2SafeValidationError,
        base.HermesS2ValidationError,
        OSError,
        ValueError,
    ) as exc:
        payload = {
            "schema_version": "bench.hermes-s2-safe-validation.v1",
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
