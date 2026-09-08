#!/usr/bin/env python3
"""ED2 paired value learning. TEST search is unreachable before model sealing."""
from __future__ import annotations
import argparse
import csv
import gzip
import json
import os
from pathlib import Path
import signal
import struct
import subprocess
import sys
import time
import numpy as np
ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from jobs.tools import ed2_value_math as m

P0_CODE='bc30d6858c4d590625f8831c4995f055816b95c2'
P0_ATTEMPT='20260908T171140Z-bc30d685'
P0_JOB='cpx62-1875-l3-ed2-data-teacher-preflight-v1'
REPLAY_N=8192
ARMS=('POINT','PARTIAL')

def ep_module():
    from jobs.tools import ed2_preflight
    return ed2_preflight

def validate_p0(source,exclusions,seal_path,preflight_path):
    ep=ep_module(); seal=json.loads(seal_path.read_text()); pre=json.loads(preflight_path.read_text())
    check=ep.validate_source(source,exclusions)
    if seal.get('code_sha')!=P0_CODE or seal.get('schema')!='jass.ed2.source_seal.v1' or seal.get('mode')!='production':
        raise ValueError('ED2 P0 identity/mode')
    if seal['files']!={f:m.sha(source/f) for f in ep.FILES} or seal['exclusions_sha256']!=m.sha(exclusions):
        raise ValueError('ED2 source seal drift')
    if any(seal[k]!=v for k,v in check.items()): raise ValueError('source validation differs from seal')
    if pre.get('verdict')!='ED2_DATA_AND_TEACHER_PREFLIGHT_READY_V1' or pre.get('data')!=seal or pre['source_seal_sha256']!=m.sha(seal_path):
        raise ValueError('P0 ready receipt absent or inconsistent')
    if not 0<pre['projected_teacher_plus_fit_seconds']<=2700 or pre['projection_workers']!=8:
        raise ValueError('P0 spending gate failed')
    return pre

def groups_for(source,role):
    ep=ep_module(); rows=ep.load_tsv(source/'groups.tsv'); parents=ep.load_tsv(source/'parents.tsv')
    result=[]
    for p in parents:
        if p['split']!=role: continue
        siblings=[r for r in rows if int(r['parent_id'])==int(p['parent_id'])]
        result.append(dict(id=int(p['parent_id']),cell=p['parent_phase']+'_stm'+p['parent_stm'],stm=int(p['parent_stm']),
                           rows=[int(r['row_index']) for r in siblings],
                           terminals=[int(r['row_index']) for r in siblings if int(r['child_rule_terminal'])]))
    return result

def write_records(path,rows):
    with path.open('xb') as f: f.write(b'JNNW'+struct.pack('<I',len(rows))+b''.join(rows))

def select_replay(data,meta,source,exclusions,out):
    ep=ep_module()
    from tools import selfplay_frontier as sf
    raw=data.read_bytes(); schema,n=sf._meta_file_info(meta)
    if raw[:4]!=b'JNNW' or struct.unpack_from('<I',raw,4)[0]!=2000000 or len(raw)!=76000008 or n!=2000000:
        raise ValueError('CURRENT_2M alignment')
    used=set(exclusions.read_text().splitlines())
    for name in ('parents.jnnw','children.jnnw'): used.update(ep.canonical(r) for r in ep.records(source/name))
    selected={}; opening_sets=[]
    with meta.open('rb') as mf:
        for name,lo,hi,seed in [('replay',0,1800796,202609081201),('wdl_holdout',1800796,2000000,202609081202)]:
            indices=[];records=[];opening=[]
            for rel in np.random.default_rng(seed).permutation(hi-lo):
                i=lo+int(rel); rec=raw[8+38*i:8+38*i+33]+b'\0'*5
                key=ep.canonical(rec)
                if key in used: continue
                mf.seek(8+i*schema.record.size)
                item=sf._decode_meta(mf.read(schema.record.size),schema)
                indices.append(i); records.append(rec); opening.append(item.opening_id);used.add(key)
                if len(indices)==REPLAY_N: break
            if len(indices)!=REPLAY_N or len(set(opening))<32: raise ValueError('WDL subset support')
            write_records(out/(name+'.jnnw'),records)
            selected[name]=dict(indices=indices,opening_ids=opening,data_sha256=m.sha(out/(name+'.jnnw')),seed=seed)
            opening_sets.append(set(opening))
    if opening_sets[0]&opening_sets[1]: raise ValueError('replay/holdout opening leakage')
    result=dict(schema='jass.ed2.wdl_selection.v1',source_data_sha256=m.sha(data),source_meta_sha256=m.sha(meta),
                subsets=selected,targets_accessed=0,benchmark_and_ed2_overlap=0)
    m.write_new(out/'wdl-selection.json',result)
    m.write_new(out/'wdl-selection.seal.json',dict(sha256=m.sha(out/'wdl-selection.json')))
    return result

