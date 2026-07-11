from __future__ import annotations

import importlib.metadata
import importlib.util
import json
import sys
from pathlib import Path


def main() -> int:
    try:
        distribution = importlib.metadata.distribution("hermes-agent")
        entry_points = {
            entry.name: entry.value
            for entry in distribution.entry_points
            if entry.group == "console_scripts"
        }
        module_spec = importlib.util.find_spec("hermes_cli.main")
        module_file = Path(module_spec.origin).resolve() if module_spec and module_spec.origin else None
        payload = {
            "ok": entry_points.get("hermes") == "hermes_cli.main:main" and module_file is not None,
            "python_executable": str(Path(sys.executable).resolve()),
            "python_prefix": str(Path(sys.prefix).resolve()),
            "distribution_version": distribution.version,
            "hermes_entry_point": entry_points.get("hermes"),
            "module_file": str(module_file) if module_file else None,
        }
    except Exception as exc:
        payload = {
            "ok": False,
            "error": type(exc).__name__,
            "python_executable": str(Path(sys.executable).resolve()),
        }
    print(json.dumps(payload, sort_keys=True))
    return 0 if payload["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
