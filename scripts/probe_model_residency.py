from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import subprocess
import time
from datetime import UTC, datetime
from ipaddress import ip_address
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

SCHEMA_VERSION = "bench.model-residency.v1"
TAGS_URL = "http://127.0.0.1:11434/api/tags"
PS_URL = "http://127.0.0.1:11434/api/ps"
GENERATE_URL = "http://127.0.0.1:11434/api/generate"
EXCLUDED_MODEL_FRAGMENTS = ("gemma4:27b",)
PROFILE = {
    "name": "h1-4k-residency",
    "num_ctx": 4096,
    "num_predict": 1,
    "temperature": 0,
    "seed": 4242,
    "keep_alive": "5m",
    "request_timeout_seconds": 420,
}


class ProbeError(RuntimeError):
    pass


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        return None


_OPENER = build_opener(ProxyHandler({}), _NoRedirect)


def _is_exact_loopback_url(url: str, path: str) -> bool:
    try:
        parsed = urlparse(url)
        return bool(
            parsed.scheme == "http"
            and parsed.hostname is not None
            and ip_address(parsed.hostname).is_loopback
            and parsed.path == path
            and not parsed.params
            and not parsed.query
            and not parsed.fragment
            and parsed.username is None
            and parsed.password is None
        )
    except ValueError:
        return False


