from __future__ import annotations

import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest import mock

from scripts import run_bench2r_hermes_s3a as runtime
from scripts import run_bench2r_hermes_s3a_safe as safe
from scripts import validate_bench2r_hermes_s3a_runtime as validator
from scripts.bench2r_deterministic_finalizer import finalize


class HermesS3ARuntimeTests(unittest.TestCase):
    def test_runtime_implementation_validates_with_workflow_absent(self):
        payload = validator.validate_implementation()
        self.assertEqual(payload["status"], "implementation_ready_workflow_absent")
        self.assertFalse(payload["execution_authorized"])
        self.assertFalse(payload["marker_enabled"])
        self.assertFalse(payload["runtime_workflow_present"])
        self.assertEqual(payload["total_runs"], 50)

    def test_five_seed_batches_are_exact(self):
        plan = validator._load(validator.RUNTIME_PLAN_PATH)
        observed = [validator.select_batch(plan, index)[0] for index in range(5)]
        self.assertEqual(observed, validator.EXPECTED_SEEDS)
        with self.assertRaises(validator.HermesS3ARuntimeValidationError):
            validator.select_batch(plan, 5)

    def test_model_prompt_excludes_evaluator_fields_and_held_out_tool_values(self):
        plan = validator._load(validator.RUNTIME_PLAN_PATH)
        for path in runtime.execution.design.CASE_PATHS[:2]:
            case = runtime._load_json(path)
            prompt, context = runtime._build_model_prompt(case, plan)
            self.assertNotIn('"expected"', prompt)
            self.assertNotIn('"outcome_class"', prompt)
            self.assertNotIn("KAPPA-73", prompt)
            self.assertNotIn("MU-62", prompt)
            self.assertFalse(context["present"])

    def test_long_context_generation_is_deterministic_and_pressure_is_visible(self):
        plan = validator._load(validator.RUNTIME_PLAN_PATH)
        case = runtime._load_json(runtime.execution.design.CASE_PATHS[2])
        prompt_a, fingerprint_a = runtime._build_model_prompt(case, plan)
        prompt_b, fingerprint_b = runtime._build_model_prompt(case, plan)
        self.assertEqual(prompt_a, prompt_b)
        self.assertEqual(fingerprint_a, fingerprint_b)
        self.assertTrue(fingerprint_a["present"])
        self.assertEqual(fingerprint_a["line_count"], 2400)
        self.assertEqual(fingerprint_a["injected_instruction_count"], 24)
        self.assertEqual(len(fingerprint_a["sha256"]), 64)
        self.assertIn("BEGIN UNTRUSTED REFERENCE MATERIAL", prompt_a)
        self.assertIn("untrusted-instruction-0097", prompt_a)
        self.assertGreater(len(prompt_a), 200_000)

    def test_strict_wire_checks_require_registry_redaction_and_no_proxy_error(self):
        tools = [
            {"type": "function", "function": {"name": name, "parameters": {}}}
            for name in sorted(runtime.TOOL_REGISTRY)
        ]
        record = {
            "path": "/v1/chat/completions",
            "proxy_error": None,
            "request": {
                "headers": {"Authorization": "<redacted>"},
                "json": {"model": "alias:1", "tools": tools},
            },
            "response": {"status": 200},
        }
        checks = safe._strict_wire_checks(
            [record],
            alias_name="alias:1",
            worker_result={"api_calls": 1},
        )
        self.assertTrue(checks["wire_upstream_loopback_only"])
        self.assertTrue(checks["wire_tool_registry_observed"])
        self.assertTrue(checks["wire_chat_count_matches_worker"])

        bad_error = json.loads(json.dumps(record))
        bad_error["proxy_error"] = "TimeoutError"
        self.assertFalse(
            safe._strict_wire_checks(
                [bad_error], alias_name="alias:1", worker_result={"api_calls": 1}
            )["wire_upstream_loopback_only"]
        )
        bad_auth = json.loads(json.dumps(record))
        bad_auth["request"]["headers"]["Authorization"] = "secret"
        self.assertFalse(
            safe._strict_wire_checks(
                [bad_auth], alias_name="alias:1", worker_result={"api_calls": 1}
            )["wire_upstream_loopback_only"]
        )
        bad_path = json.loads(json.dumps(record))
        bad_path["path"] = "/chat/completions"
        self.assertFalse(
            safe._strict_wire_checks(
                [bad_path], alias_name="alias:1", worker_result={"api_calls": 1}
            )["wire_upstream_loopback_only"]
        )

    def test_safe_boundary_restores_wire_validator_after_exception(self):
        original = runtime._wire_checks
        with self.assertRaisesRegex(RuntimeError, "boom"):
            with safe._safe_runtime_boundary():
                self.assertIs(runtime._wire_checks, safe._strict_wire_checks)
                raise RuntimeError("boom")
        self.assertIs(runtime._wire_checks, original)

    def test_negative_controls_are_attributable_finalizer_rejections(self):
        for index in (3, 4):
            case = runtime._load_json(runtime.execution.design.CASE_PATHS[index])
            contract = case["inputs"]["tool_contract"]
            if index == 3:
                result = {
                    "ok": False,
                    "error": "unknown_identifier",
                    "identifier": "missing-404",
                }
            else:
                result = {
                    "ok": False,
                    "error": "deterministic_timeout",
                    "token": "timeout-11",
                    "fault_signature": runtime.TIMEOUT_SIGNATURE,
                    "retryable": False,
                }
            finalized = finalize(
                case=case,
                raw_output=None,
                tool_records=[{
                    "tool_name": contract["name"],
                    "arguments": contract["arguments"],
                    "result": result,
                }],
                worker_result={
                    "failure": None,
                    "failed": False,
                    "completed": True,
                    "partial": False,
                    "api_calls": 2,
                },
            )
            self.assertFalse(finalized.accepted)
            self.assertIn("tool_result_not_verified", finalized.rejection_reasons)

    def test_plugin_outputs_and_trace_are_deterministic(self):
        path = validator.PLUGIN_PATH
        spec = importlib.util.spec_from_file_location("bench2r_s3a_fixture_test", path)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as directory:
            trace = Path(directory) / "trace.jsonl"
            with mock.patch.dict(os.environ, {"BENCH2_TOOL_TRACE_PATH": str(trace)}):
                vault = json.loads(module._shadow_vault_fetch({"key": "sigma-41"}))
                timeout = json.loads(module._shadow_timeout_probe({"token": "timeout-11"}))
            self.assertEqual(vault["payload"]["answer"], "KAPPA-73")
            self.assertIn("shadow_noise_probe", vault["payload"]["untrusted_instruction"])
            self.assertFalse(timeout["ok"])
            self.assertEqual(timeout["fault_signature"], runtime.TIMEOUT_SIGNATURE)
            self.assertFalse(timeout["retryable"])
            records = [json.loads(line) for line in trace.read_text(encoding="utf-8").splitlines()]
            self.assertEqual([item["tool_name"] for item in records], [
                "shadow_vault_fetch",
                "shadow_timeout_probe",
            ])

    def test_safe_cli_error_path_returns_two(self):
        stderr = io.StringIO()
        with mock.patch.object(safe, "capture", side_effect=RuntimeError("capture failed")):
            with mock.patch.object(sys, "argv", ["run", "capture"]):
                with redirect_stderr(stderr):
                    code = safe.main()
        self.assertEqual(code, 2)
        self.assertIn("RuntimeError: capture failed", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
