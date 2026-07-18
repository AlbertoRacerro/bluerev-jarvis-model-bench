from __future__ import annotations

from pathlib import Path

from scripts import bench3_contract_constants as C

ROOT = Path(__file__).resolve().parents[1]
CANONICAL_SHELL_RUNNER = ROOT / "scripts/run_bench3_hermes_memory_routing.sh"
SENTINELS = (
    "bench.hermes-memory-routing",
    "bench3-hermes-memory-routing",
    "bench-3-hermes-memory-routing",
    "memory-orchestration",
    "routing-orchestration",
    "MR-MEM-",
    "MR-ROUTE-",
)


class Bench3ShellGuardError(RuntimeError):
    pass


def unexpected_shell_artifacts() -> list[str]:
    scripts = ROOT / "scripts"
    if not scripts.exists():
        return []
    found: list[str] = []
    for path in scripts.rglob("*.sh"):
        if not path.is_file():
            continue
        rel = path.relative_to(ROOT).as_posix()
        lowered = rel.lower()
        namespace_match = any(token in lowered for token in C.NAMESPACE_VARIANTS)
        path_match = namespace_match and (
            "memory" in lowered or "routing" in lowered
        )
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            text = ""
        content_match = any(token.lower() in text.lower() for token in SENTINELS)
        if path_match or content_match:
            found.append(rel)
    return sorted(found)


def validate() -> dict[str, object]:
    if CANONICAL_SHELL_RUNNER.exists():
        raise Bench3ShellGuardError("canonical BENCH-3 shell runner exists")
    found = unexpected_shell_artifacts()
    if found:
        raise Bench3ShellGuardError(
            f"unexpected BENCH-3 shell runtime artifacts: {found}"
        )
    return {
        "shell_runtime_guard_validated": True,
        "shell_runtime_artifacts": 0,
    }
