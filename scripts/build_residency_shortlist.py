from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections.abc import Mapping
from pathlib import Path
from typing import Any

REPORT_SCHEMA = "bench.model-residency.v1"
MANIFEST_SCHEMA = "bench.model-residency-manifest.v1"
SHORTLIST_SCHEMA = "bench.model-shortlist.v1"
EXPECTED_PROFILE = {
    "name": "h1-4k-residency",
    "num_ctx": 4096,
    "num_predict": 1,
    "temperature": 0,
    "seed": 4242,
    "keep_alive": "5m",
    "request_timeout_seconds": 420,
}
EXPECTED_EXCLUSIONS = ["gemma4:27b"]
VALID_CLASSES = {"full_vram", "partial_vram", "cpu_only", "load_failed", "excluded"}
_SHA256 = frozenset("0123456789abcdef")


class ShortlistError(RuntimeError):
    pass


def _valid_sha256(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(c in _SHA256 for c in value)


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ShortlistError(f"duplicate JSON key: {key}")
        value[key] = item
    return value


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_reject_duplicate_pairs)
    except ShortlistError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ShortlistError(f"cannot read {path.name}: {type(exc).__name__}") from exc
    if not isinstance(value, dict):
        raise ShortlistError(f"{path.name} must contain an object")
    return value


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_manifest(output_dir: Path, manifest: Mapping[str, Any]) -> None:
    if manifest.get("schema_version") != MANIFEST_SCHEMA:
        raise ShortlistError("unsupported residency manifest schema")
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, Mapping) or not artifacts:
        raise ShortlistError("residency manifest has no artifacts")
    discovered = {"report.json"}
    discovered.update(
        path.relative_to(output_dir).as_posix()
        for path in (output_dir / "models").glob("*/result.json")
    )
    if set(artifacts) != discovered:
        raise ShortlistError("residency manifest inventory mismatch")
    for relative, metadata in artifacts.items():
        if not isinstance(relative, str) or not relative:
            raise ShortlistError("residency manifest contains an invalid path")
        path = output_dir / relative
        try:
            path.resolve().relative_to(output_dir.resolve())
        except ValueError as exc:
            raise ShortlistError("residency manifest path escapes output") from exc
        if not path.is_file() or not isinstance(metadata, Mapping):
            raise ShortlistError(f"missing residency artifact: {relative}")
        if metadata.get("sha256") != sha256(path):
            raise ShortlistError(f"residency digest mismatch: {relative}")
        if metadata.get("size_bytes") != path.stat().st_size:
            raise ShortlistError(f"residency size mismatch: {relative}")


def _validate_gpu_snapshot(snapshot: Any, *, label: str) -> list[dict[str, Any]]:
    if not isinstance(snapshot, Mapping) or snapshot.get("ok") is not True:
        raise ShortlistError(f"{label} GPU snapshot is unsuccessful")
    gpus = snapshot.get("gpus")
    if not isinstance(gpus, list) or not gpus:
        raise ShortlistError(f"{label} GPU snapshot has no devices")
    normalized: list[dict[str, Any]] = []
    indexes: set[int] = set()
    for gpu in gpus:
        if not isinstance(gpu, Mapping):
            raise ShortlistError(f"{label} GPU entry is invalid")
        index = gpu.get("index")
        name = gpu.get("name")
        total = gpu.get("memory_total_mib")
        used = gpu.get("memory_used_mib")
        utilization = gpu.get("utilization_gpu_percent")
        if (
            not isinstance(index, int) or isinstance(index, bool) or index < 0 or index in indexes
            or not isinstance(name, str) or not name
            or not isinstance(total, int) or isinstance(total, bool) or total <= 0
            or not isinstance(used, int) or isinstance(used, bool) or used < 0 or used > total
            or not isinstance(utilization, int) or isinstance(utilization, bool)
            or not 0 <= utilization <= 100
        ):
            raise ShortlistError(f"{label} GPU metrics are invalid")
        indexes.add(index)
        normalized.append(dict(gpu))
    return normalized


def _validate_process_identity(process: Mapping[str, Any], name: str, digest: str) -> None:
    identities = [value for value in (process.get("name"), process.get("model")) if value is not None]
    if not identities or any(value != name for value in identities):
        raise ShortlistError(f"{name} Ollama process identity is inconsistent")
    if process.get("digest") != digest:
        raise ShortlistError(f"{name} Ollama process digest is inconsistent")


