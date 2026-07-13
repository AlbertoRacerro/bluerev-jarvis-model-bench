from __future__ import annotations

import argparse
from pathlib import Path

from scripts import probe_ho_route_explicit_replay as probe
from scripts import run_direct_semantic_campaign_bound_job as base_bound
from scripts import run_ho_route_explicit_replay_job as job

probe.os = base_bound.probe.os
base_bound.probe = probe
base_bound.job = job


def capture(artifact_dir: Path = job.DEFAULT_ARTIFACTS) -> int:
    base_bound.probe = probe
    base_bound.job = job
    return base_bound.capture(artifact_dir)


def enforce(artifact_dir: Path = job.DEFAULT_ARTIFACTS) -> int:
    base_bound.probe = probe
    base_bound.job = job
    job.base_job._validate_campaign_manifest = (
        base_bound._campaign_manifest_without_nested_manifests
    )
    return base_bound.enforce(artifact_dir)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("capture", "enforce"))
    parser.add_argument("--artifact-dir", type=Path, default=job.DEFAULT_ARTIFACTS)
    args = parser.parse_args()
    return capture(args.artifact_dir) if args.mode == "capture" else enforce(args.artifact_dir)


if __name__ == "__main__":
    raise SystemExit(main())
