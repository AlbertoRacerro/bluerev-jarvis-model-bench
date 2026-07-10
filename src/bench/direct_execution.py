from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from ipaddress import ip_address
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .contracts import ContractError, extract_final, validate_manifest
from .evaluator import build_candidate_payload, evaluate_submission, load_case_file

SCHEMA_VERSION = "bench.direct-smoke.v1"
DEFAULT_GENERATE_URL = "http://127.0.0.1:11434/api/generate"
DEFAULT_TIMEOUT_SECONDS = 180
MAX_RESPONSE_BYTES = 2_000_000
MAX_PROMPT_BYTES = 64_000
_RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_SUBMISSION_FIELDS = frozenset({"output", "actions"})


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        return None


def _open_no_redirect(request: Request, timeout: int):
    return build_opener(_NoRedirect).open(request, timeout=timeout)


def _reject_duplicate_object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ContractError(f"JSON object contains duplicate key: {key}")
        result[key] = value
    return result


def _strict_json_loads(text: str, *, label: str) -> Any:
    try:
        return json.loads(text, object_pairs_hook=_reject_duplicate_object_pairs)
    except ContractError:
        raise
    except json.JSONDecodeError as exc:
        raise ContractError(f"{label} is not valid JSON: {exc.msg}") from exc


def _load_json_file(path: Path, *, label: str) -> Any:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise ContractError(f"cannot read {label}: {type(exc).__name__}") from exc
    return _strict_json_loads(text, label=label)


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _is_loopback_generate_endpoint(endpoint: str) -> bool:
    try:
        parsed = urlparse(endpoint)
        host = parsed.hostname
        return bool(
            parsed.scheme == "http"
            and host is not None
            and ip_address(host).is_loopback
            and parsed.path == "/api/generate"
            and parsed.params == ""
            and parsed.query == ""
            and parsed.fragment == ""
            and parsed.username is None
            and parsed.password is None
        )
    except ValueError:
        return False


def load_candidate(path: Path, candidate_id: str) -> dict[str, Any]:
    document = _load_json_file(path, label="candidate registry")
    if not isinstance(document, Mapping):
        raise ContractError("candidate registry must contain an object")
    if document.get("schema_version") != "bench.candidates.v1":
        raise ContractError("unsupported candidate registry schema_version")
    if document.get("mapping_status") != "validated":
        raise ContractError("candidate registry mapping_status must be validated")

    candidates = document.get("candidates")
    if not isinstance(candidates, list):
        raise ContractError("candidate registry candidates must be an array")
    matches = [
        item
        for item in candidates
        if isinstance(item, Mapping) and item.get("candidate_id") == candidate_id
    ]
    if len(matches) != 1:
        raise ContractError(f"candidate_id must resolve exactly once: {candidate_id}")

    candidate = dict(matches[0])
    if candidate.get("enabled") is not True:
        raise ContractError(f"candidate is not enabled: {candidate_id}")
    for field in ("candidate_id", "model_tag", "digest"):
        value = candidate.get(field)
        if not isinstance(value, str) or not value.strip():
            raise ContractError(f"candidate {field} must be a non-empty string")
    return candidate


def verify_scoring_environment(preflight: Mapping[str, Any], candidate: Mapping[str, Any]) -> None:
    if preflight.get("schema_version") != "bench.preflight.v1":
        raise ContractError("unsupported preflight schema_version")
    if preflight.get("runner_ready") is not True:
        raise ContractError("preflight runner_ready must be true")
    if preflight.get("scoring_ready") is not True:
        raise ContractError("preflight scoring_ready must be true")
    if preflight.get("local_only") is not True:
        raise ContractError("preflight local_only must be true")

    ollama = preflight.get("ollama")
    if not isinstance(ollama, Mapping):
        raise ContractError("preflight ollama inventory must be an object")
    models = ollama.get("models")
    if not isinstance(models, list):
        raise ContractError("preflight ollama models must be an array")

    model_tag = candidate["model_tag"]
    digest = candidate["digest"]
    matches = [
        item
        for item in models
        if isinstance(item, Mapping)
        and item.get("name") == model_tag
        and item.get("digest") == digest
    ]
    if len(matches) != 1:
        raise ContractError("candidate tag and digest do not match the preflight inventory")


