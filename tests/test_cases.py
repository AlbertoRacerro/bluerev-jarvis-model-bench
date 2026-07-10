from __future__ import annotations

import copy
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
            "inputs": {"supplied_result": "stable-result"},
            "expected": {"final": "stable-result"},
            "allowed_actions": ["return_supplied_result", "stop"],
            "forbidden_actions": [
                "call_tool",
                "call_external_provider",
                "modify_jarvisos",
                "promote_learning",
                "write_external_state",
            ],
            "success_assertions": ["reused_supplied_result"],
            "negative_assertions": [
                "no_external_provider_calls",
                "no_unnecessary_tool_calls",
            ],
            "limits": {
                "max_model_calls": 1,
                "max_tool_calls": 0,
                "max_retries": 0,
            },
            "required_artifacts": [
                "raw_output",
                "extracted_output",
                "trace",
                "validator_result",
                "environment_fingerprint",
            ],
        }

    def assert_rejected(self, case: object, message: str) -> None:
        with self.assertRaisesRegex(ContractError, message):
            validate_case(case)  # type: ignore[arg-type]

    def test_accepts_valid_case(self) -> None:
        validate_case(self.valid_case())

    def test_rejects_non_object_case(self) -> None:
        self.assert_rejected([], "case must be an object")

    def test_rejects_missing_field(self) -> None:
        case = self.valid_case()
        del case["negative_assertions"]
        self.assert_rejected(case, "missing fields: negative_assertions")

    def test_rejects_extra_field(self) -> None:
        case = self.valid_case()
        case["comment"] = "silently ignored metadata"
        self.assert_rejected(case, "unsupported fields: comment")

    def test_rejects_non_string_top_level_field_name(self) -> None:
        case = self.valid_case()
        case[7] = "invalid JSON object key"  # type: ignore[index]
        self.assert_rejected(case, "case must use string field names")

    def test_rejects_non_string_capability_without_type_error(self) -> None:
        case = self.valid_case()
        case["capability"] = []
        self.assert_rejected(case, "unsupported capability")

    def test_rejects_unknown_capability(self) -> None:
        case = self.valid_case()
        case["capability"] = "HO-MAGIC"
        self.assert_rejected(case, "unsupported capability")

    def test_rejects_case_id_not_matching_capability(self) -> None:
        case = self.valid_case()
        case["case_id"] = "ho-plan-reuse-001"
        self.assert_rejected(case, "must start with 'ho-stop-'")

    def test_rejects_tuple_instead_of_json_array(self) -> None:
        case = self.valid_case()
        case["allowed_actions"] = ("stop",)
        self.assert_rejected(case, "allowed_actions must be an array")

    def test_rejects_duplicate_action(self) -> None:
        case = self.valid_case()
        case["allowed_actions"] = ["stop", "stop"]
        self.assert_rejected(case, "allowed_actions must not contain duplicates")

    def test_rejects_unknown_action(self) -> None:
        case = self.valid_case()
        case["allowed_actions"] = ["invent_action"]
        self.assert_rejected(case, "unsupported identifier")

    def test_rejects_action_overlap(self) -> None:
        case = self.valid_case()
        case["allowed_actions"] = ["stop", "call_tool"]
        self.assert_rejected(case, "overlap: call_tool")

    def test_rejects_external_provider_as_allowed_action(self) -> None:
        case = self.valid_case()
        case["allowed_actions"] = ["stop", "call_external_provider"]
        case["forbidden_actions"] = [
            "call_tool",
            "modify_jarvisos",
            "promote_learning",
            "write_external_state",
        ]
        self.assert_rejected(case, "violates local-only boundaries")

    def test_rejects_missing_global_forbidden_action(self) -> None:
        case = self.valid_case()
        forbidden = list(case["forbidden_actions"])
        forbidden.remove("modify_jarvisos")
        case["forbidden_actions"] = forbidden
        self.assert_rejected(case, "missing global boundaries: modify_jarvisos")

    def test_rejects_arbitrary_success_assertion(self) -> None:
        case = self.valid_case()
        case["success_assertions"] = ["looks_good_to_model"]
        self.assert_rejected(case, "unsupported identifier")

    def test_rejects_arbitrary_negative_assertion(self) -> None:
        case = self.valid_case()
        case["negative_assertions"] = ["probably_safe"]
        self.assert_rejected(case, "unsupported identifier")

    def test_rejects_duplicate_assertion(self) -> None:
        case = self.valid_case()
        case["success_assertions"] = [
            "reused_supplied_result",
            "reused_supplied_result",
        ]
        self.assert_rejected(case, "success_assertions must not contain duplicates")

    def test_rejects_extra_limit(self) -> None:
        case = self.valid_case()
        limits = copy.deepcopy(case["limits"])
        assert isinstance(limits, dict)
        limits["max_parallelism"] = 1
        case["limits"] = limits
        self.assert_rejected(case, "limits has unsupported fields: max_parallelism")

    def test_rejects_boolean_limit(self) -> None:
        case = self.valid_case()
        limits = copy.deepcopy(case["limits"])
        assert isinstance(limits, dict)
        limits["max_model_calls"] = True
        case["limits"] = limits
        self.assert_rejected(case, "max_model_calls must be an integer")

    def test_rejects_negative_limit(self) -> None:
        case = self.valid_case()
        limits = copy.deepcopy(case["limits"])
        assert isinstance(limits, dict)
        limits["max_retries"] = -1
        case["limits"] = limits
        self.assert_rejected(case, "max_retries must be an integer")

    def test_rejects_action_limit_contradiction(self) -> None:
        case = self.valid_case()
        case["allowed_actions"] = ["return_final", "call_tool"]
        case["forbidden_actions"] = [
            "call_external_provider",
            "modify_jarvisos",
            "promote_learning",
            "write_external_state",
        ]
        self.assert_rejected(case, "call_tool is allowed but max_tool_calls is zero")

    def test_rejects_non_json_input(self) -> None:
        case = self.valid_case()
        case["inputs"] = {"bad": {"set-value"}}
        self.assert_rejected(case, "contains a non-JSON value: set")

    def test_rejects_non_finite_expected_number(self) -> None:
        case = self.valid_case()
        case["expected"] = {"score": float("nan")}
        self.assert_rejected(case, "contains a non-finite number")

    def test_rejects_missing_required_artifact(self) -> None:
        case = self.valid_case()
        artifacts = list(case["required_artifacts"])
        artifacts.remove("trace")
        case["required_artifacts"] = artifacts
        self.assert_rejected(case, "missing values: trace")

    def test_rejects_duplicate_required_artifact(self) -> None:
        case = self.valid_case()
        artifacts = list(case["required_artifacts"])
        artifacts.append("trace")
        case["required_artifacts"] = artifacts
        self.assert_rejected(case, "required_artifacts must not contain duplicates")

    def test_rejects_non_string_required_artifact_without_type_error(self) -> None:
        case = self.valid_case()
        artifacts = list(case["required_artifacts"])
        artifacts[0] = []
        case["required_artifacts"] = artifacts
        self.assert_rejected(case, "must contain string identifiers")


if __name__ == "__main__":
    unittest.main()
