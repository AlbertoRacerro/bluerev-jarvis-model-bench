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

SCHEMA_VERSION = "bench.h3-context-report.v1"
RESULT_SCHEMA = "bench.h3-context-result.v1"
MANIFEST_SCHEMA = "bench.h3-context-manifest.v1"
PLAN_SCHEMA = "bench.h3-primary-32k-plan.v1"
SUMMARY_SCHEMA = "bench.h2-primary-16k-summary.v1"
SUMMARY_MANIFEST_SCHEMA = "bench.h2-primary-16k-summary-manifest.v1"
EXPECTED_PLAN_SHA256 = "0bf7838ef0199be1dcf89122bbdedaf17ca4253223eafd0b89472bdcba3d7c12"
EXPECTED_SUMMARY_SHA256 = "4ae087c5aa221a80573db900cba992f3044c2205e6ded6864ea9a5c2bb02e8ca"
EXPECTED_SUMMARY_MANIFEST_SHA256 = "c9de10f2c151825000e8dd2635bf9c49263a9e4fcf5558add907ba24fb57cdb1"
EXPECTED_H2_EXECUTION_COMMIT = "8c6b73d8263c0603dfd286debec3bd4c3377746f"
EXPECTED_H2_CLOSEOUT_COMMIT = "7e937f91a83b1d369ce06891b42eaf805324cb5f"
PROFILE = {
    "name": "h3-primary-32k-context", "num_ctx": 32768, "num_predict": 32,
    "temperature": 0, "seed": 4242, "keep_alive": "5m",
    "request_timeout_seconds": 600,
}
BATCH_SIZE, BATCH_COUNT = 2, 5
_ALLOWED_RESULTS = {"qualified_32k", "cpu_offload", "context_mismatch", "load_failed"}
_SHA256_CHARS = frozenset("0123456789abcdef")


class H3ProbeError(RuntimeError):
    pass


class H3InfrastructureError(H3ProbeError):
    pass


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _source_bytes(path: Path) -> bytes:
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
    return text.encode("utf-8")


def _source_sha256(path: Path) -> str:
    return hashlib.sha256(_source_bytes(path)).hexdigest()


