from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts import validate_bench2_plan as validator

ROOT = Path(__file__).resolve().parents[1]
DOC_PATH = ROOT / "docs" / "BENCH-2-HERMES-ORCHESTRATOR-ISOLATION.md"


class Bench2HermesPlanTests(unittest.TestCase):
    def test_review_ready_plan_passes_strict_validator(self):
        plan = validator.validate_plan()
        self.assertFalse(plan["execution_authorized"])
        self.assertEqual(plan["baseline"]["status"], "unresolved")
        self.assertEqual(
            [item["candidate_id"] for item in plan["candidates"][:5]],
            validator.EXPECTED_PRIMARY,
        )
        self.assertEqual(plan["candidates"][5]["candidate_id"], validator.EXPECTED_CONTROL)

    def test_plan_digest_and_source_evidence_are_bound(self):
        plan = validator.validate_plan()
        self.assertEqual(
            validator._source_sha256(validator.PLAN_PATH),
            validator.EXPECTED_PLAN_SHA256,
        )
        bench1 = ROOT / plan["sources"]["bench1_closeout"]["path"]
        h3 = ROOT / plan["sources"]["h3_summary"]["path"]
        registry = ROOT / plan["sources"]["candidate_registry"]["path"]
        self.assertEqual(
            validator._source_sha256(bench1),
            plan["sources"]["bench1_closeout"]["sha256"],
        )
        self.assertEqual(
            validator._source_sha256(h3),
            plan["sources"]["h3_summary"]["sha256"],
        )
        self.assertEqual(
            validator._canonical_json_sha256(registry),
            plan["sources"]["candidate_registry"]["sha256"],
        )

    def test_calibration_and_core_gates_remain_distinct(self):
        plan = validator.validate_plan()
        stages = {item["id"]: item for item in plan["stages"]}
        self.assertFalse(stages["B2-PRE-0"]["model_calls"])
        self.assertFalse(stages["B2-PRE-1"]["model_calls"])
        self.assertFalse(stages["B2-CAL"]["comparative"])
        self.assertEqual(stages["B2-CAL"]["worker_pool"], "deterministic_fixture_workers")
        self.assertEqual(stages["B2-CAL"]["total_runs"], 18)
        self.assertTrue(stages["B2-CORE"]["comparative"])
        self.assertEqual(stages["B2-CORE"]["worker_pool"], "fixed_local_models")
        self.assertEqual(stages["B2-CORE"]["repetitions"], 3)
        self.assertGreaterEqual(stages["B2-CORE"]["total_runs_minimum"], 72)

    def test_authorization_cannot_be_enabled_with_unresolved_baseline(self):
        plan = json.loads(validator.PLAN_PATH.read_text(encoding="utf-8"))
        plan["execution_authorized"] = True
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "plan.json"
            path.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            rebound = validator._source_sha256(path)
            with mock.patch.object(validator, "EXPECTED_PLAN_SHA256", rebound):
                with self.assertRaisesRegex(
                    validator.Bench2PlanError,
                    "must not authorize execution",
                ):
                    validator.validate_plan(path)

    def test_unreviewed_hermes_baseline_cannot_be_embedded(self):
        plan = json.loads(validator.PLAN_PATH.read_text(encoding="utf-8"))
        plan["baseline"]["status"] = "resolved"
        plan["baseline"]["binding"]["hermes_commit"] = "0" * 40
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "plan.json"
            path.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            rebound = validator._source_sha256(path)
            with mock.patch.object(validator, "EXPECTED_PLAN_SHA256", rebound):
                with self.assertRaisesRegex(
                    validator.Bench2PlanError,
                    "baseline must remain unresolved",
                ):
                    validator.validate_plan(path)

    def test_plan_has_no_execution_surface(self):
        validator.validate_plan()
        forbidden = (
            ROOT / ".github" / "workflows" / "local-bench2-hermes-orchestrator.yml",
            ROOT / "config" / "bench2-hermes-orchestrator-oneshot.json",
            ROOT / "scripts" / "run_bench2_hermes_campaign.py",
        )
        for path in forbidden:
            self.assertFalse(path.exists(), msg=str(path))

    def test_document_matches_plan_and_execution_boundary(self):
        plan = validator.validate_plan()
        document = DOC_PATH.read_text(encoding="utf-8")
        self.assertIn(validator.EXPECTED_PLAN_SHA256, document)
        self.assertIn("execution not authorized", document.lower())
        for stage in validator.EXPECTED_STAGES:
            self.assertIn(stage, document)
        self.assertIn(plan["candidates"][5]["candidate_id"], document)


if __name__ == "__main__":
    unittest.main()
