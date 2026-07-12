from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scripts import run_h2_context_job as job


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class H2ContextJobTests(unittest.TestCase):
    def make_complete_artifact(self, root: Path) -> None:
        write_json(
            root / "job-summary.json",
            {
                "schema_version": "bench.h2-context-job.v1",
                "test_scope": "h2-primary-16k",
                "tests": {"exit_code": 0},
                "probe": {"exit_code": 0},
            },
        )
        probe = root / "h2-primary-16k"
        results = []
        for index in range(12):
            slug = f"model-{index}"
            result = {
                "schema_version": "bench.h2-context-result.v1",
                "artifact_slug": slug,
                "model": {"name": slug, "digest": f"{index:x}" * 64},
                "status": "qualified_16k" if index < 10 else "cpu_offload",
                "cleanup_after": {"verified_absent": True, "models": []},
            }
            write_json(probe / "models" / slug / "result.json", result)
            results.append(result)
        report = {
            "schema_version": "bench.h2-context-report.v1",
            "source": {"plan_sha256": job.EXPECTED_PLAN_SHA256},
            "infrastructure_error": None,
            "results": results,
            "final_cleanup": [],
            "status_counts": {
                "qualified_16k": 10,
                "cpu_offload": 2,
                "context_mismatch": 0,
                "load_failed": 0,
            },
        }
        write_json(probe / "report.json", report)
        paths = [probe / "report.json"]
        paths.extend(sorted((probe / "models").glob("*/result.json")))
        write_json(
            probe / "manifest.json",
            {
                "schema_version": "bench.h2-context-manifest.v1",
                "artifacts": {
                    path.relative_to(probe).as_posix(): {
                        "sha256": digest(path),
                        "size_bytes": path.stat().st_size,
                    }
                    for path in paths
                },
            },
        )

    def test_enforce_accepts_complete_evidence_with_expected_exclusions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_complete_artifact(root)
            self.assertEqual(job.enforce(root), 0)

    def test_enforce_rejects_incomplete_candidate_inventory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_complete_artifact(root)
            report_path = root / "h2-primary-16k" / "report.json"
            report = json.loads(report_path.read_text(encoding="utf-8"))
            report["results"].pop()
            write_json(report_path, report)
            self.assertEqual(job.enforce(root), 1)

    def test_enforce_rejects_probe_infrastructure_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_json(
                root / "job-summary.json",
                {
                    "schema_version": "bench.h2-context-job.v1",
                    "test_scope": "h2-primary-16k",
                    "tests": {"exit_code": 0},
                    "probe": {"exit_code": 2},
                },
            )
            self.assertEqual(job.enforce(root), 1)


if __name__ == "__main__":
    unittest.main()
