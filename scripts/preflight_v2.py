from __future__ import annotations

import argparse
import json
import os
import platform
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts import preflight as base
from scripts.benchmark_runtime import (
    external_env_names,
    parse_removed_environment_report,
)

GATES = ("direct", "hermes")


def _workflow_identity() -> dict[str, str | None]:
    return {
        "run_id": os.environ.get("GITHUB_RUN_ID"),
        "run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
        "event_name": os.environ.get("GITHUB_EVENT_NAME"),
        "sha": os.environ.get("GITHUB_SHA"),
        "ref": os.environ.get("GITHUB_REF"),
    }


def _environment_fingerprint() -> dict[str, Any]:
    return {
        "runner_name": os.environ.get("RUNNER_NAME"),
        "os": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "python": sys.version,
        "cpu_count": os.cpu_count(),
    }


def _direct_lane(
    *,
    ollama: dict[str, Any],
    local_only: bool,
    removed_external_names: list[str],
    workflow: dict[str, str | None],
    runner_name: str | None,
) -> dict[str, Any]:
    raw_models = ollama.get("models")
    models = raw_models if isinstance(raw_models, list) else []
    identity_invalid = (
        raw_models is not None
        and (
            not isinstance(raw_models, list)
            or any(
                not isinstance(model, dict)
                or not model.get("name")
                or not model.get("digest")
                for model in models
            )
        )
    )
    blocking_reasons = [
        reason
        for condition, reason in (
            (
                not ollama.get("ok")
                and ollama.get("error") == "NonLoopbackEndpoint",
                "ollama_endpoint_not_loopback",
            ),
            (
                not ollama.get("ok")
                and ollama.get("error") != "NonLoopbackEndpoint",
                "ollama_unreachable_or_invalid",
            ),
            (ollama.get("ok") and not models, "no_ollama_models"),
            (not local_only, "external_api_environment_present_after_sanitization"),
        )
        if condition
    ]
    scoring_blocking_reasons = list(blocking_reasons)
    scoring_blocking_reasons.extend(
        reason
        for condition, reason in (
            (not runner_name, "runner_name_unavailable"),
            (
                any(
                    not workflow.get(field)
                    for field in ("run_id", "run_attempt", "sha", "ref")
                ),
                "workflow_identity_incomplete",
            ),
            (
                ollama.get("ok")
                and not (ollama.get("version") or {}).get("ok"),
                "ollama_version_unavailable",
            ),
            (identity_invalid, "ollama_model_identity_incomplete"),
            (
                removed_external_names == ["invalid_sanitization_report"],
                "environment_sanitization_report_invalid",
            ),
        )
        if condition
    )
    runner_ready = bool(ollama.get("ok") and models and not identity_invalid)
    return {
        "evaluated": True,
        "runner_ready": runner_ready,
        "scoring_ready": runner_ready
        and local_only
        and not scoring_blocking_reasons,
        "blocking_reasons": blocking_reasons,
        "scoring_blocking_reasons": scoring_blocking_reasons,
    }


def build_report(required_gate: str) -> dict[str, Any]:
    if required_gate not in GATES:
        raise ValueError(f"unsupported preflight gate: {required_gate}")

    if required_gate == "hermes":
        report = base.build_report()
        direct = _direct_lane(
            ollama=dict(report["ollama"]),
            local_only=report["local_only"] is True,
            removed_external_names=list(
                report["environment_sanitization"]["removed_external_env_names"]
            ),
            workflow=dict(report["workflow"]),
            runner_name=report["environment"].get("runner_name"),
        )
        report["selected_gate"] = "hermes"
        report["lanes"] = {
            "direct": direct,
            "hermes": {
                "evaluated": True,
                "runner_ready": report["runner_ready"],
                "scoring_ready": report["scoring_ready"],
                "blocking_reasons": report["blocking_reasons"],
                "scoring_blocking_reasons": report[
                    "scoring_blocking_reasons"
                ],
            },
        }
        return report

    ollama = base.inspect_ollama()
    current_external_names = external_env_names(os.environ)
    removed_external_names = parse_removed_environment_report(os.environ)
    local_only = not current_external_names
    workflow = _workflow_identity()
    environment = _environment_fingerprint()
    direct = _direct_lane(
        ollama=ollama,
        local_only=local_only,
        removed_external_names=removed_external_names,
        workflow=workflow,
        runner_name=environment.get("runner_name"),
    )
    return {
        "schema_version": "bench.preflight.v1",
        "created_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "selected_gate": "direct",
        "status": "ready" if direct["runner_ready"] else "blocked",
        "runner_ready": direct["runner_ready"],
        "local_only": local_only,
        "scoring_ready": direct["scoring_ready"],
        "environment_sanitization": {
            "current_external_env_names": current_external_names,
            "removed_external_env_names": removed_external_names,
            "secret_values_recorded": False,
        },
        "external_api_env_names_present": current_external_names,
        "environment": environment,
        "workflow": workflow,
        "ollama": ollama,
        "hermes": {
            "evaluated": False,
            "reason": "not_required_for_direct_gate",
        },
        "blocking_reasons": direct["blocking_reasons"],
        "scoring_blocking_reasons": direct["scoring_blocking_reasons"],
        "lanes": {
            "direct": direct,
            "hermes": {
                "evaluated": False,
                "runner_ready": None,
                "scoring_ready": None,
                "blocking_reasons": None,
                "scoring_blocking_reasons": None,
            },
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Inventory a lane-specific local benchmark environment."
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--required-gate", choices=GATES, default="hermes")
    args = parser.parse_args()
    report = build_report(args.required_gate)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["scoring_ready"] is True else 2


if __name__ == "__main__":
    raise SystemExit(main())
