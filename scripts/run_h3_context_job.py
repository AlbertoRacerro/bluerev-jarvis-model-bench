from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

ROOT=Path(__file__).resolve().parents[1]; SRC=ROOT/"src"
for path in (ROOT,SRC):
    if str(path) not in sys.path: sys.path.insert(0,str(path))
from scripts.benchmark_runtime import run_captured,safe_reset_directory,sanitize_environment
from scripts.test_subset import run_test_subset

DEFAULT_ARTIFACTS=ROOT/"artifacts"/"context-32k-qualification"; ARTIFACT_ROOT=ROOT/"artifacts"
PLAN_PATH=ROOT/"fixtures"/"h3"/"h2-primary-32k-plan.json"
SUMMARY_PATH=ROOT/"reports"/"H2-PRIMARY-16K"/"summary.json"
SUMMARY_MANIFEST_PATH=ROOT/"reports"/"H2-PRIMARY-16K"/"manifest.json"
EXPECTED_PLAN_SHA256="0bf7838ef0199be1dcf89122bbdedaf17ca4253223eafd0b89472bdcba3d7c12"
EXPECTED_SUMMARY_SHA256="4ae087c5aa221a80573db900cba992f3044c2205e6ded6864ea9a5c2bb02e8ca"
EXPECTED_SUMMARY_MANIFEST_SHA256="c9de10f2c151825000e8dd2635bf9c49263a9e4fcf5558add907ba24fb57cdb1"
BATCH_SIZE,BATCH_COUNT=2,5
PROFILE={"name":"h3-primary-32k-context","num_ctx":32768,"num_predict":32,"temperature":0,"seed":4242,"keep_alive":"5m","request_timeout_seconds":600}
TEST_PATTERNS=("test_benchmark_runtime.py","test_lane_test_subset.py","test_probe_model_residency.py","test_probe_model_residency_v2.py","test_probe_h3_context.py","test_run_h3_context_job.py","test_h3_oneshot_bridge.py")
_SHA256=re.compile(r"^[0-9a-f]{64}$"); _ALLOWED_RESULTS={"qualified_32k","cpu_offload","context_mismatch","load_failed"}

def _environment():
    environment,removed=sanitize_environment(os.environ); environment["PYTHONPATH"]=os.pathsep.join((str(ROOT),str(SRC))); return environment,removed
def _summary_path(artifact_dir): return artifact_dir/"job-summary.json"
def _write_summary(artifact_dir,value):
    _summary_path(artifact_dir).write_text(json.dumps(value,indent=2,sort_keys=True)+"\n",encoding="utf-8"); print(json.dumps(value,indent=2,sort_keys=True))
def _sha256(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def _source_sha256(path):
    text=path.read_text(encoding="utf-8").replace("\r\n","\n").replace("\r","\n")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
def _load_json(path):
    value=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value,dict): raise ValueError(f"{path.name} must contain an object")
    return value

def batch_index_from_environment():
    try: value=int(os.environ.get("BENCH_H3_BATCH_INDEX", ""))
    except ValueError as exc: raise ValueError("H3 batch index is missing or invalid") from exc
    if not 0<=value<BATCH_COUNT: raise ValueError("H3 batch index is outside the approved range")
    return value

def selection_for(index):
    if not 0<=index<BATCH_COUNT: raise ValueError("H3 batch index is outside the approved range")
    start=index*BATCH_SIZE; return {"mode":"batch","batch_index":index,"batch_size":2,"start":start,"end":start+2,"expected_count":2,"total_candidates":10}

def _source_files_are_bound():
    return all(path.is_file() and _source_sha256(path)==digest for path,digest in ((PLAN_PATH,EXPECTED_PLAN_SHA256),(SUMMARY_PATH,EXPECTED_SUMMARY_SHA256),(SUMMARY_MANIFEST_PATH,EXPECTED_SUMMARY_MANIFEST_SHA256)))

