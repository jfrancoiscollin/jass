#!/usr/bin/env python3
"""Localize the next malformed frozen JNNW after both exact V3 salvages.

Structural diagnostic only. Authenticates frozen C0A/C0B inventories and bytes,
skips exactly the two V3-authorized objects, reads only JNNW envelope magic/count/body
length, and stops at the next malformed JNNW. No record field, position identity,
target, model, score, WDL, q-value, search result, fit, game or alpha is consumed.
"""
from __future__ import annotations
import hashlib, os, shutil, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from jobs.tools import fetch_result_files
from jobs.tools import ed4_c0c_jnnw_shape_diagnostic_stage as base
from jobs.tools import ed4_c0c_exclusion_union_v3 as v3
from jobs.tools.launch_runtime_v2 import StageEvidence, atomic_json
PHASES=["authenticate-c0b-parent-metadata","scan-after-authorized-v3-salvages","publish-third-jnnw-shape-diagnostic"]

def is_v3_authorized(job_id,attempt,desc):
    spec=v3.SALVAGE_OBJECTS.get(desc.get("path"))
    return bool(spec and job_id==v3.SALVAGE_JOB and attempt==v3.SALVAGE_ATTEMPT and desc.get("kind")=="jnnw" and desc.get("sha256")==spec["sha256"] and desc.get("size_bytes")==spec["size_bytes"])

def find_next(c0a,c0b,work):
    sources={r["job_id"]:r for r in c0a.get("sources",[])}
    checked=skipped=bytes_read=inventories=zero=0
    for job in c0b.get("candidate_jobs",[]):
        job_id=job["job_id"]; attempt=job.get("attempt_id"); candidates=job.get("candidate_files",[])
        if not candidates: continue
        source=sources.get(job_id)
        if not source or source.get("attempt_id")!=attempt: raise RuntimeError("c0a_c0b_identity_mismatch")
        state=source.get("result_state")
        if state not in {"completed","failed"}: raise RuntimeError("candidate_result_state")
        prefix=f"r2:jass-data/runs/{job_id}/{attempt}"
        invr=fetch_result_files.inspect_result_inventory(rclone="rclone",prefix=prefix,expected_state=state)
        if (invr.get("job_id"),invr.get("attempt_id"),invr.get("code_sha"),invr.get("result_state"))!=(job_id,attempt,source.get("code_sha"),state): raise RuntimeError("candidate_inventory_identity")
        inventories+=1; inv={x["path"]:x for x in invr.get("files",[])}
        for index,desc in enumerate(candidates):
            if desc.get("kind") not in {"jnnw","jnnw_gzip"}: continue
            item=inv.get(desc["path"])
            if item is None or item.get("size_bytes")!=desc.get("size_bytes") or item.get("sha256")!=desc.get("sha256"): raise RuntimeError("descriptor_drift")
            if item["size_bytes"]==0: zero+=1; continue
            if is_v3_authorized(job_id,attempt,desc): skipped+=1; continue
            local=work/("job-"+hashlib.sha256(job_id.encode()).hexdigest()[:12]); name=f"{index:04d}-{Path(desc['path']).name}"
            fetched=fetch_result_files.fetch_files(rclone="rclone",prefix=prefix,expected_state=state,selections=[(desc["path"],name)],out_dir=local)
            got=fetched["files"][0]
            if got.get("sha256")!=desc.get("sha256") or got.get("size_bytes")!=desc.get("size_bytes"): raise RuntimeError("descriptor_drift_after_download")
            checked+=1; bytes_read+=int(got["size_bytes"]); p=local/name
            shape=base.inspect_jnnw_envelope(p,desc["kind"]=="jnnw_gzip")
            p.unlink(missing_ok=True); shutil.rmtree(local,ignore_errors=True)
            if shape["state"]=="invalid":
                return {"next_failure":{"job_id":job_id,"attempt_id":attempt,"path":desc["path"],"kind":desc["kind"],"sha256":desc["sha256"],"size_bytes":desc["size_bytes"],**shape},"jnnw_files_checked_after_skip":checked,"authorized_objects_skipped":skipped,"candidate_payload_bytes_read":bytes_read,"candidate_inventories_authenticated":inventories,"zero_size_jnnw_skipped":zero}
    return {"next_failure":None,"jnnw_files_checked_after_skip":checked,"authorized_objects_skipped":skipped,"candidate_payload_bytes_read":bytes_read,"candidate_inventories_authenticated":inventories,"zero_size_jnnw_skipped":zero}

def main():
    art=Path(os.environ["JASS_ARTEFACT_DIR"]); result=Path(os.environ["JASS_RESULT_DIR"]); ev=StageEvidence(art,os.environ["LAUNCH_MODE"])
    try:
        ev.begin(PHASES[0]); c0a,c0b=base.fetch_parent_metadata(result/"parent"); ev.complete()
        ev.begin(PHASES[1]); diag=find_next(c0a,c0b,result/"scan")
        if not diag.get("next_failure"): raise RuntimeError("no_next_malformed_jnnw")
        if diag.get("authorized_objects_skipped")!=2: raise RuntimeError("authorized_skip_count")
        ev.complete(); ev.begin(PHASES[2])
        out={"schema":"jass.ed4.c0c_third_jnnw_shape_diagnostic.v1","state":"completed","classification":"TECHNICAL_STRUCTURAL_DIAGNOSTIC_ONLY","source_job_id":"cpx62-1912-l3-ed4-c0c-v3-structural-exclusion-union-v1",**diag,"record_fields_decoded":0,"position_identity_reads":0,"target_fields_decoded":0,"target_reads":0,"score_reads":0,"wdl_reads":0,"qvalue_reads":0,"model_reads":0,"teacher_calls":0,"search_calls":0,"fits":0,"games":0,"alpha_spent":0,"scientific_verdict":None,"confirmation_authorized":False,"automatic_continuation":False,"next_stage":"ED4_C0C_CLASSIFY_THIRD_MALFORMED_JNNW"}
        atomic_json(art/"ed4-c0c-third-jnnw-shape-diagnostic.json",out); atomic_json(art/"scientific-summary.json",out); ev.complete(); ev.finish(); return 0
    except Exception as exc:
        ev.fail(exc); atomic_json(art/"scientific-summary.json",{"schema":"jass.ed4.c0c_third_jnnw_shape_diagnostic_failure.v1","state":"failed","classification":"TECHNICAL","error_type":type(exc).__name__,"scientific_verdict":None,"confirmation_authorized":False}); return 2
if __name__=="__main__": raise SystemExit(main())
