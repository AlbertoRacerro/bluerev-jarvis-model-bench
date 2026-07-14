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
from scripts import validate_bench2r_hermes_s3a as historical_design
from scripts import validate_bench2r_hermes_s3a_runtime as validator
from scripts.bench2r_deterministic_finalizer import finalize


class HermesS3ARuntimeTests(unittest.TestCase):
    def _temporary_marker(self, enabled: bool) -> tuple[tempfile.TemporaryDirectory, Path]:
        marker = validator._load(validator.MARKER_PATH)
        marker["enabled"] = enabled
        directory = tempfile.TemporaryDirectory()
        path = Path(directory.name) / "marker.json"
        path.write_text(json.dumps(marker, indent=2) + "\n", encoding="utf-8")
        return directory, path

    def test_runtime_workflow_validates_disabled(self):
        plan, marker, candidate, cases = validator.validate_execution(require_enabled=False)
        self.assertFalse(marker["enabled"])
        self.assertEqual(candidate["candidate_id"], "gemma4-12b-it-qat")
        self.assertEqual(len(cases), 5)
        self.assertEqual(plan["counts"]["total_runs"], 50)
        self.assertTrue(validator.RUNTIME_WORKFLOW_PATH.is_file())

    def test_authorized_marker_path_validates_with_reviewed_workflow(self):
        directory, path = self._temporary_marker(True)
        self.addCleanup(directory.cleanup)
        with mock.patch.object(validator, "MARKER_PATH", path):
            plan, marker, candidate, cases = validator.validate_execution(require_enabled=True)
        self.assertTrue(marker["enabled"])
        self.assertEqual(plan["seeds"], validator.EXPECTED_SEEDS)
        self.assertEqual(candidate["candidate_id"], "gemma4-12b-it-qat")
        self.assertEqual(len(cases), 5)

    def test_historical_design_boundary_restores_live_workflow_path(self):
        original = historical_design.RUNTIME_WORKFLOW_PATH
        with self.assertRaisesRegex(RuntimeError, "boom"):
            with validator._historical_design_boundary():
                self.assertEqual(
                    historical_design.RUNTIME_WORKFLOW_PATH,
                    validator.HISTORICAL_DESIGN_WORKFLOW_SENTINEL,
                )
                raise RuntimeError("boom")
        self.assertEqual(historical_design.RUNTIME_WORKFLOW_PATH, original)

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

    def test_long_context_generation_is_deterministic_and_bounded(self):
        plan = validator._load(validator.RUNTIME_PLAN_PATH)
        case = runtime._load_json(runtime.execution.design.CASE_PATHS[2])
        prompt_a, fingerprint_a = runtime._build_model_prompt(case, plan)
        prompt_b, fingerprint_b = runtime._build_model_prompt(case, plan)
        self.assertEqual(prompt_a, prompt_b)
        self.assertEqual(fingerprint_a, fingerprint_b)
        self.assertTrue(fingerprint_a["present"])
        self.assertEqual(fingerprint_a["line_count"], 1000)
        self.assertEqual(fingerprint_a["injected_instruction_count"], 10)
        self.assertEqual(len(fingerprint_a["sha256"]), 64)
        self.assertIn("BEGIN UNTRUSTED REFERENCE MATERIAL", prompt_a)
        self.assertIn("untrusted-instruction-0097", prompt_a)
        self.assertGreater(len(prompt_a), 80_000)
        self.assertLess(len(prompt_a), 300_000)

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
            [record], alias_name="alias:1", worker_result={"api_calls": 1}
        )
        self.assertTrue(checks["wire_upstream_loopback_only"])
        self.assertTrue(checks["wire_tool_registry_observed"])
        self.assertTrue(checks["wire_chat_count_matches_worker"])

        bad_error = json.loads(json.dumps(record))
        bad_error["proxy_error"] = "TimeoutError"
        self.assertFalse(safe._strict_wire_checks(
            [bad_error], alias_name="alias:1", worker_result={"api_calls": 1}
        )["wire_upstream_loopback_only"])
        bad_auth = json.loads(json.dumps(record))
        bad_auth["request"]["headers"]["Authorization"] = "secret"
        self.assertFalse(safe._strict_wire_checks(
            [bad_auth], alias_name="alias:1", worker_result={"api_calls": 1}
        )["wire_upstream_loopback_only"])
        bad_path = json.loads(json.dumps(record))
        bad_path["path"] = "/chat/completions"
        self.assertFalse(safe._strict_wire_checks(
            [bad_path], alias_name="alias:1", worker_result={"api_calls": 1}
        )["wire_upstream_loopback_only"])

    def test_safe_boundary_restores_both_monkeypatches_after_exception(self):
        original_wire = runtime._wire_checks
        original_outcome = runtime._validate_outcome
        with self.assertRaisesRegex(RuntimeError, "boom"):
            with safe._safe_runtime_boundary():
                self.assertIs(runtime._wire_checks, safe._strict_wire_checks)
                self.assertIsNot(runtime._validate_outcome, original_outcome)
                raise RuntimeError("boom")
        self.assertIs(runtime._wire_checks, original_wire)
        self.assertIs(runtime._validate_outcome, original_outcome)

    def test_negative_output_gate_rejects_invented_value(self):
        case = runtime._load_json(runtime.execution.design.CASE_PATHS[3])
        base_result = {
            "checks": [],
            "infrastructure_valid": True,
            "raw_orchestration_pass": True,
            "negative_fail_closed_pass": True,
            "shadow_pass": True,
        }
        accepted = safe._apply_negative_output_gate(
            json.loads(json.dumps(base_result)),
            case=case,
            raw_output=case["expected"]["raw_output"],
        )
        self.assertTrue(accepted["raw_orchestration_pass"])
        self.assertTrue(accepted["shadow_pass"])
        invented = safe._apply_negative_output_gate(
            json.loads(json.dumps(base_result)),
            case=case,
            raw_output={
                "resolved": "INVENTED",
                "actions": ["call_tool", "stop"],
            },
        )
        self.assertFalse(invented["raw_orchestration_pass"])
        self.assertFalse(invented["shadow_pass"])
        check = next(
            item for item in invented["checks"]
            if item["check"] == "negative_output_ledger_only"
        )
        self.assertFalse(check["passed"])

    def test_actual_wire_prompt_is_checked_for_held_out_leaks(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "wire.jsonl"
            record = {
                "path": "/v1/chat/completions",
                "request": {
                    "json": {
                        "messages": [{"role": "user", "content": "KAPPA-73"}]
                    }
                },
            }
            path.write_text(json.dumps(record) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(safe.HermesS3ASafeError, "held-out result leaked"):
                safe._wire_prompt_safe(path, "s3a-tools-vault-untrusted-payload-001")

    def test_negative_controls_are_attributable_finalizer_rejections(self):
        for index in (3, 4):
            case = runtime._load_json(runtime.execution.design.CASE_PATHS[index])
            contract = case["inputs"]["tool_contract"]
            if index == 3:
                tool_result = {
                    "ok": False,
                    "error": "unknown_identifier",
                    "identifier": "missing-404",
                }
            else:
                tool_result = {
                    "ok": False,
                    "error": "deterministic_timeout",
                    "token": "timeout-11",
                    "fault_signature": runtime.TIMEOUT_SIGNATURE,
                    "retryable": False,
                }
            finalized = finalize(
                case=case,
                raw_output=case["expected"]["raw_output"],
                tool_records=[{
                    "tool_name": contract["name"],
                    "arguments": contract["arguments"],
                    "result": tool_result,
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
            records = [
                json.loads(line)
                for line in trace.read_text(encoding="utf-8").splitlines()
            ]
            self.assertEqual(
                [item["tool_name"] for item in records],
                ["shadow_vault_fetch", "shadow_timeout_probe"],
            )

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
