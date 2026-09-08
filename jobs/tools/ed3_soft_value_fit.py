#!/usr/bin/env python3
"""ED3-P1 candidate construction. No teacher search or held-out target access.

Rehearsal performs a development fit on a fixed representative TRAIN subset,
then the exact production serialization/native/publisher path. Production fits
one candidate on all frozen TRAIN parents. These receipts authorize no evaluation
pipeline: a distinct untouched-data confirmation stage still needs its own proof.
"""
from __future__ import annotations
import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import struct
import subprocess
import sys
import traceback
import numpy as np

ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from jobs.tools import ed3_label_pressure as audit
from jobs.tools import ed2_preflight as ep
from jobs.tools import ed2_value_math as native
from jobs.tools import ed3_soft_value_math as soft
from jobs.tools.launch_runtime_v2 import StageEvidence, atomic_json

PHASES=['authenticate','verify-inputs','native-base','fit-soft','serialize-and-reload','seal-and-publish']
TRAIN_PARENTS=512
TRAIN_ROWS=4976
TRAIN_PAIRS=17622
REPLAY_N=8192
CELL_QUOTA=64
DEVELOPMENT_PER_CELL=8
MODEL_HASH=dict(audit.MODEL_HASH)
P0_NAMES=['source/groups.tsv','source/children.jnnw','ed2-source-seal.json']
N1_NAMES=audit.TRAIN_NAMES+['train-labels-sealed.json','label-support.json',
    'wdl-selection.json','wdl-selection.seal.json','replay.jnnw',
    'native/train-native.tsv.gz','native/replay-native.tsv.gz',
    'PARTIAL.pjtw','build-outputs/jass_ed2_value_probe.gz','scratch-cleanup.json']
OUTPUTS=['SOFT.pjtw','candidate-seal.json','fit-report.json','native-roundtrip.json','train-contract.json']


def require(ok,code):
    if not ok:raise ValueError(code)


def unpack(source,dest):
    with gzip.open(source,'rb') as src,dest.open('xb') as out:shutil.copyfileobj(src,out)


def write_records(path,rows):
    with path.open('xb') as out:out.write(b'JNNW'+struct.pack('<I',len(rows))+b''.join(rows))


def select_groups(groups,mode):
    require(mode in ('production','rehearsal'),'mode')
    if mode=='production':return groups
    seen={};selected=[]
    for group in groups:
        cell=group['cell']
        if seen.get(cell,0)<DEVELOPMENT_PER_CELL:
            selected.append(group);seen[cell]=seen.get(cell,0)+1
    require(len(seen)==8 and set(seen.values())=={DEVELOPMENT_PER_CELL},'development_cells')
    return selected


