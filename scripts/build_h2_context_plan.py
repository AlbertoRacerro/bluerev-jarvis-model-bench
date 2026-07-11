from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

SHORTLIST_SCHEMA = "bench.model-shortlist.v1"
SHORTLIST_MANIFEST_SCHEMA = "bench.model-shortlist-manifest.v1"
H2_PLAN_SCHEMA = "bench.h2-context-plan.v1"
ALLOWED_CONTEXTS = (16384, 32768)
EXPECTED_H1_PROFILE = {
    "name": "h1-4k-residency", "num_ctx": 4096, "num_predict": 1,
    "temperature": 0, "seed": 4242, "keep_alive": "5m",
    "request_timeout_seconds": 420,
}
EXPECTED_SHORTLIST_ARTIFACTS = {"report.json", "manifest.json", "shortlist.json", "shortlist.md"}
_SHA256_CHARS = frozenset("0123456789abcdef")


class H2PlanError(RuntimeError):
    pass


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise H2PlanError(f"duplicate JSON key: {key}")
        value[key] = item
    return value


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_reject_duplicate_pairs)
    except H2PlanError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise H2PlanError(f"cannot read {path.name}: {type(exc).__name__}") from exc
    if not isinstance(value, dict):
        raise H2PlanError(f"{path.name} must contain an object")
    return value


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _valid_sha256(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(c in _SHA256_CHARS for c in value)


def _validate_artifact_record(output_dir: Path, artifacts: Mapping[str, Any], name: str) -> None:
    record = artifacts.get(name)
    if not isinstance(record, Mapping):
        raise H2PlanError(f"shortlist manifest lacks {name}")
    path = output_dir / name
    try:
        path.resolve().relative_to(output_dir.resolve())
    except ValueError as exc:
        raise H2PlanError(f"shortlist artifact path escapes output: {name}") from exc
    if not path.is_file():
        raise H2PlanError(f"shortlist artifact is missing: {name}")
    if record.get("sha256") != sha256(path):
        raise H2PlanError(f"shortlist digest mismatch: {name}")
    if record.get("size_bytes") != path.stat().st_size:
        raise H2PlanError(f"shortlist size mismatch: {name}")


def _validate_workflow_binding(source: Mapping[str, Any]) -> None:
    workflow = source.get("workflow")
    if not isinstance(workflow, Mapping) or any(
        not workflow.get(field) for field in ("run_id", "run_attempt", "event_name", "sha", "ref")
    ):
        raise H2PlanError("shortlist workflow binding is incomplete")
    if workflow.get("ref") != "refs/heads/main":
        raise H2PlanError("shortlist is not bound to trusted main")


def _candidate_identity(entry: Any, expected_class: str) -> tuple[str, str]:
    if not isinstance(entry, Mapping):
        raise H2PlanError(f"{expected_class} candidate must be an object")
    name, digest, classification = entry.get("name"), entry.get("digest"), entry.get("classification")
    if not isinstance(name, str) or not name:
        raise H2PlanError(f"{expected_class} candidate name is invalid")
    if not _valid_sha256(digest):
        raise H2PlanError(f"{name} digest is invalid")
    if classification != expected_class:
        raise H2PlanError(f"{name} is not a {expected_class} candidate")
    return name, digest


def validate_shortlist_binding(
    output_dir: Path, expected_manifest_sha256: str
) -> tuple[dict[str, Any], dict[str, Any]]:
    shortlist_path = output_dir / "shortlist.json"
    manifest_path = output_dir / "shortlist-manifest.json"
    if not _valid_sha256(expected_manifest_sha256):
        raise H2PlanError("expected shortlist manifest digest is invalid")
    if sha256(manifest_path) != expected_manifest_sha256:
        raise H2PlanError("shortlist manifest root digest mismatch")
    shortlist, manifest = load_json(shortlist_path), load_json(manifest_path)
    if shortlist.get("schema_version") != SHORTLIST_SCHEMA:
        raise H2PlanError("unsupported shortlist schema")
    if manifest.get("schema_version") != SHORTLIST_MANIFEST_SCHEMA:
        raise H2PlanError("unsupported shortlist manifest schema")
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, Mapping):
        raise H2PlanError("shortlist manifest artifacts are missing")
    if set(artifacts) != EXPECTED_SHORTLIST_ARTIFACTS:
        raise H2PlanError("shortlist manifest inventory mismatch")
    for name in sorted(EXPECTED_SHORTLIST_ARTIFACTS):
        _validate_artifact_record(output_dir, artifacts, name)
    if shortlist.get("profile") != EXPECTED_H1_PROFILE:
        raise H2PlanError("shortlist profile is not the complete fixed H1 contract")
    source = shortlist.get("source")
    if not isinstance(source, Mapping):
        raise H2PlanError("shortlist source binding is missing")
    _validate_workflow_binding(source)
    if source.get("report_sha256") != sha256(output_dir / "report.json"):
        raise H2PlanError("shortlist report source digest mismatch")
    if source.get("residency_manifest_sha256") != sha256(output_dir / "manifest.json"):
        raise H2PlanError("shortlist residency manifest source digest mismatch")

    status = shortlist.get("status")
    primary, partial, deferred, counts = (
        shortlist.get("primary_h2"), shortlist.get("secondary_partial_vram"),
        shortlist.get("deferred"), shortlist.get("counts"),
    )
    if status not in {"ready", "blocked_no_full_vram_models"}:
        raise H2PlanError("shortlist status is invalid")
    if not all(isinstance(group, list) for group in (primary, partial, deferred)):
        raise H2PlanError("shortlist candidate groups are invalid")
    if not isinstance(counts, Mapping):
        raise H2PlanError("shortlist counts are missing")
    expected_counts = {
        "model_results": len(primary) + len(partial) + len(deferred),
        "primary_h2": len(primary), "secondary_partial_vram": len(partial), "deferred": len(deferred),
    }
    if dict(counts) != expected_counts:
        raise H2PlanError("shortlist counts do not match candidate groups")
    if status == "ready" and not primary:
        raise H2PlanError("ready shortlist has no primary H2 models")
    if status == "blocked_no_full_vram_models" and primary:
        raise H2PlanError("blocked shortlist contains primary H2 models")

    active: list[tuple[str, str]] = []
    active.extend(_candidate_identity(entry, "full_vram") for entry in primary)
    active.extend(_candidate_identity(entry, "partial_vram") for entry in partial)
    active_names = [name for name, _ in active]
    active_digests = [digest for _, digest in active]
    if len(active_names) != len(set(active_names)) or len(active_digests) != len(set(active_digests)):
        raise H2PlanError("active H2 candidate identities are not unique")
    canonical_by_digest = {digest: name for name, digest in active}

    all_names = list(active_names)
    for entry in deferred:
        if not isinstance(entry, Mapping):
            raise H2PlanError("deferred candidate must be an object")
        classification, name, digest = entry.get("classification"), entry.get("name"), entry.get("digest")
        if classification not in {"full_vram", "partial_vram", "cpu_only", "load_failed", "excluded"}:
            raise H2PlanError("deferred candidate classification is invalid")
        if not isinstance(name, str) or not name or not _valid_sha256(digest):
            raise H2PlanError("deferred candidate identity is invalid")
        if classification in {"full_vram", "partial_vram"}:
            if entry.get("deferred_reason") != "duplicate_digest_alias":
                raise H2PlanError("eligible deferred candidate lacks alias reason")
            canonical = canonical_by_digest.get(digest)
            if canonical is None or entry.get("canonical_name") != canonical:
                raise H2PlanError("deferred alias is not bound to its canonical candidate")
        all_names.append(name)
    if len(all_names) != len(set(all_names)):
        raise H2PlanError("shortlist candidate names are not unique")
    return shortlist, manifest


