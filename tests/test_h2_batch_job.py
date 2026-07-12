from __future__ import annotations

import os
import unittest
from unittest import mock

from scripts import probe_h2_context_batch as probe
from scripts import run_h2_context_batch_job as job


class H2BatchTests(unittest.TestCase):
    def test_selects_four_nonoverlapping_three_model_batches(self) -> None:
        candidates = [
            {"name": str(index), "digest": f"{index:x}" * 64}
            for index in range(12)
        ]
        observed: list[dict[str, str]] = []
        for index in range(4):
            selected, selection = probe.select_candidates(
                candidates, batch_index=index, batch_size=3
            )
            self.assertEqual(selection["expected_count"], 3)
            observed.extend(selected)
        self.assertEqual(observed, candidates)

    def test_rejects_out_of_range_batch(self) -> None:
        candidates = [
            {"name": str(index), "digest": "a" * 64}
            for index in range(12)
        ]
        with self.assertRaisesRegex(probe.H2BatchError, "beyond"):
            probe.select_candidates(candidates, batch_index=4, batch_size=3)

    def test_batch_index_is_fail_closed(self) -> None:
        for value, expected in (("0", 0), ("3", 3)):
            with mock.patch.dict(os.environ, {"BENCH_H2_BATCH_INDEX": value}):
                self.assertEqual(job.batch_index_from_environment(), expected)
        for value in ("", "-1", "4", "x"):
            with mock.patch.dict(os.environ, {"BENCH_H2_BATCH_INDEX": value}):
                with self.assertRaises(ValueError):
                    job.batch_index_from_environment()


if __name__ == "__main__":
    unittest.main()
