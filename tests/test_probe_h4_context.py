from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts import probe_h4_context as probe

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "fixtures" / "h4" / "h3-lane1-hermes-minimum-64k-plan.json"
SUMMARY = ROOT / "reports" / "H3-PRIMARY-32K" / "summary.json"
MANIFEST = ROOT / "reports" / "H3-PRIMARY-32K" / "manifest.json"


class H4ProbeTests(unittest.TestCase):
    def test_plan_binds_all_ten_h3_candidates(self):
        candidates = probe.validate_plan(
            PLAN,
            SUMMARY,
            MANIFEST,
            probe.EXPECTED_PLAN_SHA256,
        )
        self.assertEqual(len(candidates), 10)
        self.assertEqual(len({item["name"] for item in candidates}), 10)
        self.assertEqual(len({item["digest"] for item in candidates}), 10)
        self.assertEqual(probe.PROFILE["num_ctx"], 65536)

    def test_batches_cover_all_candidates_exactly_once(self):
        candidates = probe.validate_plan(
            PLAN,
            SUMMARY,
            MANIFEST,
            probe.EXPECTED_PLAN_SHA256,
        )
        observed = []
        for index in range(probe.BATCH_COUNT):
            selected, selection = probe.select_candidates(candidates, batch_index=index)
            self.assertEqual(len(selected), 2)
            self.assertEqual(selection["expected_count"], 2)
            observed.extend(selected)
        self.assertEqual(observed, candidates)

    def test_non_pass_direct_models_are_not_filtered(self):
        candidates = probe.validate_plan(
            PLAN,
            SUMMARY,
            MANIFEST,
            probe.EXPECTED_PLAN_SHA256,
        )
        names = {item["name"] for item in candidates}
        self.assertIn("qwen3:8b", names)
        self.assertIn(
            "hf.co/empero-ai/Qwable-9B-Claude-Fable-5-GGUF:Q4_K_M",
            names,
        )
        self.assertIn(
            "hf.co/GnLOLot/MiniCPM5-1B-Claude-Opus-Fable5-Thinking-GGUF:Q4_K_M",
            names,
        )

    def test_classification_requires_exact_65536_context(self):
        response = {"done": True}
        status, ratio, error = probe._classify_result(
            response,
            {"context_length": 32768, "size": 100, "size_vram": 100},
            None,
        )
        self.assertEqual(status, "context_mismatch")
        self.assertIsNone(ratio)
        self.assertIn("65536", error["detail"])

        status, ratio, error = probe._classify_result(
            response,
            {"context_length": 65536, "size": 100, "size_vram": 100},
            None,
        )
        self.assertEqual(status, "qualified_64k")
        self.assertEqual(ratio, 1.0)
        self.assertIsNone(error)

    def test_tampered_plan_is_rejected(self):
        plan = json.loads(PLAN.read_text(encoding="utf-8"))
        plan["candidates"] = plan["candidates"][:-1]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "plan.json"
            path.write_text(
                json.dumps(plan, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(probe.H4ProbeError, "digest mismatch"):
                probe.validate_plan(
                    path,
                    SUMMARY,
                    MANIFEST,
                    probe.EXPECTED_PLAN_SHA256,
                )


if __name__ == "__main__":
    unittest.main()