def capture(artifact_dir=DEFAULT_ARTIFACTS):
    safe_reset_directory(artifact_dir,allowed_root=ARTIFACT_ROOT); environment,removed=_environment()
    try: index=batch_index_from_environment(); selection=selection_for(index)
    except ValueError as exc:
        _write_summary(artifact_dir,{"schema_version":"bench.h3-context-job.v1","test_scope":"h3-primary-32k-batch","selection":{"mode":"invalid","error":str(exc)},"tests":{"exit_code":0},"probe":{"exit_code":2,"error_type":type(exc).__name__}}); return 0
    tests=run_test_subset(patterns=TEST_PATTERNS,root=ROOT,environment=environment,artifact_dir=artifact_dir,timeout_seconds_per_pattern=300)
    summary={"schema_version":"bench.h3-context-job.v1","test_scope":"h3-primary-32k-batch","python":sys.executable,"repository_root":str(ROOT),"sanitization":{"removed_external_env_names":removed,"secret_values_recorded":False,"external_providers_allowed":False},"source":{"plan_path":PLAN_PATH.relative_to(ROOT).as_posix(),"plan_sha256":EXPECTED_PLAN_SHA256,"summary_path":SUMMARY_PATH.relative_to(ROOT).as_posix(),"summary_sha256":EXPECTED_SUMMARY_SHA256,"summary_manifest_path":SUMMARY_MANIFEST_PATH.relative_to(ROOT).as_posix(),"summary_manifest_sha256":EXPECTED_SUMMARY_MANIFEST_SHA256},"selection":selection,"tests":tests,"probe":{"exit_code":0,"skipped_reason":"prerequisite_failure" if tests["exit_code"] else None}}
    if tests["exit_code"]!=0: _write_summary(artifact_dir,summary); return 0
    if not _source_files_are_bound(): summary["probe"]={"exit_code":2,"skipped_reason":None,"error_type":"H3SourceBindingError"}; _write_summary(artifact_dir,summary); return 0
    probe_dir=artifact_dir/"h3-primary-32k"
    summary["probe"]=run_captured("h3-probe",[sys.executable,"scripts/probe_h3_context.py","--plan",str(PLAN_PATH),"--summary",str(SUMMARY_PATH),"--summary-manifest",str(SUMMARY_MANIFEST_PATH),"--expected-plan-sha256",EXPECTED_PLAN_SHA256,"--output-dir",str(probe_dir),"--batch-index",str(index)],cwd=ROOT,environment=environment,artifact_dir=artifact_dir,timeout_seconds=9000)
    _write_summary(artifact_dir,summary); return 0

def _validate_manifest(probe_dir,report):
    failures=[]; manifest_path=probe_dir/"manifest.json"
    if not manifest_path.is_file(): return ["H3 manifest is missing"]
    manifest=_load_json(manifest_path); artifacts=manifest.get("artifacts")
    if manifest.get("schema_version")!="bench.h3-context-manifest.v1": failures.append("H3 manifest schema is invalid")
    if not isinstance(artifacts,dict): return failures+["H3 manifest artifact map is missing"]
    expected={"report.json"}; results=report.get("results")
    if isinstance(results,list): expected.update("models/"+item["artifact_slug"]+"/result.json" for item in results if isinstance(item,dict) and isinstance(item.get("artifact_slug"),str))
    if set(artifacts)!=expected: failures.append("H3 manifest inventory does not match report results")
    for relative,record in artifacts.items():
        path=probe_dir/relative
        if not isinstance(record,dict) or not path.is_file(): failures.append(f"H3 manifest artifact is missing: {relative}"); continue
        digest,size=record.get("sha256"),record.get("size_bytes")
        if not isinstance(digest,str) or not _SHA256.fullmatch(digest): failures.append(f"H3 manifest digest is invalid: {relative}")
        elif _sha256(path)!=digest: failures.append(f"H3 manifest digest mismatch: {relative}")
        if size!=path.stat().st_size: failures.append(f"H3 manifest size mismatch: {relative}")
    return failures

def _expected_batch_candidates(index):
    candidates=_load_json(PLAN_PATH).get("candidates")
    if not isinstance(candidates,list) or len(candidates)!=10: raise ValueError("H3 plan candidate inventory is invalid")
    selection=selection_for(index); return [{"name":item["name"],"digest":item["digest"]} for item in candidates[selection["start"]:selection["end"]] if isinstance(item,dict)]

