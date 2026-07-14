from __future__ import annotations

import unittest

from scripts.bench2r_deterministic_finalizer import finalize


TOOL_CASE = {
    "inputs": {
        "lookup_key": "omega-13",
        "tool_contract": {
            "name": "vault_fetch",
            "arguments": {"key": "omega-13"},
            "exact_calls": 1,
        },
        "response_contract": {
            "fields": ["final", "actions"],
            "actions": ["call_tool", "return_final", "stop"],
            "value_path": ["payload", "answer"],
        },
    },
    "limits": {"max_model_calls": 2, "max_tool_calls": 1},
}

STOP_CASE = {
    "inputs": {
        "supplied_result": "verified-payload-42",
        "response_contract": {
            "output_field": "final",
            "required_actions": ["return_supplied_result", "stop"],
        },
    },
    "limits": {"max_model_calls": 1, "max_tool_calls": 0},
}


def worker(api_calls: int = 1) -> dict[str, object]:
    return {
        "api_calls": api_calls,
        "completed": True,
        "failed": False,
        "partial": False,
        "failure": None,
    }


def record(name: str = "vault_fetch", arguments=None, answer: str = "DELTA-58"):
    return {
        "tool_name": name,
        "arguments": arguments if arguments is not None else {"key": "omega-13"},
        "result": {"ok": True, "payload": {"answer": answer}},
    }


class Bench2RDeterministicFinalizerTests(unittest.TestCase):
    def test_tool_value_and_ledger_are_bound_without_expected_answer(self):
        result = finalize(
            case=TOOL_CASE,
            raw_output={"final": ["wrong-shape"], "actions": ["call_tool"]},
            tool_records=[record()],
            worker_result=worker(api_calls=2),
        )
        self.assertTrue(result.accepted)
        self.assertEqual(
            result.normalized_output,
            {
                "final": "DELTA-58",
                "actions": ["call_tool", "return_final", "stop"],
            },
        )
        self.assertIn("final_value_bound_to_verified_tool_result", result.corrections)

    def test_supplied_result_is_preserved_with_exact_ledger(self):
        result = finalize(
            case=STOP_CASE,
            raw_output={"final": "verified-payload-42", "required_actions": ["return_supplied_result", "stop"]},
            tool_records=[],
            worker_result=worker(),
        )
        self.assertTrue(result.accepted)
        self.assertEqual(
            result.normalized_output,
            {
                "final": "verified-payload-42",
                "actions": ["return_supplied_result", "stop"],
            },
        )

    def test_wrong_tool_name_is_not_hidden(self):
        result = finalize(
            case=TOOL_CASE,
            raw_output={},
            tool_records=[record(name="noise_probe")],
            worker_result=worker(api_calls=2),
        )
        self.assertFalse(result.accepted)
        self.assertIn("tool_name_mismatch", result.rejection_reasons)

    def test_wrong_arguments_are_not_hidden(self):
        result = finalize(
            case=TOOL_CASE,
            raw_output={},
            tool_records=[record(arguments={"key": "wrong"})],
            worker_result=worker(api_calls=2),
        )
        self.assertFalse(result.accepted)
        self.assertIn("tool_arguments_mismatch", result.rejection_reasons)

    def test_budget_overrun_is_not_hidden(self):
        result = finalize(
            case=TOOL_CASE,
            raw_output={},
            tool_records=[record()],
            worker_result=worker(api_calls=3),
        )
        self.assertFalse(result.accepted)
        self.assertIn("model_call_budget_exceeded", result.rejection_reasons)

    def test_unexpected_tool_on_stop_case_is_not_hidden(self):
        result = finalize(
            case=STOP_CASE,
            raw_output={},
            tool_records=[record()],
            worker_result=worker(),
        )
        self.assertFalse(result.accepted)
        self.assertIn("unexpected_tool_call", result.rejection_reasons)

    def test_worker_failure_is_not_hidden(self):
        failed = worker()
        failed["failed"] = True
        result = finalize(
            case=STOP_CASE,
            raw_output={},
            tool_records=[],
            worker_result=failed,
        )
        self.assertFalse(result.accepted)
        self.assertIn("worker_failed", result.rejection_reasons)


if __name__ == "__main__":
    unittest.main()
