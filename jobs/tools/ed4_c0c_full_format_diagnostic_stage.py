#!/usr/bin/env python3
from __future__ import annotations
import os, sys, time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from jobs.tools.ed4_c0c_full_format_diagnostic import RUNTIME_MAX_SECONDS, build_diagnostic
from jobs.tools.launch_runtime_v2 import StageEvidence, atomic_json

PHASES=['authenticate-1927-recovery-partition','authenticate-c0a-c0b-descriptor-universe','authenticate-and-classify-every-descriptor','verify-complete-deterministic-classification','publish-format-diagnostic']
def main():
    mode=os.environ['LAUNCH_MODE']; art=Path(os.environ['JASS_ARTEFACT_DIR']); work=Path(os.environ['JASS_RESULT_DIR'])/'c0c-full-format-diagnostic'; ev=StageEvidence(art,mode)
    try:
        if mode != 'rehearsal': raise RuntimeError('format_diagnostic_rehearsal_only')
        if not isinstance(RUNTIME_MAX_SECONDS,int) or isinstance(RUNTIME_MAX_SECONDS,bool) or RUNTIME_MAX_SECONDS != 2100: raise RuntimeError('format_diagnostic_runtime_contract')
        def checkpoint(name,event):
            if event=='begin': ev.begin(name)
            elif event=='complete': ev.complete()
            else: raise RuntimeError('checkpoint_event')
        result=build_diagnostic(work,art,time.monotonic()+RUNTIME_MAX_SECONDS,checkpoint)
        atomic_json(art/'scientific-summary.json',{k:result[k] for k in ('schema','state','classification','descriptor_count','recovery_descriptor_count','classification_sha256','failure_rows_sha256','failure_row_count','actual_position_identity_reads','actual_position_identity_reads_measurement','successful_position_rows','target_fields_decoded','target_reads','score_reads','wdl_reads','qvalue_reads','model_reads','teacher_calls','search_calls','fits','games','alpha_spent','scientific_verdict','confirmation_authorized','automatic_continuation')})
        ev.finish(); return 0
    except Exception as exc:
        ev.fail(exc)
        atomic_json(art/'scientific-summary.json',{'schema':'jass.ed4.c0c_full_format_diagnostic_failure.v1','state':'failed','classification':'TECHNICAL_FORMAT_DIAGNOSTIC_ONLY','error_type':type(exc).__name__,'scientific_verdict':None,'confirmation_authorized':False,'automatic_continuation':False,'target_reads':0,'alpha_spent':0})
        return 2
if __name__=='__main__': raise SystemExit(main())