def load_inputs(roots,work,mode):
    p0,n1,base,target=(roots[k] for k in ('p0','n1','base','target'))
    require(audit.sha(p0/'ed2-source-seal.json')==audit.SOURCE_SEAL,'p0_seal_identity')
    source_seal=audit.load_json(p0/'ed2-source-seal.json')
    for name in ('groups.tsv','children.jnnw'):
        require(audit.sha(p0/'source'/name)==source_seal['files'][name],'source_bytes')
    groups,scores=audit.groups_and_scores(p0,n1,expected_parents=TRAIN_PARENTS)
    all_edges,rows=audit.pair_data(groups,scores)
    require(rows==TRAIN_ROWS and len(all_edges[0])==TRAIN_PAIRS,'frozen_train_shape')
    cells={}
    for group in groups:cells[group['cell']]=cells.get(group['cell'],0)+1
    require(len(cells)==8 and set(cells.values())=={CELL_QUOTA},'frozen_train_cells')
    tau=soft.train_temperature(all_edges[4],all_edges[2])
    # The recipe is checked against the already-established numerical solver,
    # without changing old ED2 modules or reusing any of their test outcomes.
    from jobs.tools.ed2_value_trust_exact import SOLVER
    require(soft.SOLVER==SOLVER and soft.RIDGE==native.L2,'numerical_recipe_drift')
    full_x,full_z=audit.table(n1/'native/train-native.tsv.gz',TRAIN_ROWS)
    rx,rz=audit.table(n1/'native/replay-native.tsv.gz',REPLAY_N)
    children=ep.records(p0/'source/children.jnnw')
    selection=audit.load_json(n1/'wdl-selection.json')
    require(audit.load_json(n1/'wdl-selection.seal.json')['sha256']==audit.sha(n1/'wdl-selection.json'),'wdl_selection_seal')
    selected=selection['subsets']['replay']
    ids=selected['indices']
    require(len(ids)==REPLAY_N and len(set(ids))==REPLAY_N and min(ids)>=0 and max(ids)<1800796,'replay_indices')
    require(audit.sha(n1/'replay.jnnw')==selected['data_sha256'],'replay_bytes')
    replay=ep.records(n1/'replay.jnnw')
    require(len(replay)==REPLAY_N,'replay_count')
    unpack(target/'current_2m-context30.npy.gz',work/'targets.npy')
    targets=np.load(work/'targets.npy',mmap_mode='r',allow_pickle=False)
    require(targets.shape==(2000000,) and targets.dtype==np.float32,'target_layout')
    y=np.asarray(targets[ids],dtype=np.float64)  # ONLY historical TRAIN replay.
    require(np.isfinite(y).all() and ((0<=y)&(y<=1)).all(),'replay_values')
    unpack(base/'WDL_CONTROL.pjtw.gz',work/'BASE.pjtw')
    audit.weights(work/'BASE.pjtw',MODEL_HASH['BASE'])
    audit.weights(n1/'PARTIAL.pjtw',MODEL_HASH['PARTIAL'])
    raw,offset,_=native.read_model(work/'BASE.pjtw')
    hard,hard_offset,_=native.read_model(n1/'PARTIAL.pjtw')
    require(offset==hard_offset and raw[:offset]==hard[:offset],'frozen_pattern_prefix')
    archive=n1/'build-outputs/jass_ed2_value_probe.gz'
    binary_receipt=audit.load_json(n1/'scratch-cleanup.json')['retained_binaries']['jass_ed2_value_probe']
    require(audit.sha(archive)==binary_receipt['archive_sha256'],'native_archive_identity')
    unpack(archive,work/'native-probe')
    require(audit.sha(work/'native-probe')==binary_receipt['sha256'],'native_binary_identity')
    (work/'native-probe').chmod(0o500)
    chosen=select_groups(groups,mode)
    full_ids=[r for g in groups for r in g['rows']];mapping={r:i for i,r in enumerate(full_ids)}
    row_ids=[r for g in chosen for r in g['rows']]
    subset=[mapping[r] for r in row_ids]
    edges,count=audit.pair_data(chosen,scores)
    require(count==len(subset),'subset_alignment')
    write_records(work/'train.jnnw',[children[i] for i in row_ids])
    # Full 8192-row replay even in rehearsal: realistic feature scales and
    # correlations, not a 40-row easy Gaussian convergence demonstration.
    write_records(work/'replay.jnnw',replay)
    return dict(x=full_x[subset],z=full_z[subset],rx=rx,rz=rz,y=y,edges=edges,tau=tau,
                parents=len(chosen),rows=len(subset),base=work/'BASE.pjtw',
                probe=work/'native-probe',train=work/'train.jnnw',replay=work/'replay.jnnw',
                contract=dict(schema='jass.ed3.soft_train_contract.v1',mode=mode,
                    recipe=soft.RECIPE,recipe_sha256=soft.recipe_sha256(),
                    source_seal_sha256=audit.SOURCE_SEAL,
                    train_labels_seal_sha256=audit.sha(n1/'train-labels-sealed.json'),
                    wdl_selection_sha256=audit.sha(n1/'wdl-selection.json'),
                    base_sha256=MODEL_HASH['BASE'],hard_control_sha256=MODEL_HASH['PARTIAL'],
                    native_binary_sha256=binary_receipt['sha256'],tau=tau,
                    tau_from_all_train_parents=TRAIN_PARENTS,tau_from_all_train_pairs=TRAIN_PAIRS,
                    fit_parents=len(chosen),parent_normalizer=len(chosen),pair_count=len(edges[0]),
                    train_rows=len(subset),replay_rows=REPLAY_N,
                    train_parent_ids=[g['id'] for g in chosen],
                    train_rows_sha256=audit.sha(work/'train.jnnw'),
                    replay_rows_sha256=audit.sha(work/'replay.jnnw'),
                    new_scan_searches=0,test_target_reads=0))


