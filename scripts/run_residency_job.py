from __future__ import annotations

import argparse
import hashlib
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.benchmark_runtime import run_captured, safe_reset_directory, sanitize_environment
from scripts.test_subset import run_test_subset

ARTIFACT_ROOT = ROOT / "artifacts"
ARTIFACTS = ARTIFACT_ROOT / "model-residency"
TEST_PATTERNS = (
    "test_benchmark_runtime.py",
    "test_lane_test_subset.py",
    "test_probe_model_residency.py",
    "test_probe_model_residency_v2.py",
    "test_build_residency_shortlist.py",
    "test_residency_shortlist_binding.py",
    "test_build_h2_context_plan.py",
)


def _environment() -> dict[str, str]:
    environment, _removed = sanitize_environment(os.environ)
    environment["PYTHONPATH"] = os.pathsep.join((str(ROOT), str(ROOT / "src")))
    return environment


def prepare() -> int:
    safe_reset_directory(ARTIFACTS, allowed_root=ARTIFACT_ROOT)
    return 0


def tests() -> int:
    result = run_test_subset(
        patterns=TEST_PATTERNS,
        root=ROOT,
        environment=_environment(),
        artifact_dir=ARTIFACTS,
        timeout_seconds_per_pattern=300,
    )
    return int(result["exit_code"])


def probe() -> int:
    result = run_captured(
        "probe",
        [
            sys.executable,
            "scripts/probe_model_residency_v2.py",
            "--output-dir",
            str(ARTIFACTS),
        ],
        cwd=ROOT,
        environment=_environment(),
        artifact_dir=ARTIFACTS,
        timeout_seconds=9000,
    )
    return int(result["exit_code"])


def shortlist() -> int:
    result = run_captured(
        "shortlist",
        [
            sys.executable,
            "scripts/build_residency_shortlist.py",
            "--output-dir",
            str(ARTIFACTS),
        ],
        cwd=ROOT,
        environment=_environment(),
        artifact_dir=ARTIFACTS,
        timeout_seconds=120,
    )
    return int(result["exit_code"])


def h2_plan() -> int:
    manifest = ARTIFACTS / "shortlist-manifest.json"
    if not manifest.is_file():
        print(f"missing shortlist manifest: {manifest}", file=sys.stderr)
        return 2
    digest = hashlib.sha256(manifest.read_bytes()).hexdigest()
    (ARTIFACTS / "shortlist-manifest.sha256").write_text(
        digest + "\n", encoding="ascii"
    )
    result = run_captured(
        "h2-plan",
        [
            sys.executable,
            "scripts/build_h2_context_plan.py",
            "--output-dir",
            str(ARTIFACTS),
            "--expected-shortlist-manifest-sha256",
            digest,
        ],
        cwd=ROOT,
        environment=_environment(),
        artifact_dir=ARTIFACTS,
        timeout_seconds=120,
    )
    return int(result["exit_code"])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "mode",
        choices=("prepare", "tests", "probe", "shortlist", "h2-plan"),
    )
    mode = parser.parse_args().mode
    return {
        "prepare": prepare,
        "tests": tests,
        "probe": probe,
        "shortlist": shortlist,
        "h2-plan": h2_plan,
    }[mode]()


if __name__ == "__main__":
    raise SystemExit(main())
