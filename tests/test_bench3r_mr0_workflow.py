from __future__ import annotations

import unittest

from scripts import bench3r_mr0_validate_policy as policy
from scripts.bench3r_mr0_io import MR0DesignError, read_text


class MR0WorkflowTests(unittest.TestCase):
    def test_all_runtime_guards_are_present(self):
        workflow = read_text(policy.WORKFLOW)
        for path in policy.FORBIDDEN:
            literal = path.relative_to(policy.ROOT).as_posix()
            with self.subTest(literal=literal):
                self.assertEqual(workflow.count(literal), 3)

    def test_removed_guard_is_rejected(self):
        plan = {
            "execution": {
                "implemented": False,
                "executor_present": False,
                "canary_workflow_present": False,
                "marker_present": False,
                "ollama_calls_allowed_in_this_slice": False,
                "self_hosted_compute_allowed_in_this_slice": False,
                "hosted_static_validation_only": True,
            }
        }
        workflow = read_text(policy.WORKFLOW)
        literal = policy.FORBIDDEN[0].relative_to(policy.ROOT).as_posix()
        changed = workflow.replace(f"      - {literal}\n", "", 1)
        with self.assertRaisesRegex(MR0DesignError, "runtime guard drifted"):
            policy.validate_execution(plan, changed)


if __name__ == "__main__":
    unittest.main()
