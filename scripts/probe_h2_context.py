from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts import probe_model_residency as base
from scripts.probe_model_residency_v2 import stop_all_running_models

SCHEMA_VERSION = "bench.h2-context-report.v1"
MANIFEST_SCHEMA = "bench.h2-context-manifest.v1"
PLAN_SCHEMA = "bench.h2-context-plan.v1"
EXPECTED_PLAN_SHA256 = "cce4863f87520dae70ea97fcd75a88d4ada0dff874202376cc9223ea6c29868a"
EXPECTED_H1_ARTIFACT_SHA256 = "6458a0fcce21bf74850ced340f0172089c67143955af2c6177696d1e45045540"
EXPECTED_H1_SOURCE = {
    "run_id": "29106127334",
    "run_attempt": "4",
    "event_name": "workflow_dispatch",
    "sha": "6632bd6099343f561ad7965ddaa70263a507a79c",
    "ref": "refs/heads/main",
}
EXPECTED_SOURCE_DIGESTS = {
    "report_sha256": "eca66e93868c8b0d7783709692e38c2de84514e2f9c97fd25ba588a78a3b9c31",
    "residency_manifest_sha256": "b201455bff7d6cbdaaaf573c82df7f68b8ae99e348507af9ee59f26594575ad4",
    "shortlist_manifest_sha256": "56dcabee3ddec5a67bad76f5997af708e7752f70afe085da74db269768d09959",
    "shortlist_sha256": "b929076eb62716de75cda4766289b88a736fae2fe93497f5d1b7265467fe14dc",
}
PROFILE = {
    "name": "h2-primary-16k-context",
    "num_ctx": 16384,
    "num_predict": 32,
    "temperature": 0,
    "seed": 4242,
    "keep_alive": "5m",
    "request_timeout_seconds": 600,
}
_ALLOWED_RESULTS = {
    "qualified_16k",
    "cpu_offload",
    "context_mismatch",
    "load_failed",
}


class H2ProbeError(RuntimeError):
    pass


class H2InfrastructureError(H2ProbeError):
    pass


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise H2ProbeError(f"cannot read {path.name}: {type(exc).__name__}") from exc
    if not isinstance(value, dict):
        raise H2ProbeError(f"{path.name} must contain an object")
    return value


def validate_plan(plan_path: Path, expected_sha256: str) -> list[dict[str, str]]:
    if expected_sha256 != EXPECTED_PLAN_SHA256:
        raise H2ProbeError("untrusted H2 plan digest requested")
    if _sha256(plan_path) != expected_sha256:
        raise H2ProbeError("H2 plan digest mismatch")
    plan = _load_json(plan_path)
    if plan.get("schema_version") != PLAN_SCHEMA or plan.get("status") != "ready":
        raise H2ProbeError("H2 plan schema or status is invalid")
    if plan.get("profiles") != [16384, 32768]:
        raise H2ProbeError("H2 plan profiles are not the approved 16K/32K sequence")
    if plan.get("counts") != {"candidates": 12, "context_probes": 24}:
        raise H2ProbeError("H2 plan counts do not match the approved primary lane")
    policy = plan.get("execution_policy")
    expected_policy = {
        "credentials_allowed": False,
        "external_providers_allowed": False,
        "hermes_install_mutation_allowed": False,
        "jarvisos_access_allowed": False,
        "local_only": True,
        "max_parallel_models": 1,
        "sequential_models": True,
        "trusted_main_only": True,
    }
    if policy != expected_policy:
        raise H2ProbeError("H2 execution policy drifted")
    source = plan.get("source")
    if not isinstance(source, dict):
        raise H2ProbeError("H2 source binding is missing")
    for key, expected in EXPECTED_SOURCE_DIGESTS.items():
        if source.get(key) != expected:
            raise H2ProbeError(f"H2 source digest mismatch: {key}")
    if source.get("workflow") != EXPECTED_H1_SOURCE:
        raise H2ProbeError("H2 source workflow binding mismatch")

    raw_cases = plan.get("cases")
    if not isinstance(raw_cases, list) or len(raw_cases) != 12:
        raise H2ProbeError("H2 primary candidate list is incomplete")
    candidates: list[dict[str, str]] = []
    names: set[str] = set()
    digests: set[str] = set()
    for item in raw_cases:
        if not isinstance(item, dict):
            raise H2ProbeError("H2 case must be an object")
        candidate = item.get("candidate")
        contexts = item.get("contexts")
        if not isinstance(candidate, dict) or not isinstance(contexts, list):
            raise H2ProbeError("H2 case candidate or contexts are invalid")
        name, digest = candidate.get("name"), candidate.get("digest")
        if not isinstance(name, str) or not name:
            raise H2ProbeError("H2 candidate name is invalid")
        if not isinstance(digest, str) or len(digest) != 64:
            raise H2ProbeError(f"H2 candidate digest is invalid: {name}")
        if name in names or digest in digests:
            raise H2ProbeError("H2 candidate identities are not unique")
        names.add(name)
        digests.add(digest)
        if len(contexts) != 2:
            raise H2ProbeError(f"H2 context sequence is incomplete: {name}")
        first, second = contexts
        expected_first = {
            "allow_cpu_offload": False,
            "num_ctx": 16384,
            "required": True,
            "sequence": 1,
            "timeout_seconds": 600,
            "verify_cleanup": True,
            "verify_singleton_process": True,
        }
        expected_second = {
            "allow_cpu_offload": False,
            "num_ctx": 32768,
            "required": False,
            "sequence": 2,
            "timeout_seconds": 600,
            "verify_cleanup": True,
            "verify_singleton_process": True,
        }
        if first != expected_first or second != expected_second:
            raise H2ProbeError(f"H2 context contract drifted: {name}")
        candidates.append({"name": name, "digest": digest})
    return candidates


