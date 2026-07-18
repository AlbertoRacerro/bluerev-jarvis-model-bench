from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts import validate_bench2r_hermes_dialogic_orchestrator_design as validator


class HermesDialogicOrchestratorDesignTests(unittest.TestCase):
    def _patch(self, *, plan=None, skill=None, report=None):
        original_load = validator._load
        original_read = validator._read

        def load(path: Path):
            if path == validator.PLAN_PATH and plan is not None:
                return copy.deepcopy(plan)
            return original_load(path)

        def read(path: Path):
            if path == validator.SKILL_PATH and skill is not None:
                return skill
            if path == validator.REPORT_PATH and report is not None:
                return report
            return original_read(path)

        return mock.patch.multiple(
            validator,
            _load=mock.Mock(side_effect=load),
            _read=mock.Mock(side_effect=read),
        )

    def test_static_design_validates(self):
        payload = validator.validate()
        self.assertEqual(payload["status"], "valid_static_design")
        self.assertEqual(payload["curriculum_cases"], 9)
        self.assertEqual(payload["native_surfaces"], 10)
        self.assertEqual(payload["route_targets"], 6)
        self.assertFalse(payload["runtime_implemented"])
        self.assertEqual(payload["production_status"], "not_promoted")

    def test_byte_exact_normal_dialogue_is_rejected(self):
        plan = validator._load(validator.PLAN_PATH)
        plan["decision"]["byte_exact_output_during_normal_dialogue"] = True
        with self._patch(plan=plan):
            with self.assertRaisesRegex(validator.HermesDialogicDesignError, "byte-exact"):
                validator.validate()

    def test_missing_session_search_is_rejected(self):
        plan = validator._load(validator.PLAN_PATH)
        del plan["native_surfaces"]["session_search"]
        with self._patch(plan=plan):
            with self.assertRaisesRegex(validator.HermesDialogicDesignError, "session_search"):
                validator.validate()

    def test_exact_json_during_episode_is_rejected(self):
        plan = validator._load(validator.PLAN_PATH)
        plan["episode_protocol"]["exact_json_intermediate_output_required"] = True
        with self._patch(plan=plan):
            with self.assertRaisesRegex(validator.HermesDialogicDesignError, "exact JSON"):
                validator.validate()

    def test_dialogic_routine_creation_cannot_be_disabled(self):
        plan = validator._load(validator.PLAN_PATH)
        plan["native_surfaces"]["cron_routines"]["allowed_after_dialogic_consent"] = False
        with self._patch(plan=plan):
            with self.assertRaisesRegex(validator.HermesDialogicDesignError, "routine creation"):
                validator.validate()

    def test_recursive_cron_is_rejected(self):
        plan = validator._load(validator.PLAN_PATH)
        plan["native_surfaces"]["cron_routines"]["recursive_creation_forbidden"] = False
        with self._patch(plan=plan):
            with self.assertRaisesRegex(validator.HermesDialogicDesignError, "recursive cron"):
                validator.validate()

    def test_routing_without_decision_log_is_rejected(self):
        plan = validator._load(validator.PLAN_PATH)
        plan["routing_policy"]["decision_log_required"] = False
        with self._patch(plan=plan):
            with self.assertRaisesRegex(validator.HermesDialogicDesignError, "decision log"):
                validator.validate()

    def test_incomplete_delegation_context_pack_is_rejected(self):
        plan = validator._load(validator.PLAN_PATH)
        plan["delegation_context_pack"]["required_fields"].remove("known_failures")
        with self._patch(plan=plan):
            with self.assertRaisesRegex(validator.HermesDialogicDesignError, "context pack fields"):
                validator.validate()

    def test_external_provider_is_rejected(self):
        plan = validator._load(validator.PLAN_PATH)
        plan["hard_boundaries"]["external_providers_allowed"] = True
        with self._patch(plan=plan):
            with self.assertRaisesRegex(validator.HermesDialogicDesignError, "external_providers_allowed"):
                validator.validate()

    def test_native_trajectory_replacement_is_rejected(self):
        plan = validator._load(validator.PLAN_PATH)
        plan["post_episode_artifact"]["must_not_replace_native_trajectory"] = False
        with self._patch(plan=plan):
            with self.assertRaisesRegex(validator.HermesDialogicDesignError, "replaces native trajectory"):
                validator.validate()

    def test_skill_content_drift_is_rejected(self):
        skill = validator._read(validator.SKILL_PATH) + "\n"
        with self._patch(skill=skill):
            with self.assertRaisesRegex(validator.HermesDialogicDesignError, "skill content drifted"):
                validator.validate()

    def test_runtime_workflow_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "runtime.yml"
            path.write_text("name: forbidden\n", encoding="utf-8")
            with mock.patch.object(validator, "FORBIDDEN_RUNTIME_WORKFLOW", path):
                with self.assertRaisesRegex(validator.HermesDialogicDesignError, "runtime workflow exists"):
                    validator.validate()

    def test_activation_marker_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "marker.json"
            path.write_text("{}\n", encoding="utf-8")
            with mock.patch.object(validator, "FORBIDDEN_MARKER", path):
                with self.assertRaisesRegex(validator.HermesDialogicDesignError, "activation marker exists"):
                    validator.validate()


if __name__ == "__main__":
    unittest.main()
