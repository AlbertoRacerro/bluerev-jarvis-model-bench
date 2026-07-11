from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scripts.build_residency_shortlist import EXPECTED_PROFILE, ShortlistError, run


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def gpu_snapshot(used: int) -> dict[str, object]:
    return {
        "ok": True,
        "gpus": [
            {
                "index": 0,
                "name": "GPU",
                "memory_total_mib": 12282,
                "memory_used_mib": used,
                "utilization_gpu_percent": 0,
            }
        ],
    }


def model(name: str, digest: str = "a" * 64) -> dict[str, object]:
    return {
        "model": {"name": name, "digest": digest},
        "profile": dict(EXPECTED_PROFILE),
        "classification": "full_vram",
        "residency_ratio": 1.0,
        "probe_duration_seconds": 1.0,
        "ollama_generate": {"done": True, "done_reason": "stop"},
        "ollama_ps_entry": {
            "name": name,
            "model": name,
            "digest": digest,
            "size": 1000,
            "size_vram": 1000,
            "context_length": 4096,
        },
        "gpu_before": gpu_snapshot(100),
        "gpu_loaded": gpu_snapshot(900),
        "cleanup_after": {"verified_absent": True},
        "error": None,
    }


def report(entry: dict[str, object]) -> dict[str, object]:
    return {
        "schema_version": "bench.model-residency.v1",
        "created_at_utc": "2026-07-10T00:00:00Z",
        "workflow": {
            "run_id": "1",
            "run_attempt": "1",
            "event_name": "workflow_dispatch",
            "sha": "abc",
            "ref": "refs/heads/main",
        },
        "profile": dict(EXPECTED_PROFILE),
        "explicit_exclusions": ["gemma4:27b"],
        "initial_gpu": gpu_snapshot(50),
        "initial_cleanup": [],
        "infrastructure_error": None,
        "classification_counts": {"full_vram": 1},
        "models": [entry],
    }


def write_manifest(root: Path, *paths: Path) -> None:
    write_json(
        root / "manifest.json",
        {
            "schema_version": "bench.model-residency-manifest.v1",
            "artifacts": {
                path.relative_to(root).as_posix(): {
                    "sha256": sha256(path),
                    "size_bytes": path.stat().st_size,
                }
                for path in paths
            },
        },
    )


class ResidencyEvidenceBindingTests(unittest.TestCase):
    def test_rejects_per_model_content_different_from_report(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report_path = root / "report.json"
            model_path = root / "models" / "candidate" / "result.json"
            write_json(report_path, report(model("expected:latest")))
            write_json(model_path, model("different:latest"))
            write_manifest(root, report_path, model_path)
            with self.assertRaisesRegex(ShortlistError, "does not match"):
                run(root)

    def test_rejects_missing_per_model_file_even_when_report_exists(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report_path = root / "report.json"
            write_json(report_path, report(model("expected:latest")))
            write_manifest(root, report_path)
            with self.assertRaisesRegex(ShortlistError, "count"):
                run(root)


if __name__ == "__main__":
    unittest.main()
