from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scripts.build_residency_shortlist import ShortlistError, run


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def model(name: str) -> dict[str, object]:
    return {
        "model": {"name": name, "digest": "a" * 64},
        "classification": "full_vram",
        "residency_ratio": 1.0,
        "probe_duration_seconds": 1.0,
        "ollama_ps_entry": {"size": 1000, "size_vram": 1000},
        "cleanup_after": {"verified_absent": True},
        "error": None,
    }


def report(entry: dict[str, object]) -> dict[str, object]:
    return {
        "schema_version": "bench.model-residency.v1",
        "workflow": {"run_id": "1"},
        "profile": {"name": "h1-4k-residency", "num_ctx": 4096},
        "initial_gpu": {
            "ok": True,
            "gpus": [{"memory_total_mib": 12282, "memory_used_mib": 100}],
        },
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