def targets(path,ids):
    y=np.load(path,allow_pickle=False,mmap_mode='r')
    if y.shape!=(2000000,) or y.dtype!=np.float32: raise ValueError('CURRENT Context30 target shape')
    picked=np.asarray(y[ids],dtype=float)
    if not np.all(np.isfinite(picked)) or np.any((picked<0)|(picked>1)): raise ValueError('invalid WDL target')
    return picked

def verify_model_seal(art):
    seal=json.loads((art/'models-sealed.json').read_text())
    if set(seal['models'])!=set(ARMS) or seal['test_teacher_calls']!=0: raise ValueError('model seal contract')
    for arm in ARMS:
        if seal['models'][arm]!=m.sha(art/(arm+'.pjtw')): raise ValueError('sealed candidate changed')
    if seal['base_sha256']!=m.BASE_SHA: raise ValueError('base identity changed')
    return seal

def score_worker(source,scan,role,shard,out,timeout_s,art):
    if role=='test': verify_model_seal(art)
    from jobs.tools.scan_ceiling_scan_score import NodeScanEngine,record_to_scan_pos,terminal_observation
    if role not in ('train','test') or not 0<=shard<8: raise ValueError('score role/shard')
    children=ep_module().records(source/'children.jnnw')
    groups=groups_for(source,role); roles={r for g in groups for r in g['rows']}
    terminal={r for g in groups for r in g['terminals']}
    budgets=(5000,50000) if role=='train' else (200000,)
    engine=NodeScanEngine(str(scan.resolve()),label=f'ED2-{role}-{shard}')
    try:
        with out.open('x') as f:
            for rid in sorted(roles):
                if rid%8!=shard: continue
                for budget in budgets:
                    obs=terminal_observation() if rid in terminal else engine.search_nodes(record_to_scan_pos(children[rid]),budget,timeout_s)
                    f.write(json.dumps(dict(row=rid,budget=budget,score=int(obs['parent_score_centi']),
                         terminal=rid in terminal,elapsed=float(obs['elapsed_seconds']),last_info_nodes=int(obs['last_info_nodes'])),sort_keys=True)+'\n')
                    f.flush()
    finally: engine.close()

def load_scores(paths,groups,budgets):
    want={(r,n) for g in groups for r in g['rows'] for n in budgets}; values={}; requested=0;calls=0
    terminal={r for g in groups for r in g['terminals']}
    for path in paths:
        with path.open() as f:
            for line in f:
                r=json.loads(line); key=(r['row'],r['budget'])
                if key not in want or key in values or type(r['score']) is not int or r['terminal']!=(r['row'] in terminal):
                    raise ValueError('teacher role/coverage/value drift')
                values[key]=float(r['score'])
                if not r['terminal']: requested+=r['budget'];calls+=1
    if set(values)!=want: raise ValueError('incomplete teacher coverage')
    return values,dict(requested_nodes=requested,searches=calls,rows=len(values))

