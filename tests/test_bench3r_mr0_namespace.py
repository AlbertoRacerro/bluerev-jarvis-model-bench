from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts import bench3r_mr0_namespace as namespace
from scripts.bench3r_mr0_io import read_text


class MR0NamespaceTests(unittest.TestCase):
    def test_clean_namespace_passes(self):
        result = namespace.validate(read_text(namespace.WORKFLOW))
        self.assertTrue(result["namespace_guard_validated"])
        self.assertEqual(result["namespace_runtime_artifacts"], 0)

    def test_renamed_and_opaque_files_are_detected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            samples = {
                ".github/workflows/bench-3r-alt-mr0.yml": "name: run\n",
                "config/bench_3r_mr0.json": "{}\n",
                "scripts/worker.ps1": "schema=bench3r.mr0-decision.v1\n",
                ".github/actions/opaque/action.yml": "toolset: bench3r_mr0_synthetic\n",
            }
            for relative, text in samples.items():
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text, encoding="utf-8")
            with mock.patch.object(namespace, "ROOT", root):
                found = namespace.unexpected_files()
            self.assertEqual(found, sorted(samples))

    def test_removed_broad_trigger_is_rejected(self):
        workflow = read_text(namespace.WORKFLOW)
        trigger = namespace.BROAD_TRIGGERS[0]
        changed = workflow.replace(f"      - {trigger}\n", "", 1)
        with self.assertRaisesRegex(
            namespace.MR0NamespaceError,
            "broad namespace trigger",
        ):
            namespace.validate(changed)


if __name__ == "__main__":
    unittest.main()
