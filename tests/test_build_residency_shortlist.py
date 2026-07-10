from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scripts.build_residency_shortlist import (
    ShortlistError,
    build_shortlist,
    run,
)


def model_result(
    name: str,
    digest: str,
    classification: str,
    *,
    size: int = 1000,
    size_vram: int = 1000,
) -> dict[str, object]:
    if classification == "excluded":
        return {
            "model": {"name": name, "digest": digest},
            "classification": "excluded",
            "reason": "explicit_user_exclusion",
            "profile": {"num_ctx": 4096},
        }
    if classification == "load_failed":
        return {
            "model": {"name": name, "digest": digest},
            "classification": "load_failed",
            "probe_duration_seconds": 1.0,
            "cleanup_after": {"verified_absent": True},
            "error": {"type": "ProbeError", "detail": "load failed"},
        }
    return {
        "model": {"name": name, "digest": digest},
        "classification": classification,
        "residency_ratio": size_vram / size,
        "probe_duration_seconds": 1.0,
        "ollama_ps_entry": {"size": size, "size_vram": size_vram},
        "cleanup_after": {"verified_absent": True},
        "error": None,
    }


def valid_report() -> dict[str, object]:
    models = [
        model_result("full:latest", "a" * 64, "full_vram"),
        model_result(
            "partial:latest",
            "b" * 64,
            "partial_vram",
            size=1000,
            size_vram=750,
        ),
        model_result("gemma4:27b", "c" * 64, "excluded"),
    ]
    return {
        "schema_version": "bench.model-residency.v1",
        "created_at_utc": "2026-07-10T00:00:00Z",
        "workflow": {"run_id": "1", "sha": "abc"},
        "profile": {"name": "h1-4k-residency", "num_ctx": 4096},
        "explicit_exclusions": ["gemma4:27b"],
        "initial_gpu": {
            "ok": True,
            "gpus": [
                {
                    "index": 0,
                    "name": "GPU",
                    "memory_total_mib": 12282,
                    "memory_used_mib": 500,
                }
            ],
        },
        "initial_cleanup": [],
        "infrastructure_error": None,
        "classification_counts": {
            "full_vram": 1,
            "partial_vram": 1,
            "excluded": 1,
        },
        "models": models,
    }


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ResidencyShortlistTests(unittest.TestCase):
    def test_builds_primary_and_secondary_lists(self):
        shortlist = build_shortlist(valid_report())
        self.assertEqual(shortlist["status"], "ready")
        self.assertEqual(
            [entry["name"] for entry in shortlist["primary_h2"]],
            ["full:latest"],
        )
        self.assertEqual(
            [entry["name"] for entry in shortlist["secondary_partial_vram"]],
            ["partial:latest"],
        )
        self.assertEqual(shortlist["deferred"][0]["classification"], "excluded")

    def test_rejects_unverified_cleanup(self):
        report = valid_report()
        report["models"][0]["cleanup_after"]["verified_absent"] = False
        with self.assertRaisesRegex(ShortlistError, "cleanup"):
            build_shortlist(report)

    def test_rejects_inconsistent_classification(self):
        report = valid_report()
        report["models"][0]["classification"] = "partial_vram"
        report["classification_counts"] = {
            "partial_vram": 2,
            "excluded": 1,
        }
        with self.assertRaisesRegex(ShortlistError, "classification"):
            build_shortlist(report)

    def test_rejects_count_drift(self):
        report = valid_report()
        report["classification_counts"] = {"full_vram": 3}
        with self.assertRaisesRegex(ShortlistError, "counts"):
            build_shortlist(report)

    def test_no_full_vram_models_is_blocked_not_invalid(self):
        report = valid_report()
        report["models"] = report["models"][1:]
        report["classification_counts"] = {
            "partial_vram": 1,
            "excluded": 1,
        }
        shortlist = build_shortlist(report)
        self.assertEqual(shortlist["status"], "blocked_no_full_vram_models")

    def test_run_validates_manifest_and_binds_shortlist(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report_path = root / "report.json"
            model_path = root / "models" / "candidate" / "result.json"
            report = valid_report()
            report["models"] = [report["models"][0]]
            report["classification_counts"] = {"full_vram": 1}
            write_json(report_path, report)
            write_json(model_path, report["models"][0])
            write_json(
                root / "manifest.json",
                {
                    "schema_version": "bench.model-residency-manifest.v1",
                    "created_at_utc": "2026-07-10T00:00:00Z",
                    "artifacts": {
                        "report.json": {
                            "sha256": digest(report_path),
                            "size_bytes": report_path.stat().st_size,
                        },
                        "models/candidate/result.json": {
                            "sha256": digest(model_path),
                            "size_bytes": model_path.stat().st_size,
                        },
                    },
                },
            )

            shortlist = run(root)

            self.assertEqual(shortlist["status"], "ready")
            self.assertTrue((root / "shortlist.json").is_file())
            self.assertTrue((root / "shortlist.md").is_file())
            manifest = json.loads(
                (root / "shortlist-manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(
                set(manifest["artifacts"]),
                {"report.json", "manifest.json", "shortlist.json", "shortlist.md"},
            )

    def test_run_rejects_tampered_residency_artifact(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report_path = root / "report.json"
            write_json(report_path, valid_report())
            write_json(
                root / "manifest.json",
                {
                    "schema_version": "bench.model-residency-manifest.v1",
                    "artifacts": {
                        "report.json": {
                            "sha256": "0" * 64,
                            "size_bytes": report_path.stat().st_size,
                        }
                    },
                },
            )
            with self.assertRaisesRegex(ShortlistError, "digest"):
                run(root)


if __name__ == "__main__":
    unittest.main()
