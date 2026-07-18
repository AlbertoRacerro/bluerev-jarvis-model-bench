from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts import validate_bench3_action_namespace as guard


class Bench3ActionNamespaceTests(unittest.TestCase):
    def test_clean_repository_passes(self):
        result = guard.validate()
        self.assertTrue(result["action_namespace_guard_validated"])
        self.assertEqual(result["action_namespace_files"], 0)

    def test_named_and_opaque_composite_actions_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            samples = {
                ".github/actions/bench-3-memory-routing/action.yml": "name: runtime\n",
                ".github/actions/opaque/action.yml": "name: x\ndescription: bench.hermes-memory-routing-design.v1\n",
            }
            for relative, text in samples.items():
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text, encoding="utf-8")
            with mock.patch.object(guard, "ROOT", root):
                found = guard.unexpected_files()
            self.assertEqual(found, sorted(samples))

    def test_removing_action_trigger_fails_closed(self):
        workflow = guard.WORKFLOW_PATH.read_text(encoding="utf-8")
        changed = workflow.replace(f"      - {guard.ACTION_TRIGGER}\n", "", 1)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "workflow.yml"
            path.write_text(changed, encoding="utf-8")
            with mock.patch.object(guard, "WORKFLOW_PATH", path):
                with self.assertRaisesRegex(
                    guard.Bench3ActionNamespaceError,
                    "workflow trigger",
                ):
                    guard.validate()


if __name__ == "__main__":
    unittest.main()
