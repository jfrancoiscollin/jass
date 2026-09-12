#!/usr/bin/env python3
from __future__ import annotations
import os, sys, traceback, time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from jobs.tools.ed4_c0c_exclusion_union_v6 import RUNTIME_MAX_SECONDS, build_union_v6
from jobs.tools.launch_runtime_v2 import StageEvidence, atomic_json
PHASES=['authenticate-1927-inventory-and-class-readout','validate-pinned-231-row-partition','authenticate-c0a-c0b-descriptor-universe','download-and-parse-authenticated-candidates','verify-exact-allowlist-encounters','publish-union-v6']
def main():
    art=Path(os.environ['JASS_ARTEFACT_DIR']); work=Path(os.environ['JASS_RESULT_DIR'])/'c0c-v6-work'; ev=StageEvidence(art,os.environ['LAUNCH_MODE'])
    try:
        if not isinstance(RUNTIME_MAX_SECONDS,int) or isinstance(RUNTIME_MAX_SECONDS,bool) or RUNTIME_MAX_SECONDS <= 0: raise RuntimeError('v6_runtime_sizing_pending')
        deadline=time.monotonic()+RUNTIME_MAX_SECONDS
        def checkpoint(name,event):
            if event == 'begin': ev.begin(name)
            elif event == 'complete': ev.complete()
            else: raise RuntimeError('invalid_checkpoint_event')
        result=build_union_v6(work,art,deadline,checkpoint)
        atomic_json(art/'scientific-summary.json',{k:result[k] for k in ('schema','state','verdict','classification','inventory_job_id','inventory_attempt_id','inventory_code_sha','inventory_sha256','inventory_size_bytes','readout_sha256','readout_size_bytes','allowlist_canonical_sha256','aligned_subset_canonical_sha256','v5_salvaged_files','v5_salvaged_complete_records','aligned_count0_files','aligned_count0_records','union_sha256','target_fields_decoded','target_reads','score_reads','wdl_reads','qvalue_reads','model_reads','teacher_calls','search_calls','fits','games','alpha_spent','scientific_verdict','confirmation_authorized','automatic_continuation')}); ev.finish(); return 0
    except Exception as exc:
        tb=''.join(traceback.format_exception(type(exc),exc,exc.__traceback__))[-12000:]
        try: ev.fail(exc)
        finally: atomic_json(art/'scientific-summary.json',{'schema':'jass.ed4.c0c_failure.v6','state':'failed','classification':'TECHNICAL_STRUCTURAL_SOURCE_RECOVERY_ONLY','error_type':type(exc).__name__,'error':str(exc),'traceback_tail':tb,'scientific_verdict':None,'confirmation_authorized':False,'automatic_continuation':False,'alpha_spent':0,'target_reads':0})
        return 2
if __name__=='__main__': raise SystemExit(main())
