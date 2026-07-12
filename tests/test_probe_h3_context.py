from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from scripts import probe_h3_context as h3


ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "fixtures" / "h3" / "h2-primary-32k-plan.json"
SUMMARY = ROOT / "reports" / "H2-PRIMARY-16K" / "summary.json"
MANIFEST = ROOT / "reports" / "H2-PRIMARY-16K" / "manifest.json"


class H3ContextProbeTests(unittest.TestCase):
    def test_validates_exact_bound_plan_and_summary(self) -> None:
        candidates = h3.validate_plan(
            PLAN,
            SUMMARY,
            MANIFEST,
            h3.EXPECTED_PLAN_SHA256,
        )
        self.assertEqual(len(candidates), 10)
        self.assertEqual(candidates[0]["name"], "gemma4:12b-it-qat")
        self.assertEqual(candidates[-1]["name"], "qwythos-hermes-safe:latest")

    def test_accepts_crlf_working_tree_for_bound_source_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan = root / "plan.json"
            summary = root / "summary.json"
            manifest = root / "manifest.json"
            for source, target in (
                (PLAN, plan),
                (SUMMARY, summary),
                (MANIFEST, manifest),
            ):
                target.write_bytes(
                    source.read_text(encoding="utf-8")
                    .replace("\n", "\r\n")
                    .encode("utf-8")
                )
            candidates = h3.validate_plan(
                plan,
                summary,
                manifest,
                h3.EXPECTED_PLAN_SHA256,
            )
            self.assertEqual(len(candidates), 10)

    def test_rejects_tampered_plan_before_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan = root / "plan.json"
            shutil.copyfile(PLAN, plan)
            value = json.loads(plan.read_text(encoding="utf-8"))
            value["profile"]["num_ctx"] = 65536
            plan.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")
            with self.assertRaisesRegex(h3.H3ProbeError, "plan digest mismatch"):
                h3.validate_plan(
                    plan,
                    SUMMARY,
                    MANIFEST,
                    h3.EXPECTED_PLAN_SHA256,
                )

    def test_selects_exact_two_model_batches(self) -> None:
        candidates = [
            {"name": f"model-{index}", "digest": f"{index:x}" * 64}
            for index in range(10)
        ]
        selected, selection = h3.select_candidates(candidates, batch_index=3)
        self.assertEqual(
            [item["name"] for item in selected],
            ["model-6", "model-7"],
        )
        self.assertEqual(
            selection,
            {
                "mode": "batch",
                "batch_index": 3,
                "batch_size": 2,
                "start": 6,
                "end": 8,
                "expected_count": 2,
                "total_candidates": 10,
            },
        )
        with self.assertRaisesRegex(h3.H3ProbeError, "outside"):
            h3.select_candidates(candidates, batch_index=5)

    def test_classifies_full_vram_offload_and_context_mismatch(self) -> None:
        response = {"done": True}
        full = {"context_length": 32768, "size": 100, "size_vram": 100}
        partial = {"context_length": 32768, "size": 100, "size_vram": 75}
        wrong_context = {"context_length": 16384, "size": 100, "size_vram": 100}
        self.assertEqual(
            h3._classify_result(response, full, None)[0],
            "qualified_32k",
        )
        status, ratio, error = h3._classify_result(response, partial, None)
        self.assertEqual(status, "cpu_offload")
        self.assertEqual(ratio, 0.75)
        self.assertIsNone(error)
        status, ratio, error = h3._classify_result(
            response,
            wrong_context,
            None,
        )
        self.assertEqual(status, "context_mismatch")
        self.assertIsNone(ratio)
        self.assertIn("32768", error["detail"])


if __name__ == "__main__":
    unittest.main()