def _installed_primary(candidates: list[dict[str, str]]) -> list[dict[str, Any]]:
    installed = {item["name"]: item for item in base.list_installed_models()}
    selected: list[dict[str, Any]] = []
    for candidate in candidates:
        item = installed.get(candidate["name"])
        if item is None:
            raise H2InfrastructureError(
                f"approved H2 candidate is not installed: {candidate['name']}"
            )
        if item.get("digest") != candidate["digest"]:
            raise H2InfrastructureError(
                f"approved H2 candidate digest changed: {candidate['name']}"
            )
        selected.append(item)
    return selected


def _metric_rate(count: Any, duration_ns: Any) -> float | None:
    if (
        not isinstance(count, int)
        or isinstance(count, bool)
        or count < 0
        or not isinstance(duration_ns, int)
        or isinstance(duration_ns, bool)
        or duration_ns <= 0
    ):
        return None
    return round(count / (duration_ns / 1_000_000_000), 3)


def _classify_result(
    response: dict[str, Any] | None,
    ps_entry: dict[str, Any] | None,
    error: dict[str, str] | None,
) -> tuple[str, float | None, dict[str, str] | None]:
    if error is not None or response is None or ps_entry is None:
        return "load_failed", None, error
    if response.get("done") is not True:
        return (
            "load_failed",
            None,
            {"type": "H2ProbeError", "detail": "Ollama generation did not complete"},
        )
    context_length = ps_entry.get("context_length")
    if context_length != PROFILE["num_ctx"]:
        return (
            "context_mismatch",
            None,
            {
                "type": "H2ProbeError",
                "detail": f"expected context_length={PROFILE['num_ctx']}, got {context_length!r}",
            },
        )
    residency, ratio = base.classify_residency(
        ps_entry.get("size"), ps_entry.get("size_vram")
    )
    if residency == "unknown":
        return (
            "load_failed",
            None,
            {"type": "H2ProbeError", "detail": "invalid Ollama residency metrics"},
        )
    if residency != "full_vram":
        return "cpu_offload", ratio, None
    return "qualified_16k", ratio, None


