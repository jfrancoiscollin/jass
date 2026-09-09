"""Literal, checksum-authenticated archived inputs for the fit-free ED3-T1 audit.

No engine, data generator, optimizer, bootstrap or inventory-driven selection is
called. Target arrays are indexed only after the frozen ownership checks pass.
"""
from __future__ import annotations
from collections import Counter
import gzip
import json
from pathlib import Path
import shutil
import struct
import numpy as np
from jobs.tools import ed2_preflight as ep
from jobs.tools import ed3_label_pressure as labels
from jobs.tools import ed3_confirmation_data as data
from jobs.tools.ed2_value_math import read_model, decision_rows
from jobs.tools.ed3_confirmation import load_scores, MODEL_SHA, SOFT_SOURCE, SOFT_SEAL
from jobs.tools.ed3_soft_value_fit import verify_candidate
from jobs.tools.fetch_result_files import fetch_files

CONFIRMATION=('cpx62-1884-l3-ed3-confirmation-production-v1',
              '20260909T051901Z-0946f57d','0946f57d5443c0507fd9210371396bdf1c49abd2')
SOURCES={'p0':labels.P0,'hard':labels.N1,'soft':SOFT_SOURCE,'confirmation':CONFIRMATION}
COHORT_SEAL='f1ce4d2d8cdb947c1dbfc1bdccdfc588927a4299f661d58097b0507e28a5bb8b'
REPORT_SHA='702f9115820ed6cf7833a46483c0250ec0df9ae545f4451a64c594fdf54ec49a'
PARENT_SHA='9f884dcce3ba20a2d4d1589e0fcb6b16394d9e82bc5e50b8b93f14244c156b77'
ALLOWLIST={
 'p0':['artefacts/ed2-source-seal.json']+['artefacts/source/'+f for f in ep.FILES],
 'hard':['artefacts/'+f for f in labels.TRAIN_NAMES+[
     'train-labels-sealed.json','label-support.json','native/train-native.tsv.gz',
     'native/PARTIAL-train-native.tsv.gz','PARTIAL.pjtw']]+['work/train.jnnw'],
 'soft':['artefacts/'+f for f in ['SOFT.pjtw','candidate-seal.json','fit-report.json',
     'native-roundtrip.json','train-contract.json']]+['work/'+f for f in [
     'train-soft.tsv','train-reloaded.tsv','train-base.tsv','train.jnnw']],
 'confirmation':['artefacts/'+f for f in ['model-identities.json','cohort-seal.json',
     'guard-plan.json','confirmation-readout.json','parent-readout.json']+
     [f'reference-{i}.jsonl' for i in range(8)]]+
     ['artefacts/source/'+f for f in ep.FILES]+['work/'+f for f in [
     'BASE.pjtw','BASE-decisions.tsv','HARD-decisions.tsv','SOFT-decisions.tsv',
     'BASE-guard.tsv','HARD-guard.tsv','SOFT-guard.tsv','BASE-repeat.tsv',
     'decisions.jnnw','guard.jnnw']]+['inputs/n1/work/current-context30.npy']}
ARMS=('BASE','HARD','SOFT')

def need(ok,code):
    if not ok: raise ValueError(code)

def read(path):
    return json.loads(path.read_text())

def native_table(path,n):
    """Keep raw phase/features as well as their frozen 240-column transform."""
    opener=gzip.open if path.suffix=='.gz' else Path.open
    with opener(path,'rt') as f:
        a=np.loadtxt(f,delimiter='\t',skiprows=1,ndmin=2)
    need(a.shape==(n,124) and np.isfinite(a).all(),'native_shape_or_finite')
    need(np.array_equal(a[:,0],np.arange(n)),'native_row_order')
    need(((a[:,3]>=0)&(a[:,3]<=1)).all() and np.equal(a[:,2],np.trunc(a[:,2])).all(),
         'native_phase_or_integer')
    x=np.hstack((a[:,4:]*a[:,3,None],a[:,4:]*(1-a[:,3,None])))
    return dict(x=x,z=a[:,1],cp=a[:,2].astype(np.int64),raw_features=a[:,3:])

