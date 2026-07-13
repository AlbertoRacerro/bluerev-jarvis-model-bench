from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts import run_bench2_hermes_canary as runtime
from scripts import validate_bench2_hermes_canary as validator


class Bench2HermesCanaryTests(unittest.TestCase):
    def test_runtime_source_matches_reviewed_bytes(self):
        path = validator.ROOT / "scripts/run_bench2_hermes_canary.py"
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        self.assertEqual(
            digest,
            "cccc8a7500de332895ffd156fbdb0b8e85ab0f856a92e1bcd3db8c7115166b65",
        )

    def test_plan_is_single_candidate_single_case_with_explicit_marker_state(self):
        plan, marker, case = validator.validate_canary_plan()
        self.assertEqual(plan["counts"], {
            "candidates": 1, "cases": 1, "repetitions": 1, "total_runs": 1
        })
        self.assertEqual(plan["candidate"]["candidate_id"], "qwythos-hermes-safe")
        self.assertEqual(plan["case"]["case_id"], "ho-tools-hermes-lookup-001")
        self.assertEqual(case["capability"], "HO-TOOLS")
        self.assertIsInstance(marker["enabled"], bool)
        self.assertFalse(plan["execution"]["external_providers_allowed"])
        self.assertEqual(plan["execution"]["fallback_chain"], [])
        self.assertFalse(plan["execution"]["jarvisos_access_allowed"])

    def test_full_matrix_marker_remains_disabled(self):
        marker = json.loads(
            validator.bench2.MARKER_PATH.read_text(encoding="utf-8")
        )
        self.assertFalse(marker["enabled"])
        self.assertEqual(marker["plan_sha256"], validator.bench2.EXPECTED_PLAN_SHA256)

    def test_strict_output_parser_accepts_only_exact_json_object(self):
        value, error = runtime._parse_output(
            '{"actions":["call_tool","return_final","stop"],"final":"BRAVO-19"}'
        )
        self.assertIsNone(error)
        self.assertEqual(value["final"], "BRAVO-19")
        _, fenced_error = runtime._parse_output(
            '```json\n{"actions":["call_tool","return_final","stop"],"final":"BRAVO-19"}\n```'
        )
        self.assertIsNotNone(fenced_error)
        value, fields_error = runtime._parse_output('{"final":"BRAVO-19","extra":1}')
        self.assertEqual(value["final"], "BRAVO-19")
        self.assertEqual(fields_error, "output_fields_mismatch")

    def test_missing_tool_trace_is_semantic_failure_not_corrupt_infrastructure(self):
        with tempfile.TemporaryDirectory() as directory:
            records, error = runtime._read_tool_trace(Path(directory) / "missing.jsonl")
        self.assertEqual(records, [])
        self.assertIsNone(error)
        usage_checks = [
            {"check": "usage_provider_custom", "passed": True, "detail": ""},
            {"check": "usage_model_exact", "passed": True, "detail": ""},
            {"check": "usage_completed", "passed": True, "detail": ""},
            {"check": "usage_not_failed", "passed": True, "detail": ""},
            {"check": "usage_api_calls_bounded", "passed": True, "detail": ""},
            {"check": "usage_input_tokens_nonnegative", "passed": True, "detail": ""},
            {"check": "usage_output_tokens_nonnegative", "passed": True, "detail": ""},
            {"check": "usage_total_tokens_nonnegative", "passed": True, "detail": ""},
        ]
        result = runtime._validator_result(
            process={"returncode": 0, "timed_out": False},
            output={"actions": runtime.EXPECTED_ACTIONS, "final": runtime.EXPECTED_FINAL},
            output_error=None,
            tool_records=[],
            trace_error=None,
            usage_checks=usage_checks,
            runtime_model={"context_length": 65536},
            residency_class="full_vram",
            residency_ratio=1.0,
        )
        self.assertTrue(result["infrastructure_valid"])
        self.assertFalse(result["semantic_pass"])
        self.assertFalse(result["passed"])

    def test_sanitized_environment_removes_credentials_and_sinks_external_proxies(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            with mock.patch.dict(
                os.environ,
                {
                    "PATH": "C:\\Windows",
                    "USERPROFILE": "C:\\Users\\bench",
                    "OPENROUTER_API_KEY": "secret",
                    "GITHUB_TOKEN": "secret",
                    "CUSTOM_PASSWORD": "secret",
                    "BENIGN_VALUE": "not-copied",
                },
                clear=True,
            ):
                env, removed = runtime.sanitized_subprocess_environment(
                    hermes_home=base / "home",
                    tool_trace=base / "trace.jsonl",
                    hermes_repo=base / "repo",
                )
        self.assertNotIn("OPENROUTER_API_KEY", env)
        self.assertNotIn("GITHUB_TOKEN", env)
        self.assertNotIn("CUSTOM_PASSWORD", env)
        self.assertNotIn("BENIGN_VALUE", env)
        self.assertEqual(env["OPENAI_API_KEY"], "local-only-not-secret")
        self.assertEqual(env["HTTPS_PROXY"], "http://127.0.0.1:9")
        self.assertEqual(env["NO_PROXY"], "127.0.0.1,localhost,::1")
        self.assertEqual(
            set(removed),
            {"OPENROUTER_API_KEY", "GITHUB_TOKEN", "CUSTOM_PASSWORD"},
        )

    def test_runtime_workflow_is_guarded_and_branch_validation_is_hosted_only(self):
        runtime_text = validator.RUNTIME_WORKFLOW_PATH.read_text(encoding="utf-8")
        self.assertIn(
            "startsWith(github.event.head_commit.message, 'Activate BENCH-2 Hermes canary')",
            runtime_text,
        )
        self.assertIn("runs-on: [self-hosted, Windows, X64, bluerev-bench]", runtime_text)
        self.assertIn("shell: cmd", runtime_text)
        self.assertIn("ref: ${{ github.sha }}", runtime_text)
        self.assertNotIn("workflow_dispatch", runtime_text)
        validation_text = validator.VALIDATION_WORKFLOW_PATH.read_text(encoding="utf-8")
        self.assertIn("runs-on: ubuntu-latest", validation_text)
        self.assertNotIn("self-hosted", validation_text.lower())

    def test_plugin_and_case_are_bound_to_reviewed_digests(self):
        plan, _, _ = validator.validate_canary_plan()
        files = {item["path"]: item["sha256"] for item in plan["fixtures"]["plugin_files"]}
        self.assertEqual(
            files["fixtures/bench-2/hermes-plugin/bench2-fixture/__init__.py"],
            "ae0124562e89eef0d37295fd0e72435819b0d23f25a86a0b0b9bc2a75744d67d",
        )
        self.assertEqual(
            plan["case"]["case_definition_sha256"],
            "f2f1889edfadf1cccf84ebac7650421478aeabfb6d9b3331e24034867e5aa1ca",
        )


if __name__ == "__main__":
    unittest.main()
