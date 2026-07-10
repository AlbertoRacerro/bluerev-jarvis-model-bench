from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.probe_model_residency import (
    _is_exact_loopback_url,
    classify_residency,
    is_user_excluded,
    parse_nvidia_smi_csv,
    write_manifest,
)


class ModelResidencyProbeTests(unittest.TestCase):
    def test_exact_loopback_endpoint_accepts_expected_path(self):
        self.assertTrue(
            _is_exact_loopback_url(
                "http://127.0.0.1:11434/api/ps",
                "/api/ps",
            )
        )

    def test_endpoint_rejects_hostname_query_and_wrong_path(self):
        self.assertFalse(
            _is_exact_loopback_url(
                "http://localhost:11434/api/ps",
                "/api/ps",
            )
        )
        self.assertFalse(
            _is_exact_loopback_url(
                "http://127.0.0.1:11434/api/ps?model=x",
                "/api/ps",
            )
        )
        self.assertFalse(
            _is_exact_loopback_url(
                "http://127.0.0.1:11434/api/tags",
                "/api/ps",
            )
        )

    def test_parse_nvidia_smi_csv(self):
        rows = parse_nvidia_smi_csv("0, NVIDIA RTX, 12282, 2048, 17\n")
        self.assertEqual(
            rows,
            [
                {
                    "index": 0,
                    "name": "NVIDIA RTX",
                    "memory_total_mib": 12282,
                    "memory_used_mib": 2048,
                    "utilization_gpu_percent": 17,
                }
            ],
        )

    def test_residency_classification_boundaries(self):
        self.assertEqual(classify_residency(1000, 1000), ("full_vram", 1.0))
        self.assertEqual(classify_residency(1000, 980), ("full_vram", 0.98))
        self.assertEqual(classify_residency(1000, 979), ("partial_vram", 0.979))
        self.assertEqual(classify_residency(1000, 0), ("cpu_only", 0.0))
        self.assertEqual(classify_residency(None, 0), ("unknown", None))

    def test_explicit_gemma_27b_exclusion_is_narrow(self):
        self.assertTrue(is_user_excluded("gemma4:27b"))
        self.assertTrue(is_user_excluded("gemma4:27b-it-qat"))
        self.assertFalse(is_user_excluded("gemma4:31b-it-qat"))
        self.assertFalse(is_user_excluded("gemma4:12b-it-qat"))

    def test_manifest_binds_report_and_per_model_results(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "report.json").write_text("{}\n", encoding="utf-8")
            model_path = root / "models" / "candidate" / "result.json"
            model_path.parent.mkdir(parents=True)
            model_path.write_text('{"classification":"full_vram"}\n', encoding="utf-8")

            manifest = write_manifest(root)

            self.assertEqual(
                set(manifest["artifacts"]),
                {"report.json", "models/candidate/result.json"},
            )
            stored = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(stored, manifest)
            for item in manifest["artifacts"].values():
                self.assertRegex(item["sha256"], r"^[0-9a-f]{64}$")


if __name__ == "__main__":
    unittest.main()
