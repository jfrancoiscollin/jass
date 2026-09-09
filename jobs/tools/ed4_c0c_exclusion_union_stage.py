#!/usr/bin/env python3
from __future__ import annotations
import json, os
from pathlib import Path
from jobs.tools.ed4_c0c_exclusion_union import build_union
from jobs.tools.launch_runtime_v2 import StageEvidence, atomic_json

PHASES=['authenticate-c0b-parent','download-authenticated-candidates','parse-position-identity-only','publish-union']

def main():
    art=Path(os.environ['JASS_ARTEFACT_DIR']); work=Path(os.environ['JASS_RESULT_DIR'])/'c0c-work'
    ev=StageEvidence(art,os.environ['LAUNCH_MODE'])
    try:
        ev.begin(PHASES[0]); ev.complete()
        ev.begin(PHASES[1]); ev.complete()
        ev.begin(PHASES[2]); result=build_union(work,art); ev.complete()
        ev.begin(PHASES[3])
        summary={k:result[k] for k in ('schema','state','verdict','unique_canonical_identities','union_sha256','candidate_files_downloaded','candidate_rows_parsed','target_fields_decoded','score_reads','wdl_reads','qvalue_reads','model_reads','teacher_calls','search_calls','fits','games','alpha_spent','confirmation_authorized','automatic_continuation')}
        atomic_json(art/'scientific-summary.json',summary); ev.complete(); ev.finish(); return 0
    except Exception as exc:
        ev.fail(exc)
        atomic_json(art/'scientific-summary.json',{'schema':'jass.ed4.c0c_failure.v1','state':'failed','verdict':'ED4_C0C_TECHNICAL_OR_PARSE_FAILURE_V1','error_type':type(exc).__name__,'scientific_verdict':None,'confirmation_authorized':False})
        return 2
if __name__=='__main__': raise SystemExit(main())
