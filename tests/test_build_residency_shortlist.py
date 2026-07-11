from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scripts.build_residency_shortlist import EXPECTED_PROFILE, ShortlistError, build_shortlist, run


def gpu_snapshot(used: int = 500) -> dict[str, object]:
    return {
        "ok": True,
        "gpus": [{
            "index": 0,
            "name": "GPU",
            "memory_total_mib": 12282,
            "memory_used_mib": used,
            "utilization_gpu_percent": 0,
        }],
    }


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
            "profile": dict(EXPECTED_PROFILE),
        }
    common = {
        "model": {"name": name, "digest": digest},
        "profile": dict(EXPECTED_PROFILE),
        "probe_duration_seconds": 1.0,
        "gpu_before": gpu_snapshot(100),
        "gpu_loaded": gpu_snapshot(800),
        "cleanup_after": {"verified_absent": True},
    }
    if classification == "load_failed":
        return {**common, "classification": "load_failed", "error": {"type": "ProbeError", "detail": "load failed"}}
    return {
        **common,
        "classification": classification,
        "residency_ratio": size_vram / size,
        "ollama_generate": {"done": True},
        "ollama_ps_entry": {
            "name": name,
            "model": name,
            "digest": digest,
            "size": size,
            "size_vram": size_vram,
            "context_length": 4096,
        },
        "error": None,
    }


def valid_report() -> dict[str, object]:
    models = [
        model_result("full:latest", "a" * 64, "full_vram"),
        model_result("partial:latest", "b" * 64, "partial_vram", size_vram=750),
        model_result("gemma4:27b", "c" * 64, "excluded"),
    ]
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
        "initial_gpu": gpu_snapshot(),
        "initial_cleanup": [],
        "infrastructure_error": None,
        "classification_counts": {"full_vram": 1, "partial_vram": 1, "excluded": 1},
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
        self.assertEqual([entry["name"] for entry in shortlist["primary_h2"]], ["full:latest"])
        self.assertEqual([entry["name"] for entry in shortlist["secondary_partial_vram"]], ["partial:latest"])
        self.assertEqual(shortlist["deferred"][0]["classification"], "excluded")

    def test_duplicate_digest_alias_is_deferred_not_rejected(self):
        report = valid_report()
        alias = model_result("full:alias", "a" * 64, "full_vram")
        report["models"].append(alias)
        report["classification_counts"]["full_vram"] = 2
        shortlist = build_shortlist(report)
        self.assertEqual([entry["name"] for entry in shortlist["primary_h2"]], ["full:alias"])
        deferred_alias = next(entry for entry in shortlist["deferred"] if entry["name"] == "full:latest")
        self.assertEqual(deferred_alias["deferred_reason"], "duplicate_digest_alias")
        self.assertEqual(deferred_alias["canonical_name"], "full:alias")
        self.assertEqual(shortlist["counts"]["model_results"], 4)

    def test_rejects_unverified_cleanup(self):
        report = valid_report()
        report["models"][0]["cleanup_after"]["verified_absent"] = False
        with self.assertRaisesRegex(ShortlistError, "cleanup"):
            build_shortlist(report)

    def test_rejects_failed_gpu_snapshot(self):
        report = valid_report()
        report["models"][0]["gpu_loaded"] = {"ok": False, "gpus": []}
        with self.assertRaisesRegex(ShortlistError, "GPU snapshot"):
            build_shortlist(report)

    def test_rejects_profile_and_context_drift(self):
        report = valid_report()
        report["profile"]["seed"] = 7
        with self.assertRaisesRegex(ShortlistError, "complete fixed H1 profile"):
            build_shortlist(report)
        report = valid_report()
        report["models"][0]["ollama_ps_entry"]["context_length"] = 32768
        with self.assertRaisesRegex(ShortlistError, "context length"):
            build_shortlist(report)

    def test_rejects_incomplete_workflow_identity(self):
        report = valid_report()
        report["workflow"]["run_attempt"] = None
        with self.assertRaisesRegex(ShortlistError, "workflow identity"):
            build_shortlist(report)

    def test_rejects_inconsistent_classification_or_counts(self):
        report = valid_report()
        report["models"][0]["classification"] = "partial_vram"
        report["classification_counts"] = {"partial_vram": 2, "excluded": 1}
        with self.assertRaisesRegex(ShortlistError, "classification"):
            build_shortlist(report)
        report = valid_report()
        report["classification_counts"] = {"full_vram": 3}
        with self.assertRaisesRegex(ShortlistError, "counts"):
            build_shortlist(report)

    def test_no_full_vram_models_is_blocked_not_invalid(self):
        report = valid_report()
        report["models"] = report["models"][1:]
        report["classification_counts"] = {"partial_vram": 1, "excluded": 1}
        self.assertEqual(build_shortlist(report)["status"], "blocked_no_full_vram_models")

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
                    "artifacts": {
                        "report.json": {"sha256": digest(report_path), "size_bytes": report_path.stat().st_size},
                        "models/candidate/result.json": {"sha256": digest(model_path), "size_bytes": model_path.stat().st_size},
                    },
                },
            )
            shortlist = run(root)
            self.assertEqual(shortlist["status"], "ready")
            manifest = json.loads((root / "shortlist-manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(set(manifest["artifacts"]), {"report.json", "manifest.json", "shortlist.json", "shortlist.md"})

    def test_run_rejects_tampered_residency_artifact(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report_path = root / "report.json"
            write_json(report_path, valid_report())
            write_json(
                root / "manifest.json",
                {
                    "schema_version": "bench.model-residency-manifest.v1",
                    "artifacts": {"report.json": {"sha256": "0" * 64, "size_bytes": report_path.stat().st_size}},
                },
            )
            with self.assertRaisesRegex(ShortlistError, "digest"):
                run(root)


if __name__ == "__main__":
    unittest.main()
