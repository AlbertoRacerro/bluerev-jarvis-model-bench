from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import test_subset


class TestSubsetTests(unittest.TestCase):
    def test_missing_pattern_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "tests").mkdir()
            with self.assertRaisesRegex(
                test_subset.TestSubsetError,
                "matched no files",
            ):
                test_subset.resolve_patterns(
                    root / "tests",
                    ("test_missing.py",),
                )

    def test_overlapping_patterns_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            tests = Path(directory) / "tests"
            tests.mkdir()
            (tests / "test_alpha.py").write_text("", encoding="utf-8")
            with self.assertRaisesRegex(
                test_subset.TestSubsetError,
                "multiple patterns",
            ):
                test_subset.resolve_patterns(
                    tests,
                    ("test_alpha.py", "test_*.py"),
                )

    def test_stops_after_first_failed_pattern_and_writes_log(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tests = root / "tests"
            artifacts = root / "artifacts"
            tests.mkdir()
            artifacts.mkdir()
            for name in ("test_alpha.py", "test_beta.py"):
                (tests / name).write_text("", encoding="utf-8")

            def fake_run(name, command, **_kwargs):
                (artifacts / f"{name}.stdout.log").write_text(
                    f"stdout-{name}", encoding="utf-8"
                )
                (artifacts / f"{name}.stderr.log").write_text(
                    f"stderr-{name}", encoding="utf-8"
                )
                return {
                    "command": command,
                    "exit_code": 7,
                    "timeout_seconds": 30,
                    "timed_out": False,
                    "error_type": None,
                }

            with patch.object(test_subset, "run_captured", side_effect=fake_run) as run:
                result = test_subset.run_test_subset(
                    patterns=("test_alpha.py", "test_beta.py"),
                    root=root,
                    environment={},
                    artifact_dir=artifacts,
                    timeout_seconds_per_pattern=30,
                )
        self.assertEqual(result["exit_code"], 7)
        self.assertEqual(run.call_count, 1)
        self.assertEqual(result["resolved_files"], ["test_alpha.py", "test_beta.py"])
        self.assertIn("stdout-tests-01", (artifacts / "tests.log").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
