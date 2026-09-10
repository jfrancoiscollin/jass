#!/usr/bin/env python3
"""ED4 C0C V3: prospectively recover two exact authenticated interrupted JNNWs.

V1/V2 remain unchanged. V3 extends the authorized complete-record recovery only
to the second object localized by diagnostic 1911. Both exceptions are exact
(job, attempt, path, sha256, size, shape), decode only bytes 0:33 of each complete
38-byte record, never decode bytes 33:38, and discard only the final 32-byte tail.
Every other malformed candidate remains fail-closed under V1 semantics.
"""
from __future__ import annotations
import hashlib, json, shutil, struct
from pathlib import Path
from jobs.tools import fetch_result_files
from jobs.tools import ed4_c0c_exclusion_union as v1

SCHEMA='jass.ed4.c0c_structural_exclusion_union.v3'
VERDICT='ED4_C0C_STRUCTURAL_EXCLUSION_UNION_READY_V3'
REC=38
SALVAGE_JOB='cpx62-1785-l3-decision-math-b2-documentary-preread-schema-compat-v1'
SALVAGE_ATTEMPT='20260905T145718Z-d3657332'
SALVAGE_OBJECTS={
 'b2-preread-schema-compat/documentary-worktree/jobs/results/ccx33-0206-wdl-loop-mt60/artefacts/sp1-1.jnnw':{
  'sha256':'730ee719a651e371c782afd1c1f29a4a95a2c81b2bfdf7f9748aab4d6d7cd576','size_bytes':114914,'complete_records':3023,'tail_bytes':32},
 'b2-preread-schema-compat/documentary-worktree/jobs/results/ccx33-0206-wdl-loop-mt60/artefacts/sp1-2.jnnw':{
  'sha256':'7e1fbd21836db9bb090006b408bb1fb6cecf6ab778baf3c8182a24a18a3fbb4f','size_bytes':114914,'complete_records':3023,'tail_bytes':32},
}

def _parse_exact_interrupted_jnnw(path:Path,spec:dict):
    raw=path.read_bytes()
    if len(raw)!=spec['size_bytes'] or hashlib.sha256(raw).hexdigest()!=spec['sha256']:
        raise v1.C0CError('v3_salvage_object_identity')
    if len(raw)<8 or raw[:4]!=b'JNNW': raise v1.C0CError('v3_salvage_header')
    declared=struct.unpack('<I',raw[4:8])[0]
    if declared!=0: raise v1.C0CError('v3_salvage_expected_zero_placeholder')
    complete,tail=divmod(len(raw)-8,REC)
    if (complete,tail)!=(spec['complete_records'],spec['tail_bytes']):
        raise v1.C0CError('v3_salvage_shape_mismatch')
    ids=set()
    body=raw[8:]
    for i in range(complete):
        rec=body[i*REC:(i+1)*REC]
        ids.add(v1.canonical_from_position_bytes(rec[:33]))
    return ids,complete,{'declared_count':declared,'complete_records_recovered':complete,'partial_tail_bytes_discarded':tail,'policy':'exact_authenticated_interrupted_jnnw_complete_prefix_v3'}

def _parse_candidate_v3(local_path:Path,desc:dict,job_id:str,attempt:str):
    spec=SALVAGE_OBJECTS.get(desc.get('path'))
    exact=(spec is not None and job_id==SALVAGE_JOB and attempt==SALVAGE_ATTEMPT and desc.get('kind')=='jnnw' and desc.get('sha256')==spec['sha256'] and desc.get('size_bytes')==spec['size_bytes'])
    if exact:
        ids,rows,recovery=_parse_exact_interrupted_jnnw(local_path,spec)
        return ids,rows,'position_identity_only_v3_salvaged_complete_prefix',recovery
    ids,rows,sem=v1.parse_candidate(local_path,desc['kind'])
    return ids,rows,sem,None