def enforce(artifact_dir=DEFAULT_ARTIFACTS):
    path=_summary_path(artifact_dir)
    if not path.is_file(): print(f"missing H3 job summary: {path}",file=sys.stderr); return 2
    try:
        summary=_load_json(path)
        if summary.get("schema_version")!="bench.h3-context-job.v1" or summary.get("test_scope")!="h3-primary-32k-batch": raise ValueError("unsupported H3 job contract")
        test_exit=int(summary["tests"]["exit_code"]); probe_exit=int(summary["probe"]["exit_code"]); selection=summary["selection"]; index=int(selection["batch_index"])
    except (OSError,ValueError,TypeError,KeyError,json.JSONDecodeError) as exc: print(f"invalid H3 job summary: {type(exc).__name__}: {exc}",file=sys.stderr); return 2
    failures=[]
    if test_exit!=0: failures.append(f"H3 tests exited {test_exit}")
    if probe_exit!=0: failures.append(f"H3 probe infrastructure exited {probe_exit}")
    try: expected_selection=selection_for(index)
    except ValueError as exc: failures.append(str(exc)); expected_selection={}
    if selection!=expected_selection: failures.append("H3 job selection does not match the approved batch")
    if failures: print("; ".join(failures),file=sys.stderr); return 1
    probe_dir=artifact_dir/"h3-primary-32k"
    try: report=_load_json(probe_dir/"report.json"); expected_candidates=_expected_batch_candidates(index)
    except (OSError,ValueError,KeyError,json.JSONDecodeError) as exc: print(f"invalid H3 evidence: {type(exc).__name__}: {exc}",file=sys.stderr); return 2
    if report.get("schema_version")!="bench.h3-context-report.v1": failures.append("H3 report schema is invalid")
    source=report.get("source")
    if not isinstance(source,dict) or source.get("plan_sha256")!=EXPECTED_PLAN_SHA256 or source.get("h2_summary_sha256")!=EXPECTED_SUMMARY_SHA256 or source.get("h2_summary_manifest_sha256")!=EXPECTED_SUMMARY_MANIFEST_SHA256: failures.append("H3 report is not bound to the approved source")
    if report.get("profile")!=PROFILE: failures.append("H3 report profile drifted")
    if report.get("selection")!=expected_selection: failures.append("H3 report selection does not match the approved batch")
    if report.get("infrastructure_error") is not None: failures.append("H3 report contains an infrastructure error")
    results=report.get("results")
    if not isinstance(results,list) or len(results)!=2: failures.append("H3 report does not contain exactly two candidates"); results=[]
    observed=[]
    for result in results:
        if not isinstance(result,dict): failures.append("H3 candidate result is not an object"); continue
        model=result.get("model"); name=model.get("name") if isinstance(model,dict) else None; digest=model.get("digest") if isinstance(model,dict) else None
        if isinstance(name,str) and isinstance(digest,str): observed.append({"name":name,"digest":digest})
        else: failures.append("H3 candidate identity is invalid")
        if result.get("schema_version")!="bench.h3-context-result.v1": failures.append(f"H3 candidate result schema is invalid: {name}")
        if result.get("profile")!=PROFILE: failures.append(f"H3 candidate profile drifted: {name}")
        if result.get("status") not in _ALLOWED_RESULTS: failures.append(f"H3 candidate status is invalid: {name}")
        cleanup=result.get("cleanup_after")
        if not isinstance(cleanup,dict) or cleanup.get("verified_absent") is not True: failures.append(f"H3 cleanup is not attested: {name}")
        if not isinstance(result.get("artifact_slug"),str): failures.append(f"H3 artifact binding is missing: {name}")
    if observed!=expected_candidates: failures.append("H3 candidate identities do not match the approved batch")
    if not isinstance(report.get("final_cleanup"),list): failures.append("H3 final cleanup evidence is missing")
    failures.extend(_validate_manifest(probe_dir,report))
    if failures: print("; ".join(failures),file=sys.stderr); return 1
    counts=report.get("status_counts"); print(f"H3 32K batch evidence gate passed; batch={index}; qualified={counts.get('qualified_32k') if isinstance(counts,dict) else None}; cpu_offload={counts.get('cpu_offload') if isinstance(counts,dict) else None}; context_mismatch={counts.get('context_mismatch') if isinstance(counts,dict) else None}; load_failed={counts.get('load_failed') if isinstance(counts,dict) else None}"); return 0

def main():
    p=argparse.ArgumentParser(); p.add_argument("mode",choices=("capture","enforce")); p.add_argument("--artifact-dir",type=Path,default=DEFAULT_ARTIFACTS); a=p.parse_args(); return capture(a.artifact_dir) if a.mode=="capture" else enforce(a.artifact_dir)
if __name__=="__main__": raise SystemExit(main())
