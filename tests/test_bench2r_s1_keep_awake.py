from __future__ import annotations

import unittest
from unittest import mock

from scripts import run_bench2r_hermes_s1_awake as awake
from scripts import validate_bench2r_s1_keep_awake as validator


class Bench2RS1KeepAwakeTests(unittest.TestCase):
    def test_non_windows_boundary_is_noop(self):
        with mock.patch.object(awake.os, "name", "posix"):
            with awake.keep_windows_awake() as state:
                self.assertFalse(state["active"])
                self.assertEqual(state["reason"], "non_windows")

    def test_windows_boundary_sets_and_restores_execution_state(self):
        observed: list[int] = []

        def fake_set(flags: int) -> int:
            observed.append(flags)
            return awake.ES_CONTINUOUS

        with (
            mock.patch.object(awake.os, "name", "nt"),
            mock.patch.object(awake, "_set_thread_execution_state", side_effect=fake_set),
        ):
            with awake.keep_windows_awake() as state:
                self.assertTrue(state["active"])

        self.assertEqual(
            observed,
            [
                awake.ES_CONTINUOUS
                | awake.ES_SYSTEM_REQUIRED
                | awake.ES_DISPLAY_REQUIRED,
                awake.ES_CONTINUOUS,
            ],
        )

    def test_windows_boundary_restores_after_body_failure(self):
        observed: list[int] = []

        def fake_set(flags: int) -> int:
            observed.append(flags)
            return awake.ES_CONTINUOUS

        with (
            mock.patch.object(awake.os, "name", "nt"),
            mock.patch.object(awake, "_set_thread_execution_state", side_effect=fake_set),
        ):
            with self.assertRaisesRegex(RuntimeError, "body failed"):
                with awake.keep_windows_awake():
                    raise RuntimeError("body failed")

        self.assertEqual(observed[-1], awake.ES_CONTINUOUS)

    def test_static_keep_awake_contract_is_valid(self):
        payload = validator.validate()
        self.assertEqual(payload["status"], "ready")
        self.assertFalse(payload["execution_authorized"])
        self.assertTrue(payload["in_process_keep_awake"])
        self.assertFalse(payload["external_helper_process"])


if __name__ == "__main__":
    unittest.main()
