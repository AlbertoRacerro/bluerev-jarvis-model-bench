from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request

from . import direct_execution as base
from .contracts import ContractError, validate_manifest
from .evaluator import evaluate_submission

SCHEMA_VERSION = "bench.direct-smoke.v2"
NUM_PREDICT = 1024
NUM_CTX = 4096
TEMPERATURE = 0
SEED = 4242
KEEP_ALIVE = 0


def call_ollama_generate(
    *,
    endpoint: str,
    model_tag: str,
    prompt: str,
    timeout_seconds: int = base.DEFAULT_TIMEOUT_SECONDS,
    opener: Callable[[Request, int], Any] = base._open_no_redirect,
) -> dict[str, Any]:
    if not base._is_loopback_generate_endpoint(endpoint):
        raise ContractError(
            "Ollama generate endpoint must be an exact loopback /api/generate URL"
        )
    if (
        not isinstance(timeout_seconds, int)
        or isinstance(timeout_seconds, bool)
        or timeout_seconds < 1
    ):
        raise ContractError("timeout_seconds must be an integer >= 1")

    body = {
        "model": model_tag,
        "prompt": prompt,
        "stream": False,
        "keep_alive": KEEP_ALIVE,
        "options": {
            "temperature": TEMPERATURE,
            "seed": SEED,
            "num_predict": NUM_PREDICT,
            "num_ctx": NUM_CTX,
        },
    }
    request = Request(
        endpoint,
        data=json.dumps(body, sort_keys=True).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with opener(request, timeout_seconds) as response:
            final_url = response.geturl()
            if final_url != endpoint:
                raise ContractError("Ollama generate request was redirected")
            raw_bytes = response.read(base.MAX_RESPONSE_BYTES + 1)
    except ContractError:
        raise
    except (OSError, HTTPError, URLError, TimeoutError) as exc:
        raise ContractError(
            f"Ollama generate request failed: {type(exc).__name__}"
        ) from exc

    if len(raw_bytes) > base.MAX_RESPONSE_BYTES:
        raise ContractError("Ollama generate response exceeds the bounded response size")
    try:
        response_text = raw_bytes.decode("utf-8")
    except UnicodeError as exc:
        raise ContractError("Ollama generate response is not UTF-8") from exc

    value = base._strict_json_loads(response_text, label="Ollama generate response")
    if not isinstance(value, Mapping):
        raise ContractError("Ollama generate response must be an object")
    result = dict(value)
    if result.get("done") is not True:
        raise ContractError("Ollama generate response must be complete")
    raw_output = result.get("response")
    if not isinstance(raw_output, str) or not raw_output.strip():
        raise ContractError("Ollama generate response text must be non-empty")
    return result


def _truncation_artifacts(
    case_id: str,
    *,
    eval_count: Any,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    detail = (
        "generation_truncated: Ollama done_reason='length' "
        f"at eval_count={eval_count!r}; candidate result is invalid, not failed"
    )
    extraction = {
        "schema_version": "bench.extraction-result.v1",
        "ok": False,
        "error": {"type": "GenerationTruncated", "detail": detail},
    }
    trace_capture = {
        "schema_version": "bench.trace-capture.v1",
        "case_id": case_id,
        "ok": False,
        "events": [],
        "error": {"type": "GenerationTruncated", "detail": detail},
    }
    validator = {
        "schema_version": "bench.validator-result.v1",
        "case_id": case_id,
        "passed": False,
        "counts": {
            "complete": False,
            "model_calls": None,
            "tool_calls": None,
            "retries": None,
        },
        "checks": [
            {
                "assertion_id": "generation_complete",
                "passed": False,
                "detail": detail,
            }
        ],
    }
    return extraction, trace_capture, validator


def execute_direct_smoke(
    *,
    run_id: str,
    candidate_id: str,
    candidate_registry_path: Path,
    case_path: Path,
    preflight_path: Path,
    output_root: Path,
    endpoint: str = base.DEFAULT_GENERATE_URL,
    timeout_seconds: int = base.DEFAULT_TIMEOUT_SECONDS,
    opener: Callable[[Request, int], Any] = base._open_no_redirect,
) -> dict[str, Any]:
    if not base._RUN_ID.fullmatch(run_id):
        raise ContractError("run_id contains unsupported characters")

    preflight = base._load_json_file(preflight_path, label="preflight evidence")
    if not isinstance(preflight, Mapping):
        raise ContractError("preflight evidence must contain an object")
    candidate = base.load_candidate(candidate_registry_path, candidate_id)
    base.verify_scoring_environment(preflight, candidate)
    case = base.load_case_file(case_path)
    candidate_payload = base.build_candidate_payload(case)
    prompt = base.build_prompt(candidate_payload)

    run_dir = output_root / run_id
    if run_dir.exists():
        raise ContractError(f"run artifact directory already exists: {run_id}")
    run_dir.mkdir(parents=True)

    started_at = datetime.now(UTC)
    ollama_response = call_ollama_generate(
        endpoint=endpoint,
        model_tag=candidate["model_tag"],
        prompt=prompt,
        timeout_seconds=timeout_seconds,
        opener=opener,
    )
    completed_at = datetime.now(UTC)
    raw_output = ollama_response["response"]
    termination_reason = ollama_response.get("done_reason")
    eval_count = ollama_response.get("eval_count")
    truncated = termination_reason == "length"

    (run_dir / "prompt.txt").write_text(prompt + "\n", encoding="utf-8")
    base._write_json(run_dir / "candidate_payload.json", candidate_payload)
    base._write_json(run_dir / "ollama_response.json", ollama_response)
    (run_dir / "raw_output.txt").write_text(raw_output, encoding="utf-8")

    if truncated:
        extracted_output, trace, validator_result = _truncation_artifacts(
            case["case_id"],
            eval_count=eval_count,
        )
        result_status = "invalid"
        candidate_passed: bool | None = None
    else:
        try:
            extracted_output, trace = base.parse_submission(raw_output, case["case_id"])
            validator_result = evaluate_submission(case, extracted_output, trace)
        except ContractError as exc:
            extracted_output, trace, validator_result = base._failure_artifacts(
                case["case_id"], "candidate_submission", exc
            )
        candidate_passed = bool(validator_result["passed"])
        result_status = "passed" if candidate_passed else "failed"

    base._write_json(run_dir / "extracted_output.json", extracted_output)
    base._write_json(run_dir / "trace.json", trace)
    base._write_json(run_dir / "validator_result.json", validator_result)

    environment_fingerprint = {
        "schema_version": "bench.environment-fingerprint.v1",
        "preflight_sha256": base._sha256_file(preflight_path),
        "workflow": preflight.get("workflow"),
        "runner": preflight.get("environment"),
        "hermes": preflight.get("hermes"),
        "ollama_version": (preflight.get("ollama") or {}).get("version"),
        "candidate": {
            "candidate_id": candidate["candidate_id"],
            "model_tag": candidate["model_tag"],
            "digest": candidate["digest"],
        },
        "execution": {
            "endpoint": endpoint,
            "timeout_seconds": timeout_seconds,
            "temperature": TEMPERATURE,
            "seed": SEED,
            "num_predict": NUM_PREDICT,
            "num_ctx": NUM_CTX,
            "keep_alive": KEEP_ALIVE,
            "started_at_utc": started_at.isoformat().replace("+00:00", "Z"),
            "completed_at_utc": completed_at.isoformat().replace("+00:00", "Z"),
            "termination_reason": termination_reason,
            "eval_count": eval_count,
        },
    }
    base._write_json(run_dir / "environment_fingerprint.json", environment_fingerprint)

    artifact_names = (
        "candidate_payload.json",
        "prompt.txt",
        "ollama_response.json",
        "raw_output.txt",
        "extracted_output.json",
        "trace.json",
        "validator_result.json",
        "environment_fingerprint.json",
    )
    artifacts = {
        name: {"path": name, "sha256": base._sha256_file(run_dir / name)}
        for name in artifact_names
    }
    manifest = {
        "schema_version": "bench.run.v1",
        "run_id": run_id,
        "created_at_utc": completed_at.isoformat().replace("+00:00", "Z"),
        "lane": "direct",
        "candidate": candidate["candidate_id"],
        "case_id": case["case_id"],
        "repetition": 1,
        "status": "invalid" if truncated else "preliminary",
        "environment": environment_fingerprint,
        "artifacts": artifacts,
    }
    validate_manifest(manifest)
    base._write_json(run_dir / "manifest.json", manifest)

    summary = {
        "schema_version": SCHEMA_VERSION,
        "execution_completed": True,
        "candidate_passed": candidate_passed,
        "candidate_result_status": result_status,
        "termination_reason": termination_reason,
        "eval_count": eval_count,
        "num_predict": NUM_PREDICT,
        "run_id": run_id,
        "candidate_id": candidate["candidate_id"],
        "case_id": case["case_id"],
        "run_directory": str(run_dir),
        "manifest_sha256": base._sha256_file(run_dir / "manifest.json"),
    }
    base._write_json(run_dir / "execution_summary.json", summary)
    return summary
