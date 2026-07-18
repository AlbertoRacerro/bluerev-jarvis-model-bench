from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts import validate_bench3_hermes_memory_routing_design as validator


class MemoryRoutingDesignTests(unittest.TestCase):
    def _patch_documents(
        self,
        *,
        plan=None,
        research=None,
        memory_skill=None,
        routing_skill=None,
        bundle=None,
        workflow=None,
    ):
        original_load = validator._load
        original_read = validator._read

        def load(path: Path):
            if path == validator.PLAN_PATH and plan is not None:
                return copy.deepcopy(plan)
            return original_load(path)

        def read(path: Path):
            if path == validator.RESEARCH_PATH and research is not None:
                return research
            if path == validator.MEMORY_SKILL_PATH and memory_skill is not None:
                return memory_skill
            if path == validator.ROUTING_SKILL_PATH and routing_skill is not None:
                return routing_skill
            if path == validator.BUNDLE_PATH and bundle is not None:
                return bundle
            if path == validator.DESIGN_WORKFLOW_PATH and workflow is not None:
                return workflow
            return original_read(path)

        return mock.patch.multiple(
            validator,
            _load=mock.Mock(side_effect=load),
            _read=mock.Mock(side_effect=read),
        )

    def test_static_design_validates(self):
        payload = validator.validate()
        self.assertEqual(payload["status"], "valid_static_design")
        self.assertEqual(payload["memory_cases"], 12)
        self.assertEqual(payload["routing_cases"], 12)
        self.assertEqual(payload["total_static_cases"], 24)
        self.assertFalse(payload["execution_implemented"])
        self.assertEqual(payload["production_status"], "not_promoted")

    def test_official_source_binding_drift_is_rejected(self):
        plan = validator._load(validator.PLAN_PATH)
        plan["source"]["official_sources"][0]["git_blob_sha"] = "0" * 40
        with self._patch_documents(plan=plan):
            with self.assertRaisesRegex(validator.MemoryRoutingDesignError, "official Hermes source bindings"):
                validator.validate()

    def test_memory_skill_blob_drift_is_rejected(self):
        skill = validator._read(validator.MEMORY_SKILL_PATH) + "\n"
        with self._patch_documents(memory_skill=skill):
            with self.assertRaisesRegex(validator.MemoryRoutingDesignError, "memory skill blob"):
                validator.validate()

    def test_routing_skill_blob_drift_is_rejected(self):
        skill = validator._read(validator.ROUTING_SKILL_PATH) + "\n"
        with self._patch_documents(routing_skill=skill):
            with self.assertRaisesRegex(validator.MemoryRoutingDesignError, "routing skill blob"):
                validator.validate()

    def test_bundle_drift_is_rejected(self):
        bundle = validator._read(validator.BUNDLE_PATH).replace(
            "routing-orchestration", "routing-orchestration-v2", 1
        )
        plan = validator._load(validator.PLAN_PATH)
        plan["bundle"]["git_blob_sha"] = validator._git_blob_sha(bundle)
        with self._patch_documents(plan=plan, bundle=bundle):
            with self.assertRaisesRegex(validator.MemoryRoutingDesignError, "bundle content"):
                validator.validate()

    def test_memory_write_approval_cannot_be_disabled(self):
        plan = validator._load(validator.PLAN_PATH)
        plan["memory_architecture"]["memory_write_approval_required"] = False
        with self._patch_documents(plan=plan):
            with self.assertRaisesRegex(validator.MemoryRoutingDesignError, "memory write approval"):
                validator.validate()

    def test_skill_write_approval_cannot_be_disabled(self):
        plan = validator._load(validator.PLAN_PATH)
        plan["memory_architecture"]["skill_write_approval_required"] = False
        with self._patch_documents(plan=plan):
            with self.assertRaisesRegex(validator.MemoryRoutingDesignError, "skill write approval"):
                validator.validate()

    def test_subagent_memory_writes_are_rejected(self):
        plan = validator._load(validator.PLAN_PATH)
        plan["memory_architecture"]["subagents_may_write_persistent_memory"] = True
        with self._patch_documents(plan=plan):
            with self.assertRaisesRegex(validator.MemoryRoutingDesignError, "subagent memory writes"):
                validator.validate()

    def test_openrouter_routing_cannot_be_claimed_for_ollama(self):
        plan = validator._load(validator.PLAN_PATH)
        plan["runtime_constraints"]["provider_routing_applies_to_local_ollama"] = True
        with self._patch_documents(plan=plan):
            with self.assertRaisesRegex(validator.MemoryRoutingDesignError, "OpenRouter routing"):
                validator.validate()

    def test_unsupported_per_task_delegate_switch_is_rejected(self):
        plan = validator._load(validator.PLAN_PATH)
        plan["runtime_constraints"]["delegate_per_task_model_override_reviewed_available"] = True
        with self._patch_documents(plan=plan):
            with self.assertRaisesRegex(validator.MemoryRoutingDesignError, "per-task delegate model override"):
                validator.validate()

    def test_single_gpu_concurrency_drift_is_rejected(self):
        plan = validator._load(validator.PLAN_PATH)
        plan["routing_architecture"]["max_concurrent_children"] = 3
        with self._patch_documents(plan=plan):
            with self.assertRaisesRegex(validator.MemoryRoutingDesignError, "single-GPU concurrency"):
                validator.validate()

    def test_semantic_auto_reroute_is_rejected(self):
        plan = validator._load(validator.PLAN_PATH)
        plan["fallback_policy"]["semantic_failure_auto_reroute_allowed"] = True
        with self._patch_documents(plan=plan):
            with self.assertRaisesRegex(validator.MemoryRoutingDesignError, "semantic auto-reroute"):
                validator.validate()

    def test_post_side_effect_fallback_is_rejected(self):
        plan = validator._load(validator.PLAN_PATH)
        plan["fallback_policy"]["fallback_after_side_effect_allowed"] = True
        with self._patch_documents(plan=plan):
            with self.assertRaisesRegex(validator.MemoryRoutingDesignError, "post-side-effect fallback"):
                validator.validate()

    def test_memory_case_inventory_drift_is_rejected(self):
        plan = validator._load(validator.PLAN_PATH)
        plan["benchmark_design"]["memory_case_ids"].pop()
        with self._patch_documents(plan=plan):
            with self.assertRaisesRegex(validator.MemoryRoutingDesignError, "memory case inventory"):
                validator.validate()

    def test_routing_case_inventory_drift_is_rejected(self):
        plan = validator._load(validator.PLAN_PATH)
        plan["benchmark_design"]["routing_case_ids"].reverse()
        with self._patch_documents(plan=plan):
            with self.assertRaisesRegex(validator.MemoryRoutingDesignError, "routing case inventory"):
                validator.validate()

    def test_forbidden_workflow_path_filter_regression_is_rejected(self):
        workflow = validator._read(validator.DESIGN_WORKFLOW_PATH)
        workflow = workflow.replace(
            f"      - {validator.FORBIDDEN_WORKFLOW_LITERAL}\n", "", 1
        )
        with self._patch_documents(workflow=workflow):
            with self.assertRaisesRegex(validator.MemoryRoutingDesignError, "guard forbidden runtime workflow"):
                validator.validate()

    def test_forbidden_marker_path_filter_regression_is_rejected(self):
        workflow = validator._read(validator.DESIGN_WORKFLOW_PATH)
        workflow = workflow.replace(
            f"      - {validator.FORBIDDEN_MARKER_LITERAL}\n", "", 1
        )
        with self._patch_documents(workflow=workflow):
            with self.assertRaisesRegex(validator.MemoryRoutingDesignError, "guard forbidden marker"):
                validator.validate()

    def test_forbidden_runner_path_filter_regression_is_rejected(self):
        workflow = validator._read(validator.DESIGN_WORKFLOW_PATH)
        workflow = workflow.replace(
            f"      - {validator.FORBIDDEN_RUNNER_LITERAL}\n", "", 1
        )
        with self._patch_documents(workflow=workflow):
            with self.assertRaisesRegex(validator.MemoryRoutingDesignError, "guard forbidden runner"):
                validator.validate()

    def test_runtime_workflow_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "canary.yml"
            path.write_text("name: forbidden\n", encoding="utf-8")
            with mock.patch.object(validator, "FORBIDDEN_WORKFLOW_PATH", path):
                with self.assertRaisesRegex(validator.MemoryRoutingDesignError, "runtime workflow exists"):
                    validator.validate()

    def test_runtime_marker_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "marker.json"
            path.write_text("{}\n", encoding="utf-8")
            with mock.patch.object(validator, "FORBIDDEN_MARKER_PATH", path):
                with self.assertRaisesRegex(validator.MemoryRoutingDesignError, "runtime marker exists"):
                    validator.validate()

    def test_runtime_runner_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "run.py"
            path.write_text("print('forbidden')\n", encoding="utf-8")
            with mock.patch.object(validator, "FORBIDDEN_RUNNER_PATH", path):
                with self.assertRaisesRegex(validator.MemoryRoutingDesignError, "runtime runner exists"):
                    validator.validate()

    def test_profiles_cannot_be_claimed_as_filesystem_sandbox(self):
        plan = validator._load(validator.PLAN_PATH)
        plan["routing_architecture"]["profiles_are_filesystem_sandbox"] = True
        with self._patch_documents(plan=plan):
            with self.assertRaisesRegex(validator.MemoryRoutingDesignError, "filesystem sandbox"):
                validator.validate()

    def test_absolute_terminal_cwd_is_required(self):
        plan = validator._load(validator.PLAN_PATH)
        plan["routing_architecture"]["absolute_terminal_cwd_required"] = False
        with self._patch_documents(plan=plan):
            with self.assertRaisesRegex(validator.MemoryRoutingDesignError, "absolute terminal cwd"):
                validator.validate()

    def test_explicit_max_iterations_is_required(self):
        plan = validator._load(validator.PLAN_PATH)
        plan["routing_architecture"]["explicit_max_iterations_required"] = False
        with self._patch_documents(plan=plan):
            with self.assertRaisesRegex(validator.MemoryRoutingDesignError, "explicit max_iterations"):
                validator.validate()

    def test_dispatcher_watchdog_is_required(self):
        plan = validator._load(validator.PLAN_PATH)
        plan["routing_architecture"]["dispatcher_wall_clock_watchdog_required"] = False
        with self._patch_documents(plan=plan):
            with self.assertRaisesRegex(validator.MemoryRoutingDesignError, "dispatcher watchdog"):
                validator.validate()


if __name__ == "__main__":
    unittest.main()