def verify_tables(tables,weights):
    base=tables['BASE']; errors={}
    for arm in ARMS:
        a=tables[arm]
        need(np.array_equal(a['raw_features'],base['raw_features']), 'native_features_changed')
        error=float(np.max(np.abs(a['z']-(base['z']+base['x']@(weights[arm]-weights['BASE'])))))
        need(error<=1e-9,'native_model_reconstruction')
        errors[arm]=error
    return errors

def verify_repeat(a,b):
    need(all(np.array_equal(a[k],b[k]) for k in ('raw_features','z','cp')), 'native_repeat_changed')

def group_ids(groups,n):
    need(len(groups)==512 and len({g['id'] for g in groups})==512,'parent_identity_count')
    need(Counter(g['cell'] for g in groups)==Counter({c:64 for c in data.CELLS}), 'fixed_parent_cells')
    ids=[r for g in groups for r in g['rows']]
    need(len(ids)==n and len(set(ids))==n and min(ids)>=0,'child_identity_count')
    for g in groups:
        need(g['rows']==sorted(g['rows']) and set(g['terminals'])<=set(g['rows']), 'sibling_order')
    return ids

def verify_records(path,records):
    expected=b'JNNW'+struct.pack('<I',len(records))+b''.join(records)
    need(path.read_bytes()==expected,'sealed_native_record_order')

def to_global(groups,ids,tables):
    size=max(ids)+1; result={}
    signs=np.array([1 if g['stm']==1 else -1 for g in groups for _ in g['rows']])
    for arm in ARMS:
        cp=np.zeros(size,dtype=np.int64); z=np.zeros(size,dtype=np.float64)
        cp[ids]=tables[arm]['cp']; z[ids]=signs*tables[arm]['z']
        result[arm]=cp; result[arm+'_logit']=z
    return result

def _spend(evidence,heldout=0,train=0):
    if evidence is not None:
        evidence.value['actual_side_effects']['test_target_reads']+=heldout
        evidence.value['existing_heldout_target_reads']=evidence.value.get('existing_heldout_target_reads',0)+heldout
        evidence.value['existing_train_label_reads']=evidence.value.get('existing_train_label_reads',0)+train
        evidence.value['historical_read_counters_upper_bounds_until_load_complete']=True
        evidence.save()

def guard_targets(path,ids,evidence=None):
    targets=np.load(path,mmap_mode='r',allow_pickle=False)
    need(targets.shape==(2000000,) and targets.dtype==np.float32,'target_layout')
    _spend(evidence,heldout=len(ids))
    y=np.asarray(targets[ids],dtype=np.float64)
    need(np.isfinite(y).all() and ((0<=y)&(y<=1)).all(),'guard_target_values')
    return y

