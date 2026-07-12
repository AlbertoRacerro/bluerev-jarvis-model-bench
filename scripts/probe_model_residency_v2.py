from __future__ import annotations

import argparse
import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts import probe_model_residency as base

_STALE_EVIDENCE = (
    "report.json",
    "manifest.json",
    "shortlist.json",
    "shortlist-manifest.json",
    "h2-context-plan.json",
    "models",
)


def _running_names(items: list[dict[str, Any]]) -> list[str]:
    names: list[str] = []
    for item in items:
        name = base._running_name(item)
        if name:
            names.append(name)
    return names


def stop_all_running_models() -> list[dict[str, Any]]:
    """Unload the observed set and attest that Ollama is empty afterwards."""
    observed = base.running_models()
    results: list[dict[str, Any]] = []
    for name in _running_names(observed):
        results.append({"model": name, **base.stop_model(name)})

    failed = [
        item["model"]
        for item in results
        if item.get("verified_absent") is not True
    ]
    if failed:
        raise base.InfrastructureProbeError(
            "could not verify model unload: " + ", ".join(failed)
        )

    remaining_names = _running_names(base.running_models())
    if remaining_names:
        raise base.InfrastructureProbeError(
            "Ollama cleanup left running models: " + ", ".join(remaining_names)
        )
    return results


def _cleanup_attestation() -> dict[str, Any]:
    return {
        "verified_absent": True,
        "models": stop_all_running_models(),
    }


def _combine_infrastructure_failures(
    primary: base.InfrastructureProbeError | None,
    cleanup: base.ProbeError | None,
) -> base.InfrastructureProbeError | None:
    details: list[str] = []
    if primary is not None:
        details.append(f"primary={primary}")
    if cleanup is not None:
        details.append(f"cleanup={cleanup}")
    if not details:
        return None
    return base.InfrastructureProbeError("; ".join(details))