def teacher_deadline(groups,role,pre):
    ns=(5000,50000) if role=='train' else (200000,)
    times=pre['observed_seconds_by_budget']; rowcost=sum(max(times[str(n)]) for n in ns)
    count=max(sum(r%8==i for g in groups for r in g['rows']) for i in range(8))
    return max(60.0,2.0*rowcost*count+60.0)

def role_search(source,scan,role,art,work,pre):
    if role=='test': verify_model_seal(art)
    gs=groups_for(source,role); ns=(5000,50000) if role=='train' else (200000,)
    deadline=teacher_deadline(gs,role,pre)
    if deadline>1200: raise ValueError('per-stage teacher spending limit exceeded')
    files=[art/f'{role}-{i}.jsonl' for i in range(8)];procs=[];logs=[];started=time.monotonic()
    try:
        for i,path in enumerate(files):
            log=(work/f'{role}-{i}.log').open('xb');logs.append(log)
            cmd=[sys.executable,str(Path(__file__).resolve()),'score','--source',str(source),'--scan',str(scan),
                 '--role',role,'--shard',str(i),'--out',str(path),'--art',str(art),'--rpc-timeout','30']
            procs.append(subprocess.Popen(cmd,stdout=log,stderr=subprocess.STDOUT,start_new_session=True))
        while any(p.poll() is None for p in procs):
            if any(p.poll() not in (None,0) for p in procs): raise ValueError('teacher worker failed; no partial harvest')
            if time.monotonic()-started>deadline: raise TimeoutError('teacher batch timeout')
            time.sleep(.2)
        if any(p.returncode!=0 for p in procs): raise ValueError('teacher worker failed')
    finally:
        for p in procs:
            # Kill the worker process group, including any orphaned Scan child.
            try: os.killpg(p.pid,signal.SIGTERM)
            except ProcessLookupError: pass
        for p in procs:
            try: p.wait(timeout=3)
            except subprocess.TimeoutExpired:
                try: os.killpg(p.pid,signal.SIGKILL)
                except ProcessLookupError: pass
                p.wait()
        for f in logs: f.close()
    values,cost=load_scores(files,gs,ns)
    cost.update(wall_seconds=time.monotonic()-started,timeout_seconds=deadline)
    m.write_new(art/(role+'-teacher.json'),cost)
    return values,cost

def run_probe(binary,data,model,out):
    subprocess.run([str(binary),str(data),str(model),str(out)],check=True,timeout=180)
    n=struct.unpack_from('<I',data.read_bytes(),4)[0]
    return m.native_table(out,n)

def terminal(art,verdict,**kw):
    payload=dict(schema='jass.ed2.paired_value_terminal.v1',verdict=verdict,**kw,
          new_jass_search_nodes=0,strength_games=0,selfplay_games=0,promotions=0,bakes=0,
          benchmark_training_allowed=False,reference_is_exact_truth=False,
          strength_authorized=False,automatic_continuation=False)
    m.write_new(art/'scientific-summary.json',payload)
    (art/('VERDICT__'+verdict)).write_text(verdict+'\n')
    return payload

def phase(art,work,name):
    text='phase='+name+' time_utc='+time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())+'\n'
    with (work/'RESULTS.txt').open('a') as f: f.write(text)
    (art/'PROGRESS.txt').write_text(text)
    print(text,flush=True)

