from __future__ import annotations

from pathlib import Path

from scripts import bench3_contract_constants as C

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = ROOT / ".github/workflows/bench3-hermes-memory-routing-design-validation.yml"
ACTION_TRIGGER = ".github/" + "actions/**"
TOKENS = (
    "bench.hermes-" + "memory-routing",
    "bench3-hermes-" + "memory-routing",
    "bench-3-hermes-" + "memory-routing",
    "memory-" + "orchestration",
    "routing-" + "orchestration",
    "MR-" + "MEM-",
    "MR-" + "ROUTE-",
)


class Bench3ActionNamespaceError(RuntimeError):
    pass


def unexpected_files() -> list[str]:
    directory = ROOT / ".github/actions"
    if not directory.exists():
        return []
    found: list[str] = []
    for path in directory.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(ROOT).as_posix()
        lowered = rel.lower()
        named = any(token in lowered for token in C.NAMESPACE_VARIANTS) and (
            "memory" in lowered or "routing" in lowered
        )
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            text = ""
        tagged = any(token.lower() in text.lower() for token in TOKENS)
        if named or tagged:
            found.append(rel)
    return sorted(found)


def validate() -> dict[str, object]:
    try:
        workflow = WORKFLOW_PATH.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise Bench3ActionNamespaceError(
            f"cannot read action-guard workflow: {type(exc).__name__}: {exc}"
        ) from exc
    if workflow.count(ACTION_TRIGGER) != 2:
        raise Bench3ActionNamespaceError(
            "composite-action workflow trigger missing or duplicated"
        )
    found = unexpected_files()
    if found:
        raise Bench3ActionNamespaceError(
            f"unexpected BENCH-3 action namespace files: {found}"
        )
    return {
        "action_namespace_guard_validated": True,
        "action_namespace_files": 0,
    }
