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

    def test_triggers_are_owner_comment_and_seed_push_only(self) -> None:
        for required in (
            "issue_comment:",
            "types: [created]",
            "push:",
            "branches: [main]",
            '".github/workflows/benchmark-command-bridge.yml"',
            '"tests/test_benchmark_command_bridge.py"',
        ):
            self.assertIn(required, self.workflow)
        self.assertNotIn("pull_request_target:", self.workflow)
        self.assertNotIn("workflow_run:", self.workflow)

    def test_job_gate_is_bound_to_repository_and_inbox_issue(self) -> None:
        self.assertIn(
            "github.repository == 'AlbertoRacerro/bluerev-jarvis-model-bench'",
            self.workflow,
        )
        self.assertIn("github.event_name == 'push'", self.workflow)
        self.assertIn("github.event.issue.number == 24", self.workflow)
        self.assertIn("group: benchmark-command-control", self.workflow)
        self.assertIn("cancel-in-progress: false", self.workflow)

    def test_full_owner_identity_and_exact_commands_are_rechecked(self) -> None:
        for required in (
            "const OWNER_LOGIN = 'AlbertoRacerro';",
            "const OWNER_ID = 293122393;",
            "comment.user?.type === 'User'",
            "comment.author_association === 'OWNER'",
            "Object.hasOwn(workflows, comment.body)",
        ):
            self.assertIn(required, self.workflow)
        for command, target in TARGETS.items():
            self.assertIn(f"'{command}': '{target}'", self.workflow)

    def test_dispatch_is_fixed_to_main_without_checkout_or_shell(self) -> None:
        self.assertIn("github.rest.actions.createWorkflowDispatch", self.workflow)
        self.assertIn("workflow_id: workflowId", self.workflow)
        self.assertIn("ref: 'main'", self.workflow)
        self.assertNotIn("actions/checkout", self.workflow)
        self.assertNotRegex(self.workflow, re.compile(r"(?m)^\s*run:"))
        self.assertNotIn("${{ github.event.comment.body }}", self.workflow)

    def test_permissions_are_limited_to_control_operations(self) -> None:
        self.assertIn(
            "permissions:\n  contents: read\n  actions: write\n  issues: write\n  statuses: write\n",
            self.workflow,
        )
        self.assertNotIn("contents: write", self.workflow)
        self.assertNotIn("pull-requests: write", self.workflow)

    def test_initial_push_registers_discoverable_seed_without_dispatch(self) -> None:
        self.assertIn("github.rest.repos.createCommitStatus", self.workflow)
        self.assertIn("benchmark-command-runner/seed", self.workflow)
        self.assertIn("context.runId", self.workflow)
        self.assertIn("Number(process.env.RUN_ATTEMPT) === 1", self.workflow)
        self.assertLess(
            self.workflow.index("await registerSeed();"),
            self.workflow.index("const comment = context.eventName"),
        )

    def test_rerun_fallback_reads_latest_unconsumed_owner_command(self) -> None:
        for required in (
            "github.rest.issues.listComments",
            "github.paginate",
            "receiptSourceId",
            "const ACTIONS_BOT_ID = 41898282;",
            "comment?.user?.login === 'github-actions[bot]'",
            "comment?.user?.type === 'Bot'",
            "const lastConsumedId = Math.max",
            "Number(comment.id) > lastConsumedId",
            "await findPendingCommand()",
        ):
            self.assertIn(required, self.workflow)

    def test_successful_dispatch_writes_bound_receipt(self) -> None:
        for required in (
            "github.rest.issues.createComment",
            "bench.command-receipt.v1",
            "source_comment_id: comment.id",
            "target_workflow: workflowId",
            "dispatcher_run_id: context.runId",
            "dispatcher_run_attempt: Number(process.env.RUN_ATTEMPT)",
        ):
            self.assertIn(required, self.workflow)

    def test_every_target_explicitly_supports_manual_dispatch(self) -> None:
        for target in TARGETS.values():
            workflow = (ROOT / ".github" / "workflows" / target).read_text(
                encoding="utf-8"
            )
            self.assertIn("workflow_dispatch:", workflow, target)


if __name__ == "__main__":
    unittest.main()
