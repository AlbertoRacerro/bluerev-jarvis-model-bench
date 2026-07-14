from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts import validate_bench2r_hermes_s3a as base
from scripts import validate_bench2r_hermes_s3a_contract as strict


class HermesS3AStrictContractTests(unittest.TestCase):
    def _temporary_plan(self, plan: dict) -> tuple[tempfile.TemporaryDirectory, Path]:
        directory = tempfile.TemporaryDirectory()
        path = Path(directory.name) / "plan.json"
        path.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
        return directory, path

    def _strict_validate(self):
        sentinel = base.ROOT / ".bench2r-s3a-test-no-runtime-workflow"
        with mock.patch.object(base, "RUNTIME_WORKFLOW_PATH", sentinel):
            return strict.validate()

    def test_reviewed_strict_contract_validates(self):
        payload = self._strict_validate()
        self.assertTrue(payload["strict_contract_valid"])
        self.assertTrue(payload["governed_stack_exact"])
        self.assertTrue(payload["scope_split_enforced"])
        self.assertTrue(payload["case_tool_contracts_exact"])
        self.assertTrue(payload["negative_outputs_ledger_only"])

    def test_governed_stack_drift_is_rejected(self):
        plan = base._load(base.PLAN_PATH)
        plan["governed_stack"]["skill_version"] = "1.2.0"
        directory, path = self._temporary_plan(plan)
        self.addCleanup(directory.cleanup)
        with mock.patch.object(base, "PLAN_PATH", path):
            with self.assertRaisesRegex(strict.HermesS3AContractError, "governed-stack contract drifted"):
                self._strict_validate()

    def test_multi_tool_scope_expansion_is_rejected(self):
        plan = base._load(base.PLAN_PATH)
        plan["scope_exclusions"]["multi_tool_chains"] = "included in S3A"
        directory, path = self._temporary_plan(plan)
        self.addCleanup(directory.cleanup)
        with mock.patch.object(base, "PLAN_PATH", path):
            with self.assertRaisesRegex(strict.HermesS3AContractError, "scope boundary drifted"):
                self._strict_validate()

    def test_strict_nominal_acceptance_gate_cannot_be_disabled(self):
        plan = base._load(base.PLAN_PATH)
        plan["acceptance"]["all_nominal_runs_must_pass_raw_orchestration"] = False
        directory, path = self._temporary_plan(plan)
        self.addCleanup(directory.cleanup)
        with mock.patch.object(base, "PLAN_PATH", path):
            with self.assertRaisesRegex(strict.HermesS3AContractError, "acceptance gate disabled"):
                self._strict_validate()

    def test_tool_sequence_must_match_exact_tool_contract(self):
        case = copy.deepcopy(base._load(base.CASE_PATHS[0]))
        case["expected"]["tool_sequence"] = ["shadow_noise_probe"]
        with self.assertRaisesRegex(strict.HermesS3AContractError, "tool sequence no longer matches"):
            strict._validate_case_contract(case)

    def test_negative_raw_output_cannot_contain_result_value(self):
        case = copy.deepcopy(base._load(base.CASE_PATHS[3]))
        case["expected"]["raw_output"] = {
            "resolved": "INVENTED",
            "actions": ["call_tool", "stop"],
        }
        with self.assertRaisesRegex(strict.HermesS3AContractError, "not ledger-only"):
            strict._validate_case_contract(case)

    def test_timeout_fault_signature_is_frozen(self):
        case = copy.deepcopy(base._load(base.CASE_PATHS[4]))
        case["inputs"]["fault_injection"]["trace_before_return"] = False
        with self.assertRaisesRegex(strict.HermesS3AContractError, "fault-injection signature drifted"):
            strict._validate_case_contract(case)


if __name__ == "__main__":
    unittest.main()
