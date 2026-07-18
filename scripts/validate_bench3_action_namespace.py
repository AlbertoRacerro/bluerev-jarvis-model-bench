from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = ROOT / ".github/workflows" / (
    "bench3-hermes-" + "memory-routing-design-validation.yml"
)
ACTION_TRIGGER = ".github/" + "actions/**"


class Bench3ActionNamespaceError(RuntimeError):
    pass


def unexpected_files() -> list[str]:
    directory = ROOT / ".github/actions"
    if not directory.exists():
        return []
    return sorted(
        path.relative_to(ROOT).as_posix()
        for path in directory.rglob("*")
        if path.is_file()
    )


def validate() -> dict[str, object]:
    try:
        workflow = WORKFLOW_PATH.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise Bench3ActionNamespaceError(
            f"cannot read action workflow: {type(exc).__name__}: {exc}"
        ) from exc
    if workflow.count(ACTION_TRIGGER) != 2:
        raise Bench3ActionNamespaceError(
            "action workflow trigger missing or duplicated"
        )
    found = unexpected_files()
    if found:
        raise Bench3ActionNamespaceError(
            f"unexpected action files: {found}"
        )
    return {
        "action_namespace_guard_validated": True,
        "action_namespace_files": 0,
    }
