from __future__ import annotations

import json
import os
import unittest
from unittest import mock

from scripts import run_bench2r_hermes_s1 as runner
from scripts import validate_bench2r_hermes_s1 as execution


def _usage_checks() -> list[dict[str, object]]:
    return [
        {"check": name, "passed": True, "detail": ""}
        for name in (
            "usage_file_valid",
            "usage_provider_custom",
            "usage_model_exact",
            "usage_api_calls_nonnegative",
            "usage_api_calls_match_worker",
            "usage_input_tokens_nonnegative",
            "usage_output_tokens_nonnegative",
            "usage_total_tokens_nonnegative",
        )
    ]


def _worker_result(*, skill: bool, api_calls: int) -> dict[str, object]:
    return {
        "skill_expanded": skill,
        "messages": [
            {
                "role": "system",
                "content": "available tools: bench_lookup and bench_distractor",
            }
        ],
        "api_calls": api_calls,
        "completed": True,
        "failed": False,
        "failure": None,
        "partial": False,
        "turn_exit_reason": "text_response(content)",
    }


def _alias() -> dict[str, object]:
    return {
        "parameter_attestation": {
            "passed": True,
            "mismatches": {},
        }
    }


class Bench2RHermesS1Tests(unittest.TestCase):
    def test_disabled_s1_contract_is_valid_but_not_authorized(self):
        plan, marker, candidates, cases = execution.validate_execution(
            require_enabled=False
        )
        self.assertFalse(marker["enabled"])
        self.assertEqual(len(candidates), 8)
        self.assertEqual(len(cases), 2)
        self.assertEqual(plan["counts"]["total_runs"], 32)

    def test_four_batches_cover_all_candidates_once(self):
        _, _, candidates, _ = execution.validate_execution()
        seen: list[str] = []
        for batch_index in range(4):
            selected, selection = execution.select_batch(candidates, batch_index)
            self.assertEqual(selection["expected_runs"], 8)
            seen.extend(item["candidate_id"] for item in selected)
        self.assertEqual(seen, [item["candidate_id"] for item in candidates])

    def test_batch_index_is_explicit_and_bounded(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(runner.HermesS1Error):
                runner.batch_index_from_environment()
        with mock.patch.dict(os.environ, {runner.BATCH_INDEX_ENV: "3"}, clear=True):
            self.assertEqual(runner.batch_index_from_environment(), 3)

    def test_parameter_attestation_accepts_exact_profile(self):
        profile = {
            "max_output_tokens": 4096,
            "sampling": {
                "temperature": 0.6,
                "top_p": 0.95,
                "top_k": 20,
                "repeat_penalty": 1.05,
            },
        }
        observed = "\n".join(
            [
                "num_ctx 65536",
                "num_predict 4096",
                "seed 42",
                "temperature 0.6",
                "top_p 0.95",
                "top_k 20",
                "repeat_penalty 1.05",
            ]
        )
        result = runner._attest_alias_parameters(
            profile,
            seed=42,
            parameter_text=observed,
        )
        self.assertTrue(result["passed"])
        self.assertEqual(result["mismatches"], {})

    def test_stop_budget_overrun_is_semantic_not_infrastructure(self):
        case = {
            "case_id": "stop",
            "capability": "HO-STOP",
            "expected": {
                "actions": ["return_supplied_result", "stop"],
                "final": "stable-result",
            },
            "limits": {"max_model_calls": 1},
        }
        result = runner._semantic_validator(
            case=case,
            arm="profile_only",
            process={"returncode": 0, "timed_out": False},
            output={
                "actions": ["return_supplied_result", "stop"],
                "final": "stable-result",
            },
            output_error=None,
            tool_records=[],
            trace_error=None,
            worker_result=_worker_result(skill=False, api_calls=2),
            worker_error=None,
            usage={"api_calls": 2},
            usage_checks=_usage_checks(),
            runtime_model={"context_length": 65536},
            residency_class="full_vram",
            residency_ratio=1.0,
            trajectory_files=["trajectory_samples.jsonl"],
            tool_registry_observed=True,
            alias=_alias(),
        )
        self.assertTrue(result["infrastructure_valid"])
        self.assertFalse(result["semantic_pass"])
        failed = {
            item["check"]
            for item in result["checks"]
            if item["passed"] is False
        }
        self.assertEqual(failed, {"model_call_budget_within_limit"})

    def test_profile_plus_skill_arm_requires_confirmed_expansion(self):
        case = {
            "case_id": "stop",
            "capability": "HO-STOP",
            "expected": {
                "actions": ["return_supplied_result", "stop"],
                "final": "stable-result",
            },
            "limits": {"max_model_calls": 1},
        }
        result = runner._semantic_validator(
            case=case,
            arm="profile_plus_skill",
            process={"returncode": 0, "timed_out": False},
            output={
                "actions": ["return_supplied_result", "stop"],
                "final": "stable-result",
            },
            output_error=None,
            tool_records=[],
            trace_error=None,
            worker_result=_worker_result(skill=True, api_calls=1),
            worker_error=None,
            usage={"api_calls": 1},
            usage_checks=_usage_checks(),
            runtime_model={"context_length": 65536},
            residency_class="full_vram",
            residency_ratio=1.0,
            trajectory_files=["trajectory_samples.jsonl"],
            tool_registry_observed=True,
            alias=_alias(),
        )
        self.assertTrue(result["passed"])

    def test_worker_uses_pinned_hermes_skill_expansion(self):
        source = execution.WORKER_PATH.read_text(encoding="utf-8")
        self.assertIn("build_skill_invocation_message", source)
        self.assertIn('"/bounded-tool-orchestration"', source)
        self.assertIn('toolsets=["bench2_fixture"]', source)
        self.assertIn("turn_exit_reason", source)
        self.assertIn("messages", source)

    def test_runtime_workflow_is_serial_and_activation_guarded(self):
        text = execution.RUNTIME_WORKFLOW_PATH.read_text(encoding="utf-8")
        self.assertIn("batch: [0, 1, 2, 3]", text)
        self.assertIn("max-parallel: 1", text)
        self.assertIn("runs-on: [self-hosted, Windows, X64, bluerev-bench]", text)
        self.assertIn(
            "startsWith(github.event.head_commit.message, "
            "'Activate BENCH-2R Hermes S1 preflight')",
            text,
        )
        self.assertNotIn("workflow_dispatch", text)

    def test_s1_marker_is_disabled(self):
        marker = json.loads(execution.MARKER_PATH.read_text(encoding="utf-8"))
        self.assertFalse(marker["enabled"])


if __name__ == "__main__":
    unittest.main()
