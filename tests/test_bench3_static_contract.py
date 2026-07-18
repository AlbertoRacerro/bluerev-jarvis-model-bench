from __future__ import annotations

import unittest

from scripts import bench3_contract_constants as constants
from scripts import validate_bench3_hermes_memory_routing_design as base
from scripts import validate_bench3_static_contract as contract


class Bench3StaticContractTests(unittest.TestCase):
    def test_complete_static_contract_stamps_authoritative_evidence(self):
        payload = contract.validate()
        self.assertEqual(payload["schema_version"], "bench3.static-contract-validation.v1")
        self.assertEqual(payload["status"], "valid_static_design")
        self.assertFalse(payload["execution_implemented"])
        self.assertEqual(payload["case_contracts_blob_sha"], constants.CASE_CONTRACT_BLOB_SHA)
        for key in (
            "complete_contract_validated",
            "acceptance_gates_validated",
            "conflict_precedence_validated",
            "runtime_namespace_guard_validated",
            "candidate_fixture_bindings_validated",
            "case_contracts_validated",
            "shell_runtime_guard_validated",
            "action_namespace_guard_validated",
        ):
            self.assertIs(payload[key], True)

    def test_conflict_precedence_is_exact(self):
        plan = base._load(base.PLAN_PATH)
        self.assertEqual(
            plan["memory_architecture"]["conflict_precedence"],
            constants.CONFLICT_PRECEDENCE,
        )


if __name__ == "__main__":
    unittest.main()