def build_plan(output_dir: Path, expected_manifest_sha256: str) -> dict[str, Any]:
    shortlist, _ = validate_shortlist_binding(output_dir, expected_manifest_sha256)
    primary = [
        {"name": name, "digest": digest}
        for name, digest in (_candidate_identity(entry, "full_vram") for entry in shortlist["primary_h2"])
    ]
    cases = [
        {
            "candidate": candidate,
            "contexts": [
                {
                    "num_ctx": num_ctx, "sequence": index, "required": num_ctx == 16384,
                    "allow_cpu_offload": False, "timeout_seconds": 600,
                    "verify_singleton_process": True, "verify_cleanup": True,
                }
                for index, num_ctx in enumerate(ALLOWED_CONTEXTS, start=1)
            ],
        }
        for candidate in sorted(primary, key=lambda item: item["name"].casefold())
    ]
    source = shortlist["source"]
    return {
        "schema_version": H2_PLAN_SCHEMA,
        "status": "ready" if primary else "blocked_no_full_vram_models",
        "execution_policy": {
            "local_only": True, "sequential_models": True, "max_parallel_models": 1,
            "trusted_main_only": True, "external_providers_allowed": False,
            "credentials_allowed": False, "jarvisos_access_allowed": False,
            "hermes_install_mutation_allowed": False,
        },
        "source": {
            "shortlist_sha256": sha256(output_dir / "shortlist.json"),
            "shortlist_manifest_sha256": sha256(output_dir / "shortlist-manifest.json"),
            "report_sha256": source["report_sha256"],
            "residency_manifest_sha256": source["residency_manifest_sha256"],
            "workflow": source["workflow"],
        },
        "profiles": list(ALLOWED_CONTEXTS), "cases": cases,
        "counts": {"candidates": len(cases), "context_probes": len(cases) * len(ALLOWED_CONTEXTS)},
    }


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def run(output_dir: Path, expected_manifest_sha256: str) -> dict[str, Any]:
    plan = build_plan(output_dir, expected_manifest_sha256)
    write_json(output_dir / "h2-context-plan.json", plan)
    write_json(
        output_dir / "h2-context-plan-manifest.json",
        {
            "schema_version": "bench.h2-context-plan-manifest.v1",
            "artifacts": {
                name: {"sha256": sha256(output_dir / name), "size_bytes": (output_dir / name).stat().st_size}
                for name in ("report.json", "manifest.json", "shortlist.json", "shortlist-manifest.json", "h2-context-plan.json")
            },
        },
    )
    return plan


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--expected-shortlist-manifest-sha256", required=True)
    args = parser.parse_args()
    try:
        result = run(args.output_dir, args.expected_shortlist_manifest_sha256)
    except H2PlanError as exc:
        write_json(args.output_dir / "h2-context-plan-error.json", {"type": type(exc).__name__, "detail": str(exc)})
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
