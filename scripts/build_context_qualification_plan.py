from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

SHORTLIST_SCHEMA = "bench.model-shortlist.v1"
SHORTLIST_MANIFEST_SCHEMA = "bench.model-shortlist-manifest.v1"
PLAN_SCHEMA = "bench.context-qualification-plan.v1"
PLAN_MANIFEST_SCHEMA = "bench.context-qualification-plan-manifest.v1"
REQUIRED_SOURCE_ARTIFACTS = {
    "report.json",
    "manifest.json",
    "shortlist.json",
    "shortlist.md",
}


class PlanError(RuntimeError):
    pass


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise PlanError(f"duplicate JSON key: {key}")
        value[key] = item
    return value


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_reject_duplicate_pairs,
        )
    except PlanError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PlanError(f"cannot read {path.name}: {type(exc).__name__}") from exc
    if not isinstance(value, dict):
        raise PlanError(f"{path.name} must contain an object")
    return value


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _validate_source_artifacts(source_dir: Path) -> tuple[dict[str, Any], str]:
    manifest_path = source_dir / "shortlist-manifest.json"
    manifest = load_json(manifest_path)
    if manifest.get("schema_version") != SHORTLIST_MANIFEST_SCHEMA:
        raise PlanError("unsupported shortlist manifest schema")
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, Mapping):
        raise PlanError("shortlist manifest artifacts must be an object")
    if set(artifacts) != REQUIRED_SOURCE_ARTIFACTS:
        raise PlanError("shortlist manifest inventory mismatch")

    source_root = source_dir.resolve()
    for relative, metadata in artifacts.items():
        if not isinstance(relative, str) or not relative:
            raise PlanError("shortlist manifest contains an invalid path")
        path = source_dir / relative
        try:
            path.resolve().relative_to(source_root)
        except ValueError as exc:
            raise PlanError("shortlist manifest path escapes source directory") from exc
        if not path.is_file() or not isinstance(metadata, Mapping):
            raise PlanError(f"missing shortlist source artifact: {relative}")
        if metadata.get("sha256") != sha256(path):
            raise PlanError(f"shortlist source digest mismatch: {relative}")
        if metadata.get("size_bytes") != path.stat().st_size:
            raise PlanError(f"shortlist source size mismatch: {relative}")

    shortlist = load_json(source_dir / "shortlist.json")
    source = shortlist.get("source")
    if not isinstance(source, Mapping):
        raise PlanError("shortlist source binding is missing")
    if source.get("report_sha256") != sha256(source_dir / "report.json"):
        raise PlanError("shortlist report binding mismatch")
    if source.get("residency_manifest_sha256") != sha256(
        source_dir / "manifest.json"
    ):
        raise PlanError("shortlist residency manifest binding mismatch")
    return shortlist, sha256(manifest_path)


def _validate_primary(shortlist: Mapping[str, Any]) -> list[dict[str, Any]]:
    if shortlist.get("schema_version") != SHORTLIST_SCHEMA:
        raise PlanError("unsupported shortlist schema")
    status = shortlist.get("status")
    if status not in {"ready", "blocked_no_full_vram_models"}:
        raise PlanError("unsupported shortlist status")
    primary = shortlist.get("primary_h2")
    secondary = shortlist.get("secondary_partial_vram")
    if not isinstance(primary, list) or not isinstance(secondary, list):
        raise PlanError("shortlist model groups must be arrays")
    if status == "ready" and not primary:
        raise PlanError("ready shortlist has no primary H2 models")
    if status == "blocked_no_full_vram_models" and primary:
        raise PlanError("blocked shortlist unexpectedly has primary H2 models")

    normalized: list[dict[str, Any]] = []
    names: set[str] = set()
    digests: set[str] = set()
    for entry in primary:
        if not isinstance(entry, Mapping):
            raise PlanError("primary H2 entry must be an object")
        name = entry.get("name")
        digest = entry.get("digest")
        classification = entry.get("classification")
        ratio = entry.get("residency_ratio")
        if not isinstance(name, str) or not name:
            raise PlanError("primary H2 model name is invalid")
        if not isinstance(digest, str) or not digest:
            raise PlanError(f"{name} has an invalid digest")
        if classification != "full_vram":
            raise PlanError(f"{name} is not full_vram")
        if (
            not isinstance(ratio, (int, float))
            or isinstance(ratio, bool)
            or not 0.98 <= float(ratio) <= 1.0
        ):
            raise PlanError(f"{name} has an invalid full-VRAM ratio")
        if name in names or digest in digests:
            raise PlanError("primary H2 model identities are not unique")
        names.add(name)
        digests.add(digest)
        normalized.append(
            {
                "name": name,
                "digest": digest,
                "h1_residency_ratio": float(ratio),
            }
        )
    return sorted(normalized, key=lambda item: item["name"].casefold())


