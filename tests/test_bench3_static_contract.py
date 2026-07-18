from __future__ import annotations

import copy
import unittest
from unittest import mock

from scripts import validate_bench3_hermes_memory_routing_design as base
from scripts import validate_bench3_static_contract as contract


class Bench3StaticContractTests(unittest.TestCase):
    def test_complete_static_contract_validates(self):
        payload = contract.validate()
        self.assertEqual(payload["status"], "valid_static_design")
        self.assertFalse(payload["execution_implemented"])

    def test_memory_conflict_precedence_drift_is_rejected(self):
        plan = base._load(base.PLAN_PATH)
        drifted = copy.deepcopy(plan)
        drifted["memory_architecture"]["conflict_precedence"] = [
            "approved_persistent_memory",
            "current_user_statement",
            "verified_current_project_state",
            "session_history",
        ]

        original_load = base._load

        def load(path):
            if path == base.PLAN_PATH:
                return copy.deepcopy(drifted)
            return original_load(path)

        with mock.patch.object(base, "_load", side_effect=load):
            with self.assertRaisesRegex(
                base.MemoryRoutingDesignError,
                "memory conflict precedence",
            ):
                contract.validate()


if __name__ == "__main__":
    unittest.main()
