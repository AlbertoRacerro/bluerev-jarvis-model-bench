from __future__ import annotations

import sys
import types
import unittest
from pathlib import Path
from unittest import mock

from scripts import run_bench2r_hermes_worker as worker

ROOT = Path(__file__).resolve().parents[1]
SKILL_PATH = ROOT / "fixtures/bench-2r/hermes-skills/bounded-tool-orchestration/SKILL.md"
MARKER_PATH = ROOT / "config/bench2r-hermes-s1-marker.json"


class Bench2RS1RTrajectorySkillTests(unittest.TestCase):
    def test_worker_forces_and_restores_native_trajectory_constructor_flag(self):
        calls: list[dict[str, object]] = []

        class FakeAgent:
            def __init__(self, *args, **kwargs):
                calls.append(dict(kwargs))

        original_init = FakeAgent.__init__
        fake_module = types.ModuleType("run_agent")
        fake_module.AIAgent = FakeAgent

        with mock.patch.dict(sys.modules, {"run_agent": fake_module}):
            with worker._force_native_trajectory_capture():
                FakeAgent(model="candidate")
                self.assertIsNot(FakeAgent.__init__, original_init)

        self.assertIs(FakeAgent.__init__, original_init)
        self.assertEqual(calls, [{"model": "candidate", "save_trajectories": True}])

    def test_constructor_restores_after_failure(self):
        class FakeAgent:
            def __init__(self, *args, **kwargs):
                pass

        original_init = FakeAgent.__init__
        fake_module = types.ModuleType("run_agent")
        fake_module.AIAgent = FakeAgent

        with mock.patch.dict(sys.modules, {"run_agent": fake_module}):
            with self.assertRaisesRegex(RuntimeError, "worker failure"):
                with worker._force_native_trajectory_capture():
                    raise RuntimeError("worker failure")

        self.assertIs(FakeAgent.__init__, original_init)

    def test_skill_v11_separates_runtime_stop_from_output_ledger(self):
        text = SKILL_PATH.read_text(encoding="utf-8")
        self.assertIn("version: 1.1.0", text)
        self.assertIn("runtime behavior", text)
        self.assertIn("output ledger", text)
        self.assertIn("copy every item exactly once and in the original order", text)
        self.assertIn("Do not return the raw tool object", text)
        for forbidden_literal in ("BRAVO-19", "stable-result", "alpha-7"):
            self.assertNotIn(forbidden_literal, text)

    def test_review_branch_keeps_s1_disabled(self):
        import json

        marker = json.loads(MARKER_PATH.read_text(encoding="utf-8"))
        self.assertFalse(marker["enabled"])


if __name__ == "__main__":
    unittest.main()
