from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/bench3r-mr0-design-validation.yml"
VARIANTS = ("bench3r", "bench-3r", "bench_3r")
BROAD_TRIGGERS = (
    ".github/workflows/*bench*3*r*mr0**",
    "config/*bench*3*r*mr0**",
    "scripts/*bench*3*r*mr0**",
    ".github/actions/**",
)
STATIC_ALLOWLIST = {
    WORKFLOW.relative_to(ROOT).as_posix(),
    "scripts/bench3r_mr0_ids.py",
    "scripts/bench3r_mr0_contract.py",
    "scripts/bench3r_mr0_io.py",
    "scripts/bench3r_mr0_validate_design.py",
    "scripts/bench3r_mr0_validate_policy.py",
    "scripts/bench3r_mr0_namespace.py",
    "scripts/validate_bench3r_mr0_design.py",
}
SENTINELS = (
    "bench3r.mr0-" + "memory-routing-canary-design.v1",
    "bench3r.mr0-" + "decision.v1",
    "bench3r_mr0_" + "synthetic",
)


class MR0NamespaceError(RuntimeError):
    pass


def unexpected_files() -> list[str]:
    scans = (
        (ROOT / ".github/workflows", {".yml", ".yaml"}),
        (ROOT / "config", {".json"}),
        (ROOT / "scripts", {".py", ".ps1", ".cmd", ".bat", ".sh"}),
        (ROOT / ".github/actions", None),
    )
    found: list[str] = []
    for directory, suffixes in scans:
        if not directory.exists():
            continue
        for path in directory.rglob("*"):
            if not path.is_file():
                continue
            if suffixes is not None and path.suffix.lower() not in suffixes:
                continue
            relative = path.relative_to(ROOT).as_posix()
            if relative in STATIC_ALLOWLIST:
                continue
            lowered = relative.lower()
            named = "mr0" in lowered and any(item in lowered for item in VARIANTS)
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeError):
                text = ""
            tagged = any(item.lower() in text.lower() for item in SENTINELS)
            if named or tagged:
                found.append(relative)
    return sorted(found)


def validate(workflow: str) -> dict[str, object]:
    for trigger in BROAD_TRIGGERS:
        if workflow.count(trigger) != 2:
            raise MR0NamespaceError(f"broad namespace trigger drifted: {trigger}")
    found = unexpected_files()
    if found:
        raise MR0NamespaceError(f"unexpected MR0 runtime artifacts: {found}")
    return {
        "namespace_guard_validated": True,
        "namespace_runtime_artifacts": 0,
    }
