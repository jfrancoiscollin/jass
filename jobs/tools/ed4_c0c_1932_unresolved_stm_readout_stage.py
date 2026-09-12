#!/usr/bin/env python3
from __future__ import annotations
import hashlib, json, os, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from jobs.tools import fetch_result_files
from jobs.tools.launch_runtime_v2 import StageEvidence, atomic_json

JOB='cpx62-1932-l3-ed4-c0c-exact-linkage-diagnostic-rehearsal-v1'
ATTEMPT='20260912T141224Z-038c7dce'
CODE='038c7dceb057f8a150459d8d521dda84137ae343'
PATH='artefacts/ed4-c0c-exact-linkage-diagnostic-v1.json'
EXPECTED_TERMINAL='ED4_C0C_V7_BLOCKED_BY_INCOMPLETE_STRUCTURAL_COVERAGE'

def main():
    art=Path(os.environ['JASS_ARTEFACT_DIR']); result=Path(os.environ['JASS_RESULT_DIR']); ev=StageEvidence(art,os.environ['LAUNCH_MODE'])
    try:
        if os.environ['LAUNCH_MODE']!='rehearsal': raise RuntimeError('rehearsal_only')
        ev.begin('authenticate-1932-publication')
        prefix=f'r2:jass-data/runs/{JOB}/{ATTEMPT}'
        inv=fetch_result_files.inspect_result_inventory(rclone='rclone',prefix=prefix,expected_state='completed')
        if (inv.get('job_id'),inv.get('attempt_id'),inv.get('code_sha'),inv.get('result_state'),inv.get('exit_code'))!=(JOB,ATTEMPT,CODE,'completed',0): raise RuntimeError('parent_identity')
        item=next((x for x in inv.get('files',[]) if x.get('path')==PATH),None)
        if not item: raise RuntimeError('parent_artifact_missing')
        out=result/'parent'; out.mkdir(parents=True,exist_ok=True)
        got=fetch_result_files.fetch_files(rclone='rclone',prefix=prefix,expected_state='completed',selections=[(PATH,'diagnostic.json')],out_dir=out)
        f=got['files'][0]
        raw=(out/'diagnostic.json').read_bytes()
        if f.get('sha256')!=item.get('sha256') or f.get('size_bytes')!=item.get('size_bytes') or hashlib.sha256(raw).hexdigest()!=item.get('sha256') or len(raw)!=item.get('size_bytes'): raise RuntimeError('parent_artifact_drift')
        ev.complete()
        ev.begin('select-exact-three-unresolved-stm-aliases')
        obj=json.loads(raw)
        if obj.get('state')!='completed' or obj.get('terminal')!=EXPECTED_TERMINAL or obj.get('descriptor_count')!=21 or obj.get('resolved_descriptor_count')!=18 or obj.get('unresolved_descriptor_count')!=3: raise RuntimeError('parent_summary_drift')
        rows=[]
        for row in obj.get('recovery_evidence',[]):
            if row.get('evidence')!='unresolved-fail-closed': continue
            desc=row.get('descriptor')
            if not (isinstance(desc,list) and len(desc)==3 and all(isinstance(x,str) and x for x in desc)): raise RuntimeError('descriptor_shape')
            if row.get('kind')!='jnnw' or row.get('artifact_causality_proven') is not False or row.get('complete_coverage_proven') is not False: raise RuntimeError('unresolved_class_drift')
            rows.append({'job_id':desc[0],'attempt_id':desc[1],'path':desc[2],'kind':'jnnw','sha256':row.get('sha256'),'size_bytes':row.get('size_bytes'),'declared_count':row.get('declared_count'),'nominal_stm_histogram':row.get('nominal_stm_histogram'),'strict_nominal_valid_prefixes':row.get('strict_nominal_valid_prefixes'),'strict_nominal_projection_sha256':row.get('strict_nominal_projection_sha256'),'artifact_causality_proven':False,'complete_coverage_proven':False})
        rows.sort(key=lambda r:(r['job_id'],r['attempt_id'],r['path']))
        if len(rows)!=3 or len({(r['job_id'],r['attempt_id'],r['path']) for r in rows})!=3: raise RuntimeError('unresolved_cardinality')
        ev.complete()
        ev.begin('publish-provenance-readout')
        result_obj={'schema':'jass.ed4.c0c_1932_unresolved_stm_readout.v1','state':'completed','parent_job_id':JOB,'parent_attempt_id':ATTEMPT,'unresolved_count':3,'rows':rows,'target_reads':0,'wdl_reads':0,'qvalue_reads':0,'score_reads':0,'position_identity_values_published':0,'alpha_spent':0,'scientific_verdict':None,'confirmation_authorized':False,'automatic_continuation':False}
        atomic_json(art/'ed4-c0c-1932-unresolved-stm-readout-v1.json',result_obj); atomic_json(art/'scientific-summary.json',result_obj)
        ev.complete(); ev.finish(); return 0
    except Exception as exc:
        ev.fail(exc); atomic_json(art/'scientific-summary.json',{'schema':'jass.ed4.c0c_1932_unresolved_stm_readout_failure.v1','state':'failed','classification':'TECHNICAL_PROVENANCE_READOUT_ONLY','error_type':type(exc).__name__,'target_reads':0,'alpha_spent':0,'scientific_verdict':None,'confirmation_authorized':False}); return 2

if __name__=='__main__': raise SystemExit(main())
