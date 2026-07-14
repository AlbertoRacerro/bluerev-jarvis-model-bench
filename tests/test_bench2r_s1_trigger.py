from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/bench2r-hermes-s1-oneshot.yml"


class Bench2RS1TriggerTests(unittest.TestCase):
    def test_execution_workflow_is_marker_only(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("paths:\n      - config/bench2r-hermes-s1-marker.json", text)
        self.assertIn("branches: [main]", text)
        self.assertIn("cancel-in-progress: true", text)
        self.assertIn(
            "startsWith(github.event.head_commit.message, "
            "'Activate BENCH-2R Hermes S1 preflight')",
            text,
        )
        self.assertNotIn("workflow_dispatch", text)


if __name__ == "__main__":
    unittest.main()
