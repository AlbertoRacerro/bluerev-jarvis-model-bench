from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.test_subset import TestSubsetError, resolve_patterns, run_test_subset


class LaneSubsetTests(unittest.TestCase):
    def test_requires_existing_unique_test_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            tests = Path(directory)
            (tests / "test_one.py").write_text("", encoding="utf-8")
            self.assertEqual(
                resolve_patterns(tests, ("test_one.py",)),
                {"test_one.py": ["test_one.py"]},
            )
            with self.assertRaises(TestSubsetError):
                resolve_patterns(tests, ("test_none.py",))
            with self.assertRaises(TestSubsetError):
                resolve_patterns(tests, ("test_one.py", "test_*.py"))

    def test_invalid_subset_returns_failure_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "tests").mkdir()
            artifacts = root / "artifacts"
            result = run_test_subset(
                patterns=("test_missing.py",),
                root=root,
                environment={},
                artifact_dir=artifacts,
            )
            error = json.loads(
                (artifacts / "tests.error.json").read_text(encoding="utf-8")
            )
            log = (artifacts / "tests.log").read_text(encoding="utf-8")
        self.assertEqual(result["exit_code"], 2)
        self.assertEqual(error["type"], "TestSubsetError")
        self.assertIn("test_missing.py", error["detail"])
        self.assertIn("validation failed", log)


if __name__ == "__main__":
    unittest.main()
