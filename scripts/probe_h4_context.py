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

SCHEMA_VERSION = "bench.h4-context-report.v1"
RESULT_SCHEMA = "bench.h4-context-result.v1"
MANIFEST_SCHEMA = "bench.h4-context-manifest.v1"
PLAN_SCHEMA = "bench.h4-hermes-minimum-64k-plan.v1"
H3_SUMMARY_SCHEMA = "bench.h3-primary-32k-summary.v1"
H3_MANIFEST_SCHEMA = "bench.h3-primary-32k-summary-manifest.v1"
EXPECTED_PLAN_SHA256 = "b94032a9104316f2e05cb4c1b8934772fee66804dd609d84a570d4f4e940e146"
EXPECTED_H3_SUMMARY_SHA256 = "4e92a93269f3c574c86224f24535122aa14e1976508adeac69a49ea6fdf3bfcf"
EXPECTED_H3_MANIFEST_SHA256 = "10521b1cbc3762878a5b932d673d34d8744cade9acafd1f8da4dc386bbf0db3c"
EXPECTED_H3_CLOSEOUT_COMMIT = "7c82dc8335208c87c14a1dd0e1ae1de066bcba74"
EXPECTED_HERMES_COMMIT = "73b611ad19720d70308dad6b0fb64648aaadc216"
PROFILE = {
    "name": "h4-hermes-minimum-64k-context",
    "num_ctx": 65536,
    "num_predict": 32,
    "temperature": 0,
    "seed": 4242,
    "keep_alive": "5m",
    "request_timeout_seconds": 900,
}
BATCH_SIZE = 2
BATCH_COUNT = 5
_ALLOWED_RESULTS = {"qualified_64k", "cpu_offload", "context_mismatch", "load_failed"}
_SHA256_CHARS = frozenset("0123456789abcdef")


class H4ProbeError(RuntimeError):
    pass


class H4InfrastructureError(H4ProbeError):
    pass


def _source_bytes(path: Path) -> bytes:
    return path.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")


def _source_sha256(path: Path) -> str:
    return hashlib.sha256(_source_bytes(path)).hexdigest()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise H4ProbeError(f"cannot read {path.name}: {type(exc).__name__}") from exc
    if not isinstance(value, dict):
        raise H4ProbeError(f"{path.name} must contain an object")
    return value