def normalize_entry(entry: Mapping[str, Any]) -> dict[str, Any]:
    model = entry.get("model")
    if not isinstance(model, Mapping):
        raise ShortlistError("model identity is missing")
    name = model.get("name")
    digest = model.get("digest")
    if not isinstance(name, str) or not name or not _valid_sha256(digest):
        raise ShortlistError("model name or digest is invalid")
    classification = entry.get("classification")
    if classification not in VALID_CLASSES:
        raise ShortlistError(f"{name} has unsupported classification")
    if entry.get("profile") != EXPECTED_PROFILE:
        raise ShortlistError(f"{name} profile does not match fixed H1 contract")

    result: dict[str, Any] = {"name": name, "digest": digest, "classification": classification}
    if classification == "excluded":
        if entry.get("reason") != "explicit_user_exclusion":
            raise ShortlistError(f"{name} has invalid exclusion reason")
        return result

    cleanup = entry.get("cleanup_after")
    if not isinstance(cleanup, Mapping) or cleanup.get("verified_absent") is not True:
        raise ShortlistError(f"{name} cleanup was not verified")
    _validate_gpu_snapshot(entry.get("gpu_before"), label=f"{name} before-load")
    _validate_gpu_snapshot(entry.get("gpu_loaded"), label=f"{name} loaded")
    duration = entry.get("probe_duration_seconds")
    if (
        not isinstance(duration, (int, float)) or isinstance(duration, bool)
        or not math.isfinite(float(duration)) or duration < 0
        or duration > EXPECTED_PROFILE["request_timeout_seconds"] + 120
    ):
        raise ShortlistError(f"{name} has invalid probe duration")
    result["probe_duration_seconds"] = float(duration)

    if classification == "load_failed":
        if not isinstance(entry.get("error"), Mapping):
            raise ShortlistError(f"{name} load failure lacks error evidence")
        result["error"] = dict(entry["error"])
        return result

    generate = entry.get("ollama_generate")
    if not isinstance(generate, Mapping) or generate.get("done") is not True:
        raise ShortlistError(f"{name} lacks completed Ollama generation evidence")
    process = entry.get("ollama_ps_entry")
    if not isinstance(process, Mapping):
        raise ShortlistError(f"{name} lacks Ollama residency evidence")
    _validate_process_identity(process, name, digest)
    if process.get("context_length") != EXPECTED_PROFILE["num_ctx"]:
        raise ShortlistError(f"{name} Ollama context length is not fixed H1 4K")
    size = process.get("size")
    size_vram = process.get("size_vram")
    ratio = entry.get("residency_ratio")
    if not isinstance(size, int) or isinstance(size, bool) or size <= 0:
        raise ShortlistError(f"{name} has invalid model size")
    if not isinstance(size_vram, int) or isinstance(size_vram, bool) or size_vram < 0:
        raise ShortlistError(f"{name} has invalid VRAM size")
    expected_ratio = size_vram / size
    if (
        not isinstance(ratio, (int, float)) or isinstance(ratio, bool)
        or not math.isfinite(float(ratio))
        or not math.isclose(float(ratio), expected_ratio, rel_tol=1e-9, abs_tol=1e-12)
    ):
        raise ShortlistError(f"{name} residency ratio is inconsistent")
    expected_class = "full_vram" if expected_ratio >= 0.98 else "partial_vram" if size_vram else "cpu_only"
    if classification != expected_class:
        raise ShortlistError(f"{name} classification is inconsistent")
    result.update(residency_ratio=expected_ratio, size_bytes=size, size_vram_bytes=size_vram)
    return result