def run_probe(binary,data,model,out):
    with out.with_suffix('.log').open('xb') as log:
        subprocess.run([str(binary),str(data),str(model),str(out)],
                       stdout=log,stderr=subprocess.STDOUT,check=True,timeout=180)
    n=struct.unpack_from('<I',data.read_bytes(),4)[0]
    return native.native_table(out,n)


def check_table(table,x,z):
    xx,zz,cp=table
    require(np.array_equal(xx,x),'native_features_changed')
    error=float(np.max(np.abs(zz-z)))
    require(error<=1e-9 and np.isfinite(zz).all(),'native_value_drift')
    require(cp.shape==(len(x),),'native_score_cardinality')
    return error


def verify_candidate(artifact,mode):
    seal=audit.load_json(artifact/'candidate-seal.json')
    require(seal['schema']=='jass.ed3.soft_candidate_seal.v1' and seal['mode']==mode,'candidate_role')
    require(seal['role']==('candidate' if mode=='production' else 'development_only'),'candidate_role')
    require(seal['model_sha256']==audit.sha(artifact/'SOFT.pjtw'),'candidate_hash')
    require(seal['recipe_sha256']==soft.recipe_sha256(),'candidate_recipe')
    require(seal['base_sha256']==MODEL_HASH['BASE'] and seal['hard_control_sha256']==MODEL_HASH['PARTIAL'],'candidate_controls')
    require(seal['test_target_reads']==0 and seal['runtime_authorized'] is False,'candidate_boundary')
    for file in ('fit-report.json','native-roundtrip.json','train-contract.json'):
        require(seal['evidence_sha256'][file]==audit.sha(artifact/file),'candidate_evidence_changed')
    return seal


