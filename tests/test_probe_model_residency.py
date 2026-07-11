from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.probe_model_residency import (
    InfrastructureProbeError,
    ProbeError,
    _find_single_running_model,
    _is_exact_loopback_url,
    build_report,
    classify_residency,
    is_user_excluded,
    list_installed_models,
    model_artifact_slug,
    parse_nvidia_smi_csv,
    stop_all_running_models,
    write_manifest,
)


class ModelResidencyProbeTests(unittest.TestCase):
    def test_exact_loopback_endpoint_accepts_expected_path(self):
        self.assertTrue(_is_exact_loopback_url("http://127.0.0.1:11434/api/ps", "/api/ps"))

    def test_endpoint_rejects_hostname_query_and_wrong_path(self):
        for url, path in (
            ("http://localhost:11434/api/ps", "/api/ps"),
            ("http://127.0.0.1:11434/api/ps?model=x", "/api/ps"),
            ("http://127.0.0.1:11434/api/tags", "/api/ps"),
        ):
            with self.subTest(url=url):
                self.assertFalse(_is_exact_loopback_url(url, path))

    def test_parse_nvidia_smi_csv(self):
        self.assertEqual(
            parse_nvidia_smi_csv("0, NVIDIA RTX, 12282, 2048, 17\n"),
            [{
                "index": 0,
                "name": "NVIDIA RTX",
                "memory_total_mib": 12282,
                "memory_used_mib": 2048,
                "utilization_gpu_percent": 17,
            }],
        )

    def test_invalid_gpu_metrics_are_rejected(self):
        with self.assertRaisesRegex(ProbeError, "invalid metrics"):
            parse_nvidia_smi_csv("0, NVIDIA RTX, 100, 101, 0\n")

    def test_residency_classification_boundaries(self):
        self.assertEqual(classify_residency(1000, 1000), ("full_vram", 1.0))
        self.assertEqual(classify_residency(1000, 980), ("full_vram", 0.98))
        self.assertEqual(classify_residency(1000, 979), ("partial_vram", 0.979))
        self.assertEqual(classify_residency(1000, 0), ("cpu_only", 0.0))
        self.assertEqual(classify_residency(None, 0), ("unknown", None))

    def test_installed_inventory_rejects_malformed_entry(self):
        with patch(
            "scripts.probe_model_residency._request_json",
            return_value={"models": [{"name": "broken", "size": 1}]},
        ):
            with self.assertRaisesRegex(InfrastructureProbeError, "no digest"):
                list_installed_models()

    def test_installed_inventory_rejects_duplicate_name(self):
        inventory = {
            "models": [
                {"name": "same", "digest": "a" * 64, "size": 1},
                {"name": "same", "digest": "b" * 64, "size": 1},
            ]
        }
        with patch("scripts.probe_model_residency._request_json", return_value=inventory):
            with self.assertRaisesRegex(InfrastructureProbeError, "duplicate name"):
                list_installed_models()

    def test_installed_inventory_allows_distinct_tags_with_same_digest(self):
        digest = "a" * 64
        inventory = {
            "models": [
                {"name": "model:latest", "digest": digest, "size": 1},
                {"name": "model:alias", "digest": digest, "size": 1},
            ]
        }
        with patch("scripts.probe_model_residency._request_json", return_value=inventory):
            models = list_installed_models()
        self.assertEqual([model["name"] for model in models], ["model:alias", "model:latest"])

    def test_running_process_must_be_singleton_and_digest_bound(self):
        model = {"name": "candidate:latest", "digest": "a" * 64}
        with patch(
            "scripts.probe_model_residency.running_models",
            return_value=[
                {"name": "candidate:latest", "digest": "a" * 64},
                {"name": "other:latest", "digest": "b" * 64},
            ],
        ):
            with self.assertRaisesRegex(InfrastructureProbeError, "exactly one"):
                _find_single_running_model(model)
        with patch(
            "scripts.probe_model_residency.running_models",
            return_value=[{"name": "candidate:latest", "digest": "b" * 64}],
        ):
            with self.assertRaisesRegex(InfrastructureProbeError, "digest changed"):
                _find_single_running_model(model)

    def test_explicit_gemma_27b_exclusion_is_narrow(self):
        self.assertTrue(is_user_excluded("gemma4:27b"))
        self.assertTrue(is_user_excluded("gemma4:27b-it-qat"))
        self.assertFalse(is_user_excluded("prefix-gemma4:27b"))
        self.assertFalse(is_user_excluded("gemma4:31b-it-qat"))

    def test_model_artifact_slug_is_stable_and_collision_resistant(self):
        first = model_artifact_slug("hf.co/example/model:Q4_K_M")
        second = model_artifact_slug("hf.co_example_model:Q4_K_M")
        self.assertEqual(first, model_artifact_slug("hf.co/example/model:Q4_K_M"))
        self.assertNotEqual(first, second)
        self.assertRegex(first, r"^[A-Za-z0-9._-]+-[0-9a-f]{12}$")

    def test_unverified_unload_blocks_following_measurements(self):
        with patch(
            "scripts.probe_model_residency.running_models",
            return_value=[{"name": "candidate:latest"}],
        ), patch(
            "scripts.probe_model_residency.stop_model",
            return_value={"verified_absent": False},
        ):
            with self.assertRaisesRegex(InfrastructureProbeError, "could not verify"):
                stop_all_running_models()

    def test_initial_gpu_failure_is_infrastructure_error(self):
        with patch(
            "scripts.probe_model_residency.gpu_snapshot",
            return_value={"ok": False, "gpus": []},
        ):
            report = build_report(Path("unused"))
        self.assertIsNotNone(report["infrastructure_error"])
        self.assertEqual(report["models"], [])

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


if __name__ == "__main__":
    unittest.main()