def build_union_v3(work:Path,artifact:Path)->dict:
    if work.exists() or work.is_symlink(): raise v1.C0CError('work_dir_must_not_exist')
    work.mkdir(parents=True); artifact.mkdir(parents=True,exist_ok=True)
    c0a,c0b=v1.fetch_parent(work); sources={x['job_id']:x for x in c0a.get('sources',[])}
    all_ids=set(); receipts=[]; total_rows=downloaded=zero=salvage_count=salvaged_records=discarded=0
    for job in c0b.get('candidate_jobs',[]):
        job_id,attempt=job['job_id'],job.get('attempt_id'); candidates=job.get('candidate_files',[])
        if not candidates: continue
        source=sources.get(job_id)
        if not source or source.get('attempt_id')!=attempt: raise v1.C0CError('c0a_c0b_identity_mismatch')
        state=source.get('result_state')
        if state not in {'completed','failed'}: raise v1.C0CError('candidate_result_state')
        prefix=f'r2:jass-data/runs/{job_id}/{attempt}'; local=work/('job-'+hashlib.sha256(job_id.encode()).hexdigest()[:12])
        nonempty,zero_receipts=v1._authenticate_candidate_descriptors(prefix=prefix,state=state,job_id=job_id,attempt=attempt,candidates=candidates)
        receipts.extend(zero_receipts); zero+=len(zero_receipts)
        if not nonempty: continue
        selections=[(d['path'],f'{i:04d}-{Path(d["path"]).name}') for i,d in nonempty]
        fetched=fetch_result_files.fetch_files(rclone='rclone',prefix=prefix,expected_state=state,selections=selections,out_dir=local)
        if fetched.get('job_id')!=job_id or fetched.get('attempt_id')!=attempt: raise v1.C0CError('download_identity')
        fmap={x['path']:x for x in fetched['files']}
        for i,desc in nonempty:
            got=fmap.get(desc['path'])
            if not got or got['sha256']!=desc['sha256'] or got['size_bytes']!=desc['size_bytes']: raise v1.C0CError('descriptor_drift')
            path=local/f'{i:04d}-{Path(desc["path"]).name}'
            ids,rows,sem,recovery=_parse_candidate_v3(path,desc,job_id,attempt)
            all_ids.update(ids); total_rows+=rows; downloaded+=1
            receipt={'job_id':job_id,'attempt_id':attempt,'path':desc['path'],'kind':desc['kind'],'sha256':desc['sha256'],'rows':rows,'unique_identities':len(ids),'semantics':sem}
            if recovery is not None:
                receipt['recovery']=recovery; salvage_count+=1; salvaged_records+=recovery['complete_records_recovered']; discarded+=recovery['partial_tail_bytes_discarded']
            receipts.append(receipt); path.unlink(missing_ok=True)
        shutil.rmtree(local,ignore_errors=True)
    if salvage_count!=2: raise v1.C0CError('v3_exact_salvage_count')
    if salvaged_records!=6046 or discarded!=64: raise v1.C0CError('v3_exact_salvage_totals')
    if not all_ids: raise v1.C0CError('empty_exclusion_union')
    raw=('\n'.join(sorted(all_ids))+'\n').encode('ascii'); (artifact/'ed4-c0c-structural-exclusion-union.txt').write_bytes(raw)
    manifest={'schema':SCHEMA,'state':'completed','verdict':VERDICT,'protocol_change':'prospective_v3_exact_second_object_complete_record_salvage_authorized_2026-09-10','parent_job_id':v1.PARENT_JOB,'parent_attempt_id':v1.PARENT_ATTEMPT,'parent_c0a_sha256':v1.C0A_SHA,'parent_c0b_sha256':v1.C0B_SHA,'candidate_files_downloaded':downloaded,'candidate_zero_size_authenticated':zero,'candidate_rows_parsed':total_rows,'salvaged_files':salvage_count,'salvaged_complete_records':salvaged_records,'discarded_partial_tail_bytes':discarded,'unique_canonical_identities':len(all_ids),'union_sha256':hashlib.sha256(raw).hexdigest(),'union_size_bytes':len(raw),'target_fields_decoded':0,'score_reads':0,'wdl_reads':0,'qvalue_reads':0,'model_reads':0,'teacher_calls':0,'search_calls':0,'fits':0,'games':0,'alpha_spent':0,'confirmation_authorized':False,'automatic_continuation':False,'files':receipts}
    (artifact/'ed4-c0c-structural-exclusion-manifest.json').write_text(json.dumps(manifest,sort_keys=True,separators=(',',':'))+'\n')
    return manifest