def _valid_sha256(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(c in _SHA256_CHARS for c in value)


def _validate_h3_source(summary_path: Path, manifest_path: Path) -> list[dict[str, str]]:
    if _source_sha256(summary_path) != EXPECTED_H3_SUMMARY_SHA256:
        raise H4ProbeError("H3 summary digest mismatch")
    if _source_sha256(manifest_path) != EXPECTED_H3_MANIFEST_SHA256:
        raise H4ProbeError("H3 manifest digest mismatch")
    manifest = _load_json(manifest_path)
    if manifest.get("schema_version") != H3_MANIFEST_SCHEMA:
        raise H4ProbeError("H3 manifest schema is invalid")
    artifacts = manifest.get("artifacts")
    record = artifacts.get("summary.json") if isinstance(artifacts, dict) else None
    if not isinstance(record, dict) or record.get("sha256") != EXPECTED_H3_SUMMARY_SHA256:
        raise H4ProbeError("H3 manifest summary binding mismatch")
    if record.get("size_bytes") != len(_source_bytes(summary_path)):
        raise H4ProbeError("H3 manifest summary size mismatch")

    summary = _load_json(summary_path)
    if summary.get("schema_version") != H3_SUMMARY_SCHEMA:
        raise H4ProbeError("H3 summary schema is invalid")
    if summary.get("counts") != {
        "artifacts": 5,
        "candidates": 10,
        "context_mismatch": 0,
        "cpu_offload": 0,
        "load_failed": 0,
        "qualified_32k": 10,
    }:
        raise H4ProbeError("H3 summary counts are not the approved closeout")
    integrity = summary.get("integrity")
    if not isinstance(integrity, dict) or not all(
        integrity.get(key) is True
        for key in (
            "all_archives_match_github_digest",
            "all_cleanup_verified",
            "all_context_lengths_32768",
            "all_manifests_verified",
            "unique_candidate_digests",
            "unique_candidate_names",
        )
    ):
        raise H4ProbeError("H3 summary integrity is invalid")
    if any(
        integrity.get(key) is not False
        for key in (
            "external_providers_used",
            "hermes_executed",
            "jarvisos_accessed",
            "secret_values_recorded",
        )
    ):
        raise H4ProbeError("H3 source crossed a forbidden boundary")

    qualified = summary.get("qualified_32k")
    results = summary.get("results")
    if not isinstance(qualified, list) or len(qualified) != 10 or not isinstance(results, list) or len(results) != 10:
        raise H4ProbeError("H3 candidate inventory is incomplete")
    by_digest = {item.get("digest"): item for item in results if isinstance(item, dict)}
    candidates: list[dict[str, str]] = []
    for item in qualified:
        if not isinstance(item, dict):
            raise H4ProbeError("H3 candidate must be an object")
        name, digest = item.get("name"), item.get("digest")
        source = by_digest.get(digest)
        if not isinstance(name, str) or not name or not _valid_sha256(digest) or not isinstance(source, dict):
            raise H4ProbeError("H3 candidate identity is invalid")
        if not (
            source.get("name") == name
            and source.get("status") == "qualified_32k"
            and source.get("context_length") == 32768
            and source.get("residency_ratio") == 1.0
            and source.get("cleanup_verified") is True
        ):
            raise H4ProbeError(f"H3 candidate evidence is invalid: {name}")
        candidates.append({"name": name, "digest": digest})
    if len({item["name"] for item in candidates}) != 10 or len({item["digest"] for item in candidates}) != 10:
        raise H4ProbeError("H3 candidate identities are not unique")
    return candidates


def validate_plan(
    plan_path: Path,
    summary_path: Path,
    manifest_path: Path,
    expected_digest: str,
) -> list[dict[str, str]]:
    if expected_digest != EXPECTED_PLAN_SHA256 or _source_sha256(plan_path) != EXPECTED_PLAN_SHA256:
        raise H4ProbeError("H4 plan digest mismatch")
    source_candidates = _validate_h3_source(summary_path, manifest_path)
    plan = _load_json(plan_path)
    if plan.get("schema_version") != PLAN_SCHEMA or plan.get("status") != "ready":
        raise H4ProbeError("H4 plan schema or status is invalid")
    if plan.get("profile") != PROFILE or plan.get("batching") != {"batch_count": 5, "batch_size": 2}:
        raise H4ProbeError("H4 profile or batching drifted")
    if plan.get("counts") != {"batches": 5, "candidates": 10, "context_probes": 10}:
        raise H4ProbeError("H4 counts drifted")
    expected_policy = {
        "allow_cpu_offload": False,
        "credentials_allowed": False,
        "external_providers_allowed": False,
        "hermes_execution_allowed": False,
        "jarvisos_access_allowed": False,
        "local_only": True,
        "max_parallel_models": 1,
        "sequential_models": True,
        "verify_cleanup": True,
        "verify_singleton_process": True,
    }
    if plan.get("execution_policy") != expected_policy:
        raise H4ProbeError("H4 execution policy drifted")
    expected_source = {
        "h3_closeout_commit_sha": EXPECTED_H3_CLOSEOUT_COMMIT,
        "h3_manifest_path": "reports/H3-PRIMARY-32K/manifest.json",
        "h3_manifest_sha256": EXPECTED_H3_MANIFEST_SHA256,
        "h3_summary_path": "reports/H3-PRIMARY-32K/summary.json",
        "h3_summary_sha256": EXPECTED_H3_SUMMARY_SHA256,
        "hermes_commit_sha": EXPECTED_HERMES_COMMIT,
        "hermes_minimum_context_tokens": 64000,
        "hermes_version": "0.18.2",
    }
    if plan.get("source") != expected_source:
        raise H4ProbeError("H4 source binding drifted")
    raw = plan.get("candidates")
    if not isinstance(raw, list) or len(raw) != 10:
        raise H4ProbeError("H4 candidate list is incomplete")
    for index, item in enumerate(raw):
        expected = {
            "sequence": index,
            "name": source_candidates[index]["name"],
            "digest": source_candidates[index]["digest"],
            "source_32k_status": "qualified_32k",
            "source_32k_residency_ratio": 1.0,
        }
        if item != expected:
            raise H4ProbeError(f"H4 candidate binding drifted at sequence {index}")
    return source_candidates


def select_candidates(
    candidates: list[dict[str, str]], *, batch_index: int
) -> tuple[list[dict[str, str]], dict[str, int | str]]:
    if not 0 <= batch_index < BATCH_COUNT:
        raise H4ProbeError("H4 batch index is outside the approved range")
    start = batch_index * BATCH_SIZE
    selected = candidates[start : start + BATCH_SIZE]
    if len(selected) != BATCH_SIZE:
        raise H4ProbeError("H4 batch is incomplete")
    return selected, {
        "mode": "batch",
        "batch_index": batch_index,
        "batch_size": BATCH_SIZE,
        "start": start,
        "end": start + BATCH_SIZE,
        "expected_count": BATCH_SIZE,
        "total_candidates": len(candidates),
    }


def _installed_candidates(candidates: list[dict[str, str]]) -> list[dict[str, Any]]:
    installed = {item["name"]: item for item in base.list_installed_models()}
    selected: list[dict[str, Any]] = []
    for candidate in candidates:
        item = installed.get(candidate["name"])
        if item is None or item.get("digest") != candidate["digest"]:
            raise H4InfrastructureError(f"approved H4 candidate missing or changed: {candidate['name']}")
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
        return "load_failed", None, {"type": "H4ProbeError", "detail": "generation did not complete"}
    if ps_entry.get("context_length") != PROFILE["num_ctx"]:
        return "context_mismatch", None, {
            "type": "H4ProbeError",
            "detail": f"expected context_length=65536, got {ps_entry.get('context_length')!r}",
        }
    residency, ratio = base.classify_residency(ps_entry.get("size"), ps_entry.get("size_vram"))
    if residency == "unknown":
        return "load_failed", None, {"type": "H4ProbeError", "detail": "invalid residency metrics"}
    return ("qualified_64k" if residency == "full_vram" else "cpu_offload"), ratio, None


def probe_candidate(model: dict[str, Any], output_dir: Path) -> dict[str, Any]:
    name = model["name"]
    model_dir = output_dir / "models" / base.model_artifact_slug(name)
    model_dir.mkdir(parents=True, exist_ok=True)
    cleanup_before = stop_all_running_models()
    gpu_before = base.gpu_snapshot()
    if gpu_before.get("ok") is not True:
        raise H4InfrastructureError(f"GPU snapshot failed before candidate: {name}")
    started = time.monotonic()
    response = None
    ps_entry = None
    error = None
    primary_error: Exception | None = None
    cleanup_after = None
    gpu_loaded: dict[str, Any] = {"ok": False, "gpus": []}
    try:
        try:
            response = base._request_json(
                base.GENERATE_URL,
                expected_path="/api/generate",
                timeout=PROFILE["request_timeout_seconds"],
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
            primary_error = H4InfrastructureError(f"GPU snapshot failed after loading candidate: {name}")
    finally:
        try:
            cleanup_after = {"verified_absent": True, "models": stop_all_running_models()}
        except base.ProbeError as exc:
            primary_error = H4InfrastructureError(f"primary={primary_error}; cleanup={exc}")
    if primary_error is not None or cleanup_after is None:
        raise H4InfrastructureError(str(primary_error or "cleanup attestation missing"))
    status, ratio, error = _classify_result(response, ps_entry, error)
    metrics = {
        key: response.get(key) if response else None
        for key in (
            "total_duration",
            "load_duration",
            "prompt_eval_count",
            "prompt_eval_duration",
            "eval_count",
            "eval_duration",
            "done_reason",
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
    paths = [output_dir / "report.json", *sorted((output_dir / "models").glob("*/result.json"))]
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
    infrastructure_error = None
    initial_gpu = base.gpu_snapshot()
    initial_cleanup: list[dict[str, Any]] = []
    final_cleanup: list[dict[str, Any]] = []
    candidates: list[dict[str, str]] = []
    selected: list[dict[str, str]] = []
    selection = None
    try:
        if initial_gpu.get("ok") is not True:
            raise H4InfrastructureError("initial GPU snapshot failed")
        candidates = validate_plan(plan_path, summary_path, manifest_path, expected_digest)
        selected, selection = select_candidates(candidates, batch_index=batch_index)
        installed = _installed_candidates(selected)
        initial_cleanup = stop_all_running_models()
        results = [probe_candidate(model, output_dir) for model in installed]
    except (H4ProbeError, base.ProbeError) as exc:
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
            "h3_summary_path": summary_path.as_posix(),
            "h3_summary_sha256": EXPECTED_H3_SUMMARY_SHA256,
            "h3_summary_manifest_path": manifest_path.as_posix(),
            "h3_summary_manifest_sha256": EXPECTED_H3_MANIFEST_SHA256,
            "h3_closeout_commit_sha": EXPECTED_H3_CLOSEOUT_COMMIT,
            "hermes_commit_sha": EXPECTED_HERMES_COMMIT,
            "hermes_minimum_context_tokens": 64000,
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
            if result.get("status") != "qualified_64k"
        ],
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one deterministic H4 64K batch.")
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
