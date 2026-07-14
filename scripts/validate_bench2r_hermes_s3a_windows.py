from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from scripts import validate_bench2r_hermes_s3a as design
from scripts import validate_bench2r_hermes_s3a_runtime as runtime

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = ROOT / ".github/workflows/bench2r-hermes-s3a-oneshot.yml"
PREFLIGHT_WRAPPER_PATH = ROOT / "scripts/run_bench2r_hermes_s3a_preflight.py"
EXPECTED_VALIDATOR_COMMAND = "python -m scripts.run_bench2r_hermes_s3a_preflight"


class HermesS3AWindowsValidationError(RuntimeError):
    pass


def normalized_git_blob_sha(path: Path) -> str:
    """Return the Git blob SHA for repository text independent of checkout EOLs."""
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        data = raw
    else:
        data = text.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")
    return hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()


def normalized_workflow_text(text: str) -> str:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    return " ".join(normalized.split())


def _historical_disabled_marker() -> dict[str, Any]:
    return {
        **runtime.EXPECTED_MARKER_BASE,
        "enabled": False,
    }


@contextmanager
def historical_design_disabled_boundary() -> Iterator[None]:
    """Validate immutable design with its reviewed disabled marker only."""
    original_workflow_path = design.RUNTIME_WORKFLOW_PATH
    original_marker_path = design.MARKER_PATH
    with tempfile.TemporaryDirectory(prefix="bench2r-s3a-historical-") as directory:
        marker_path = Path(directory) / "marker.json"
        marker_path.write_text(
            json.dumps(_historical_disabled_marker(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        design.RUNTIME_WORKFLOW_PATH = runtime.HISTORICAL_DESIGN_WORKFLOW_SENTINEL
        design.MARKER_PATH = marker_path
        try:
            yield
        finally:
            design.RUNTIME_WORKFLOW_PATH = original_workflow_path
            design.MARKER_PATH = original_marker_path


def _validate_preflight_wrapper() -> None:
    if not PREFLIGHT_WRAPPER_PATH.is_file():
        raise HermesS3AWindowsValidationError("S3A durable preflight wrapper is missing")
    source = PREFLIGHT_WRAPPER_PATH.read_text(encoding="utf-8")
    required = {
        "output_dir.mkdir(parents=True, exist_ok=True)",
        "subprocess.run(",
        "capture_output=True",
        "check=False",
        "if not json_path.is_file():",
        '"execution_authorized": False',
        'JSON_NAME = "s3a-preflight.json"',
        'LOG_NAME = "s3a-preflight.log"',
    }
    missing = sorted(token for token in required if token not in source)
    if missing:
        raise HermesS3AWindowsValidationError(
            f"S3A durable preflight wrapper drifted: {missing}"
        )


def _validate_live_workflow(*, required: bool) -> bool:
    present = WORKFLOW_PATH.is_file()
    if required and not present:
        raise HermesS3AWindowsValidationError("S3A runtime workflow is missing")
    if not present:
        return False
    _validate_preflight_wrapper()
    workflow = WORKFLOW_PATH.read_text(encoding="utf-8")
    logical_workflow = normalized_workflow_text(workflow)
    required_tokens = {
        "paths:\n      - config/bench2r-hermes-s3a-marker.json",
        "runs-on: [self-hosted, Windows, X64, bluerev-bench]",
        "batch: [0, 1, 2, 3, 4]",
        "max-parallel: 1",
        "cancel-in-progress: true",
        EXPECTED_VALIDATOR_COMMAND,
        "name: bench2r-hermes-s3a-preflight-${{ github.run_id }}-${{ github.run_attempt }}-b${{ matrix.batch }}",
        "path: artifacts/preflight/",
        "python -m scripts.run_bench2r_hermes_s3a_awake capture",
        "python -m scripts.run_bench2r_hermes_s3a_safe enforce",
        "Activate BENCH-2R Hermes S3A shadow soak",
    }
    missing = sorted(
        token
        for token in required_tokens
        if token not in workflow and token not in logical_workflow
    )
    if missing:
        raise HermesS3AWindowsValidationError(
            f"S3A Windows workflow contract drifted: {missing}"
        )
    if workflow.count("if: always()") < 3:
        raise HermesS3AWindowsValidationError(
            "S3A workflow lost a required failure-evidence boundary"
        )
    if workflow.count("shell: cmd") != 3:
        raise HermesS3AWindowsValidationError(
            "S3A Windows Python steps must use exactly three cmd shells"
        )
    if "workflow_dispatch" in workflow:
        raise HermesS3AWindowsValidationError("S3A workflow exposes manual dispatch")
    forbidden = {
        "shell: powershell",
        "python -m scripts.validate_bench2r_hermes_s3a_windows",
        "python -m scripts.validate_bench2r_hermes_s3a_runtime --require-enabled",
        "python -m scripts.run_bench2r_hermes_s3a capture",
        "python -m scripts.run_bench2r_hermes_s3a enforce",
        "*> artifacts/preflight",
    }
    present_forbidden = sorted(token for token in forbidden if token in logical_workflow)
    if present_forbidden:
        raise HermesS3AWindowsValidationError(
            f"S3A workflow bypasses the durable Windows/safe boundary: {present_forbidden}"
        )
    return True


@contextmanager
def windows_runtime_boundary() -> Iterator[None]:
    original_runtime_hash = runtime._git_blob_sha
    original_design_hash = design._git_blob_sha
    original_workflow_validator = runtime._validate_workflow
    original_historical_boundary = runtime._historical_design_boundary
    runtime._git_blob_sha = normalized_git_blob_sha
    design._git_blob_sha = normalized_git_blob_sha
    runtime._validate_workflow = _validate_live_workflow
    runtime._historical_design_boundary = historical_design_disabled_boundary
    try:
        yield
    finally:
        runtime._git_blob_sha = original_runtime_hash
        design._git_blob_sha = original_design_hash
        runtime._validate_workflow = original_workflow_validator
        runtime._historical_design_boundary = original_historical_boundary


def validate_execution(
    *,
    require_enabled: bool | None = None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    with windows_runtime_boundary():
        return runtime.validate_execution(require_enabled=require_enabled)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate BENCH-2R Hermes S3A with Windows-normalized source bindings."
    )
    parser.add_argument("--require-enabled", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        plan, marker, candidate, cases = validate_execution(
            require_enabled=True if args.require_enabled else False
        )
        payload = {
            "schema_version": "bench.hermes-s3a-windows-validation.v1",
            "status": (
                "execution_ready"
                if marker["enabled"]
                else "runtime_ready_execution_disabled"
            ),
            "execution_authorized": marker["enabled"],
            "candidate_id": candidate["candidate_id"],
            "case_count": len(cases),
            "seed_count": len(plan["seeds"]),
            "repetitions": plan["repetitions"],
            "total_runs": plan["counts"]["total_runs"],
            "text_blob_eol_normalized": True,
            "historical_marker_isolated": True,
            "workflow_boundary_authoritative": True,
            "automatic_production_promotion_allowed": False,
        }
        code = 0
    except (
        runtime.design.HermesS3AValidationError,
        runtime.strict_design.HermesS3AContractError,
        runtime.HermesS3ARuntimeValidationError,
        HermesS3AWindowsValidationError,
        OSError,
        ValueError,
        SyntaxError,
    ) as exc:
        payload = {
            "schema_version": "bench.hermes-s3a-windows-validation.v1",
            "status": "invalid",
            "execution_authorized": False,
            "error_type": type(exc).__name__,
            "error": str(exc),
        }
        code = 2
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text, end="")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
