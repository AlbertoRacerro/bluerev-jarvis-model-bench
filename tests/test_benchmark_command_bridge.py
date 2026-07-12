from __future__ import annotations

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
BRIDGE = ROOT / ".github" / "workflows" / "benchmark-command-bridge.yml"
TARGETS = {
    "/bench preflight": "local-benchmark.yml",
    "/bench residency": "local-model-residency.yml",
    "/bench direct-smoke": "local-direct-smoke.yml",
}


class BenchmarkCommandBridgeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.workflow = BRIDGE.read_text(encoding="utf-8")

    def test_trigger_is_created_issue_comment_only(self) -> None:
        self.assertIn("issue_comment:", self.workflow)
        self.assertIn("types: [created]", self.workflow)
        self.assertNotIn("pull_request_target:", self.workflow)
        self.assertNotIn("workflow_run:", self.workflow)

    def test_job_gate_is_bound_to_repository_and_inbox_issue(self) -> None:
        self.assertIn(
            "github.repository == 'AlbertoRacerro/bluerev-jarvis-model-bench'",
            self.workflow,
        )
        self.assertIn("github.event.issue.number == 24", self.workflow)

    def test_script_rechecks_full_maintainer_identity(self) -> None:
        for required in (
            "context.repo.owner === 'AlbertoRacerro'",
            "context.repo.repo === 'bluerev-jarvis-model-bench'",
            "context.payload.issue.number === 24",
            "!context.payload.issue.pull_request",
            "context.payload.comment.user.login === 'AlbertoRacerro'",
            "Number(context.payload.comment.user.id) === 293122393",
            "context.payload.comment.user.type === 'User'",
            "context.payload.comment.author_association === 'OWNER'",
        ):
            self.assertIn(required, self.workflow)
        self.assertIn("if (!authorized)", self.workflow)

    def test_only_exact_commands_map_to_fixed_workflows(self) -> None:
        for command, target in TARGETS.items():
            self.assertIn(f"'{command}': '{target}'", self.workflow)
        self.assertIn("const workflowId = workflows[command];", self.workflow)
        self.assertIn("if (!workflowId)", self.workflow)

    def test_dispatch_is_fixed_to_main_without_shell_interpolation(self) -> None:
        self.assertIn("github.rest.actions.createWorkflowDispatch", self.workflow)
        self.assertIn("workflow_id: workflowId", self.workflow)
        self.assertIn("ref: 'main'", self.workflow)
        self.assertNotIn("actions/checkout", self.workflow)
        self.assertNotRegex(self.workflow, re.compile(r"(?m)^\s*run:"))
        self.assertNotIn("${{ github.event.comment.body }}", self.workflow)

    def test_permissions_are_limited_to_dispatch_and_receipt(self) -> None:
        self.assertIn(
            "permissions:\n  contents: read\n  actions: write\n  issues: write\n",
            self.workflow,
        )
        self.assertNotIn("contents: write", self.workflow)
        self.assertNotIn("pull-requests: write", self.workflow)

    def test_successful_dispatch_writes_structured_receipt(self) -> None:
        self.assertIn("github.rest.issues.createComment", self.workflow)
        self.assertIn("bench.command-receipt.v1", self.workflow)
        self.assertIn("source_comment_id: context.payload.comment.id", self.workflow)
        self.assertIn("target_workflow: workflowId", self.workflow)

    def test_every_target_explicitly_supports_manual_dispatch(self) -> None:
        for target in TARGETS.values():
            workflow = (ROOT / ".github" / "workflows" / target).read_text(
                encoding="utf-8"
            )
            self.assertIn("workflow_dispatch:", workflow, target)


if __name__ == "__main__":
    unittest.main()