def _valid_sha256(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(c in _SHA256_CHARS for c in value)


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise H3ProbeError(f"cannot read {path.name}: {type(exc).__name__}") from exc
    if not isinstance(value, dict):
        raise H3ProbeError(f"{path.name} must contain an object")
    return value


def _validate_summary_manifest(summary_path: Path, manifest_path: Path) -> None:
    if _source_sha256(summary_path) != EXPECTED_SUMMARY_SHA256:
        raise H3ProbeError("H2 summary digest mismatch")
    if _source_sha256(manifest_path) != EXPECTED_SUMMARY_MANIFEST_SHA256:
        raise H3ProbeError("H2 summary manifest root digest mismatch")
    manifest = _load_json(manifest_path)
    artifacts = manifest.get("artifacts")
    if manifest.get("schema_version") != SUMMARY_MANIFEST_SCHEMA:
        raise H3ProbeError("H2 summary manifest schema is invalid")
    if not isinstance(artifacts, dict) or set(artifacts) != {"summary.json", "summary.md"}:
        raise H3ProbeError("H2 summary manifest inventory mismatch")
    record = artifacts.get("summary.json")
    if not isinstance(record, dict) or record.get("sha256") != EXPECTED_SUMMARY_SHA256:
        raise H3ProbeError("H2 summary manifest digest binding mismatch")
    if record.get("size_bytes") != len(_source_bytes(summary_path)):
        raise H3ProbeError("H2 summary manifest size binding mismatch")


def _validate_summary(summary: dict[str, Any]) -> list[dict[str, str]]:
    if summary.get("schema_version") != SUMMARY_SCHEMA or summary.get("status") != "complete":
        raise H3ProbeError("H2 summary schema or status is invalid")
    if summary.get("counts") != {
        "artifacts": 4, "candidates": 12, "context_mismatch": 0,
        "cpu_offload": 2, "load_failed": 0, "qualified_16k": 10,
    }:
        raise H3ProbeError("H2 summary counts are not the approved closeout")
    expected_integrity = {
        "all_archives_match_github_digest": True, "all_cleanup_verified": True,
        "all_context_lengths_16384": True, "all_manifests_verified": True,
        "external_providers_used": False, "hermes_executed": False,
        "jarvisos_accessed": False, "secret_values_recorded": False,
        "unique_candidate_digests": True, "unique_candidate_names": True,
    }
    if summary.get("integrity") != expected_integrity:
        raise H3ProbeError("H2 summary integrity contract drifted")
    primary, results = summary.get("primary_32k"), summary.get("results")
    if not isinstance(primary, list) or len(primary) != 10:
        raise H3ProbeError("H2 primary 32K candidate list is incomplete")
    if not isinstance(results, list) or len(results) != 12:
        raise H3ProbeError("H2 summary result inventory is incomplete")
    by_digest = {item.get("digest"): item for item in results if isinstance(item, dict)}
    candidates: list[dict[str, str]] = []
    names: set[str] = set()
    digests: set[str] = set()
    for item in primary:
        if not isinstance(item, dict):
            raise H3ProbeError("H2 primary candidate must be an object")
        name, digest = item.get("name"), item.get("digest")
        if not isinstance(name, str) or not name or not _valid_sha256(digest):
            raise H3ProbeError("H2 primary candidate identity is invalid")
        source = by_digest.get(digest)
        if name in names or digest in digests or not isinstance(source, dict):
            raise H3ProbeError("H2 primary candidate identities are not unique")
        if not (
            source.get("name") == name and source.get("status") == "qualified_16k"
            and source.get("residency_ratio") == 1.0
            and source.get("context_length") == 16384
            and source.get("cleanup_verified") is True
        ):
            raise H3ProbeError(f"H2 primary source evidence is invalid: {name}")
        names.add(name)
        digests.add(digest)
        candidates.append({"name": name, "digest": digest})
    return candidates


def validate_plan(
    plan_path: Path,
    summary_path: Path,
    manifest_path: Path,
    expected_digest: str,
) -> list[dict[str, str]]:
    if expected_digest != EXPECTED_PLAN_SHA256:
        raise H3ProbeError("untrusted H3 plan digest requested")
    if _source_sha256(plan_path) != expected_digest:
        raise H3ProbeError("H3 plan digest mismatch")
    _validate_summary_manifest(summary_path, manifest_path)
    source_candidates = _validate_summary(_load_json(summary_path))
    plan = _load_json(plan_path)
    if plan.get("schema_version") != PLAN_SCHEMA or plan.get("status") != "ready":
        raise H3ProbeError("H3 plan schema or status is invalid")
    if plan.get("profile") != PROFILE or plan.get("batching") != {"batch_count": 5, "batch_size": 2}:
        raise H3ProbeError("H3 profile or batching contract drifted")
    if plan.get("counts") != {"batches": 5, "candidates": 10, "context_probes": 10}:
        raise H3ProbeError("H3 plan counts are invalid")
    if plan.get("execution_policy") != {
        "allow_cpu_offload": False, "credentials_allowed": False,
        "external_providers_allowed": False, "hermes_execution_allowed": False,
        "jarvisos_access_allowed": False, "local_only": True,
        "max_parallel_models": 1, "sequential_models": True,
        "verify_cleanup": True, "verify_singleton_process": True,
    }:
        raise H3ProbeError("H3 execution policy drifted")
    if plan.get("source") != {
        "h1_artifact_sha256": "6458a0fcce21bf74850ced340f0172089c67143955af2c6177696d1e45045540",
        "h2_16k_plan_sha256": "cce4863f87520dae70ea97fcd75a88d4ada0dff874202376cc9223ea6c29868a",
        "h2_closeout_commit_sha": EXPECTED_H2_CLOSEOUT_COMMIT,
        "h2_execution_commit_sha": EXPECTED_H2_EXECUTION_COMMIT,
        "h2_manifest_path": "reports/H2-PRIMARY-16K/manifest.json",
        "h2_manifest_sha256": EXPECTED_SUMMARY_MANIFEST_SHA256,
        "h2_summary_path": "reports/H2-PRIMARY-16K/summary.json",
        "h2_summary_sha256": EXPECTED_SUMMARY_SHA256,
    }:
        raise H3ProbeError("H3 source binding drifted")
    raw = plan.get("candidates")
    if not isinstance(raw, list) or len(raw) != 10:
        raise H3ProbeError("H3 candidate list is incomplete")
    for index, item in enumerate(raw):
        expected = {
            "sequence": index,
            "name": source_candidates[index]["name"],
            "digest": source_candidates[index]["digest"],
            "source_16k_status": "qualified_16k",
            "source_16k_residency_ratio": 1.0,
        }
        if item != expected:
            raise H3ProbeError(f"H3 candidate binding drifted at sequence {index}")
    return source_candidates


def select_candidates(
    candidates: list[dict[str, str]],
    *,
    batch_index: int,
) -> tuple[list[dict[str, str]], dict[str, int | str]]:
    if not 0 <= batch_index < BATCH_COUNT:
        raise H3ProbeError("H3 batch index is outside the approved range")
    start, end = batch_index * BATCH_SIZE, (batch_index + 1) * BATCH_SIZE
    selected = candidates[start:end]
    if len(selected) != BATCH_SIZE:
        raise H3ProbeError("H3 batch does not contain exactly two candidates")
    return selected, {
        "mode": "batch", "batch_index": batch_index, "batch_size": 2,
        "start": start, "end": end, "expected_count": 2,
        "total_candidates": len(candidates),
    }


def _installed_candidates(candidates: list[dict[str, str]]) -> list[dict[str, Any]]:
    installed = {item["name"]: item for item in base.list_installed_models()}
    selected: list[dict[str, Any]] = []
    for candidate in candidates:
        item = installed.get(candidate["name"])
        if item is None or item.get("digest") != candidate["digest"]:
            raise H3InfrastructureError(
                f"approved H3 candidate missing or changed: {candidate['name']}"
            )
        selected.append(item)
    return selected


def _metric_rate(count: Any, duration_ns: Any) -> float | None:
    if not isinstance(count, int) or isinstance(count, bool) or count < 0:
        return None
    if not isinstance(duration_ns, int) or isinstance(duration_ns, bool) or duration_ns <= 0:
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
        return "load_failed", None, {
            "type": "H3ProbeError", "detail": "generation did not complete",
        }
    if ps_entry.get("context_length") != PROFILE["num_ctx"]:
        return "context_mismatch", None, {
            "type": "H3ProbeError",
            "detail": f"expected context_length=32768, got {ps_entry.get('context_length')!r}",
        }
    residency, ratio = base.classify_residency(
        ps_entry.get("size"), ps_entry.get("size_vram")
    )
    if residency == "unknown":
        return "load_failed", None, {
            "type": "H3ProbeError", "detail": "invalid residency metrics",
        }
    return ("qualified_32k" if residency == "full_vram" else "cpu_offload"), ratio, None


def probe_candidate(model: dict[str, Any], output_dir: Path) -> dict[str, Any]:
    name = model["name"]
    model_dir = output_dir / "models" / base.model_artifact_slug(name)
    model_dir.mkdir(parents=True, exist_ok=True)
    cleanup_before = stop_all_running_models()
    gpu_before = base.gpu_snapshot()
    if gpu_before.get("ok") is not True:
        raise H3InfrastructureError(f"GPU snapshot failed before candidate: {name}")
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
                timeout=600,
                payload={
                    "model": name,
                    "prompt": "Provide a short acknowledgement.",
                    "stream": False,
                    "keep_alive": "5m",
                    "options": {
                        "temperature": 0,
                        "seed": 4242,
                        "num_predict": 32,
                        "num_ctx": 32768,
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
            primary_error = H3InfrastructureError(
                f"GPU snapshot failed after loading candidate: {name}"
            )
    finally:
        try:
            cleanup_after = {
                "verified_absent": True,
                "models": stop_all_running_models(),
            }
        except base.ProbeError as exc:
            primary_error = H3InfrastructureError(
                f"primary={primary_error}; cleanup={exc}"
            )
    if primary_error is not None or cleanup_after is None:
        raise H3InfrastructureError(str(primary_error or "cleanup attestation missing"))
    status, ratio, error = _classify_result(response, ps_entry, error)
    metrics = {
        key: response.get(key) if response else None
        for key in (
            "total_duration", "load_duration", "prompt_eval_count",
            "prompt_eval_duration", "eval_count", "eval_duration", "done_reason",
        )
    }
    metrics["prompt_tokens_per_second"] = _metric_rate(
        metrics["prompt_eval_count"], metrics["prompt_eval_duration"]
    )
    metrics["generation_tokens_per_second"] = _metric_rate(
        metrics["eval_count"], metrics["eval_duration"]
    )
    result = {
        "schema_version": RESULT_SCHEMA,
        "artifact_slug": base.model_artifact_slug(name),
        "model": model,
        "profile": PROFILE,
        "status": status,
        "residency_ratio": ratio,
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
    paths = [
        output_dir / "report.json",
        *sorted((output_dir / "models").glob("*/result.json")),
    ]
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


def build_report(
    plan_path: Path,
    summary_path: Path,
    manifest_path: Path,
    expected_digest: str,
    output_dir: Path,
    *,
    batch_index: int,
) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    infrastructure_error: dict[str, str] | None = None
    initial_gpu = base.gpu_snapshot()
    initial_cleanup: list[dict[str, Any]] = []
    final_cleanup: list[dict[str, Any]] = []
    candidates: list[dict[str, str]] = []
    selected: list[dict[str, str]] = []
    selection: dict[str, int | str] | None = None
    try:
        if initial_gpu.get("ok") is not True:
            raise H3InfrastructureError("initial GPU snapshot failed")
        candidates = validate_plan(
            plan_path, summary_path, manifest_path, expected_digest
        )
        selected, selection = select_candidates(candidates, batch_index=batch_index)
        installed = _installed_candidates(selected)
        initial_cleanup = stop_all_running_models()
        results = [probe_candidate(model, output_dir) for model in installed]
    except (H3ProbeError, base.ProbeError) as exc:
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
    counts = {
        status: sum(result.get("status") == status for result in results)
        for status in sorted(_ALLOWED_RESULTS)
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "created_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "workflow": {
            "run_id": os.environ.get("GITHUB_RUN_ID"),
            "run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
            "event_name": os.environ.get("GITHUB_EVENT_NAME"),
            "sha": os.environ.get("GITHUB_SHA"),
            "ref": os.environ.get("GITHUB_REF"),
        },
        "source": {
            "plan_path": plan_path.as_posix(),
            "plan_sha256": expected_digest,
            "h2_summary_path": summary_path.as_posix(),
            "h2_summary_sha256": EXPECTED_SUMMARY_SHA256,
            "h2_summary_manifest_path": manifest_path.as_posix(),
            "h2_summary_manifest_sha256": EXPECTED_SUMMARY_MANIFEST_SHA256,
            "h2_execution_commit_sha": EXPECTED_H2_EXECUTION_COMMIT,
            "h2_closeout_commit_sha": EXPECTED_H2_CLOSEOUT_COMMIT,
        },
        "profile": PROFILE,
        "candidate_count": len(selected),
        "plan_candidate_count": len(candidates),
        "selection": selection,
        "initial_gpu": initial_gpu,
        "initial_cleanup": initial_cleanup,
        "final_cleanup": final_cleanup,
        "infrastructure_error": infrastructure_error,
        "status_counts": counts,
        "required_failures": [
            result["model"]["name"]
            for result in results
            if result.get("status") != "qualified_32k"
        ],
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one deterministic H3 32K batch.")
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--summary-manifest", type=Path, required=True)
    parser.add_argument("--expected-plan-sha256", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--batch-index", type=int, required=True)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    report = build_report(
        args.plan,
        args.summary,
        args.summary_manifest,
        args.expected_plan_sha256,
        args.output_dir,
        batch_index=args.batch_index,
    )
    _write_json(args.output_dir / "report.json", report)
    write_manifest(args.output_dir)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 2 if report["infrastructure_error"] is not None else 0


if __name__ == "__main__":
    raise SystemExit(main())