def load_inputs(result,art,evidence=None):
    need(shutil.disk_usage(result).free>=3_000_000_000,'disk_free_below_3GB')
    roots={k:result/'inputs'/k for k in SOURCES}; receipts={}
    for key,identity in SOURCES.items():
        job,attempt,code=identity
        receipt=fetch_files(rclone='rclone',prefix=f'r2:jass-data/runs/{job}/{attempt}',
             selections=[(p,p) for p in ALLOWLIST[key]],out_dir=roots[key],expected_state='completed')
        need((receipt['job_id'],receipt['attempt_id'],receipt['code_sha'],receipt['result_state'],
              receipt['exit_code'],receipt['host'])==(job,attempt,code,'completed',0,'cpx62'),'source_identity')
        need([x['path'] for x in receipt['files']]==ALLOWLIST[key],'source_allowlist')
        receipts[key]=receipt
    p0=roots['p0']/'artefacts'; hard=roots['hard']/'artefacts'; soft=roots['soft']/'artefacts'
    confirm=roots['confirmation']/'artefacts'; cw=roots['confirmation']/'work'
    need(data.sha(p0/'ed2-source-seal.json')==labels.SOURCE_SEAL,'source_seal_identity')
    source_seal=read(p0/'ed2-source-seal.json')
    need(source_seal['files']=={f:data.sha(p0/'source'/f) for f in ep.FILES},'source_seal_files')
    need(data.sha(confirm/'cohort-seal.json')==COHORT_SEAL,'confirmation_cohort_identity')
    cohort=read(confirm/'cohort-seal.json')
    need(cohort['source_files']=={f:data.sha(confirm/'source'/f) for f in ep.FILES},'confirmation_source_files')
    need(cohort['guard_plan_sha256']==data.sha(confirm/'guard-plan.json') and cohort['models']==MODEL_SHA,
         'confirmation_guard_or_models')
    need(cohort['mode']=='production' and cohort['decision_parents']==512 and cohort['selection_before_target_reads'],
         'confirmation_role')
    need(data.sha(soft/'candidate-seal.json')==SOFT_SEAL,'soft_seal_identity')
    verify_candidate(soft,'production')
    need(read(confirm/'model-identities.json')['models']==MODEL_SHA,'published_models')
    models={'BASE':cw/'BASE.pjtw','HARD':hard/'PARTIAL.pjtw','SOFT':soft/'SOFT.pjtw'}
    weights={}; base_prefix=None
    for arm,path in models.items():
        need(data.sha(path)==MODEL_SHA[arm],'model_sha256')
        raw,off,w=read_model(path)
        if base_prefix is None: base_prefix=raw[:off]
        need(raw[:off]==base_prefix,'model_frozen_pattern_prefix'); weights[arm]=w
    need(data.sha(confirm/'confirmation-readout.json')==REPORT_SHA and
         data.sha(confirm/'parent-readout.json')==PARENT_SHA,'old_report_identity')
    old_report=read(confirm/'confirmation-readout.json'); old_parents=read(confirm/'parent-readout.json')

    # The guard identity and row ordering are validated before any Context30 indexing.
    plan=read(confirm/'guard-plan.json'); guard=plan['subsets']['confirmation']
    ids=guard['indices']; openings=guard['opening_ids']; guard_records=ep.records(cw/'guard.jnnw')
    need(len(ids)==8192 and len(set(ids))==8192 and all(type(i) is int and 1800796<=i<2000000 for i in ids),
         'guard_indices')
    need(len(openings)==8192 and all(type(i) is int for i in openings) and len(set(openings))==2394
         and guard['clusters']==2394,'guard_openings')
    need(len(guard_records)==8192 and all(r[33:]==b'\0'*5 and r[32] in (0,1) for r in guard_records),
         'guard_scorefree_records')
    need([data.canonical(r) for r in guard_records]==guard['canonical_identities'] and
         len(set(guard['canonical_identities']))==8192,'guard_canonical_order')
    need(plan['targets_read_at_selection']==0 and plan['historical_context30'] is True,'guard_historical_role')

    _spend(evidence,train=9952)
    train_groups,train_scores=labels.groups_and_scores(p0,hard)
    train_ids=group_ids(train_groups,4976)
    train_edges,train_rows=labels.pair_data(train_groups,train_scores)
    need(train_rows==4976 and len(train_edges[0])==17622,'retained_train_support')
    contract=read(soft/'train-contract.json')
    need(contract['mode']=='production' and contract['source_seal_sha256']==labels.SOURCE_SEAL
         and contract['train_labels_seal_sha256']==data.sha(hard/'train-labels-sealed.json'), 'train_contract_seals')
    need(contract['train_parent_ids']==[g['id'] for g in train_groups] and contract['train_rows']==4976
         and contract['pair_count']==17622 and contract['fit_parents']==512,'train_contract_ownership')
    train_records=ep.records(p0/'source/children.jnnw')
    selected=[train_records[i] for i in train_ids]
    for path in (roots['hard']/'work/train.jnnw',roots['soft']/'work/train.jnnw'):
        verify_records(path,selected)
        need(data.sha(path)==contract['train_rows_sha256'],'train_record_hash')
    need(all(r[32]==1-g['stm'] for g in train_groups for r in [train_records[i] for i in g['rows']]), 'train_child_stm')
    confirmation_groups=data.selected_groups(ep.load_tsv(confirm/'source/parents.tsv'),
                                             ep.load_tsv(confirm/'source/groups.tsv'),'production')
    confirmation_ids=group_ids(confirmation_groups,4702)
    confirmation_records=ep.records(confirm/'source/children.jnnw')
    verify_records(cw/'decisions.jnnw',[confirmation_records[i] for i in confirmation_ids])
    need(all(confirmation_records[i][32]==1-g['stm'] for g in confirmation_groups for i in g['rows']),
         'confirmation_child_stm')

    train_tables={'BASE':native_table(hard/'native/train-native.tsv.gz',4976),
                  'HARD':native_table(hard/'native/PARTIAL-train-native.tsv.gz',4976),
                  'SOFT':native_table(roots['soft']/'work/train-soft.tsv',4976)}
    verify_repeat(train_tables['BASE'],native_table(roots['soft']/'work/train-base.tsv',4976))
    verify_repeat(train_tables['SOFT'],native_table(roots['soft']/'work/train-reloaded.tsv',4976))
    confirmation_tables={a:native_table(cw/(a+'-decisions.tsv'),4702) for a in ARMS}
    verify_repeat(confirmation_tables['BASE'],native_table(cw/'BASE-repeat.tsv',4702))
    guard_tables={a:native_table(cw/(a+'-guard.tsv'),8192) for a in ARMS}
    reconstruction={name:verify_tables(tables,weights) for name,tables in
                    [('train',train_tables),('confirmation',confirmation_tables),('guard',guard_tables)]}
    train_native=to_global(train_groups,train_ids,train_tables)
    confirmation_native=to_global(confirmation_groups,confirmation_ids,confirmation_tables)

    _spend(evidence,heldout=4702)
    confirmation_scores,calls=load_scores([confirm/f'reference-{i}.jsonl' for i in range(8)],confirmation_groups)
    need(calls==4675 and len(confirmation_scores)==4702,'archived_reference_coverage')
    for arm in ARMS:
        need(decision_rows(confirmation_groups,confirmation_scores,confirmation_native[arm])==old_parents[arm],
             'old_parent_choices_or_reference_changed')
    need(old_report['parents']==512 and old_report['guard_rows']==8192,'old_readout_shape')
    y=guard_targets(roots['confirmation']/'inputs/n1/work/current-context30.npy',ids,evidence)
    counts=dict(train_parents=512,train_children=4976,train_pairs=17622,
                confirmation_parents=512,confirmation_children=4702,guard_rows=8192,opening_groups=2394,
                existing_heldout_target_reads=12894,existing_train_label_reads=9952,
                native_prediction_rows=5*4976+4*4702+3*8192)
    auth=dict(schema='jass.ed3.transfer_source_authentication.v1',sources=receipts,models=MODEL_SHA,
              source_seal_sha256=labels.SOURCE_SEAL,soft_seal_sha256=SOFT_SEAL,
              cohort_seal_sha256=COHORT_SEAL,old_report_sha256=REPORT_SHA,old_parent_rows_sha256=PARENT_SHA,
              native_reconstruction_max_abs_error=reconstruction,counts=counts,
              target_identity_checks_before_decode=True,classification='EXPLORATORY_CONSUMED_DATA')
    if evidence is not None:
        evidence.value['historical_read_counters_upper_bounds_until_load_complete']=False
        evidence.value['native_prediction_rows']=counts['native_prediction_rows']; evidence.save()
    calculation=dict(train_groups=train_groups,train_scores=train_scores,train_native=train_native,
                confirmation_groups=confirmation_groups,
                confirmation_ref={r:q for (r,_),q in confirmation_scores.items()},
                confirmation_native=confirmation_native,
                guard=dict(y=y,opening_ids=np.asarray(openings),indices=np.asarray(ids),
                           signs=np.array([1 if r[32] else -1 for r in guard_records]),
                           native_cp={a:guard_tables[a]['cp'] for a in ARMS}))
    old_result=dict(versus_base=old_report['versus_base'],versus_hard=old_report['versus_hard'],
                    wdl_soft_minus_base_ci95=old_report['wdl_delta_bootstrap']['ci95'],
                    wdl_soft_minus_base_mean=old_report['wdl_delta_bootstrap']['mean'])
    return dict(**calculation,auth=auth,old_result=old_result,
                old_report=old_report,old_parent_rows=old_parents,counts=counts)
