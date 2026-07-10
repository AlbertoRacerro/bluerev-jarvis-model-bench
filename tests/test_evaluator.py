from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from bench.contracts import ContractError
from bench.evaluator import (
    build_candidate_payload,
    evaluate_submission,
    load_case_directory,
    validate_trace,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "fixtures" / "bench-1"


def trace(case_id: str, *actions: str) -> dict[str, object]:
    return {
        "schema_version": "bench.trace.v1",
        "case_id": case_id,
        "events": [
            {"index": index, "action_id": action, "details": {}}
            for index, action in enumerate(actions, start=1)
        ],
    }


class FixtureExecutionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.cases = load_case_directory(FIXTURES)

    def test_fixture_inventory_is_exact_and_unique(self) -> None:
        self.assertEqual(
            set(self.cases),
            {"ho-route-local-coder-001", "ho-stop-reuse-001"},
        )

    def test_candidate_payload_hides_evaluator_oracle(self) -> None:
        payload = build_candidate_payload(self.cases["ho-route-local-coder-001"])
        self.assertEqual(payload["schema_version"], "bench.candidate-task.v1")
        for evaluator_only in (
            "expected",
            "success_assertions",
            "negative_assertions",
            "required_artifacts",
        ):
            self.assertNotIn(evaluator_only, payload)

    def test_candidate_payload_is_detached_from_case(self) -> None:
        case = self.cases["ho-route-local-coder-001"]
        payload = build_candidate_payload(case)
        payload["inputs"]["eligible_routes"].append("tampered")  # type: ignore[index]
        self.assertNotIn("tampered", case["inputs"]["eligible_routes"])

    def test_stop_fixture_passes_canonical_submission(self) -> None:
        case = self.cases["ho-stop-reuse-001"]
        result = evaluate_submission(
            case,
            {"final": "stable-result"},
            trace(case["case_id"], "return_supplied_result", "stop"),
        )
        self.assertTrue(result["passed"])
        self.assertEqual(result["counts"], {"model_calls": 0, "tool_calls": 0, "retries": 0})

    def test_stop_fixture_fails_tool_call_even_with_correct_final(self) -> None:
        case = self.cases["ho-stop-reuse-001"]
        result = evaluate_submission(
            case,
            {"final": "stable-result"},
            trace(case["case_id"], "call_tool", "return_supplied_result", "stop"),
        )
        self.assertFalse(result["passed"])
        failed = {item["assertion_id"] for item in result["checks"] if not item["passed"]}
        self.assertIn("trace_actions_allowed", failed)
        self.assertIn("trace_limits_respected", failed)
        self.assertIn("no_forbidden_actions", failed)
        self.assertIn("no_unnecessary_tool_calls", failed)

    def test_stop_fixture_rejects_extra_output_fields(self) -> None:
        case = self.cases["ho-stop-reuse-001"]
        result = evaluate_submission(
            case,
            {"final": "stable-result", "commentary": "extra"},
            trace(case["case_id"], "return_supplied_result", "stop"),
        )
        self.assertFalse(result["passed"])
        failed = {item["assertion_id"] for item in result["checks"] if not item["passed"]}
        self.assertIn("reused_supplied_result", failed)

    def test_route_fixture_passes_canonical_submission(self) -> None:
        case = self.cases["ho-route-local-coder-001"]
        result = evaluate_submission(
            case,
            {"selected_route": "local_coder"},
            trace(case["case_id"], "route_local", "return_final", "stop"),
        )
        self.assertTrue(result["passed"])

    def test_route_fixture_fails_wrong_route(self) -> None:
        case = self.cases["ho-route-local-coder-001"]
        result = evaluate_submission(
            case,
            {"selected_route": "local_fast"},
            trace(case["case_id"], "route_local", "return_final", "stop"),
        )
        self.assertFalse(result["passed"])
        failed = {item["assertion_id"] for item in result["checks"] if not item["passed"]}
        self.assertEqual(failed, {"selected_route_equals_expected"})

    def test_route_fixture_rejects_duplicate_allowed_actions(self) -> None:
        case = self.cases["ho-route-local-coder-001"]
        result = evaluate_submission(
            case,
            {"selected_route": "local_coder"},
            trace(case["case_id"], "route_local", "route_local", "return_final", "stop"),
        )
        self.assertFalse(result["passed"])
        failed = {item["assertion_id"] for item in result["checks"] if not item["passed"]}
        self.assertEqual(failed, {"selected_route_equals_expected"})

    def test_external_provider_action_is_a_semantic_failure(self) -> None:
        case = self.cases["ho-route-local-coder-001"]
        result = evaluate_submission(
            case,
            {"selected_route": "local_coder"},
            trace(case["case_id"], "call_external_provider", "route_local", "stop"),
        )
        self.assertFalse(result["passed"])
        failed = {item["assertion_id"] for item in result["checks"] if not item["passed"]}
        self.assertIn("no_external_provider_calls", failed)
        self.assertIn("no_forbidden_actions", failed)

    def test_trace_rejects_candidate_supplied_aggregate_counts(self) -> None:
        value = trace("ho-stop-reuse-001", "stop")
        value["model_calls"] = 0
        with self.assertRaisesRegex(ContractError, "unsupported fields: model_calls"):
            validate_trace(value)

    def test_trace_rejects_non_sequential_indexes(self) -> None:
        value = trace("ho-stop-reuse-001", "stop")
        value["events"][0]["index"] = 2  # type: ignore[index]
        with self.assertRaisesRegex(ContractError, "index must equal 1"):
            validate_trace(value)

    def test_trace_case_id_must_match_case(self) -> None:
        case = self.cases["ho-stop-reuse-001"]
        with self.assertRaisesRegex(ContractError, "does not match"):
            evaluate_submission(case, {"final": "stable-result"}, trace("wrong-case", "stop"))

    def test_unimplemented_assertion_never_silently_passes(self) -> None:
        case = copy.deepcopy(self.cases["ho-stop-reuse-001"])
        case["success_assertions"] = ["final_schema_valid"]
        with self.assertRaisesRegex(ContractError, "not implemented"):
            evaluate_submission(
                case,
                {"final": "stable-result"},
                trace(case["case_id"], "return_supplied_result", "stop"),
            )

    def test_duplicate_case_id_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            case = self.cases["ho-stop-reuse-001"]
            for name in ("a.json", "b.json"):
                (path / name).write_text(json.dumps(case), encoding="utf-8")
            with self.assertRaisesRegex(ContractError, "duplicate case_id"):
                load_case_directory(path)

    def test_empty_trace_is_rejected(self) -> None:
        with self.assertRaisesRegex(ContractError, "must not be empty"):
            validate_trace(trace("ho-stop-reuse-001"))


if __name__ == "__main__":
    unittest.main()
