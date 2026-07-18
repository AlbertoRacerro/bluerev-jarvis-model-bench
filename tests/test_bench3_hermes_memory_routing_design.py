from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts import validate_bench3_hermes_memory_routing_design as core


class MemoryRoutingDesignTests(unittest.TestCase):
    def patch_plan(self, plan):
        original = core._load
        return mock.patch.object(
            core,
            "_load",
            side_effect=lambda path: copy.deepcopy(plan) if path == core.PLAN_PATH else original(path),
        )

    def test_static_design_validates(self):
        result = core.validate()
        self.assertEqual(result["status"], "valid_static_design")
        self.assertEqual(result["total_static_cases"], 24)
        self.assertFalse(result["execution_implemented"])

    def test_memory_and_routing_mutations_fail_closed(self):
        mutations = [
            ("memory_architecture", "memory_write_approval_required", False),
            ("memory_architecture", "skill_write_approval_required", False),
            ("memory_architecture", "parent_only_persistent_memory_writes", False),
            ("memory_architecture", "subagents_may_write_persistent_memory", True),
            ("memory_architecture", "conflict_precedence", ["approved_persistent_memory"]),
            ("routing_architecture", "global_model_score_routing_allowed", True),
            ("routing_architecture", "max_concurrent_children", 3),
            ("routing_architecture", "profiles_are_filesystem_sandbox", True),
            ("routing_architecture", "absolute_terminal_cwd_required", False),
            ("routing_architecture", "explicit_max_iterations_required", False),
            ("routing_architecture", "dispatcher_wall_clock_watchdog_required", False),
            ("fallback_policy", "semantic_failure_auto_reroute_allowed", True),
            ("fallback_policy", "fallback_after_side_effect_allowed", True),
        ]
        for section, key, value in mutations:
            with self.subTest(section=section, key=key):
                plan = core._load(core.PLAN_PATH)
                plan[section][key] = value
                with self.patch_plan(plan), self.assertRaises(core.MemoryRoutingDesignError):
                    core.validate()

    def test_all_acceptance_and_execution_gates_are_enforced(self):
        base = core._load(core.PLAN_PATH)
        for section in ("acceptance", "execution"):
            for key, value in base[section].items():
                if not isinstance(value, bool):
                    continue
                with self.subTest(section=section, key=key):
                    plan = copy.deepcopy(base)
                    plan[section][key] = not value
                    with self.patch_plan(plan), self.assertRaises(core.MemoryRoutingDesignError):
                        core.validate()

    def test_case_source_and_provider_drift_are_rejected(self):
        changes = [
            ("source", "official_sources", []),
            ("runtime_constraints", "provider_routing_applies_to_local_ollama", True),
            ("runtime_constraints", "delegate_per_task_model_override_reviewed_available", True),
            ("benchmark_design", "memory_case_ids", []),
            ("benchmark_design", "routing_case_ids", []),
        ]
        for section, key, value in changes:
            with self.subTest(section=section, key=key):
                plan = core._load(core.PLAN_PATH)
                plan[section][key] = value
                with self.patch_plan(plan), self.assertRaises(core.MemoryRoutingDesignError):
                    core.validate()

    def test_candidate_skill_and_bundle_fixture_bindings_are_enforced(self):
        mutations = [
            ("skills", 0, "version", "9.9.9"),
            ("skills", 0, "path", "skills/memory-orchestration/SKILL.md"),
            ("skills", 1, "version", "9.9.9"),
            ("skills", 1, "path", "skills/routing-orchestration/SKILL.md"),
            ("bundle", None, "name", "installed-bundle"),
            ("bundle", None, "path", "skills/bundles/jarvis.yaml"),
        ]
        for section, index, key, value in mutations:
            with self.subTest(section=section, index=index, key=key):
                plan = core._load(core.PLAN_PATH)
                target = plan[section] if index is None else plan[section][index]
                target[key] = value
                with self.patch_plan(plan), self.assertRaises(core.MemoryRoutingDesignError):
                    core.validate()

    def test_renamed_and_opaque_runtime_artifacts_are_detected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            renamed = root / ".github/workflows/bench3-alternate-routing-canary.yml"
            renamed.parent.mkdir(parents=True)
            renamed.write_text("name: runtime\n", encoding="utf-8")
            opaque = root / "scripts/worker.py"
            opaque.parent.mkdir(parents=True)
            opaque.write_text("SCHEMA = 'bench.hermes-memory-routing-design.v1'\n", encoding="utf-8")
            with mock.patch.object(core, "ROOT", root):
                found = core._unexpected_runtime_artifacts()
            self.assertIn(renamed.relative_to(root).as_posix(), found)
            self.assertIn(opaque.relative_to(root).as_posix(), found)


if __name__ == "__main__":
    unittest.main()
