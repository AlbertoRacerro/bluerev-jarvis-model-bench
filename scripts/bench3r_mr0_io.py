from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


class MR0DesignError(RuntimeError):
    pass


def reject_duplicates(items: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in items:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=reject_duplicates,
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise MR0DesignError(
            f"cannot read {path}: {type(exc).__name__}: {exc}"
        ) from exc
    if not isinstance(value, dict):
        raise MR0DesignError(f"{path} must contain an object")
    return value


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise MR0DesignError(
            f"cannot read {path}: {type(exc).__name__}: {exc}"
        ) from exc


def git_blob_sha(text: str) -> str:
    raw = text.encode("utf-8")
    header = f"blob {len(raw)}\0".encode("ascii")
    return hashlib.sha1(header + raw).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise MR0DesignError(message)
