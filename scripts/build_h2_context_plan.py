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
        value = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_reject_duplicate_pairs,
        )
    except H2PlanError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise H2PlanError(f"cannot read {path.name}: {type(exc).__name__}") from exc
    if not isinstance(value, dict):
        raise H2PlanError(f"{path.name} must contain an object")
    return value


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _artifact_record(manifest: Mapping[str, Any], name: str) -> Mapping[str, Any]:
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, Mapping):
        raise H2PlanError("shortlist manifest artifacts are missing")
    record = artifacts.get(name)
    if not isinstance(record, Mapping):
        raise H2PlanError(f"shortlist manifest lacks {name}")
    return record


def validate_shortlist_binding(output_dir: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    shortlist_path = output_dir / "shortlist.json"
    manifest_path = output_dir / "shortlist-manifest.json"
    shortlist = load_json(shortlist_path)
    manifest = load_json(manifest_path)

    if shortlist.get("schema_version") != SHORTLIST_SCHEMA:
        raise H2PlanError("unsupported shortlist schema")
    if manifest.get("schema_version") != SHORTLIST_MANIFEST_SCHEMA:
        raise H2PlanError("unsupported shortlist manifest schema")

    record = _artifact_record(manifest, "shortlist.json")
    if record.get("sha256") != sha256(shortlist_path):
        raise H2PlanError("shortlist digest mismatch: shortlist.json")
    if record.get("size_bytes") != shortlist_path.stat().st_size:
        raise H2PlanError("shortlist size mismatch: shortlist.json")

    source = shortlist.get("source")
    if not isinstance(source, Mapping):
        raise H2PlanError("shortlist source binding is missing")
    report_sha = source.get("report_sha256")
    residency_manifest_sha = source.get("residency_manifest_sha256")
    if not isinstance(report_sha, str) or len(report_sha) != 64:
        raise H2PlanError("shortlist report digest is invalid")
    if not isinstance(residency_manifest_sha, str) or len(residency_manifest_sha) != 64:
        raise H2PlanError("shortlist residency manifest digest is invalid")

    status = shortlist.get("status")
    primary = shortlist.get("primary_h2")
    partial = shortlist.get("secondary_partial_vram")
    if status not in {"ready", "blocked_no_full_vram_models"}:
        raise H2PlanError("shortlist status is invalid")
    if not isinstance(primary, list) or not isinstance(partial, list):
        raise H2PlanError("shortlist candidate groups are invalid")
    if status == "ready" and not primary:
        raise H2PlanError("ready shortlist has no primary H2 models")
    if status == "blocked_no_full_vram_models" and primary:
        raise H2PlanError("blocked shortlist contains primary H2 models")

    return shortlist, manifest


def _normalize_candidate(entry: Any) -> dict[str, str]:
    if not isinstance(entry, Mapping):
        raise H2PlanError("primary H2 candidate must be an object")
    name = entry.get("name")
    digest = entry.get("digest")
    classification = entry.get("classification")
    if not isinstance(name, str) or not name:
        raise H2PlanError("primary H2 candidate name is invalid")
    if not isinstance(digest, str) or not digest:
        raise H2PlanError(f"{name} digest is invalid")
    if classification != "full_vram":
        raise H2PlanError(f"{name} is not a full-VRAM candidate")
    return {"name": name, "digest": digest}


def build_plan(output_dir: Path) -> dict[str, Any]:
    shortlist, _manifest = validate_shortlist_binding(output_dir)
    primary = [_normalize_candidate(entry) for entry in shortlist["primary_h2"]]
    names = [entry["name"] for entry in primary]
    digests = [entry["digest"] for entry in primary]
    if len(names) != len(set(names)) or len(digests) != len(set(digests)):
        raise H2PlanError("primary H2 candidates are not unique")

    source = shortlist["source"]
    cases = [
        {
            "candidate": candidate,
            "contexts": [
                {
                    "num_ctx": num_ctx,
                    "sequence": index,
                    "required": num_ctx == 16384,
                    "allow_cpu_offload": False,
                }
                for index, num_ctx in enumerate(ALLOWED_CONTEXTS, start=1)
            ],
        }
        for candidate in sorted(primary, key=lambda item: item["name"].casefold())
    ]
    return {
        "schema_version": H2_PLAN_SCHEMA,
        "status": "ready" if primary else "blocked_no_full_vram_models",
        "execution_policy": {
            "local_only": True,
            "sequential_models": True,
            "max_parallel_models": 1,
            "trusted_main_only": True,
            "external_providers_allowed": False,
            "credentials_allowed": False,
            "jarvisos_access_allowed": False,
            "hermes_install_mutation_allowed": False,
        },
        "source": {
            "shortlist_sha256": sha256(output_dir / "shortlist.json"),
            "shortlist_manifest_sha256": sha256(
                output_dir / "shortlist-manifest.json"
            ),
            "report_sha256": source["report_sha256"],
            "residency_manifest_sha256": source["residency_manifest_sha256"],
        },
        "profiles": list(ALLOWED_CONTEXTS),
        "cases": cases,
        "counts": {
            "candidates": len(cases),
            "context_probes": len(cases) * len(ALLOWED_CONTEXTS),
        },
    }


def write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def run(output_dir: Path) -> dict[str, Any]:
    plan = build_plan(output_dir)
    write_json(output_dir / "h2-context-plan.json", plan)
    write_json(
        output_dir / "h2-context-plan-manifest.json",
        {
            "schema_version": "bench.h2-context-plan-manifest.v1",
            "artifacts": {
                name: {
                    "sha256": sha256(output_dir / name),
                    "size_bytes": (output_dir / name).stat().st_size,
                }
                for name in (
                    "shortlist.json",
                    "shortlist-manifest.json",
                    "h2-context-plan.json",
                )
            },
        },
    )
    return plan


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = run(args.output_dir)
    except H2PlanError as exc:
        write_json(
            args.output_dir / "h2-context-plan-error.json",
            {"type": type(exc).__name__, "detail": str(exc)},
        )
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