def _job_id(name: str, digest: str, num_ctx: int) -> str:
    binding = f"{name}\n{digest}\n{num_ctx}".encode("utf-8")
    return "h2-" + hashlib.sha256(binding).hexdigest()[:20]


def build_plan(shortlist: Mapping[str, Any]) -> dict[str, Any]:
    primary = _validate_primary(shortlist)
    jobs: list[dict[str, Any]] = []
    for model in primary:
        prior_job_id: str | None = None
        for num_ctx, gate in ((16384, "required"), (32768, "after_prior_success")):
            job_id = _job_id(model["name"], model["digest"], num_ctx)
            jobs.append(
                {
                    "job_id": job_id,
                    "sequence": len(jobs) + 1,
                    "model": dict(model),
                    "profile": {
                        "num_ctx": num_ctx,
                        "temperature": 0,
                        "seed": 4242,
                        "num_predict": 16,
                        "request_timeout_seconds": 900,
                    },
                    "admission": {
                        "mode": gate,
                        "depends_on_job_id": prior_job_id,
                    },
                    "required_evidence": [
                        "ollama_ps_before",
                        "ollama_generate_response",
                        "ollama_ps_loaded",
                        "nvidia_smi_before",
                        "nvidia_smi_loaded",
                        "cleanup_verified_absent",
                    ],
                }
            )
            prior_job_id = job_id

    return {
        "schema_version": PLAN_SCHEMA,
        "status": "ready" if jobs else "blocked_no_full_vram_models",
        "execution_policy": {
            "local_only": True,
            "single_gpu": True,
            "sequential": True,
            "max_concurrent_models": 1,
            "stop_campaign_on_model_failure": False,
            "stop_campaign_on_infrastructure_integrity_failure": True,
            "cleanup_between_jobs_required": True,
            "resume_requires_checkpoint_binding": True,
        },
        "contexts": {
            "required": [16384],
            "conditional": [32768],
        },
        "counts": {
            "primary_models": len(primary),
            "planned_jobs": len(jobs),
        },
        "jobs": jobs,
    }


def run(source_dir: Path, output_dir: Path) -> dict[str, Any]:
    shortlist, shortlist_manifest_sha256 = _validate_source_artifacts(source_dir)
    plan = build_plan(shortlist)
    plan["source"] = {
        "shortlist_sha256": sha256(source_dir / "shortlist.json"),
        "shortlist_manifest_sha256": shortlist_manifest_sha256,
        "residency_report_sha256": shortlist["source"]["report_sha256"],
        "residency_manifest_sha256": shortlist["source"][
            "residency_manifest_sha256"
        ],
    }
    plan_path = output_dir / "h2-plan.json"
    write_json(plan_path, plan)
    write_json(
        output_dir / "h2-plan-manifest.json",
        {
            "schema_version": PLAN_MANIFEST_SCHEMA,
            "artifacts": {
                "h2-plan.json": {
                    "sha256": sha256(plan_path),
                    "size_bytes": plan_path.stat().st_size,
                }
            },
        },
    )
    return plan


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = run(args.source_dir, args.output_dir)
    except PlanError as exc:
        write_json(
            args.output_dir / "h2-plan-error.json",
            {"type": type(exc).__name__, "detail": str(exc)},
        )
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