def run(a):
    ep=ep_module();source=a.source;art=a.art;work=a.work
    phase(art,work,'authenticate-source-and-spending-gate')
    pre=validate_p0(source,a.exclusions,a.source_seal,a.preflight)
    if m.sha(a.base)!=m.BASE_SHA: raise ValueError('frozen WDL_CONTROL mismatch')
    build=json.loads(a.scan_build.read_text())
    if build['source_commit']!='7aae17e7b7bfc47744601afb1ee7655e18983ce5' or build['scan_binary_sha256']!=m.sha(a.scan) or pre['scan_binary_sha256']!=m.sha(a.scan):
        raise ValueError('official Scan identity mismatch')
    phase(art,work,'select-and-seal-wdl-replay-without-targets')
    train=groups_for(source,'train');test=groups_for(source,'test')
    if len(train)!=512 or len(test)!=256: raise ValueError('fixed split cardinalities')
    caps={role:teacher_deadline(gs,role,pre) for role,gs in [('train',train),('test',test)]}
    if max(caps.values())>1200:
        return terminal(art,'ED2_PAIRED_COMPUTE_REVIEW_REQUIRED_V1',fits=0,training_labels_generated=0,test_labels_generated=0,teacher_caps=caps,next_stage='STOP_COMPUTE_REVIEW')
    selection=select_replay(a.current,a.meta,source,a.exclusions,art)
    children=ep.records(source/'children.jnnw');train_ids=[r for g in train for r in g['rows']]
    write_records(work/'train.jnnw',[children[i] for i in train_ids])
    tx,tz,_=run_probe(a.probe,work/'train.jnnw',a.base,work/'train-native.tsv')
    rx,rz,_=run_probe(a.probe,art/'replay.jnnw',a.base,work/'replay-native.tsv')
    phi=np.zeros((len(children),240));z=np.zeros(len(children))
    phi[train_ids]=tx;z[train_ids]=tz
    y=targets(a.targets,selection['subsets']['replay']['indices'])
    phase(art,work,'train-only-scan-5k-50k')
    low,train_cost=role_search(source,a.scan,'train',art,work,pre)
    edges={};support={}
    for arm in ARMS: edges[arm],support[arm]=m.pair_edges(train,low,arm)
    m.write_new(art/'label-support.json',support)
    m.write_new(art/'train-labels-sealed.json',dict(source_seal=m.sha(a.source_seal),
         teacher_files={f'train-{i}.jsonl':m.sha(art/f'train-{i}.jsonl') for i in range(8)},
         recipe=m.RECIPE,test_teacher_calls=0,support=support))
    s=support['PARTIAL']
    if s['supported_parents']<256 or any(s['cells'].get('P'+str(p)+'_stm'+str(c),0)<16 for p in range(4) for c in range(2)) or s['mean_retained_coverage']<.25:
        return terminal(art,'ED2_PARTIAL_ORDER_TRAIN_SUPPORT_INSUFFICIENT_V1',fits=0,train_teacher=train_cost,next_stage='STOP_ED2')
    models={}
    for arm in ARMS:
        phase(art,work,'fit-'+arm.lower())
        def fit_timeout(_signum,_frame): raise TimeoutError('300s fit cap reached')
        prior_handler=signal.signal(signal.SIGALRM,fit_timeout)
        signal.alarm(300)
        try: beta,report=m.fit(phi,z,edges[arm],rx,rz,y)
        finally:
            signal.alarm(0);signal.signal(signal.SIGALRM,prior_handler)
        report['model']=m.quantize(a.base,beta,art/(arm+'.pjtw'))
        report['training_labels_seal_sha256']=m.sha(art/'train-labels-sealed.json')
        # Reopen the actual quantized artifact with the production C++ loader.
        xx,zz,_=run_probe(a.probe,work/'train.jnnw',art/(arm+'.pjtw'),work/(arm+'-train-native.tsv'))
        if not np.array_equal(xx,tx): raise ValueError('native feature path changed between arms')
        models[arm]=m.sha(art/(arm+'.pjtw')); m.write_new(art/(arm+'-fit.json'),report)
    if m.sha(a.base)!=m.BASE_SHA: raise ValueError('base mutated during training')
    m.write_new(art/'models-sealed.json',dict(models=models,base_sha256=m.BASE_SHA,test_teacher_calls=0,
              label_seal_sha256=m.sha(art/'train-labels-sealed.json'),wdl_selection_sha256=m.sha(art/'wdl-selection.json')))
    # This is the FIRST permitted TEST reference access/call.
    phase(art,work,'models-sealed-then-test-scan-200k')
    high,test_cost=role_search(source,a.scan,'test',art,work,pre)
    test_ids=[r for g in test for r in g['rows']]
    write_records(work/'test.jnnw',[children[i] for i in test_ids])
    yh=targets(a.targets,selection['subsets']['wdl_holdout']['indices'])
    hold=ep.records(art/'wdl_holdout.jnnw')
    stm_sign=np.array([1 if r[32]==1 else -1 for r in hold])
    drows={};wdl={};losses={};probs={}
    for arm in ('BASE',)+ARMS:
        model=a.base if arm=='BASE' else art/(arm+'.pjtw')
        _,_,cp=run_probe(a.probe,work/'test.jnnw',model,work/(arm+'-test-native.tsv'))
        scores=np.zeros(len(children),dtype=int);scores[test_ids]=cp
        drows[arm]=m.decision_rows(test,high,scores)
        _,_,hc=run_probe(a.probe,art/'wdl_holdout.jnnw',model,work/(arm+'-holdout-native.tsv'))
        black=stm_sign*hc/100.0
        losses[arm]=np.logaddexp(0,black)-yh*black;probs[arm]=1/(1+np.exp(-black))
        wdl[arm]=dict(logloss=float(np.mean(losses[arm])),brier=float(np.mean((probs[arm]-yh)**2)))
    phase(art,work,'native-readout-and-opening-cluster-wdl-guard')
    vsbase=m.compare_decisions(drows['BASE'],drows['PARTIAL'],202609081301)
    vspoint=m.compare_decisions(drows['POINT'],drows['PARTIAL'],202609081302)
    wb=m.bootstrap_opening(losses['PARTIAL']-losses['BASE'],selection['subsets']['wdl_holdout']['opening_ids'],202609081303)
    gates=dict(regret_beats_base=vsbase['ci95'][0]>0,regret_beats_point=vspoint['ci95'][0]>0,
               top_hit_not_lower=vsbase['top_hit_delta']>=0 and vspoint['top_hit_delta']>=0,
               harms_not_more_than_improvements=vsbase['harmed']<=vsbase['improved'],
               wdl_noninferior=wb['ci95'][1]<=.002,
               brier_noninferior=wdl['PARTIAL']['brier']<=wdl['BASE']['brier']+.002)
    verify_model_seal(art)
    m.write_new(art/'test-parent-readout.json',drows)
    return terminal(art,'ED2_PARTIAL_ORDER_VALUE_SIGNAL_V1' if all(gates.values()) else 'ED2_PARTIAL_ORDER_VALUE_NOT_SUPPORTED_V1',
          fits=2,model_searches=0,recipe=m.RECIPE,models=models,gates=gates,versus_base=vsbase,versus_point=vspoint,
          wdl_holdout=wdl,wdl_delta_bootstrap=wb,train_teacher=train_cost,test_teacher=test_cost,
          test_parents=256,test_cells=32,wdl_rows=REPLAY_N,wdl_is_historical_context30_guard=True,
          next_stage='PREREG_NATIVE_GATE0' if all(gates.values()) else 'STOP_ED2',
          source_seal_sha256=m.sha(a.source_seal),model_seal_sha256=m.sha(art/'models-sealed.json'))

def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='cmd',required=True)
    score=sub.add_parser('score')
    for name in ('source','scan','out','art'): score.add_argument('--'+name,type=Path,required=True)
    score.add_argument('--role',choices=['train','test'],required=True);score.add_argument('--shard',type=int,required=True)
    score.add_argument('--rpc-timeout',type=float,default=30)
    r=sub.add_parser('run')
    for name in ('source','exclusions','source-seal','preflight','base','current','meta','targets','scan','scan-build','probe','art','work'):
        r.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args()
    try:
        if a.cmd=='score': score_worker(a.source,a.scan,a.role,a.shard,a.out,a.rpc_timeout,a.art)
        else: print(run(a)['verdict'])
        return 0
    except (OSError,ValueError,KeyError,TypeError,TimeoutError,subprocess.SubprocessError) as e:
        print('ED2_PAIRED_VALUE_TECHNICAL_FAILURE: '+str(e),file=sys.stderr);return 2
if __name__=='__main__': raise SystemExit(main())
