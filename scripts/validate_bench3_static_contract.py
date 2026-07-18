from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from scripts import validate_bench3_hermes_memory_routing_design as base

EXPECTED_CONFLICT_PRECEDENCE = [
    "current_user_statement",
    "verified_current_project_state",
    "approved_persistent_memory",
    "session_history",
]


def _validate_conflict_precedence(plan: dict[str, Any]) -> None:
    memory = plan.get("memory_architecture")
    base._require(isinstance(memory, dict), "memory architecture missing")
    base._require(
        memory.get("conflict_precedence") == EXPECTED_CONFLICT_PRECEDENCE,
        "memory conflict precedence drifted",
    )


def validate() -> dict[str, Any]:
    payload = base.validate()
    _validate_conflict_precedence(base._load(base.PLAN_PATH))
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate the complete non-executive BENCH-3 static contract."
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        payload = validate()
        code = 0
    except (base.MemoryRoutingDesignError, OSError, ValueError, TypeError) as exc:
        payload = {
            "schema_version": "bench3.static-contract-validation.v1",
            "status": "invalid",
            "error_type": type(exc).__name__,
            "error": str(exc),
        }
        code = 2
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text, end="")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