def probe_model(model: dict[str, Any], output_dir: Path) -> dict[str, Any]:
    model_name = model["name"]
    model_dir = output_dir / "models" / base.model_artifact_slug(model_name)
    model_dir.mkdir(parents=True, exist_ok=True)

    if base.is_user_excluded(model_name):
        result = {
            "model": model,
            "classification": "excluded",
            "reason": "explicit_user_exclusion",
            "profile": base.PROFILE,
        }
        base._write_json(model_dir / "result.json", result)
        return result

    cleanup_before = stop_all_running_models()
    baseline_gpu = base.gpu_snapshot()
    if baseline_gpu.get("ok") is not True:
        raise base.InfrastructureProbeError(
            f"GPU snapshot failed before model: {model_name}"
        )

    started = time.monotonic()
    generate_response: dict[str, Any] | None = None
    ps_entry: dict[str, Any] | None = None
    error: dict[str, str] | None = None
    primary_failure: base.InfrastructureProbeError | None = None
    cleanup_after: dict[str, Any] | None = None
    cleanup_failure: base.ProbeError | None = None
    loaded_gpu: dict[str, Any] = {"ok": False, "gpus": []}

    try:
        try:
            generate_response = base._request_json(
                base.GENERATE_URL,
                expected_path="/api/generate",
                timeout=int(base.PROFILE["request_timeout_seconds"]),
                payload={
                    "model": model_name,
                    "prompt": "Return exactly OK.",
                    "stream": False,
                    "keep_alive": base.PROFILE["keep_alive"],
                    "options": {
                        "temperature": base.PROFILE["temperature"],
                        "seed": base.PROFILE["seed"],
                        "num_predict": base.PROFILE["num_predict"],
                        "num_ctx": base.PROFILE["num_ctx"],
                    },
                },
            )
            if generate_response.get("done") is not True:
                raise base.ProbeError("Ollama generate response was incomplete")
            ps_entry = base._find_single_running_model(model)
        except base.InfrastructureProbeError as exc:
            primary_failure = exc
        except base.ProbeError as exc:
            error = {"type": type(exc).__name__, "detail": str(exc)}

        loaded_gpu = base.gpu_snapshot()
        if loaded_gpu.get("ok") is not True and primary_failure is None:
            primary_failure = base.InfrastructureProbeError(
                f"GPU snapshot failed after loading model: {model_name}"
            )
    finally:
        try:
            cleanup_after = _cleanup_attestation()
        except base.ProbeError as exc:
            cleanup_failure = exc

    duration_seconds = time.monotonic() - started
    combined = _combine_infrastructure_failures(primary_failure, cleanup_failure)
    if combined is not None:
        raise combined
    if cleanup_after is None:
        raise base.InfrastructureProbeError(
            f"cleanup attestation missing after model: {model_name}"
        )

    if error is not None or ps_entry is None:
        classification = "load_failed"
        residency_ratio = None
    else:
        classification, residency_ratio = base.classify_residency(
            ps_entry.get("size"), ps_entry.get("size_vram")
        )
        if classification == "unknown":
            error = {
                "type": "ProbeError",
                "detail": "Ollama returned invalid residency metrics",
            }
            classification = "load_failed"
            residency_ratio = None

    result = {
        "model": model,
        "profile": base.PROFILE,
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
    base._write_json(model_dir / "result.json", result)
    return result


def build_report(output_dir: Path) -> dict[str, Any]:
    created_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    initial_gpu = base.gpu_snapshot()
    initial_cleanup: list[dict[str, Any]] = []
    final_cleanup: list[dict[str, Any]] = []
    models: list[dict[str, Any]] = []
    infrastructure_error: dict[str, str] | None = None

    try:
        if initial_gpu.get("ok") is not True:
            raise base.InfrastructureProbeError("initial GPU snapshot failed")
        installed = base.list_installed_models()
        initial_cleanup = stop_all_running_models()
        for model in installed:
            models.append(probe_model(model, output_dir))
    except base.ProbeError as exc:
        infrastructure_error = {"type": type(exc).__name__, "detail": str(exc)}
    finally:
        try:
            final_cleanup = stop_all_running_models()
        except base.ProbeError as exc:
            cleanup_detail = f"final cleanup failed: {exc}"
            if infrastructure_error is None:
                infrastructure_error = {
                    "type": type(exc).__name__,
                    "detail": cleanup_detail,
                }
            else:
                infrastructure_error["detail"] += "; " + cleanup_detail

    counts: dict[str, int] = {}
    for result in models:
        classification = str(result.get("classification"))
        counts[classification] = counts.get(classification, 0) + 1

    return {
        "schema_version": base.SCHEMA_VERSION,
        "created_at_utc": created_at,
        "workflow": {
            "run_id": os.environ.get("GITHUB_RUN_ID"),
            "run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
            "event_name": os.environ.get("GITHUB_EVENT_NAME"),
            "sha": os.environ.get("GITHUB_SHA"),
            "ref": os.environ.get("GITHUB_REF"),
        },
        "profile": base.PROFILE,
        "explicit_exclusions": list(base.EXCLUDED_MODEL_FRAGMENTS),
        "initial_gpu": initial_gpu,
        "initial_cleanup": initial_cleanup,
        "final_cleanup": final_cleanup,
        "infrastructure_error": infrastructure_error,
        "classification_counts": counts,
        "models": models,
    }


def _stale_evidence(output_dir: Path) -> list[str]:
    return [name for name in _STALE_EVIDENCE if (output_dir / name).exists()]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Measure sequential Ollama residency with fail-safe cleanup."
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    stale = _stale_evidence(args.output_dir)
    if stale:
        print(
            "refusing to mix H1 evidence with stale artifacts: " + ", ".join(stale),
            file=os.sys.stderr,
        )
        return 2
    report = build_report(args.output_dir)
    base._write_json(args.output_dir / "report.json", report)
    base.write_manifest(args.output_dir)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 2 if report["infrastructure_error"] is not None else 0


if __name__ == "__main__":
    raise SystemExit(main())
