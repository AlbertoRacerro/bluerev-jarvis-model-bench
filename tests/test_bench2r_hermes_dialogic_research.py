from __future__ import annotations

import copy
import unittest
from pathlib import Path
from unittest import mock

from scripts import validate_bench2r_hermes_dialogic_research as validator


class HermesDialogicResearchTests(unittest.TestCase):
    def _patch_recommendations(self, recommendations):
        original = validator._load

        def load(path: Path):
            if path == validator.RECOMMENDATIONS_PATH:
                return copy.deepcopy(recommendations)
            return original(path)

        return mock.patch.object(validator, "_load", side_effect=load)

    def test_research_recommendations_validate(self):
        payload = validator.validate()
        self.assertEqual(payload["status"], "valid_static_research_recommendations")
        self.assertEqual(payload["primary_research_sources"], 4)
        self.assertEqual(payload["community_risk_signals"], 6)
        self.assertFalse(payload["runtime_implemented"])
        self.assertEqual(payload["production_status"], "not_promoted")

    def test_protocol_cannot_become_primary(self):
        recommendations = validator._load(validator.RECOMMENDATIONS_PATH)
        recommendations["scope"]["protocol_conformance_role"] = "primary_objective"
        with self._patch_recommendations(recommendations):
            with self.assertRaisesRegex(validator.HermesDialogicResearchError, "protocol gate"):
                validator.validate()

    def test_issue_cannot_be_promoted_to_authoritative_evidence(self):
        recommendations = validator._load(validator.RECOMMENDATIONS_PATH)
        recommendations["hermes_community_risk_signals"][0]["status"] = "authoritative_runtime_evidence"
        with self._patch_recommendations(recommendations):
            with self.assertRaisesRegex(validator.HermesDialogicResearchError, "promoted"):
                validator.validate()

    def test_monolithic_context_rewrite_is_rejected(self):
        recommendations = validator._load(validator.RECOMMENDATIONS_PATH)
        recommendations["required_design_invariants"]["context_playbook"]["monolithic_summary_rewrite_forbidden"] = False
        with self._patch_recommendations(recommendations):
            with self.assertRaisesRegex(validator.HermesDialogicResearchError, "monolithic"):
                validator.validate()

    def test_whole_session_loading_is_rejected(self):
        recommendations = validator._load(validator.RECOMMENDATIONS_PATH)
        recommendations["required_design_invariants"]["historical_retrieval"]["whole_session_load_by_default"] = True
        with self._patch_recommendations(recommendations):
            with self.assertRaisesRegex(validator.HermesDialogicResearchError, "whole long sessions"):
                validator.validate()

    def test_route_without_similar_case_retrieval_is_rejected(self):
        recommendations = validator._load(validator.RECOMMENDATIONS_PATH)
        recommendations["required_design_invariants"]["route_experience_memory"]["similar_case_retrieval_required"] = False
        with self._patch_recommendations(recommendations):
            with self.assertRaisesRegex(validator.HermesDialogicResearchError, "similar prior cases"):
                validator.validate()

    def test_route_without_regret_is_rejected(self):
        recommendations = validator._load(validator.RECOMMENDATIONS_PATH)
        recommendations["required_design_invariants"]["route_experience_memory"]["route_regret_recorded"] = False
        with self._patch_recommendations(recommendations):
            with self.assertRaisesRegex(validator.HermesDialogicResearchError, "route regret"):
                validator.validate()

    def test_routine_cannot_assume_interactive_memory(self):
        recommendations = validator._load(validator.RECOMMENDATIONS_PATH)
        recommendations["required_design_invariants"]["routine_context_capsule"]["memory_availability_assumed"] = True
        with self._patch_recommendations(recommendations):
            with self.assertRaisesRegex(validator.HermesDialogicResearchError, "interactive memory"):
                validator.validate()

    def test_delegation_cannot_be_background_queue(self):
        recommendations = validator._load(validator.RECOMMENDATIONS_PATH)
        recommendations["required_design_invariants"]["durability"]["delegate_task_as_background_queue_allowed"] = True
        with self._patch_recommendations(recommendations):
            with self.assertRaisesRegex(validator.HermesDialogicResearchError, "durable queue"):
                validator.validate()

    def test_isolation_cannot_be_relaxed(self):
        recommendations = validator._load(validator.RECOMMENDATIONS_PATH)
        recommendations["required_design_invariants"]["experiment_isolation"]["isolated_state_db"] = False
        with self._patch_recommendations(recommendations):
            with self.assertRaisesRegex(validator.HermesDialogicResearchError, "isolation"):
                validator.validate()


if __name__ == "__main__":
    unittest.main()
