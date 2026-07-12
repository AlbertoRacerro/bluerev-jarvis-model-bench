from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from scripts import run_h3_context_job as job

def write_json(path,value): path.parent.mkdir(parents=True,exist_ok=True); path.write_text(json.dumps(value,indent=2,sort_keys=True)+"\n",encoding="utf-8")
def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()

class H3ContextJobTests(unittest.TestCase):
    def test_batch_index_is_allowlisted(self):
        for index in range(5):
            with mock.patch.dict(os.environ,{"BENCH_H3_BATCH_INDEX":str(index)},clear=False): self.assertEqual(job.batch_index_from_environment(),index); self.assertEqual(job.selection_for(index)["start"],index*2)
        with mock.patch.dict(os.environ,{"BENCH_H3_BATCH_INDEX":"5"},clear=False):
            with self.assertRaisesRegex(ValueError,"outside"): job.batch_index_from_environment()
    def test_source_files_are_bound_to_closeout(self):
        self.assertTrue(job._source_files_are_bound()); self.assertEqual(job._source_sha256(job.PLAN_PATH),job.EXPECTED_PLAN_SHA256); self.assertEqual(job._source_sha256(job.SUMMARY_PATH),job.EXPECTED_SUMMARY_SHA256); self.assertEqual(job._source_sha256(job.SUMMARY_MANIFEST_PATH),job.EXPECTED_SUMMARY_MANIFEST_SHA256)
    def make_artifact(self,root,status="cpu_offload"):
        selection=job.selection_for(0); expected=job._expected_batch_candidates(0); write_json(root/"job-summary.json",{"schema_version":"bench.h3-context-job.v1","test_scope":"h3-primary-32k-batch","selection":selection,"tests":{"exit_code":0},"probe":{"exit_code":0}}); results=[]; probe_dir=root/"h3-primary-32k"
        for sequence,candidate in enumerate(expected):
            slug=f"model-{sequence}"; result={"schema_version":"bench.h3-context-result.v1","artifact_slug":slug,"model":candidate,"profile":job.PROFILE,"status":status if sequence==0 else "qualified_32k","cleanup_after":{"verified_absent":True}}; results.append(result); write_json(probe_dir/"models"/slug/"result.json",result)
        report={"schema_version":"bench.h3-context-report.v1","source":{"plan_sha256":job.EXPECTED_PLAN_SHA256,"h2_summary_sha256":job.EXPECTED_SUMMARY_SHA256,"h2_summary_manifest_sha256":job.EXPECTED_SUMMARY_MANIFEST_SHA256},"profile":job.PROFILE,"selection":selection,"infrastructure_error":None,"results":results,"final_cleanup":[],"status_counts":{"qualified_32k":1,"cpu_offload":1,"context_mismatch":0,"load_failed":0}}; write_json(probe_dir/"report.json",report); paths=[probe_dir/"report.json",*[probe_dir/"models"/item["artifact_slug"]/"result.json" for item in results]]; write_json(probe_dir/"manifest.json",{"schema_version":"bench.h3-context-manifest.v1","artifacts":{path.relative_to(probe_dir).as_posix():{"sha256":digest(path),"size_bytes":path.stat().st_size} for path in paths}})
    def test_candidate_offload_is_valid_evidence(self):
        with tempfile.TemporaryDirectory() as tmp: root=Path(tmp); self.make_artifact(root); self.assertEqual(job.enforce(root),0)
    def test_rejects_candidate_identity_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); self.make_artifact(root); report_path=root/"h3-primary-32k"/"report.json"; report=json.loads(report_path.read_text(encoding="utf-8")); report["results"][0]["model"]["name"]="tampered"; write_json(report_path,report); manifest_path=root/"h3-primary-32k"/"manifest.json"; manifest=json.loads(manifest_path.read_text(encoding="utf-8")); manifest["artifacts"]["report.json"]={"sha256":digest(report_path),"size_bytes":report_path.stat().st_size}; write_json(manifest_path,manifest); self.assertEqual(job.enforce(root),1)

if __name__=="__main__": unittest.main()