def build_prompt(candidate_payload: Mapping[str, Any]) -> str:
    forbidden_oracle_fields = {
        "expected",
        "success_assertions",
        "negative_assertions",
        "required_artifacts",
    }
    leaked = sorted(forbidden_oracle_fields & set(candidate_payload))
    if leaked:
        raise ContractError("candidate payload leaks evaluator-only fields: " + ", ".join(leaked))

    payload_text = json.dumps(candidate_payload, sort_keys=True, separators=(",", ":"))
    prompt = (
        "You are executing one bounded benchmark task. Do not call tools, external providers, "
        "or other models. Use only the supplied task data. Return exactly one final line in this "
        "format and no text after it:\n"
        "FINAL: {\"output\":{...},\"actions\":[\"action_id\",...]}\n"
        "The output object must contain only the requested answer fields. The actions array must "
        "list the actions you actually selected, in order, using only allowed_actions.\n"
        f"TASK={payload_text}"
    )
    if len(prompt.encode("utf-8")) > MAX_PROMPT_BYTES:
        raise ContractError("candidate prompt exceeds the bounded prompt size")
    return prompt


def call_ollama_generate(
    *,
    endpoint: str,
    model_tag: str,
    prompt: str,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    opener: Callable[[Request, int], Any] = _open_no_redirect,
) -> dict[str, Any]:
    if not _is_loopback_generate_endpoint(endpoint):
        raise ContractError("Ollama generate endpoint must be an exact loopback /api/generate URL")
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
        "keep_alive": 0,
        "options": {
            "temperature": 0,
            "seed": 4242,
            "num_predict": 256,
            "num_ctx": 4096,
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
            raw_bytes = response.read(MAX_RESPONSE_BYTES + 1)
    except ContractError:
        raise
    except (OSError, HTTPError, URLError, TimeoutError) as exc:
        raise ContractError(f"Ollama generate request failed: {type(exc).__name__}") from exc

    if len(raw_bytes) > MAX_RESPONSE_BYTES:
        raise ContractError("Ollama generate response exceeds the bounded response size")
    try:
        response_text = raw_bytes.decode("utf-8")
    except UnicodeError as exc:
        raise ContractError("Ollama generate response is not UTF-8") from exc

    value = _strict_json_loads(response_text, label="Ollama generate response")
    if not isinstance(value, Mapping):
        raise ContractError("Ollama generate response must be an object")
    result = dict(value)
    if result.get("done") is not True:
        raise ContractError("Ollama generate response must be complete")
    raw_output = result.get("response")
    if not isinstance(raw_output, str) or not raw_output.strip():
        raise ContractError("Ollama generate response text must be non-empty")
    return result


def parse_submission(raw_output: str, case_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    final_text = extract_final(raw_output)
    value = _strict_json_loads(final_text, label="candidate FINAL payload")
    if not isinstance(value, Mapping):
        raise ContractError("candidate FINAL payload must be an object")
    keys = set(value)
    missing = sorted(_SUBMISSION_FIELDS - keys)
    extra = sorted(keys - _SUBMISSION_FIELDS)
    if missing:
        raise ContractError("candidate FINAL payload missing fields: " + ", ".join(missing))
    if extra:
        raise ContractError("candidate FINAL payload has unsupported fields: " + ", ".join(extra))

    output = value["output"]
    actions = value["actions"]
    if not isinstance(output, Mapping) or not output:
        raise ContractError("candidate output must be a non-empty object")
    if not isinstance(actions, list) or not actions:
        raise ContractError("candidate actions must be a non-empty array")
    if any(not isinstance(action, str) or not action.strip() for action in actions):
        raise ContractError("candidate actions must contain non-empty strings")

    extracted_output = dict(output)
    trace = {
        "schema_version": "bench.trace.v1",
        "case_id": case_id,
        "events": [
            {"index": index, "action_id": action, "details": {}}
            for index, action in enumerate(actions, start=1)
        ],
    }
    return extracted_output, trace


def _failure_artifacts(
    case_id: str,
    stage: str,
    exc: ContractError,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    detail = f"{stage}: {exc}"
    extraction = {
        "schema_version": "bench.extraction-result.v1",
        "ok": False,
        "error": {"type": type(exc).__name__, "detail": detail},
    }
    trace_capture = {
        "schema_version": "bench.trace-capture.v1",
        "case_id": case_id,
        "ok": False,
        "events": [],
        "error": {"type": type(exc).__name__, "detail": detail},
    }
    validator = {
        "schema_version": "bench.validator-result.v1",
        "case_id": case_id,
        "passed": False,
        "counts": {"complete": False, "model_calls": None, "tool_calls": None, "retries": None},
        "checks": [
            {
                "assertion_id": "submission_contract",
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
    endpoint: str = DEFAULT_GENERATE_URL,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    opener: Callable[[Request, int], Any] = _open_no_redirect,
) -> dict[str, Any]:
    if not _RUN_ID.fullmatch(run_id):
        raise ContractError("run_id contains unsupported characters")

    preflight = _load_json_file(preflight_path, label="preflight evidence")
    if not isinstance(preflight, Mapping):
        raise ContractError("preflight evidence must contain an object")
    candidate = load_candidate(candidate_registry_path, candidate_id)
    verify_scoring_environment(preflight, candidate)
    case = load_case_file(case_path)
    candidate_payload = build_candidate_payload(case)
    prompt = build_prompt(candidate_payload)

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

    (run_dir / "prompt.txt").write_text(prompt + "\n", encoding="utf-8")
    _write_json(run_dir / "candidate_payload.json", candidate_payload)
    _write_json(run_dir / "ollama_response.json", ollama_response)
    (run_dir / "raw_output.txt").write_text(raw_output, encoding="utf-8")

    try:
        extracted_output, trace = parse_submission(raw_output, case["case_id"])
        validator_result = evaluate_submission(case, extracted_output, trace)
    except ContractError as exc:
        extracted_output, trace, validator_result = _failure_artifacts(
            case["case_id"], "candidate_submission", exc
        )

    _write_json(run_dir / "extracted_output.json", extracted_output)
    _write_json(run_dir / "trace.json", trace)
    _write_json(run_dir / "validator_result.json", validator_result)

    environment_fingerprint = {
        "schema_version": "bench.environment-fingerprint.v1",
        "preflight_sha256": _sha256_file(preflight_path),
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
            "temperature": 0,
            "seed": 4242,
            "num_predict": 256,
            "num_ctx": 4096,
            "keep_alive": 0,
            "started_at_utc": started_at.isoformat().replace("+00:00", "Z"),
            "completed_at_utc": completed_at.isoformat().replace("+00:00", "Z"),
        },
    }
    _write_json(run_dir / "environment_fingerprint.json", environment_fingerprint)

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
        name: {"path": name, "sha256": _sha256_file(run_dir / name)} for name in artifact_names
    }
    manifest = {
        "schema_version": "bench.run.v1",
        "run_id": run_id,
        "created_at_utc": completed_at.isoformat().replace("+00:00", "Z"),
        "lane": "direct",
        "candidate": candidate["candidate_id"],
        "case_id": case["case_id"],
        "repetition": 1,
        "status": "preliminary",
        "environment": environment_fingerprint,
        "artifacts": artifacts,
    }
    validate_manifest(manifest)
    _write_json(run_dir / "manifest.json", manifest)

    summary = {
        "schema_version": SCHEMA_VERSION,
        "execution_completed": True,
        "candidate_passed": validator_result["passed"],
        "run_id": run_id,
        "candidate_id": candidate["candidate_id"],
        "case_id": case["case_id"],
        "run_directory": str(run_dir),
        "manifest_sha256": _sha256_file(run_dir / "manifest.json"),
    }
    _write_json(run_dir / "execution_summary.json", summary)
    return summary
