from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import probe_model_residency as base
from scripts import probe_model_residency_v2 as hardened


def gpu_snapshot() -> dict[str, object]:
    return {
        "ok": True,
        "gpus": [
            {
                "index": 0,
                "name": "GPU",
                "memory_total_mib": 12000,
                "memory_used_mib": 100,
                "utilization_gpu_percent": 0,
            }
        ],
    }


def model() -> dict[str, object]:
    return {
        "name": "candidate:latest",
        "digest": "a" * 64,
        "size": 1000,
    }


class HardenedResidencyCleanupTests(unittest.TestCase):
    def test_final_recheck_rejects_new_running_model(self) -> None:
        with (
            patch.object(
                base,
                "running_models",
                side_effect=[
                    [{"name": "candidate:latest"}],
                    [{"name": "intruder:latest"}],
                ],
            ),
            patch.object(
                base,
                "stop_model",
                return_value={"verified_absent": True},
            ),
        ):
            with self.assertRaisesRegex(
                base.InfrastructureProbeError,
                "cleanup left running models: intruder:latest",
            ):
                hardened.stop_all_running_models()

    def test_singleton_failure_still_runs_recovery_cleanup(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with (
                patch.object(
                    hardened,
                    "stop_all_running_models",
                    side_effect=[[], []],
                ) as cleanup,
                patch.object(base, "gpu_snapshot", return_value=gpu_snapshot()),
                patch.object(
                    base,
                    "_request_json",
                    return_value={"done": True},
                ),
                patch.object(
                    base,
                    "_find_single_running_model",
                    side_effect=base.InfrastructureProbeError(
                        "expected exactly one running Ollama model"
                    ),
                ),
            ):
                with self.assertRaisesRegex(
                    base.InfrastructureProbeError,
                    "expected exactly one running Ollama model",
                ):
                    hardened.probe_model(model(), Path(directory))
        self.assertEqual(cleanup.call_count, 2)

    def test_unexpected_exception_still_runs_recovery_cleanup(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with (
                patch.object(
                    hardened,
                    "stop_all_running_models",
                    side_effect=[[], []],
                ) as cleanup,
                patch.object(base, "gpu_snapshot", return_value=gpu_snapshot()),
                patch.object(
                    base,
                    "_request_json",
                    side_effect=RuntimeError("unexpected bug"),
                ),
            ):
                with self.assertRaisesRegex(RuntimeError, "unexpected bug"):
                    hardened.probe_model(model(), Path(directory))
        self.assertEqual(cleanup.call_count, 2)

    def test_successful_probe_records_empty_cleanup_attestation(self) -> None:
        candidate = model()
        process = {
            "name": candidate["name"],
            "model": candidate["name"],
            "digest": candidate["digest"],
            "size": 1000,
            "size_vram": 1000,
            "context_length": 4096,
        }
        with tempfile.TemporaryDirectory() as directory:
            with (
                patch.object(
                    hardened,
                    "stop_all_running_models",
                    side_effect=[[], []],
                ),
                patch.object(base, "gpu_snapshot", return_value=gpu_snapshot()),
                patch.object(
                    base,
                    "_request_json",
                    return_value={"done": True},
                ),
                patch.object(
                    base,
                    "_find_single_running_model",
                    return_value=process,
                ),
            ):
                result = hardened.probe_model(candidate, Path(directory))
        self.assertEqual(result["classification"], "full_vram")
        self.assertEqual(
            result["cleanup_after"],
            {"verified_absent": True, "models": []},
        )

    def test_main_rejects_stale_h1_evidence_before_hardware_access(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "report.json").write_text("{}\n", encoding="utf-8")
            with (
                patch.object(
                    sys,
                    "argv",
                    ["probe_model_residency_v2.py", "--output-dir", str(root)],
                ),
                patch.object(hardened, "build_report") as build_report,
            ):
                self.assertEqual(hardened.main(), 2)
        build_report.assert_not_called()


if __name__ == "__main__":
    unittest.main()