def probe_candidate(model: dict[str, Any], output_dir: Path) -> dict[str, Any]:
    name = model["name"]
    model_dir = output_dir / "models" / base.model_artifact_slug(name)
    model_dir.mkdir(parents=True, exist_ok=True)
    cleanup_before = stop_all_running_models()
    gpu_before = base.gpu_snapshot()
    if gpu_before.get("ok") is not True:
        raise H2InfrastructureError(f"GPU snapshot failed before candidate: {name}")

    started = time.monotonic()
    response: dict[str, Any] | None = None
    ps_entry: dict[str, Any] | None = None
    error: dict[str, str] | None = None
    primary_error: Exception | None = None
    cleanup_after: dict[str, Any] | None = None
    gpu_loaded: dict[str, Any] = {"ok": False, "gpus": []}
    try:
        try:
            response = base._request_json(
                base.GENERATE_URL,
                expected_path="/api/generate",
                timeout=int(PROFILE["request_timeout_seconds"]),
                payload={
                    "model": name,
                    "prompt": "Provide a short acknowledgement.",
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
            ps_entry = base._find_single_running_model(model)
        except base.InfrastructureProbeError as exc:
            primary_error = exc
        except base.ProbeError as exc:
            error = {"type": type(exc).__name__, "detail": str(exc)}
        gpu_loaded = base.gpu_snapshot()
        if gpu_loaded.get("ok") is not True and primary_error is None:
            primary_error = H2InfrastructureError(
                f"GPU snapshot failed after loading candidate: {name}"
            )
    finally:
        try:
            cleanup_after = {
                "verified_absent": True,
                "models": stop_all_running_models(),
            }
        except base.ProbeError as exc:
            if primary_error is None:
                primary_error = exc
            else:
                primary_error = H2InfrastructureError(
                    f"primary={primary_error}; cleanup={exc}"
                )
    if primary_error is not None:
        raise H2InfrastructureError(str(primary_error))
    if cleanup_after is None:
        raise H2InfrastructureError(f"cleanup attestation missing: {name}")

    status, residency_ratio, error = _classify_result(response, ps_entry, error)
    metrics = {
        "total_duration_ns": response.get("total_duration") if response else None,
        "load_duration_ns": response.get("load_duration") if response else None,
        "prompt_eval_count": response.get("prompt_eval_count") if response else None,
        "prompt_eval_duration_ns": response.get("prompt_eval_duration") if response else None,
        "eval_count": response.get("eval_count") if response else None,
        "eval_duration_ns": response.get("eval_duration") if response else None,
        "prompt_tokens_per_second": _metric_rate(
            response.get("prompt_eval_count") if response else None,
            response.get("prompt_eval_duration") if response else None,
        ),
        "generation_tokens_per_second": _metric_rate(
            response.get("eval_count") if response else None,
            response.get("eval_duration") if response else None,
        ),
        "done_reason": response.get("done_reason") if response else None,
    }
    result = {
        "schema_version": "bench.h2-context-result.v1",
        "artifact_slug": base.model_artifact_slug(name),
        "model": model,
        "profile": PROFILE,
        "status": status,
        "residency_ratio": residency_ratio,
        "probe_duration_seconds": round(time.monotonic() - started, 3),
        "ollama_ps_entry": ps_entry,
        "metrics": metrics,
        "gpu_before": gpu_before,
        "gpu_loaded": gpu_loaded,
        "cleanup_before": cleanup_before,
        "cleanup_after": cleanup_after,
        "error": error,
    }
    _write_json(model_dir / "result.json", result)
    return result


def write_manifest(output_dir: Path) -> dict[str, Any]:
    paths = [output_dir / "report.json"]
    paths.extend(sorted((output_dir / "models").glob("*/result.json")))
    manifest = {
        "schema_version": MANIFEST_SCHEMA,
        "created_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "artifacts": {
            path.relative_to(output_dir).as_posix(): {
                "sha256": _sha256(path),
                "size_bytes": path.stat().st_size,
            }
            for path in paths
            if path.is_file()
        },
    }
    _write_json(output_dir / "manifest.json", manifest)
    return manifest


def build_report(plan_path: Path, expected_plan_sha256: str, output_dir: Path) -> dict[str, Any]:
    created_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    results: list[dict[str, Any]] = []
    infrastructure_error: dict[str, str] | None = None
    initial_gpu = base.gpu_snapshot()
    initial_cleanup: list[dict[str, Any]] = []
    final_cleanup: list[dict[str, Any]] = []
    candidates: list[dict[str, str]] = []
    try:
        if initial_gpu.get("ok") is not True:
            raise H2InfrastructureError("initial GPU snapshot failed")
        candidates = validate_plan(plan_path, expected_plan_sha256)
        installed = _installed_primary(candidates)
        initial_cleanup = stop_all_running_models()
        for model in installed:
            results.append(probe_candidate(model, output_dir))
    except (H2ProbeError, base.ProbeError) as exc:
        infrastructure_error = {"type": type(exc).__name__, "detail": str(exc)}
    finally:
        try:
            final_cleanup = stop_all_running_models()
        except base.ProbeError as exc:
            detail = f"final cleanup failed: {exc}"
            if infrastructure_error is None:
                infrastructure_error = {"type": type(exc).__name__, "detail": detail}
            else:
                infrastructure_error["detail"] += "; " + detail

    counts = {status: 0 for status in sorted(_ALLOWED_RESULTS)}
    for result in results:
        status = result.get("status")
        if status in counts:
            counts[status] += 1
    required_failures = [
        result["model"]["name"]
        for result in results
        if result.get("status") != "qualified_16k"
    ]
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
        "source": {
            "plan_path": plan_path.as_posix(),
            "plan_sha256": expected_plan_sha256,
            "h1_artifact_sha256": EXPECTED_H1_ARTIFACT_SHA256,
            "h1_workflow": EXPECTED_H1_SOURCE,
            **EXPECTED_SOURCE_DIGESTS,
        },
        "profile": PROFILE,
        "candidate_count": len(candidates),
        "initial_gpu": initial_gpu,
        "initial_cleanup": initial_cleanup,
        "final_cleanup": final_cleanup,
        "infrastructure_error": infrastructure_error,
        "status_counts": counts,
        "required_failures": required_failures,
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Qualify H1 primary models at 16K context.")
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--expected-plan-sha256", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    report = build_report(args.plan, args.expected_plan_sha256, args.output_dir)
    _write_json(args.output_dir / "report.json", report)
    write_manifest(args.output_dir)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 2 if report["infrastructure_error"] is not None else 0


if __name__ == "__main__":
    raise SystemExit(main())
