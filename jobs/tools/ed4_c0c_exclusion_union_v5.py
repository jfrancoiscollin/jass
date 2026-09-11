#!/usr/bin/env python3
from __future__ import annotations
import hashlib, json, shutil, struct
from pathlib import Path
from jobs.tools import fetch_result_files
from jobs.tools import ed4_c0c_exclusion_union as v1

SCHEMA='jass.ed4.c0c_structural_exclusion_union.v5'
VERDICT='ED4_C0C_STRUCTURAL_EXCLUSION_UNION_READY_V5_INVENTORY_CLOSED'
REC=38
INV_JOB='cpx62-1922-l3-ed4-c0c-v4-full-malformed-inventory-v1'
INV_ATTEMPT='20260911T181346Z-832b0339'
INV_CODE='832b0339fe02cbf3b187377ff475a3ddd289e0d6'
INV_PATH='ed4-c0c-v4-full-malformed-inventory.json'


def _load_inventory(work:Path):
    prefix=f'r2:jass-data/runs/{INV_JOB}/{INV_ATTEMPT}'
    invr=fetch_result_files.inspect_result_inventory(rclone='rclone',prefix=prefix,expected_state='completed')
    if (invr.get('job_id'),invr.get('attempt_id'),invr.get('code_sha'),invr.get('result_state'))!=(INV_JOB,INV_ATTEMPT,INV_CODE,'completed'):
        raise v1.C0CError('v5_inventory_identity')
    item=next((x for x in invr.get('files',[]) if x.get('path')==INV_PATH),None)
    if item is None or not item.get('sha256') or not item.get('size_bytes'):
        raise v1.C0CError('v5_inventory_artifact_missing')
    out=work/'inventory'; out.mkdir(parents=True,exist_ok=True)
    fetched=fetch_result_files.fetch_files(rclone='rclone',prefix=prefix,expected_state='completed',selections=[(INV_PATH,'inventory.json')],out_dir=out)
    got=fetched['files'][0]
    if got.get('sha256')!=item.get('sha256') or got.get('size_bytes')!=item.get('size_bytes'):
        raise v1.C0CError('v5_inventory_artifact_drift')
    raw=(out/'inventory.json').read_bytes()
    obj=json.loads(raw)
    if obj.get('schema')!='jass.ed4.c0c_v4_full_malformed_inventory.v1' or obj.get('state')!='completed':
        raise v1.C0CError('v5_inventory_schema')
    if obj.get('target_fields_decoded')!=0 or obj.get('target_reads')!=0 or obj.get('wdl_reads')!=0 or obj.get('qvalue_reads')!=0 or obj.get('alpha_spent')!=0:
        raise v1.C0CError('v5_inventory_contamination')
    rows=obj.get('malformed') or []
    if not rows or obj.get('malformed_count')!=len(rows):
        raise v1.C0CError('v5_inventory_empty_or_count')
    allow={}
    for row in rows:
        if row.get('kind')!='jnnw' or row.get('state')!='invalid' or row.get('reason')!='jnnw_trailing_bytes' or row.get('declared_count')!=0 or row.get('interrupted_writer_shape') is not True:
            raise v1.C0CError('v5_new_malformed_class')
        complete=row.get('complete_records_from_size'); tail=row.get('partial_tail_bytes_from_size')
        if not isinstance(complete,int) or complete<1 or not isinstance(tail,int) or not (1<=tail<=REC-1):
            raise v1.C0CError('v5_bad_interrupted_geometry')
        key=(row.get('job_id'),row.get('attempt_id'),row.get('path'))
        if not all(isinstance(x,str) and x for x in key) or key in allow:
            raise v1.C0CError('v5_inventory_key')
        allow[key]={'sha256':row.get('sha256'),'size_bytes':row.get('size_bytes'),'complete':complete,'tail':tail}
    return allow, hashlib.sha256(raw).hexdigest(), len(raw)


