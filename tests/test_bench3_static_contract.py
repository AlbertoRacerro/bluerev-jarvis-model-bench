from __future__ import annotations

import unittest

from scripts import validate_bench3_hermes_memory_routing_design as core


class Bench3StaticContractTests(unittest.TestCase):
    def test_complete_static_contract_validates(self):
        payload = core.validate()
        self.assertEqual(payload["status"], "valid_static_design")
        self.assertFalse(payload["execution_implemented"])

    def test_conflict_precedence_is_exact(self):
        plan = core._load(core.PLAN_PATH)
        self.assertEqual(
            plan["memory_architecture"]["conflict_precedence"],
            [
                "current_user_statement",
                "verified_current_project_state",
                "approved_persistent_memory",
                "session_history",
            ],
        )


if __name__ == "__main__":
    unittest.main()
