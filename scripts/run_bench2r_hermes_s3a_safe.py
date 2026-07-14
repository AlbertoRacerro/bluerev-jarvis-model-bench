from __future__ import annotations

import argparse
import json
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from scripts import run_bench2r_hermes_s3a as base

DEFAULT_ARTIFACTS = base.DEFAULT_ARTIFACTS
_PROXY_SOURCE_SHA = "eed3b03c22d9b87c54ed697ecd611c40f64973ea"


class HermesS3ASafeError(RuntimeError):
    pass


def _strict_wire_checks(
    records: list[dict[str, Any]],
    *,
    alias_name: str,
    worker_result: dict[str, Any] | None,
) -> dict[str, Any]:
    chats = [
        item
        for item in records
        if str(item.get("path", "")).split("?", 1)[0].endswith("/chat/completions")
    ]
    api_calls = worker_result.get("api_calls") if isinstance(worker_result, dict) else None
    registry_seen = False
    model_exact = True
    paths_v1_only = bool(records)
    proxy_errors_absent = bool(records)
    authorization_redacted = True
    for item in records:
        path = str(item.get("path") or "")
        paths_v1_only = paths_v1_only and path.startswith("/v1/")
        proxy_errors_absent = proxy_errors_absent and item.get("proxy_error") is None
        headers = item.get("request", {}).get("headers")
        if isinstance(headers, dict):
            for key, value in headers.items():
                if str(key).casefold() == "authorization" and value != "<redacted>":
                    authorization_redacted = False
    for item in chats:
        body = item.get("request", {}).get("json")
        if not isinstance(body, dict):
            model_exact = False
            continue
        if body.get("model") != alias_name:
            model_exact = False
        tools = body.get("tools")
        if isinstance(tools, list):
            names = {
                tool.get("function", {}).get("name")
                for tool in tools
                if isinstance(tool, dict)
            }
            registry_seen = registry_seen or base.TOOL_REGISTRY <= names
    return {
        "wire_trace_present": bool(records),
        "wire_chat_count_matches_worker": (
            isinstance(api_calls, int)
            and not isinstance(api_calls, bool)
            and len(chats) == api_calls
        ),
        "wire_all_http_200": bool(chats) and all(
            item.get("response", {}).get("status") == 200 for item in chats
        ),
        "wire_model_exact": bool(chats) and model_exact,
        "wire_tool_registry_observed": registry_seen,
        "wire_upstream_loopback_only": (
            paths_v1_only and proxy_errors_absent and authorization_redacted
        ),
        "wire_chat_count": len(chats),
        "wire_paths_v1_only": paths_v1_only,
        "wire_proxy_errors_absent": proxy_errors_absent,
        "wire_authorization_redacted": authorization_redacted,
        "wire_proxy_source_git_blob_sha": _PROXY_SOURCE_SHA,
    }


def _apply_negative_output_gate(
    result: dict[str, Any],
    *,
    case: dict[str, Any],
    raw_output: dict[str, Any] | None,
) -> dict[str, Any]:
    if case.get("outcome_class") != "expected_fail_closed_rejection":
        return result
    expected_raw = case.get("expected", {}).get("raw_output")
    passed = isinstance(expected_raw, dict) and raw_output == expected_raw
    checks = result.get("checks")
    if not isinstance(checks, list):
        raise HermesS3ASafeError("S3A validator checks are missing")
    checks.append({
        "check": "negative_output_ledger_only",
        "passed": passed,
        "detail": f"expected={expected_raw!r} observed={raw_output!r}",
    })
    result["raw_orchestration_pass"] = (
        result.get("raw_orchestration_pass") is True and passed
    )
    result["shadow_pass"] = (
        result.get("infrastructure_valid") is True
        and result.get("raw_orchestration_pass") is True
        and result.get("negative_fail_closed_pass") is True
    )
    return result


@contextmanager
def _safe_runtime_boundary() -> Iterator[None]:
    original_wire_checks = base._wire_checks
    original_validate_outcome = base._validate_outcome

    def strict_outcome(**kwargs: Any) -> dict[str, Any]:
        result = original_validate_outcome(**kwargs)
        return _apply_negative_output_gate(
            result,
            case=kwargs["case"],
            raw_output=kwargs.get("raw_output"),
        )

    base._wire_checks = _strict_wire_checks
    base._validate_outcome = strict_outcome
    try:
        yield
    finally:
        base._wire_checks = original_wire_checks
        base._validate_outcome = original_validate_outcome


def capture(output_dir: Path = DEFAULT_ARTIFACTS) -> int:
    with _safe_runtime_boundary():
        return base.capture(output_dir)


def _require_file(run_dir: Path, relative: str) -> Path:
    path = run_dir / relative
    if not path.is_file():
        raise HermesS3ASafeError(f"required S3A run artifact is missing: {path}")
    return path


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise HermesS3ASafeError(f"cannot read {path}: {type(exc).__name__}") from exc
    if not isinstance(value, dict):
        raise HermesS3ASafeError(f"{path} must contain an object")
    return value


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    try:
        for raw in path.read_text(encoding="utf-8").splitlines():
            if not raw.strip():
                continue
            value = json.loads(raw)
            if not isinstance(value, dict):
                raise HermesS3ASafeError(f"JSONL record is not an object: {path}")
            records.append(value)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise HermesS3ASafeError(f"cannot read JSONL {path}: {type(exc).__name__}") from exc
    return records


