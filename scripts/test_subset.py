from __future__ import annotations

from collections.abc import Mapping, Sequence
import json
from pathlib import Path
from typing import Any
import sys

from scripts.benchmark_runtime import run_captured


class TestSubsetError(RuntimeError):
    pass


def resolve_patterns(tests_dir: Path, patterns: Sequence[str]) -> dict[str, list[str]]:
    if not patterns:
        raise TestSubsetError("test subset must contain at least one pattern")
    resolved: dict[str, list[str]] = {}
    claimed: dict[str, str] = {}
    for pattern in patterns:
        if not isinstance(pattern, str) or not pattern or Path(pattern).name != pattern:
            raise TestSubsetError(f"invalid test pattern: {pattern!r}")
        matches = sorted(
            path.name
            for path in tests_dir.glob(pattern)
            if path.is_file() and path.name.startswith("test_") and path.suffix == ".py"
        )
        if not matches:
            raise TestSubsetError(f"test pattern matched no files: {pattern}")
        for name in matches:
            previous = claimed.get(name)
            if previous is not None:
                raise TestSubsetError(
                    f"test file matched by multiple patterns: {name} ({previous}, {pattern})"
                )
            claimed[name] = pattern
        resolved[pattern] = matches
    return resolved


def _validation_failure(
    *,
    artifact_dir: Path,
    patterns: Sequence[str],
    exc: TestSubsetError,
) -> dict[str, Any]:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    error = {"type": type(exc).__name__, "detail": str(exc)}
    (artifact_dir / "tests.error.json").write_text(
        json.dumps(error, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (artifact_dir / "tests.log").write_text(
        f"test subset validation failed: {exc}\n",
        encoding="utf-8",
    )
    return {
        "exit_code": 2,
        "patterns": list(patterns),
        "resolved_files": [],
        "results": [],
        "error": error,
    }


def run_test_subset(
    *,
    patterns: Sequence[str],
    root: Path,
    environment: Mapping[str, str],
    artifact_dir: Path,
    timeout_seconds_per_pattern: int = 300,
) -> dict[str, Any]:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    try:
        if (
            not isinstance(timeout_seconds_per_pattern, int)
            or isinstance(timeout_seconds_per_pattern, bool)
            or timeout_seconds_per_pattern < 1
        ):
            raise TestSubsetError(
                "timeout_seconds_per_pattern must be an integer >= 1"
            )
        resolved = resolve_patterns(root / "tests", patterns)
    except TestSubsetError as exc:
        return _validation_failure(
            artifact_dir=artifact_dir,
            patterns=patterns,
            exc=exc,
        )

    results: list[dict[str, Any]] = []
    combined: list[str] = []
    exit_code = 0
    for index, pattern in enumerate(patterns, start=1):
        name = f"tests-{index:02d}"
        result = run_captured(
            name,
            [
                sys.executable,
                "-m",
                "unittest",
                "discover",
                "-s",
                "tests",
                "-p",
                pattern,
                "-v",
            ],
            cwd=root,
            environment=environment,
            artifact_dir=artifact_dir,
            timeout_seconds=timeout_seconds_per_pattern,
        )
        stdout_path = artifact_dir / f"{name}.stdout.log"
        stderr_path = artifact_dir / f"{name}.stderr.log"
        combined.extend(
            [
                f"===== {pattern} ({', '.join(resolved[pattern])}) stdout =====\n",
                stdout_path.read_text(encoding="utf-8"),
                f"\n===== {pattern} stderr =====\n",
                stderr_path.read_text(encoding="utf-8"),
                "\n",
            ]
        )
        results.append(
            {
                "pattern": pattern,
                "files": resolved[pattern],
                **result,
            }
        )
        if result["exit_code"] != 0:
            exit_code = int(result["exit_code"])
            break

    (artifact_dir / "tests.log").write_text("".join(combined), encoding="utf-8")
    return {
        "exit_code": exit_code,
        "patterns": list(patterns),
        "resolved_files": sorted(
            name for names in resolved.values() for name in names
        ),
        "results": results,
        "error": None,
    }
