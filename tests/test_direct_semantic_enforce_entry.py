from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

from scripts import run_direct_semantic_enforce_entry as entry


class DirectSemanticEnforceEntryTests(unittest.TestCase):
    def test_nonzero_gate_result_preserves_stdout_and_stderr(self):
        def fail_gate(_artifact_dir: Path) -> int:
            print("gate stdout")
            print("gate stderr", file=sys.stderr)
            return 1

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.assertEqual(entry.run_enforce(fail_gate, root), 1)
            summary = json.loads((root / "enforce-summary.json").read_text())
            self.assertEqual(summary["exit_code"], 1)
            self.assertIsNone(summary["error"])
            self.assertIn("gate stdout", (root / "enforce-stdout.log").read_text())
            self.assertIn("gate stderr", (root / "enforce-stderr.log").read_text())

    def test_exception_preserves_traceback_and_structured_error(self):
        def explode(_artifact_dir: Path) -> int:
            raise RuntimeError("enforce diagnostic")

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.assertEqual(entry.run_enforce(explode, root), 2)
            summary = json.loads((root / "enforce-summary.json").read_text())
            self.assertEqual(summary["exit_code"], 2)
            self.assertEqual(summary["error"]["type"], "RuntimeError")
            self.assertEqual(summary["error"]["detail"], "enforce diagnostic")
            self.assertIn(
                "enforce diagnostic",
                (root / "enforce-traceback.txt").read_text(),
            )


if __name__ == "__main__":
    unittest.main()
