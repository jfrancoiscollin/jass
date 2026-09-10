#!/usr/bin/env python3
from __future__ import annotations
import hashlib, json, shutil, struct
from pathlib import Path
from jobs.tools import fetch_result_files
from jobs.tools import ed4_c0c_exclusion_union as v1

SCHEMA='jass.ed4.c0c_structural_exclusion_union.v4'
VERDICT='ED4_C0C_STRUCTURAL_EXCLUSION_UNION_READY_V4_CLASS'
REC=38
SALVAGE_JOB='cpx62-1785-l3-decision-math-b2-documentary-preread-schema-compat-v1'
SALVAGE_ATTEMPT='20260905T145718Z-d3657332'
SALVAGE_PREFIX='b2-preread-schema-compat/documentary-worktree/jobs/results/ccx33-0206-wdl-loop-mt60/artefacts/'


def _parse_scoped_interrupted_jnnw(path:Path, desc:dict, job_id:str, attempt:str):
    if not (job_id==SALVAGE_JOB and attempt==SALVAGE_ATTEMPT and desc.get('kind')=='jnnw' and str(desc.get('path','')).startswith(SALVAGE_PREFIX)):
        return None
    raw=path.read_bytes()
    if len(raw)!=desc.get('size_bytes') or hashlib.sha256(raw).hexdigest()!=desc.get('sha256'):
        raise v1.C0CError('v4_class_object_identity')
    if len(raw)<8 or raw[:4]!=b'JNNW':
        raise v1.C0CError('v4_class_bad_magic')
    declared=struct.unpack('<I',raw[4:8])[0]
    if declared!=0:
        return None
    complete,tail=divmod(len(raw)-8,REC)
    if complete<1 or tail==0:
        return None
    ids=set(); body=raw[8:]
    for i in range(complete):
        rec=body[i*REC:(i+1)*REC]
        ids.add(v1.canonical_from_position_bytes(rec[:33]))
        # rec[33:38] is intentionally never decoded or interpreted.
    return ids, complete, {
        'declared_count':0,
        'complete_records_recovered':complete,
        'partial_tail_bytes_discarded':tail,
        'policy':'scoped_authenticated_interrupted_writer_class_v4',
    }


def _parse_candidate_v4(path:Path, desc:dict, job_id:str, attempt:str):
    recovered=_parse_scoped_interrupted_jnnw(path,desc,job_id,attempt)
    if recovered is not None:
        ids,rows,recovery=recovered
        return ids,rows,'position_identity_only_v4_class_salvage',recovery
    try:
        ids,rows,sem=v1.parse_candidate(path,desc['kind'])
        return ids,rows,sem,None
    except v1.C0CError as exc:
        # Any malformed object not matching the exact preregistered class remains fail-closed.
        raise


def build_union_v4(work:Path, artifact:Path)->dict:
    if work.exists() or work.is_symlink(): raise v1.C0CError('work_dir_must_not_exist')
    work.mkdir(parents=True); artifact.mkdir(parents=True,exist_ok=True)
    c0a,c0b=v1.fetch_parent(work); sources={x['job_id']:x for x in c0a.get('sources',[])}
    all_ids=set(); receipts=[]; total_rows=downloaded=zero=class_files=class_records=discarded=0
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
            ids,rows,sem,recovery=_parse_candidate_v4(path,desc,job_id,attempt)
            all_ids.update(ids); total_rows+=rows; downloaded+=1
            receipt={'job_id':job_id,'attempt_id':attempt,'path':desc['path'],'kind':desc['kind'],'sha256':desc['sha256'],'size_bytes':desc['size_bytes'],'rows':rows,'unique_identities':len(ids),'semantics':sem}
            if recovery is not None:
                receipt['recovery']=recovery; class_files+=1; class_records+=recovery['complete_records_recovered']; discarded+=recovery['partial_tail_bytes_discarded']
            receipts.append(receipt); path.unlink(missing_ok=True)
        shutil.rmtree(local,ignore_errors=True)
    if class_files<3: raise v1.C0CError('v4_expected_class_instances_missing')
    if not all_ids: raise v1.C0CError('empty_exclusion_union')
    raw=('\n'.join(sorted(all_ids))+'\n').encode('ascii'); (artifact/'ed4-c0c-structural-exclusion-union.txt').write_bytes(raw)
    manifest={'schema':SCHEMA,'state':'completed','verdict':VERDICT,'protocol_change':'prospective_v4_scoped_interrupted_writer_class_2026-09-10','parent_job_id':v1.PARENT_JOB,'parent_attempt_id':v1.PARENT_ATTEMPT,'parent_c0a_sha256':v1.C0A_SHA,'parent_c0b_sha256':v1.C0B_SHA,'candidate_files_downloaded':downloaded,'candidate_zero_size_authenticated':zero,'candidate_rows_parsed':total_rows,'class_salvaged_files':class_files,'class_salvaged_complete_records':class_records,'discarded_partial_tail_bytes':discarded,'unique_canonical_identities':len(all_ids),'union_sha256':hashlib.sha256(raw).hexdigest(),'union_size_bytes':len(raw),'target_fields_decoded':0,'target_reads':0,'score_reads':0,'wdl_reads':0,'qvalue_reads':0,'model_reads':0,'teacher_calls':0,'search_calls':0,'fits':0,'games':0,'alpha_spent':0,'confirmation_authorized':False,'automatic_continuation':False,'files':receipts}
    (artifact/'ed4-c0c-structural-exclusion-manifest.json').write_text(json.dumps(manifest,sort_keys=True,separators=(',',':'))+'\n')
    return manifest
