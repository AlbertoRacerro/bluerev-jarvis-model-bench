from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts import probe_h2_context as h2


ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "fixtures" / "h2" / "h1-primary-context-plan.json"


class H2ContextProbeTests(unittest.TestCase):
    def test_validates_exact_bound_primary_plan(self) -> None:
        candidates = h2.validate_plan(PLAN, h2.EXPECTED_PLAN_SHA256)
        self.assertEqual(len(candidates), 12)
        self.assertEqual(len({item["name"] for item in candidates}), 12)
        self.assertEqual(len({item["digest"] for item in candidates}), 12)

    def test_rejects_tampered_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "plan.json"
            value = json.loads(PLAN.read_text(encoding="utf-8"))
            value["cases"][0]["candidate"]["name"] = "tampered"
            path.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaisesRegex(h2.H2ProbeError, "digest mismatch"):
                h2.validate_plan(path, h2.EXPECTED_PLAN_SHA256)

    def test_classifies_full_vram_16k_as_qualified(self) -> None:
        status, ratio, error = h2._classify_result(
            {"done": True},
            {"context_length": 16384, "size": 100, "size_vram": 100},
            None,
        )
        self.assertEqual(status, "qualified_16k")
        self.assertEqual(ratio, 1.0)
        self.assertIsNone(error)

    def test_classifies_context_mismatch_before_residency(self) -> None:
        status, ratio, error = h2._classify_result(
            {"done": True},
            {"context_length": 4096, "size": 100, "size_vram": 100},
            None,
        )
        self.assertEqual(status, "context_mismatch")
        self.assertIsNone(ratio)
        self.assertIn("context_length", error["detail"])

    def test_classifies_partial_vram_as_cpu_offload(self) -> None:
        status, ratio, error = h2._classify_result(
            {"done": True},
            {"context_length": 16384, "size": 100, "size_vram": 60},
            None,
        )
        self.assertEqual(status, "cpu_offload")
        self.assertEqual(ratio, 0.6)
        self.assertIsNone(error)

    def test_installed_primary_requires_exact_digest(self) -> None:
        candidate = {"name": "model-a", "digest": "a" * 64}
        with mock.patch.object(
            h2.base,
            "list_installed_models",
            return_value=[{"name": "model-a", "digest": "b" * 64, "size": 1}],
        ):
            with self.assertRaisesRegex(h2.H2InfrastructureError, "digest changed"):
                h2._installed_primary([candidate])

    def test_metric_rate_is_bounded_and_deterministic(self) -> None:
        self.assertEqual(h2._metric_rate(32, 2_000_000_000), 16.0)
        self.assertIsNone(h2._metric_rate(32, 0))
        self.assertIsNone(h2._metric_rate(True, 1))


if __name__ == "__main__":
    unittest.main()
