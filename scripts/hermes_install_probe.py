from __future__ import annotations

import importlib.metadata
import json
import sys
from pathlib import Path


def _distribution_file(distribution: importlib.metadata.Distribution, relative: str) -> Path | None:
    for item in distribution.files or ():
        if item.as_posix() == relative:
            return Path(distribution.locate_file(item)).resolve()
    return None


def main() -> int:
    try:
        distribution = importlib.metadata.distribution("hermes-agent")
        entry_points = {
            entry.name: entry.value
            for entry in distribution.entry_points
            if entry.group == "console_scripts"
        }
        module_file = _distribution_file(distribution, "hermes_cli/main.py")
        payload = {
            "ok": entry_points.get("hermes") == "hermes_cli.main:main" and module_file is not None,
            "python_executable": str(Path(sys.executable).resolve()),
            "python_prefix": str(Path(sys.prefix).resolve()),
            "distribution_version": distribution.version,
            "hermes_entry_point": entry_points.get("hermes"),
            "module_file": str(module_file) if module_file else None,
            "package_imported": False,
        }
    except Exception as exc:
        payload = {
            "ok": False,
            "error": type(exc).__name__,
            "python_executable": str(Path(sys.executable).resolve()),
            "package_imported": False,
        }
    print(json.dumps(payload, sort_keys=True))
    return 0 if payload["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
