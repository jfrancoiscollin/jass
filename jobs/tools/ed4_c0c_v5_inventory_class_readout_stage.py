#!/usr/bin/env python3
from __future__ import annotations
import collections, json, os, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from jobs.tools import fetch_result_files
from jobs.tools.launch_runtime_v2 import StageEvidence, atomic_json

INV_JOB='cpx62-1922-l3-ed4-c0c-v4-full-malformed-inventory-v1'
INV_ATTEMPT='20260911T181346Z-832b0339'
INV_CODE='832b0339fe02cbf3b187377ff475a3ddd289e0d6'
INV_PATH='artefacts/ed4-c0c-v4-full-malformed-inventory.json'


def main():
    art=Path(os.environ['JASS_ARTEFACT_DIR']); result=Path(os.environ['JASS_RESULT_DIR']); ev=StageEvidence(art,os.environ['LAUNCH_MODE'])
    try:
        ev.begin('authenticate-1922-inventory')
        prefix=f'r2:jass-data/runs/{INV_JOB}/{INV_ATTEMPT}'
        inv=fetch_result_files.inspect_result_inventory(rclone='rclone',prefix=prefix,expected_state='completed')
        if (inv.get('job_id'),inv.get('attempt_id'),inv.get('code_sha'),inv.get('result_state'))!=(INV_JOB,INV_ATTEMPT,INV_CODE,'completed'):
            raise RuntimeError('inventory_identity')
        item=next((x for x in inv.get('files',[]) if x.get('path')==INV_PATH),None)
        if not item: raise RuntimeError('inventory_artifact_missing')
        out=result/'inventory'; out.mkdir(parents=True,exist_ok=True)
        got=fetch_result_files.fetch_files(rclone='rclone',prefix=prefix,expected_state='completed',selections=[(INV_PATH,'inventory.json')],out_dir=out)
        f=got['files'][0]
        if f.get('sha256')!=item.get('sha256') or f.get('size_bytes')!=item.get('size_bytes'): raise RuntimeError('inventory_artifact_drift')
        ev.complete()
        ev.begin('classify-structural-rows-only')
        obj=json.loads((out/'inventory.json').read_text())
        rows=obj.get('malformed') or []
        hist=collections.Counter((str(r.get('kind')),str(r.get('reason')),str(bool(r.get('interrupted_writer_shape')))) for r in rows)
        outside=[]
        for r in rows:
            if r.get('interrupted_writer_shape') is True: continue
            outside.append({k:r.get(k) for k in ('job_id','attempt_id','path','kind','reason','state','declared_count','sha256','size_bytes','complete_records_from_size','partial_tail_bytes_from_size','interrupted_writer_shape')})
        ev.complete()
        ev.begin('publish-class-readout')
        result_obj={'schema':'jass.ed4.c0c_v5_inventory_class_readout.v1','state':'completed','inventory_job_id':INV_JOB,'malformed_count':len(rows),'interrupted_writer_count':sum(1 for r in rows if r.get('interrupted_writer_shape') is True),'outside_class_count':len(outside),'histogram':[{'kind':k[0],'reason':k[1],'interrupted_writer_shape':k[2]=='True','count':v} for k,v in sorted(hist.items())],'outside_class':outside,'record_fields_decoded':0,'position_identity_reads':0,'target_fields_decoded':0,'target_reads':0,'wdl_reads':0,'qvalue_reads':0,'alpha_spent':0,'scientific_verdict':None,'confirmation_authorized':False}
        atomic_json(art/'ed4-c0c-v5-inventory-class-readout.json',result_obj); atomic_json(art/'scientific-summary.json',result_obj)
        ev.complete(); ev.finish(); return 0
    except Exception as exc:
        ev.fail(exc); atomic_json(art/'scientific-summary.json',{'schema':'jass.ed4.c0c_v5_inventory_class_readout_failure.v1','state':'failed','classification':'TECHNICAL','error_type':type(exc).__name__,'scientific_verdict':None,'target_reads':0,'alpha_spent':0}); return 2

if __name__=='__main__': raise SystemExit(main())
