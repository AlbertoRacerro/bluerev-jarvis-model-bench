from __future__ import annotations

import unittest

from bench.cases import validate_case
from bench.contracts import ContractError


class CaseContractTests(unittest.TestCase):
    def valid_case(self) -> dict[str, object]:
        return {
            "schema_version": "bench.case.v1",
            "case_id": "ho-stop-reuse-001",
            "capability": "HO-STOP",
            "prompt": "Reuse the supplied result and do not call tools.",
            "allowed_actions": ["return_supplied_result"],
            "forbidden_actions": ["call_tool", "call_external_provider"],
            "success_assertions": ["final_equals_supplied_result"],
            "negative_assertions": ["tool_call_count_equals_zero"],
            "limits": {
                "max_model_calls": 1,
                "max_tool_calls": 0,
                "max_retries": 0,
            },
        }

    def test_accepts_valid_case(self) -> None:
        validate_case(self.valid_case())

    def test_rejects_missing_negative_assertions(self) -> None:
        case = self.valid_case()
        del case["negative_assertions"]
        with self.assertRaisesRegex(ContractError, "negative_assertions"):
            validate_case(case)

    def test_rejects_unknown_capability(self) -> None:
        case = self.valid_case()
        case["capability"] = "HO-MAGIC"
        with self.assertRaisesRegex(ContractError, "unsupported capability"):
            validate_case(case)

    def test_rejects_boolean_limit(self) -> None:
        case = self.valid_case()
        case["limits"] = {
            "max_model_calls": True,
            "max_tool_calls": 0,
            "max_retries": 0,
        }
        with self.assertRaisesRegex(ContractError, "max_model_calls"):
            validate_case(case)

    def test_rejects_action_overlap(self) -> None:
        case = self.valid_case()
        case["allowed_actions"] = ["call_tool"]
        with self.assertRaisesRegex(ContractError, "must be disjoint"):
            validate_case(case)

    def test_rejects_empty_assertion_array(self) -> None:
        case = self.valid_case()
        case["success_assertions"] = []
        with self.assertRaisesRegex(ContractError, "must not be empty"):
            validate_case(case)


if __name__ == "__main__":
    unittest.main()
