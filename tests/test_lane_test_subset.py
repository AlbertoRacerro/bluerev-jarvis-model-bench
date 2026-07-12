from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.test_subset import TestSubsetError, resolve_patterns


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


if __name__ == "__main__":
    unittest.main()