def _request_json(
    url: str,
    *,
    expected_path: str,
    payload: dict[str, Any] | None = None,
    timeout: int = 30,
) -> dict[str, Any]:
    if not _is_exact_loopback_url(url, expected_path):
        raise ProbeError(f"endpoint must be exact loopback {expected_path}")
    data = None if payload is None else json.dumps(payload, sort_keys=True).encode("utf-8")
    request = Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"} if data is not None else {},
        method="POST" if data is not None else "GET",
    )
    try:
        with _OPENER.open(request, timeout=timeout) as response:
            if response.geturl() != url:
                raise ProbeError("loopback request was redirected")
            raw = response.read(4_000_001)
    except ProbeError:
        raise
    except Exception as exc:  # urllib exposes platform-specific subclasses
        raise ProbeError(f"loopback request failed: {type(exc).__name__}") from exc
    if len(raw) > 4_000_000:
        raise ProbeError("loopback response exceeds size limit")
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ProbeError("loopback response is not valid UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise ProbeError("loopback response must be an object")
    return value


def _run(command: list[str], *, timeout: int = 60) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return {"ok": False, "command": command, "error": type(exc).__name__}
    return {
        "ok": completed.returncode == 0,
        "command": command,
        "returncode": completed.returncode,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
    }


def parse_nvidia_smi_csv(text: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for raw_row in csv.reader(line for line in text.splitlines() if line.strip()):
        if len(raw_row) != 5:
            raise ProbeError("unexpected nvidia-smi CSV shape")
        index, name, total_mib, used_mib, utilization = (
            item.strip() for item in raw_row
        )
        try:
            rows.append(
                {
                    "index": int(index),
                    "name": name,
                    "memory_total_mib": int(total_mib),
                    "memory_used_mib": int(used_mib),
                    "utilization_gpu_percent": int(utilization),
                }
            )
        except ValueError as exc:
            raise ProbeError("nvidia-smi CSV contains non-integer metrics") from exc
    if not rows:
        raise ProbeError("nvidia-smi returned no GPUs")
    return rows


def gpu_snapshot() -> dict[str, Any]:
    result = _run(
        [
            "nvidia-smi",
            "--query-gpu=index,name,memory.total,memory.used,utilization.gpu",
            "--format=csv,noheader,nounits",
        ],
        timeout=30,
    )
    if not result.get("ok"):
        return {"ok": False, "command_result": result, "gpus": []}
    try:
        gpus = parse_nvidia_smi_csv(str(result.get("stdout") or ""))
    except ProbeError as exc:
        return {
            "ok": False,
            "command_result": result,
            "error": str(exc),
            "gpus": [],
        }
    return {"ok": True, "command_result": result, "gpus": gpus}


def classify_residency(size: Any, size_vram: Any) -> tuple[str, float | None]:
    if not isinstance(size, int) or isinstance(size, bool) or size <= 0:
        return "unknown", None
    if not isinstance(size_vram, int) or isinstance(size_vram, bool) or size_vram < 0:
        return "unknown", None
    ratio = size_vram / size
    if ratio >= 0.98:
        return "full_vram", ratio
    if size_vram > 0:
        return "partial_vram", ratio
    return "cpu_only", ratio


def is_user_excluded(model_name: str) -> bool:
    normalized = model_name.casefold()
    return any(fragment in normalized for fragment in EXCLUDED_MODEL_FRAGMENTS)


def list_installed_models() -> list[dict[str, Any]]:
    payload = _request_json(TAGS_URL, expected_path="/api/tags", timeout=30)
    models: list[dict[str, Any]] = []
    for item in payload.get("models", []):
        if not isinstance(item, dict):
            continue
        name = item.get("name") or item.get("model")
        if not isinstance(name, str) or not name:
            continue
        models.append(
            {
                "name": name,
                "digest": item.get("digest"),
                "size": item.get("size"),
                "modified_at": item.get("modified_at"),
            }
        )
    models.sort(key=lambda item: item["name"].casefold())
    if not models:
        raise ProbeError("Ollama returned no installed models")
    return models


def running_models() -> list[dict[str, Any]]:
    payload = _request_json(PS_URL, expected_path="/api/ps", timeout=30)
    return [
        dict(item)
        for item in payload.get("models", [])
        if isinstance(item, dict)
    ]


def _running_name(item: dict[str, Any]) -> str | None:
    value = item.get("name") or item.get("model")
    return value if isinstance(value, str) else None


def stop_model(model_name: str) -> dict[str, Any]:
    result = _run(["ollama", "stop", model_name], timeout=60)
    deadline = time.monotonic() + 45
    absent = False
    last_error: str | None = None
    while time.monotonic() < deadline:
        try:
            names = {_running_name(item) for item in running_models()}
            if model_name not in names:
                absent = True
                break
        except ProbeError as exc:
            last_error = str(exc)
        time.sleep(1)
    return {
        "command": result,
        "verified_absent": absent,
        "verification_error": last_error,
    }


def stop_all_running_models() -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for item in running_models():
        name = _running_name(item)
        if name:
            results.append({"model": name, **stop_model(name)})
    return results


def _find_running_model(model_name: str) -> dict[str, Any] | None:
    matches = [
        item for item in running_models() if _running_name(item) == model_name
    ]
    if len(matches) != 1:
        return None
    return matches[0]


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_manifest(output_dir: Path) -> dict[str, Any]:
    evidence_paths = [output_dir / "report.json"]
    evidence_paths.extend(sorted((output_dir / "models").glob("*/result.json")))
    artifacts = {
        path.relative_to(output_dir).as_posix(): {
            "sha256": _sha256_file(path),
            "size_bytes": path.stat().st_size,
        }
        for path in evidence_paths
        if path.exists()
    }
    manifest = {
        "schema_version": "bench.model-residency-manifest.v1",
        "created_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "artifacts": artifacts,
    }
    _write_json(output_dir / "manifest.json", manifest)
    return manifest


def probe_model(model: dict[str, Any], output_dir: Path) -> dict[str, Any]:
    model_name = model["name"]
    safe_name = "".join(
        character if character.isalnum() or character in "._-" else "_"
        for character in model_name
    )
    model_dir = output_dir / "models" / safe_name
    model_dir.mkdir(parents=True, exist_ok=True)

    if is_user_excluded(model_name):
        result = {
            "model": model,
            "classification": "excluded",
            "reason": "explicit_user_exclusion",
            "profile": PROFILE,
        }
        _write_json(model_dir / "result.json", result)
        return result

    cleanup_before = stop_all_running_models()
    baseline_gpu = gpu_snapshot()
    started = time.monotonic()
    generate_response: dict[str, Any] | None = None
    ps_entry: dict[str, Any] | None = None
    error: dict[str, str] | None = None

    try:
        generate_response = _request_json(
            GENERATE_URL,
            expected_path="/api/generate",
            timeout=int(PROFILE["request_timeout_seconds"]),
            payload={
                "model": model_name,
                "prompt": "Return exactly OK.",
                "stream": False,
                "keep_alive": PROFILE["keep_alive"],
                "options": {
                    "temperature": PROFILE["temperature"],
                    "seed": PROFILE["seed"],
                    "num_predict": PROFILE["num_predict"],
                    "num_ctx": PROFILE["num_ctx"],
                },
            },
        )
        if generate_response.get("done") is not True:
            raise ProbeError("Ollama generate response was incomplete")
        ps_entry = _find_running_model(model_name)
        if ps_entry is None:
            raise ProbeError("loaded model was not uniquely visible in /api/ps")
    except ProbeError as exc:
        error = {"type": type(exc).__name__, "detail": str(exc)}

    duration_seconds = time.monotonic() - started
    loaded_gpu = gpu_snapshot()
    cleanup_after = stop_model(model_name)

    if error is not None or ps_entry is None:
        classification = "load_failed"
        residency_ratio = None
    else:
        classification, residency_ratio = classify_residency(
            ps_entry.get("size"),
            ps_entry.get("size_vram"),
        )

    result = {
        "model": model,
        "profile": PROFILE,
        "classification": classification,
        "residency_ratio": residency_ratio,
        "probe_duration_seconds": round(duration_seconds, 3),
        "ollama_generate": generate_response,
        "ollama_ps_entry": ps_entry,
        "gpu_before": baseline_gpu,
        "gpu_loaded": loaded_gpu,
        "cleanup_before": cleanup_before,
        "cleanup_after": cleanup_after,
        "error": error,
    }
    _write_json(model_dir / "result.json", result)
    return result


def build_report(output_dir: Path) -> dict[str, Any]:
    created_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    initial_gpu = gpu_snapshot()
    initial_cleanup: list[dict[str, Any]] = []
    models: list[dict[str, Any]] = []
    infrastructure_error: dict[str, str] | None = None

    try:
        installed = list_installed_models()
        initial_cleanup = stop_all_running_models()
        for model in installed:
            models.append(probe_model(model, output_dir))
    except ProbeError as exc:
        infrastructure_error = {"type": type(exc).__name__, "detail": str(exc)}

    counts: dict[str, int] = {}
    for result in models:
        classification = str(result.get("classification"))
        counts[classification] = counts.get(classification, 0) + 1

    return {
        "schema_version": SCHEMA_VERSION,
        "created_at_utc": created_at,
        "workflow": {
            "run_id": os.environ.get("GITHUB_RUN_ID"),
            "run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
            "event_name": os.environ.get("GITHUB_EVENT_NAME"),
            "sha": os.environ.get("GITHUB_SHA"),
            "ref": os.environ.get("GITHUB_REF"),
        },
        "profile": PROFILE,
        "explicit_exclusions": list(EXCLUDED_MODEL_FRAGMENTS),
        "initial_gpu": initial_gpu,
        "initial_cleanup": initial_cleanup,
        "infrastructure_error": infrastructure_error,
        "classification_counts": counts,
        "models": models,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Measure sequential Ollama model GPU residency."
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    report = build_report(args.output_dir)
    _write_json(args.output_dir / "report.json", report)
    write_manifest(args.output_dir)
    print(json.dumps(report, indent=2, sort_keys=True))

    if report["infrastructure_error"] is not None:
        return 2
    if not report["initial_gpu"].get("ok"):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