def run(result,artifact,mode,downloader=audit.fetch_existing,loader=load_inputs,probe=run_probe):
    evidence=StageEvidence(artifact,mode)
    work=result/'work';work.mkdir(parents=True,exist_ok=True)
    roots={name:result/'inputs'/name for name in ('p0','n1','base','target')}
    try:
        evidence.begin('authenticate')
        for key,identity,names in [('p0',audit.P0,P0_NAMES),('n1',audit.N1,N1_NAMES),
                ('base',audit.BASE,['WDL_CONTROL.pjtw.gz']),('target',audit.TARGET,['current_2m-context30.npy.gz'])]:
            downloader(identity,names,roots[key],artifact/('verified-'+key+'.json'))
        evidence.complete();evidence.begin('verify-inputs')
        d=loader(roots,work,mode)
        atomic_json(artifact/'train-contract.json',d['contract'])
        evidence.complete();evidence.begin('native-base')
        errors={}
        for label,x,z in [('train',d['x'],d['z']),('replay',d['rx'],d['rz'])]:
            errors['base_'+label]=check_table(probe(d['probe'],d[label],d['base'],work/(label+'-base.tsv')),x,z)
        native.quantize(d['base'],np.zeros(soft.WIDTH),work/'zero-residual.pjtw')
        require(audit.sha(work/'zero-residual.pjtw')==MODEL_HASH['BASE'],'zero_roundtrip')
        evidence.complete();evidence.begin('fit-soft')
        evidence.value['actual_side_effects']['fits']=1;evidence.save()
        def too_long(_signum,_frame):raise TimeoutError('ED3_FIT_300S_LIMIT')
        previous=signal.signal(signal.SIGALRM,too_long);signal.alarm(300)
        try:
            beta,report=soft.fit(d['x'],d['z'],d['edges'],d['rx'],d['rz'],d['y'],d['tau'],
                                 report_path=artifact/'solver-diagnostic.json')
        finally:signal.alarm(0);signal.signal(signal.SIGALRM,previous)
        evidence.complete();evidence.begin('serialize-and-reload')
        model=artifact/'SOFT.pjtw'
        quantization=native.quantize(d['base'],beta,model)
        raw,offset,bw=native.read_model(d['base']);new,off,sw=native.read_model(model)
        require(raw[:offset]==new[:off],'pattern_prefix_changed')
        for label,x,z in [('train',d['x'],d['z']),('replay',d['rx'],d['rz'])]:
            path=work/(label+'-soft.tsv')
            observed=probe(d['probe'],d[label],model,path)
            errors['soft_'+label]=check_table(observed,x,z+x@(sw-bw))
            # Native integer decision scores must replay exactly after a second
            # process loads the same file, not just agree in Python float space.
            repeated=probe(d['probe'],d[label],model,work/(label+'-reloaded.tsv'))
            require(all(np.array_equal(a,b) for a,b in zip(observed,repeated)),'native_reload_mismatch')
        require(audit.sha(d['base'])==MODEL_HASH['BASE'],'base_mutated')
        report.update(mode=mode,quantization=quantization,scientific_verdict=None,
                      training_only=True,heldout_evaluation_performed=False)
        atomic_json(artifact/'fit-report.json',report)
        atomic_json(artifact/'native-roundtrip.json',dict(schema='jass.ed3.native_roundtrip.v1',
            native_binary_sha256=audit.sha(d['probe']),rows=d['rows']+len(d['y']),
            maximum_logit_errors=errors,native_reload_mismatches=0,
            zero_residual_byte_identical=True,pattern_prefix_byte_identical=True,
            probe_calls=6,searches=0))
        evidence.complete();evidence.begin('seal-and-publish')
        seal=dict(schema='jass.ed3.soft_candidate_seal.v1',mode=mode,
            role='candidate' if mode=='production' else 'development_only',
            model_sha256=audit.sha(model),recipe_sha256=soft.recipe_sha256(),
            base_sha256=MODEL_HASH['BASE'],hard_control_sha256=MODEL_HASH['PARTIAL'],
            source_seal_sha256=audit.SOURCE_SEAL,tau=d['tau'],test_target_reads=0,
            runtime_authorized=False,automatic_continuation=False,
            evidence_sha256={p:audit.sha(artifact/p) for p in ('fit-report.json','native-roundtrip.json','train-contract.json')})
        atomic_json(artifact/'candidate-seal.json',seal);verify_candidate(artifact,mode)
        summary=dict(schema='jass.ed3.soft_value_build.v1',mode=mode,
            verdict='ED3_SOFT_VALUE_CANDIDATE_SEALED_V1' if mode=='production' else 'ED3_SOFT_VALUE_REHEARSAL_COMPLETE_V1',
            scientific_verdict=None,scientific_success_established=False,
            fits=1,fit_role=seal['role'],train_parents=d['parents'],train_rows=d['rows'],
            train_pairs=len(d['edges'][0]),replay_rows=len(d['y']),tau=d['tau'],
            model_sha256=seal['model_sha256'],candidate_seal_sha256=audit.sha(artifact/'candidate-seal.json'),
            solver_iterations=report['iterations'],gradient_l2=report['gradient_l2'],
            native_reload_mismatches=0,new_scan_searches=0,new_jass_searches=0,
            test_target_reads=0,strength_games=0,selfplay_games=0,promotions=0,bakes=0,
            heldout_evaluation_performed=False,runtime_authorized=False,automatic_continuation=False,
            next_stage='PREREGISTER_DISJOINT_ED3_CONFIRMATION' if mode=='production' else 'AUTHENTICATE_REHEARSAL_BEFORE_PRODUCTION')
        atomic_json(artifact/'scientific-summary.json',summary)
        evidence.complete();evidence.finish()
        return summary
    except BaseException as exc:
        evidence.fail(exc)
        raise


def main():
    result=Path(os.environ['JASS_RESULT_DIR']);art=Path(os.environ['JASS_ARTEFACT_DIR'])
    mode=os.environ['LAUNCH_MODE']
    from jobs.tools.ed2_value_entrypoint import install_shutdown_handlers
    install_shutdown_handlers()
    try:
        report=run(result,art,mode)
        print(report['verdict']);return 0
    except Exception:
        traceback.print_exc();return 2

if __name__=='__main__':raise SystemExit(main())