def _prompt_text_safe(text: str, case_id: str, source: str) -> None:
    if '"expected"' in text or '"outcome_class"' in text:
        raise HermesS3ASafeError(
            f"evaluator fields leaked into S3A {source} prompt: {case_id}"
        )
    if case_id == "s3a-tools-vault-untrusted-payload-001" and "KAPPA-73" in text:
        raise HermesS3ASafeError(f"vault held-out result leaked into S3A {source} prompt")
    if case_id == "s3a-tools-registry-stability-002" and "MU-62" in text:
        raise HermesS3ASafeError(f"registry held-out result leaked into S3A {source} prompt")


def _model_prompt_safe(run_dir: Path, case_id: str) -> None:
    prompt = _require_file(run_dir, "model-prompt.txt").read_text(
        encoding="utf-8",
        errors="strict",
    )
    _prompt_text_safe(prompt, case_id, "stored")


def _wire_prompt_safe(wire_path: Path, case_id: str) -> None:
    records = _read_jsonl(wire_path)
    chats = [
        item
        for item in records
        if str(item.get("path", "")).split("?", 1)[0].endswith("/chat/completions")
    ]
    if not chats:
        raise HermesS3ASafeError("S3A wire trace contains no chat request")
    body = chats[0].get("request", {}).get("json")
    if not isinstance(body, dict) or not isinstance(body.get("messages"), list):
        raise HermesS3ASafeError("S3A first wire request has no message inventory")
    _prompt_text_safe(
        json.dumps(body["messages"], sort_keys=True),
        case_id,
        "wire",
    )


def enforce(output_dir: Path = DEFAULT_ARTIFACTS) -> int:
    with _safe_runtime_boundary():
        code = base.enforce(output_dir)
    report = _load(output_dir / "batch-report.json")
    runs = report.get("runs")
    if not isinstance(runs, list) or len(runs) != 10:
        raise HermesS3ASafeError("S3A run inventory is missing or incomplete")
    rich = (
        "model-prompt.txt",
        "context-fingerprint.json",
        "raw-output.txt",
        "stderr.txt",
        "worker-result.json",
        "worker-debug.txt",
        "usage.json",
        "extracted-output.json",
        "tool-trace.jsonl",
        "wire-trace.jsonl",
        "validator-result.json",
        "environment-fingerprint.json",
        "effective-config.yaml",
        "manifest.json",
    )
    for run in runs:
        if not isinstance(run, dict):
            raise HermesS3ASafeError("S3A run record is not an object")
        relative = run.get("artifact_path")
        if not isinstance(relative, str) or not relative:
            raise HermesS3ASafeError("S3A run artifact path is missing")
        run_dir = output_dir / relative
        for name in rich:
            _require_file(run_dir, name)
        trajectory_candidates = (
            run_dir / "trajectory_samples.jsonl",
            run_dir / "failed_trajectories.jsonl",
        )
        if not any(path.is_file() and path.stat().st_size > 0 for path in trajectory_candidates):
            raise HermesS3ASafeError(f"native S3A trajectory is missing: {run_dir}")
        wire_path = _require_file(run_dir, "wire-trace.jsonl")
        if wire_path.stat().st_size <= 0:
            raise HermesS3ASafeError(f"S3A wire trace is empty: {run_dir}")
        validator = _load(run_dir / "validator-result.json")
        diagnostics = validator.get("diagnostics")
        if not isinstance(diagnostics, dict):
            raise HermesS3ASafeError(f"S3A diagnostics are missing: {run_dir}")
        duration = diagnostics.get("duration_seconds")
        if not isinstance(duration, (int, float)) or isinstance(duration, bool) or duration < 0:
            raise HermesS3ASafeError(f"S3A run duration is invalid: {run_dir}")
        case_id = str(run.get("case_id"))
        _model_prompt_safe(run_dir, case_id)
        _wire_prompt_safe(wire_path, case_id)
        if case_id == "s3a-stop-long-context-untrusted-003":
            context = _load(run_dir / "context-fingerprint.json")
            if context.get("present") is not True:
                raise HermesS3ASafeError("S3A long-context fingerprint is absent")
            if context.get("line_count") != 1000:
                raise HermesS3ASafeError("S3A long-context line count drifted")
            if not isinstance(context.get("sha256"), str) or len(context["sha256"]) != 64:
                raise HermesS3ASafeError("S3A long-context digest is invalid")
        if case_id == "s3a-tools-injected-timeout-005":
            records = _read_jsonl(run_dir / "tool-trace.jsonl")
            if len(records) != 1:
                raise HermesS3ASafeError("S3A timeout control trace count drifted")
            result = records[0].get("result")
            if not isinstance(result, dict) or result.get("fault_signature") != base.TIMEOUT_SIGNATURE:
                raise HermesS3ASafeError("S3A timeout control signature is missing")
    decision = report.get("decision")
    if not isinstance(decision, dict):
        raise HermesS3ASafeError("S3A batch decision is missing")
    if decision.get("automatic_production_promotion_allowed") is not False:
        raise HermesS3ASafeError("S3A batch permits automatic production promotion")
    if decision.get("production_status") != "not_promoted":
        raise HermesS3ASafeError("S3A production status drifted")
    return code


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run BENCH-2R Hermes S3A through the authoritative safe boundary."
    )
    parser.add_argument("mode", choices=("capture", "enforce"))
    parser.add_argument("--artifact-dir", type=Path, default=DEFAULT_ARTIFACTS)
    args = parser.parse_args()
    try:
        return capture(args.artifact_dir) if args.mode == "capture" else enforce(args.artifact_dir)
    except Exception as exc:
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