def _salvage(path:Path,desc:dict,job_id:str,attempt:str,allow:dict):
    exact=allow.get((job_id,attempt,str(desc.get('path',''))))
    if exact is None:
        return None
    if desc.get('kind')!='jnnw' or desc.get('sha256')!=exact['sha256'] or desc.get('size_bytes')!=exact['size_bytes']:
        raise v1.C0CError('v5_exact_object_identity')
    raw=path.read_bytes()
    if len(raw)!=exact['size_bytes'] or hashlib.sha256(raw).hexdigest()!=exact['sha256']:
        raise v1.C0CError('v5_download_identity')
    if len(raw)<8 or raw[:4]!=b'JNNW' or struct.unpack('<I',raw[4:8])[0]!=0:
        raise v1.C0CError('v5_header_identity')
    complete,tail=divmod(len(raw)-8,REC)
    if (complete,tail)!=(exact['complete'],exact['tail']):
        raise v1.C0CError('v5_geometry_drift')
    ids=set(); body=raw[8:]
    for i in range(complete):
        rec=body[i*REC:(i+1)*REC]
        ids.add(v1.canonical_from_position_bytes(rec[:33]))
        # rec[33:38] intentionally never decoded or interpreted.
    return ids,complete,{'declared_count':0,'complete_records_recovered':complete,'partial_tail_bytes_discarded':tail,'policy':'inventory_closed_exact_authenticated_v5'}


def build_union_v5(work:Path,artifact:Path)->dict:
    if work.exists() or work.is_symlink(): raise v1.C0CError('work_dir_must_not_exist')
    work.mkdir(parents=True); artifact.mkdir(parents=True,exist_ok=True)
    allow,inv_sha,inv_size=_load_inventory(work)
    c0a,c0b=v1.fetch_parent(work/'parent'); sources={x['job_id']:x for x in c0a.get('sources',[])}
    all_ids=set(); receipts=[]; total_rows=downloaded=zero=salv_files=salv_records=discarded=0; seen=set()
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
        fmap={x['path']:x for x in fetched['files']}
        for i,desc in nonempty:
            got=fmap.get(desc['path'])
            if not got or got['sha256']!=desc['sha256'] or got['size_bytes']!=desc['size_bytes']: raise v1.C0CError('descriptor_drift')
            path=local/f'{i:04d}-{Path(desc["path"]).name}'
            recovered=_salvage(path,desc,job_id,attempt,allow)
            if recovered is not None:
                ids,rows,recovery=recovered; seen.add((job_id,attempt,desc['path'])); sem='position_identity_only_v5_inventory_salvage'
            else:
                try:
                    ids,rows,sem=v1.parse_candidate(path,desc['kind']); recovery=None
                except v1.C0CError:
                    raise v1.C0CError('v5_malformed_not_in_inventory')
            all_ids.update(ids); total_rows+=rows; downloaded+=1
            receipt={'job_id':job_id,'attempt_id':attempt,'path':desc['path'],'kind':desc['kind'],'sha256':desc['sha256'],'size_bytes':desc['size_bytes'],'rows':rows,'unique_identities':len(ids),'semantics':sem}
            if recovery is not None:
                receipt['recovery']=recovery; salv_files+=1; salv_records+=recovery['complete_records_recovered']; discarded+=recovery['partial_tail_bytes_discarded']
            receipts.append(receipt); path.unlink(missing_ok=True)
        shutil.rmtree(local,ignore_errors=True)
    if seen!=set(allow): raise v1.C0CError('v5_inventory_universe_mismatch')
    if not all_ids: raise v1.C0CError('empty_exclusion_union')
    raw=('\n'.join(sorted(all_ids))+'\n').encode('ascii'); (artifact/'ed4-c0c-structural-exclusion-union.txt').write_bytes(raw)
    manifest={'schema':SCHEMA,'state':'completed','verdict':VERDICT,'protocol_change':'inventory_closed_exact_authenticated_salvage_v5_2026-09-11','inventory_job_id':INV_JOB,'inventory_attempt_id':INV_ATTEMPT,'inventory_sha256':inv_sha,'inventory_size_bytes':inv_size,'parent_job_id':v1.PARENT_JOB,'parent_attempt_id':v1.PARENT_ATTEMPT,'parent_c0a_sha256':v1.C0A_SHA,'parent_c0b_sha256':v1.C0B_SHA,'candidate_files_downloaded':downloaded,'candidate_zero_size_authenticated':zero,'candidate_rows_parsed':total_rows,'inventory_salvaged_files':salv_files,'inventory_salvaged_complete_records':salv_records,'discarded_partial_tail_bytes':discarded,'unique_canonical_identities':len(all_ids),'union_sha256':hashlib.sha256(raw).hexdigest(),'union_size_bytes':len(raw),'target_fields_decoded':0,'target_reads':0,'score_reads':0,'wdl_reads':0,'qvalue_reads':0,'model_reads':0,'teacher_calls':0,'search_calls':0,'fits':0,'games':0,'alpha_spent':0,'confirmation_authorized':False,'automatic_continuation':False,'files':receipts}
    (artifact/'ed4-c0c-structural-exclusion-manifest.json').write_text(json.dumps(manifest,sort_keys=True,separators=(',',':'))+'\n')
    return manifest
