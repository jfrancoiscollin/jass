#!/usr/bin/env python3
"""ED4 C0C structural-only exhaustive malformed-JNNW inventory.

Scans every authenticated candidate JNNW in the frozen C0A/C0B source universe and
publishes all malformed envelopes in one pass. It never decodes record fields, position
identity, target bytes, scores, WDL, q-values, model values, or confirmation targets.
"""
from __future__ import annotations
import hashlib, os, shutil, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from jobs.tools import fetch_result_files
from jobs.tools import ed4_c0c_jnnw_shape_diagnostic_stage as base
from jobs.tools.launch_runtime_v2 import StageEvidence, atomic_json

PHASES=["authenticate-c0b-parent-metadata","scan-all-jnnw-envelopes","publish-full-malformed-inventory"]
REC=38
HEADER=8


def classify_shape(desc:dict, shape:dict)->dict:
    size=desc.get('size_bytes')
    out={'path':desc['path'],'kind':desc['kind'],'sha256':desc['sha256'],'size_bytes':size,**shape}
    if desc.get('kind')=='jnnw' and shape.get('state')=='invalid' and shape.get('reason')=='jnnw_trailing_bytes' and shape.get('declared_count')==0 and isinstance(size,int) and size>=HEADER:
        complete,tail=divmod(size-HEADER,REC)
        out['complete_records_from_size']=complete
        out['partial_tail_bytes_from_size']=tail
        out['interrupted_writer_shape']=(complete>=1 and 1<=tail<=REC-1)
    else:
        out['complete_records_from_size']=None
        out['partial_tail_bytes_from_size']=None
        out['interrupted_writer_shape']=False
    return out


def scan_all(c0a,c0b,work:Path)->dict:
    sources={r['job_id']:r for r in c0a.get('sources',[])}
    malformed=[]; checked=bytes_read=inventories=zero=0; by_job={}
    for job in c0b.get('candidate_jobs',[]):
        job_id=job['job_id']; attempt=job.get('attempt_id'); candidates=job.get('candidate_files',[])
        if not candidates: continue
        source=sources.get(job_id)
        if not source or source.get('attempt_id')!=attempt: raise RuntimeError('c0a_c0b_identity_mismatch')
        state=source.get('result_state')
        if state not in {'completed','failed'}: raise RuntimeError('candidate_result_state')
        prefix=f'r2:jass-data/runs/{job_id}/{attempt}'
        invr=fetch_result_files.inspect_result_inventory(rclone='rclone',prefix=prefix,expected_state=state)
        if (invr.get('job_id'),invr.get('attempt_id'),invr.get('code_sha'),invr.get('result_state'))!=(job_id,attempt,source.get('code_sha'),state): raise RuntimeError('candidate_inventory_identity')
        inventories+=1; inv={x['path']:x for x in invr.get('files',[])}; job_bad=[]
        for index,desc in enumerate(candidates):
            if desc.get('kind') not in {'jnnw','jnnw_gzip'}: continue
            item=inv.get(desc['path'])
            if item is None or item.get('size_bytes')!=desc.get('size_bytes') or item.get('sha256')!=desc.get('sha256'): raise RuntimeError('descriptor_drift')
            if item['size_bytes']==0: zero+=1; continue
            local=work/('job-'+hashlib.sha256(job_id.encode()).hexdigest()[:12]); name=f"{index:04d}-{Path(desc['path']).name}"
            fetched=fetch_result_files.fetch_files(rclone='rclone',prefix=prefix,expected_state=state,selections=[(desc['path'],name)],out_dir=local)
            got=fetched['files'][0]
            if got.get('sha256')!=desc.get('sha256') or got.get('size_bytes')!=desc.get('size_bytes'): raise RuntimeError('descriptor_drift_after_download')
            checked+=1; bytes_read+=int(got['size_bytes']); p=local/name
            shape=base.inspect_jnnw_envelope(p,desc['kind']=='jnnw_gzip')
            p.unlink(missing_ok=True); shutil.rmtree(local,ignore_errors=True)
            if shape.get('state')=='invalid':
                row={'job_id':job_id,'attempt_id':attempt,**classify_shape(desc,shape)}
                malformed.append(row); job_bad.append(row)
        if job_bad: by_job[job_id]={'attempt_id':attempt,'malformed_count':len(job_bad),'paths':[x['path'] for x in job_bad]}
    return {'malformed':malformed,'malformed_count':len(malformed),'malformed_by_job':by_job,'jnnw_files_checked':checked,'candidate_payload_bytes_read':bytes_read,'candidate_inventories_authenticated':inventories,'zero_size_jnnw_skipped':zero,'all_malformed_are_interrupted_writer_shape':bool(malformed) and all(x.get('interrupted_writer_shape') for x in malformed)}


def main():
    art=Path(os.environ['JASS_ARTEFACT_DIR']); result=Path(os.environ['JASS_RESULT_DIR']); ev=StageEvidence(art,os.environ['LAUNCH_MODE'])
    try:
        ev.begin(PHASES[0]); c0a,c0b=base.fetch_parent_metadata(result/'parent'); ev.complete()
        ev.begin(PHASES[1]); diag=scan_all(c0a,c0b,result/'scan'); ev.complete()
        if not diag.get('malformed_count'): raise RuntimeError('no_malformed_jnnw_found')
        ev.begin(PHASES[2])
        out={'schema':'jass.ed4.c0c_v4_full_malformed_inventory.v1','state':'completed','classification':'TECHNICAL_STRUCTURAL_DIAGNOSTIC_ONLY',**diag,'record_fields_decoded':0,'position_identity_reads':0,'target_fields_decoded':0,'target_reads':0,'score_reads':0,'wdl_reads':0,'qvalue_reads':0,'model_reads':0,'teacher_calls':0,'search_calls':0,'fits':0,'games':0,'alpha_spent':0,'scientific_verdict':None,'confirmation_authorized':False,'automatic_continuation':False,'next_stage':'ED4_C0C_PREREGISTER_EXACT_MALFORMED_TABLE'}
        atomic_json(art/'ed4-c0c-v4-full-malformed-inventory.json',out); atomic_json(art/'scientific-summary.json',out); ev.complete(); ev.finish(); return 0
    except Exception as exc:
        ev.fail(exc); atomic_json(art/'scientific-summary.json',{'schema':'jass.ed4.c0c_v4_full_malformed_inventory_failure.v1','state':'failed','classification':'TECHNICAL','error_type':type(exc).__name__,'error':str(exc),'scientific_verdict':None,'confirmation_authorized':False,'alpha_spent':0}); return 2

if __name__=='__main__': raise SystemExit(main())
