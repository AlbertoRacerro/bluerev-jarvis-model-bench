from __future__ import annotations

import importlib.metadata
import json
import sys
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse
from urllib.request import url2pathname


def _distribution_file(
    distribution: importlib.metadata.Distribution,
    relative: str,
) -> Path | None:
    for item in distribution.files or ():
        if item.as_posix() == relative:
            return Path(distribution.locate_file(item)).resolve()
    return None


def _editable_source_root(distribution: importlib.metadata.Distribution) -> Path | None:
    raw = distribution.read_text("direct_url.json")
    if not raw:
        return None
    value: Any = json.loads(raw)
    if not isinstance(value, dict):
        return None
    dir_info = value.get("dir_info")
    if not isinstance(dir_info, dict) or dir_info.get("editable") is not True:
        return None
    url = value.get("url")
    if not isinstance(url, str):
        return None
    parsed = urlparse(url)
    if parsed.scheme != "file" or parsed.query or parsed.fragment:
        return None
    local_path = url2pathname(unquote(parsed.path))
    if parsed.netloc and parsed.netloc.lower() != "localhost":
        local_path = f"//{parsed.netloc}{local_path}"
    return Path(local_path).resolve()


def _resolve_module_file(
    distribution: importlib.metadata.Distribution,
) -> tuple[Path | None, str | None, Path | None]:
    packaged = _distribution_file(distribution, "hermes_cli/main.py")
    if packaged is not None:
        return packaged, "installed-files", None
    source_root = _editable_source_root(distribution)
    if source_root is None:
        return None, None, None
    candidate = (source_root / "hermes_cli" / "main.py").resolve()
    if not candidate.is_file():
        return None, "editable", source_root
    return candidate, "editable", source_root


def main() -> int:
    try:
        distribution = importlib.metadata.distribution("hermes-agent")
        entry_points = {
            entry.name: entry.value
            for entry in distribution.entry_points
            if entry.group == "console_scripts"
        }
        module_file, install_mode, source_root = _resolve_module_file(distribution)
        payload = {
            "ok": entry_points.get("hermes") == "hermes_cli.main:main"
            and module_file is not None,
            "python_executable": str(Path(sys.executable).resolve()),
            "python_prefix": str(Path(sys.prefix).resolve()),
            "distribution_version": distribution.version,
            "hermes_entry_point": entry_points.get("hermes"),
            "module_file": str(module_file) if module_file else None,
            "install_mode": install_mode,
            "source_root": str(source_root) if source_root else None,
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
