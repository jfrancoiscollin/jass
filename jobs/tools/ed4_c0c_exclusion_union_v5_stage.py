#!/usr/bin/env python3
from __future__ import annotations
import os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from jobs.tools.ed4_c0c_exclusion_union_v5 import build_union_v5
from jobs.tools.launch_runtime_v2 import StageEvidence,atomic_json
PHASES=['authenticate-1922-inventory','authenticate-c0b-parent','download-authenticated-candidates','parse-position-identity-only-v5-inventory-closed','publish-union-v5']

def main():
    art=Path(os.environ['JASS_ARTEFACT_DIR']); work=Path(os.environ['JASS_RESULT_DIR'])/'c0c-v5-work'; ev=StageEvidence(art,os.environ['LAUNCH_MODE'])
    try:
        ev.begin(PHASES[0]); ev.complete(); ev.begin(PHASES[1]); ev.complete(); ev.begin(PHASES[2]); ev.complete(); ev.begin(PHASES[3]); result=build_union_v5(work,art); ev.complete(); ev.begin(PHASES[4])
        keys=('schema','state','verdict','protocol_change','inventory_job_id','inventory_attempt_id','inventory_sha256','inventory_size_bytes','unique_canonical_identities','union_sha256','candidate_files_downloaded','candidate_zero_size_authenticated','candidate_rows_parsed','inventory_salvaged_files','inventory_salvaged_complete_records','discarded_partial_tail_bytes','target_fields_decoded','target_reads','score_reads','wdl_reads','qvalue_reads','model_reads','teacher_calls','search_calls','fits','games','alpha_spent','confirmation_authorized','automatic_continuation')
        atomic_json(art/'scientific-summary.json',{k:result[k] for k in keys}); ev.complete(); ev.finish(); return 0
    except Exception as exc:
        ev.fail(exc); atomic_json(art/'scientific-summary.json',{'schema':'jass.ed4.c0c_failure.v5','state':'failed','verdict':'ED4_C0C_V5_TECHNICAL_OR_PARSE_FAILURE','error_type':type(exc).__name__,'error':str(exc),'scientific_verdict':None,'confirmation_authorized':False,'automatic_continuation':False,'alpha_spent':0}); return 2
if __name__=='__main__': raise SystemExit(main())