def validate_per_model_evidence(output_dir: Path, report: Mapping[str, Any]) -> None:
    report_models = report.get("models")
    if not isinstance(report_models, list):
        raise ShortlistError("residency report models must be an array")
    file_models = [load_json(path) for path in sorted((output_dir / "models").glob("*/result.json"))]
    if len(file_models) != len(report_models):
        raise ShortlistError("per-model evidence count does not match report")

    def keyed(entries: list[Any]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for entry in entries:
            if not isinstance(entry, Mapping):
                raise ShortlistError("model evidence entry must be an object")
            model = entry.get("model")
            name = model.get("name") if isinstance(model, Mapping) else None
            if not isinstance(name, str) or not name or name in result:
                raise ShortlistError("per-model evidence identity is invalid")
            result[name] = dict(entry)
        return result

    if keyed(report_models) != keyed(file_models):
        raise ShortlistError("per-model evidence does not match aggregate report")


def _deduplicate_candidates(
    full: list[dict[str, Any]], partial: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    selected_by_digest: dict[str, str] = {}
    primary: list[dict[str, Any]] = []
    secondary: list[dict[str, Any]] = []
    aliases: list[dict[str, Any]] = []
    for source, target in ((full, primary), (partial, secondary)):
        for entry in source:
            digest = entry["digest"]
            canonical = selected_by_digest.get(digest)
            if canonical is None:
                selected_by_digest[digest] = entry["name"]
                target.append(entry)
            else:
                aliases.append(
                    {
                        **entry,
                        "deferred_reason": "duplicate_digest_alias",
                        "canonical_name": canonical,
                    }
                )
    return primary, secondary, aliases


def build_shortlist(report: Mapping[str, Any]) -> dict[str, Any]:
    if report.get("schema_version") != REPORT_SCHEMA:
        raise ShortlistError("unsupported residency report schema")
    if report.get("infrastructure_error") is not None:
        raise ShortlistError("residency report contains an infrastructure error")
    workflow = report.get("workflow")
    if not isinstance(workflow, Mapping) or any(
        not workflow.get(field) for field in ("run_id", "run_attempt", "event_name", "sha", "ref")
    ):
        raise ShortlistError("residency workflow identity is incomplete")
    if workflow.get("ref") != "refs/heads/main":
        raise ShortlistError("residency evidence is not bound to trusted main")
    if report.get("profile") != EXPECTED_PROFILE:
        raise ShortlistError("report does not match the complete fixed H1 profile")
    if report.get("explicit_exclusions") != EXPECTED_EXCLUSIONS:
        raise ShortlistError("report exclusions do not match the H1 contract")
    gpus = _validate_gpu_snapshot(report.get("initial_gpu"), label="initial")
    if not isinstance(report.get("initial_cleanup"), list):
        raise ShortlistError("initial cleanup evidence is invalid")
    raw_models = report.get("models")
    if not isinstance(raw_models, list) or not raw_models:
        raise ShortlistError("residency report has no model results")

    models = [normalize_entry(entry) for entry in raw_models if isinstance(entry, Mapping)]
    if len(models) != len(raw_models):
        raise ShortlistError("residency report contains a non-object model result")
    names = [entry["name"] for entry in models]
    if len(names) != len(set(names)):
        raise ShortlistError("residency report contains duplicate model names")

    classification_counts: dict[str, int] = {}
    for entry in models:
        key = entry["classification"]
        classification_counts[key] = classification_counts.get(key, 0) + 1
    if report.get("classification_counts") != classification_counts:
        raise ShortlistError("classification counts do not match model results")

    full = sorted(
        (entry for entry in models if entry["classification"] == "full_vram"),
        key=lambda entry: entry["name"].casefold(),
    )
    partial = sorted(
        (entry for entry in models if entry["classification"] == "partial_vram"),
        key=lambda entry: (-entry["residency_ratio"], entry["name"].casefold()),
    )
    primary, secondary, aliases = _deduplicate_candidates(full, partial)
    deferred = sorted(
        [
            entry
            for entry in models
            if entry["classification"] not in {"full_vram", "partial_vram"}
        ]
        + aliases,
        key=lambda entry: entry["name"].casefold(),
    )
    return {
        "schema_version": SHORTLIST_SCHEMA,
        "status": "ready" if primary else "blocked_no_full_vram_models",
        "profile": dict(EXPECTED_PROFILE),
        "gpus": gpus,
        "counts": {
            "model_results": len(models),
            "primary_h2": len(primary),
            "secondary_partial_vram": len(secondary),
            "deferred": len(deferred),
        },
        "primary_h2": primary,
        "secondary_partial_vram": secondary,
        "deferred": deferred,
    }


def markdown(shortlist: Mapping[str, Any]) -> str:
    lines = [
        "# H1 validated shortlist", "", f"Status: `{shortlist['status']}`.", "",
        "Hardware eligibility only; this is not a capability ranking.", "",
        "## Primary H2 — full VRAM",
    ]
    lines.extend(f"- `{e['name']}`: {e['residency_ratio']:.3f}" for e in shortlist["primary_h2"])
    if not shortlist["primary_h2"]:
        lines.append("- None.")
    lines.extend(["", "## Secondary — partial VRAM"])
    lines.extend(f"- `{e['name']}`: {e['residency_ratio']:.3f}" for e in shortlist["secondary_partial_vram"])
    if not shortlist["secondary_partial_vram"]:
        lines.append("- None.")
    lines.extend(["", "## Deferred or excluded"])
    lines.extend(
        f"- `{e['name']}`: `{e['classification']}`"
        + (f" ({e['deferred_reason']}; canonical `{e['canonical_name']}`)" if e.get("deferred_reason") else "")
        for e in shortlist["deferred"]
    )
    if not shortlist["deferred"]:
        lines.append("- None.")
    return "\n".join(lines) + "\n"


def run(output_dir: Path) -> dict[str, Any]:
    report_path = output_dir / "report.json"
    manifest_path = output_dir / "manifest.json"
    report = load_json(report_path)
    manifest = load_json(manifest_path)
    validate_manifest(output_dir, manifest)
    validate_per_model_evidence(output_dir, report)
    shortlist = build_shortlist(report)
    shortlist["source"] = {
        "report_sha256": sha256(report_path),
        "residency_manifest_sha256": sha256(manifest_path),
        "workflow": report.get("workflow"),
    }
    shortlist_path = output_dir / "shortlist.json"
    markdown_path = output_dir / "shortlist.md"
    write_json(shortlist_path, shortlist)
    markdown_path.write_text(markdown(shortlist), encoding="utf-8")
    write_json(
        output_dir / "shortlist-manifest.json",
        {
            "schema_version": "bench.model-shortlist-manifest.v1",
            "artifacts": {
                path.name: {"sha256": sha256(path), "size_bytes": path.stat().st_size}
                for path in (report_path, manifest_path, shortlist_path, markdown_path)
            },
        },
    )
    return shortlist


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = run(args.output_dir)
    except ShortlistError as exc:
        write_json(args.output_dir / "shortlist-error.json", {"type": type(exc).__name__, "detail": str(exc)})
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
