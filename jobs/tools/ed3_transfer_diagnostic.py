#!/usr/bin/env python3
"""ED3-T1 frozen, fit-free consumed-data transfer diagnostic.

This entrypoint deliberately has no engine, fitting, bootstrap, or discovery
path.  Its public helpers are also used by the synthetic publication contract.
"""
from __future__ import annotations
import csv
import gzip
import hashlib
import itertools
import json
import math
import os
from pathlib import Path
import struct
import sys
import traceback
import numpy as np
from scipy.special import expit

ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from jobs.tools.launch_runtime_v2 import StageEvidence, atomic_json
from jobs.tools.ed3_label_pressure import groups_and_scores, pair_data
from jobs.tools.ed3_confirmation_data import selected_groups, sha as file_sha
from jobs.tools.ed2_value_math import native_table, read_model, decision_rows
from jobs.tools.ed3_soft_value_fit import verify_candidate

PHASES=['authenticate','load-frozen-inputs','calculate-twice','publish']
ARMS=('BASE','HARD','SOFT')
STATES=('correct','tie','wrong')
MARGIN_STATES=('positive','zero','negative')
MODEL_SHA={'BASE':'e4d510fbb9b81cbe74574d92da48e8de6f61d8f98de6472eeb409713785f0de0',
           'HARD':'3db65fe6dcc3dc828a7467ac27a43c4904c33d5791b484a2b2f19efcef70570e',
           'SOFT':'d8a193de2017a6c156a46d89692245bdc1af00d29d056af3a41e7d6d4f5a486a'}
SOURCE_SEAL='31f763049fef50544bd1cbb240eeb4f51670728ae0697a77e982186df007152c'
COHORT_SEAL='f1ce4d2d8cdb947c1dbfc1bdccdfc588927a4299f661d58097b0507e28a5bb8b'
SOURCES={
 'p0':('cpx62-1875-l3-ed2-data-teacher-preflight-v1','20260908T171140Z-bc30d685','bc30d6858c4d590625f8831c4995f055816b95c2'),
 'hard':('cpx62-1878-l3-ed2-numerical-recovery-n1','20260908T191343Z-d71679e9','d71679e96d78609b6d32052be80ca78c0deaece0'),
 'soft':('cpx62-1882-l3-ed3-soft-value-fit-production-v1','20260908T220255Z-20a5e4eb','20a5e4ebebedbf9340eafd3750506c1aed851506'),
 'confirmation':('cpx62-1884-l3-ed3-confirmation-production-v1','20260909T051901Z-0946f57d','0946f57d5443c0507fd9210371396bdf1c49abd2')}
OUTPUTS=['ed3-transfer-diagnostic.json','train-pair-transitions.jsonl','confirmation-pair-transitions.jsonl',
 'parent-transfer.jsonl','wdl-row-contributions.jsonl','wdl-opening-contributions.jsonl','source-authentication.json','publication-manifest.json']

def need(ok,code):
    if not ok: raise ValueError(code)

def _json(path): return json.loads(Path(path).read_text())
def _write_jsonl(path, rows):
    with Path(path).open('x',encoding='utf8') as f:
        for row in rows: f.write(json.dumps(row,sort_keys=True,allow_nan=False,separators=(',',':'))+'\n')

def _native(path,n):
    x,z,cp=native_table(path,n)
    return x,np.asarray(z,dtype=float),np.asarray(cp,dtype=int)

def _state(a,b): return 'correct' if a>b else 'tie' if a==b else 'wrong'
def _margin_state(x): return 'positive' if x>0 else 'zero' if x==0 else 'negative'
def _summary(values):
    x=np.asarray(values,dtype=float); need(len(x)>0 and np.isfinite(x).all(),'nonfinite_distribution')
    q=np.quantile(x,[0,.05,.10,.25,.50,.75,.90,.95,1],method='linear')
    return {'n':int(len(x)),'finite':True,'mean':float(x.mean()),'population_stddev':float(x.std()),
      'min':float(x.min()),'max':float(x.max()),'lt_zero':int((x<0).sum()),'eq_zero':int((x==0).sum()),
      'gt_zero':int((x>0).sum()),'quantiles':{str(k):float(v) for k,v in zip((0,.05,.10,.25,.50,.75,.90,.95,1),q)}}

def _matrix(rows, states, keya, keyb):
    index={x:i for i,x in enumerate(states)}; count=np.zeros((len(states),len(states)),dtype=int)
    buckets=[[[] for _ in states] for _ in states]
    for row in rows:
        a,b=index[row[keya]],index[row[keyb]]; count[a,b]+=1; buckets[a][b].append(row['full_parent_mass'])
    mass=np.array([[math.fsum(v) for v in line] for line in buckets])
    return {'order':list(states),'counts':count.tolist(),'full_parent_mass':mass.tolist(),
      'total_pairs':len(rows),'total_mass':math.fsum(row['full_parent_mass'] for row in rows)}

def pair_matrix(rows,keya='hard_state',keyb='soft_state',component=False):
    result=_matrix(rows,STATES,keya,keyb); support=len({r['parent_id'] for r in rows})
    result.update(supported_parents=support,unsupported_parents=512-support,
                  parent_denominator=512,normalization='inherited_primary_pair_weights' if component else 'equal_parent_within_fixed_support')
    if not component: need(abs(result['total_mass']-support/512)<=1e-15,'pair_mass_reconciliation')
    return result

def _choice(rows, utility, terminals, terminal_priority):
    return min(terminals) if terminal_priority and terminals else max(rows,key=lambda r:(utility(r),-r))

def analyse_population(groups, reference, base, hard, soft, base_logit, hard_logit, soft_logit, *, population, terminals_priority):
    """Return fixed pair, margin, and choice records for one frozen population."""
    ids={r for g in groups for r in g['rows']}
    base,hard,soft=({r:int(a[r]) for r in ids} for a in (base,hard,soft))
    base_logit,hard_logit,soft_logit=({r:float(a[r]) for r in ids} for a in (base_logit,hard_logit,soft_logit))
    need(all(math.isfinite(a[r]) for a in (base_logit,hard_logit,soft_logit) for r in ids),'nonfinite_native_logit')
    pairs=[]; parents=[]; nonempty=0
    for g in groups:
        rows=list(g['rows']); terminal=set(g.get('terminals',()))
        if not rows:
            parents.append({'population':population,'parent_id':g['id'],'cell':g['cell'],'pair_support':False,'choice_support':False,'margin_support':False,'terminal_priority_parent':False,'base_choice':None,'hard_choice':None,'soft_choice':None,'base_logit_choice':None,'hard_logit_choice':None,'soft_logit_choice':None,'base_hit':False,'hard_hit':False,'soft_hit':False,'hard_margin':None,'soft_margin':None,'soft_minus_hard_margin':None,'hard_logit_margin':None,'soft_logit_margin':None,'soft_minus_hard_logit_margin':None,'best_rows':[]})
            continue
        eligible=[]
        for a,b in itertools.combinations(rows,2):
            if reference[a]==reference[b]: continue
            w,l=(a,b) if reference[a]>reference[b] else (b,a); eligible.append((w,l))
        if eligible: nonempty+=1
        mass=1/(512*len(eligible)) if eligible else 0.
        for w,l in eligible:
            rec={'population':population,'parent_id':g['id'],'cell':g['cell'],'winner_row':w,'loser_row':l,
              'reference_gap':float(reference[w]-reference[l]),'terminal_involving':bool(w in terminal or l in terminal),
              'terminal_family':'terminal_involving' if w in terminal or l in terminal else 'nonterminal_only',
              'full_parent_mass':mass,'base_state':_state(-base[w],-base[l]),'hard_state':_state(-hard[w],-hard[l]),'soft_state':_state(-soft[w],-soft[l]),
              'base_integer_margin':int(-base[w]+base[l]),'hard_integer_margin':int(-hard[w]+hard[l]),'soft_integer_margin':int(-soft[w]+soft[l]),
              'base_logit_margin':base_logit[w]-base_logit[l],'hard_logit_margin':hard_logit[w]-hard_logit[l],'soft_logit_margin':soft_logit[w]-soft_logit[l],
              'base_logit_state':_state(base_logit[w],base_logit[l]),'hard_logit_state':_state(hard_logit[w],hard_logit[l]),'soft_logit_state':_state(soft_logit[w],soft_logit[l])}
            pairs.append(rec)
        best=max(reference[r] for r in rows); bestset={r for r in rows if reference[r]==best}; rest=[r for r in rows if r not in bestset]
        hm=sm=hlm=slm=None
        if rest:
            hm=max(-hard[r] for r in bestset)-max(-hard[r] for r in rest); sm=max(-soft[r] for r in bestset)-max(-soft[r] for r in rest)
            hlm=max(hard_logit[r] for r in bestset)-max(hard_logit[r] for r in rest); slm=max(soft_logit[r] for r in bestset)-max(soft_logit[r] for r in rest)
        bc=_choice(rows,lambda r:-base[r],terminal,terminals_priority); hc=_choice(rows,lambda r:-hard[r],terminal,terminals_priority); sc=_choice(rows,lambda r:-soft[r],terminal,terminals_priority)
        blc=_choice(rows,lambda r:base_logit[r],terminal,terminals_priority); hlc=_choice(rows,lambda r:hard_logit[r],terminal,terminals_priority); slc=_choice(rows,lambda r:soft_logit[r],terminal,terminals_priority)
        parents.append({'population':population,'parent_id':g['id'],'cell':g['cell'],'pair_support':bool(eligible),'choice_support':bool(rows),
          'margin_support':bool(rest),'terminal_priority_parent':bool(terminal) and terminals_priority,
          'raw_margin_equivalent_to_production_choice_rule':None if population=='TRAIN' else not bool(terminal),
          'choice_rule':'nonterminal_argmax_diagnostic' if population=='TRAIN' else 'terminal_priority_then_argmax',
          'base_choice':bc,'hard_choice':hc,'soft_choice':sc,
          'base_logit_choice':blc,'hard_logit_choice':hlc,'soft_logit_choice':slc,'base_hit':bc in bestset,'hard_hit':hc in bestset,'soft_hit':sc in bestset,
          'hard_margin':hm,'soft_margin':sm,'soft_minus_hard_margin':None if hm is None else sm-hm,
          'hard_logit_margin':hlm,'soft_logit_margin':slm,'soft_minus_hard_logit_margin':None if hlm is None else slm-hlm,
          'best_rows':sorted(bestset)})
    return pairs,parents,{'supported_parents':nonempty,'unsupported_parents':512-nonempty,'eligible_pairs':len(pairs)}

def _parent_summaries(parents):
    m=[r for r in parents if r['margin_support']]
    changed={'same_row':0,'changed_both_best':0,'hard_outside_to_soft_best':0,'hard_best_to_soft_outside':0,'changed_both_outside':0}
    hit=np.zeros((2,2),int)
    choices_supported=0
    for r in parents:
        if not r['choice_support']: continue
        choices_supported+=1
        h,s=r['hard_hit'],r['soft_hit']; hit[int(h),int(s)]+=1
        if r['hard_choice']==r['soft_choice']: changed['same_row']+=1
        elif h and s: changed['changed_both_best']+=1
        elif not h and s: changed['hard_outside_to_soft_best']+=1
        elif h and not s: changed['hard_best_to_soft_outside']+=1
        else: changed['changed_both_outside']+=1
    def sensitivity():
        lm=[r for r in parents if r['margin_support']]
        changed={'same_row':0,'changed_both_best':0,'hard_outside_to_soft_best':0,'hard_best_to_soft_outside':0,'changed_both_outside':0}; hit=np.zeros((2,2),int)
        for r in parents:
            if not r['choice_support']: continue
            h=r['hard_logit_choice'] in r['best_rows']; s=r['soft_logit_choice'] in r['best_rows']; hit[int(h),int(s)]+=1
            if r['hard_logit_choice']==r['soft_logit_choice']: changed['same_row']+=1
            elif h and s: changed['changed_both_best']+=1
            elif not h and s: changed['hard_outside_to_soft_best']+=1
            elif h and not s: changed['hard_best_to_soft_outside']+=1
            else: changed['changed_both_outside']+=1
        return {'label':'quantized_model_unrounded_logit_sensitivity','margin_transition':_matrix([{'hard':_margin_state(r['hard_logit_margin']),'soft':_margin_state(r['soft_logit_margin']),'full_parent_mass':1/512} for r in lm],MARGIN_STATES,'hard','soft'),'margins':{'hard':_summary([r['hard_logit_margin'] for r in lm]),'soft':_summary([r['soft_logit_margin'] for r in lm]),'soft_minus_hard':_summary([r['soft_minus_hard_logit_margin'] for r in lm])},'rest_unsupported':512-len(lm),'argmax_propagation':changed,'hard_hit_to_soft_hit':hit.tolist(),'choice_unsupported':512-choices_supported}
    return {'margin_transition':_matrix([{'hard':_margin_state(r['hard_margin']),'soft':_margin_state(r['soft_margin']),'full_parent_mass':1/512} for r in m],MARGIN_STATES,'hard','soft'),
      'margins':{'hard':_summary([r['hard_margin'] for r in m]),'soft':_summary([r['soft_margin'] for r in m]),'soft_minus_hard':_summary([r['soft_minus_hard_margin'] for r in m])},
      'rest_unsupported':512-len(m),'argmax_propagation':changed,'hard_hit_to_soft_hit':hit.tolist(),
      'terminal_priority_parents':sum(r['terminal_priority_parent'] for r in parents),'choice_unsupported':512-choices_supported,
      'quantized_model_unrounded_logit_sensitivity':sensitivity()}

def _wdl(guard):
    y=np.asarray(guard['y'],float); signs=np.asarray(guard['signs'],float); opening=np.asarray(guard['opening_ids'])
    need(y.shape==(8192,) and opening.shape==(8192,) and signs.shape==(8192,),'guard_shape')
    need(np.isfinite(y).all() and ((y>=0)&(y<=1)).all() and np.all(np.isin(signs,[-1,1])),'guard_values')
    need(len(set(opening.tolist()))==2394 and set(guard['native_cp'])==set(ARMS),'guard_openings_or_arms')
    rows=[]; metrics={}
    for arm,cp in guard['native_cp'].items():
        need(np.shape(cp)==(8192,) and np.isfinite(cp).all(),'guard_native_shape')
        z=signs*np.asarray(cp,float)/100.; ll=np.logaddexp(0,z)-y*z; br=(expit(z)-y)**2
        metrics[arm]={'logloss':float(ll.mean()),'brier':float(br.mean()),'_ll':ll,'_br':br}
    for i in range(8192):
        row={'guard_row':i,'opening_id':int(opening[i]),'source_row':int(guard['indices'][i])}
        for loss,key in (('_ll','logloss'),('_br','brier')):
            row[f'{key}_soft_minus_base']=float(metrics['SOFT'][loss][i]-metrics['BASE'][loss][i])
            row[f'{key}_soft_minus_hard']=float(metrics['SOFT'][loss][i]-metrics['HARD'][loss][i])
        rows.append(row)
    openings=[]
    for oid in sorted(set(opening.tolist())):
        rr=[r for r in rows if r['opening_id']==oid]; out={'opening_id':int(oid),'row_count':len(rr)}
        for key in ('logloss_soft_minus_base','logloss_soft_minus_hard','brier_soft_minus_base','brier_soft_minus_hard'):
            total=float(sum(r[key] for r in rr)); out.update({key+'_sum':total,key+'_mean':total/len(rr),key+'_global_mean_contribution':total/8192})
        openings.append(out)
    for key in ('logloss_soft_minus_base','logloss_soft_minus_hard','brier_soft_minus_base','brier_soft_minus_hard'):
        need(abs(sum(x[key+'_global_mean_contribution'] for x in openings)-np.mean([x[key] for x in rows]))<=1e-15,'opening_additive_reconciliation')
    public={a:{k:v for k,v in d.items() if not k.startswith('_')} for a,d in metrics.items()}
    return rows,openings,public

def calculate(train_groups, train_scores, train_native, confirmation_groups, confirmation_ref, confirmation_native, guard=None):
    """Pure calculation used twice before publishing. Inputs have already authenticated."""
    tb,th,ts,tbz,thz,tsz=(train_native[x] for x in ('BASE','HARD','SOFT','BASE_logit','HARD_logit','SOFT_logit'))
    # exact frozen PARTIAL support, delegated only to the frozen pure helper
    edges,_=pair_data(train_groups,train_scores); w,l,mass,_,_=edges
    local=[r for g in train_groups for r in g['rows']]
    ref50={r:train_scores[r,50000] for r in local}
    # TRAIN choice/margin support is explicitly nonterminal-only and is not an
    # approximation to confirmation's terminal-priority policy.
    train_nonterminal=[dict(g,rows=[r for r in g['rows'] if r not in set(g.get('terminals',()))],terminals=[]) for g in train_groups]
    train_pairs,train_parents,_=analyse_population(train_nonterminal,ref50,tb,th,ts,tbz,thz,tsz,population='TRAIN',terminals_priority=False)
    retained={(local[int(a)],local[int(b)]) for a,b in zip(w,l)}
    train_pairs=[p for p in train_pairs if (p['winner_row'],p['loser_row']) in retained]
    # Preserve helper masses exactly for the retained support.
    edge_mass={(local[int(a)],local[int(b)]):float(wt) for a,b,wt in zip(w,l,mass)}
    for p in train_pairs: p['full_parent_mass']=edge_mass[(p['winner_row'],p['loser_row'])]
    supported_train={p['parent_id'] for p in train_pairs}
    for p in train_parents:p['pair_support']=p['parent_id'] in supported_train
    cb,ch,cs,cbl,chl,csl=(confirmation_native[x] for x in ('BASE','HARD','SOFT','BASE_logit','HARD_logit','SOFT_logit'))
    conf_pairs,conf_parents,_=analyse_population(confirmation_groups,confirmation_ref,cb,ch,cs,cbl,chl,csl,population='CONFIRMATION',terminals_priority=True)
    train_info={'pair_transition':pair_matrix(train_pairs),**_parent_summaries(train_parents)}
    conf_info={'pair_transition':pair_matrix(conf_pairs),**_parent_summaries(conf_parents)}
    for info,pairs,support in ((train_info,train_pairs,'PARTIAL_retained_Q5_Q50'),(conf_info,conf_pairs,'all_strict_Q200')):
        info['pair_support_definition']=support
        info['pair_transition']['support_definition']=support
        info['quantized_model_unrounded_logit_sensitivity']['pair_transition']=pair_matrix(pairs,'hard_logit_state','soft_logit_state')
        info['quantized_model_unrounded_logit_sensitivity']['pair_transition']['support_definition']=support
    ti=[p for p in conf_pairs if p['terminal_involving']]; nt=[p for p in conf_pairs if not p['terminal_involving']]
    a=np.array(conf_info['pair_transition']['counts']); need(np.array_equal(a,np.array(_matrix(ti,STATES,'hard_state','soft_state')['counts'])+np.array(_matrix(nt,STATES,'hard_state','soft_state')['counts'])),'terminal_pair_reconciliation')
    for keya,keyb,destination in [('hard_state','soft_state',conf_info),
            ('hard_logit_state','soft_logit_state',conf_info['quantized_model_unrounded_logit_sensitivity'])]:
        components={name:pair_matrix(rows,keya,keyb,component=True) for name,rows in
                    [('terminal_involving',ti),('nonterminal_only',nt)]}
        for key in ('counts','full_parent_mass'):
            total=np.array(components['terminal_involving'][key])+np.array(components['nonterminal_only'][key])
            need(np.allclose(total,np.asarray(destination['pair_transition'][key]),rtol=0,atol=1e-15),'terminal_component_reconciliation')
        destination['pair_components']=components
    for r in conf_parents:
        q=confirmation_ref
        g=next(g for g in confirmation_groups if g['id']==r['parent_id'])
        best=max(q[x] for x in g['rows']); r.update(base_hit=r['base_choice'] in r['best_rows'],base_regret=best-q[r['base_choice']],hard_regret=best-q[r['hard_choice']],soft_regret=best-q[r['soft_choice']])
        r['delta_base_minus_soft']=r['base_regret']-r['soft_regret']; r['delta_hard_minus_soft']=r['hard_regret']-r['soft_regret']
    wrows,wopen,wdl= _wdl(guard) if guard is not None else ([],[],{})
    if wrows:
        wdl['row_distributions']={k:_summary([r[k] for r in wrows]) for k in ('logloss_soft_minus_base','logloss_soft_minus_hard','brier_soft_minus_base','brier_soft_minus_hard')}
        wdl['opening_distributions']={k:{'sum':_summary([r[k+'_sum'] for r in wopen]),'mean':_summary([r[k+'_mean'] for r in wopen]),'global_mean_contribution':_summary([r[k+'_global_mean_contribution'] for r in wopen])} for k in ('logloss_soft_minus_base','logloss_soft_minus_hard','brier_soft_minus_base','brier_soft_minus_hard')}
    cells={}
    for cell in sorted({r['cell'] for r in conf_parents}):
        rs=[r for r in conf_parents if r['cell']==cell]; need(len(rs)==64,'confirmation_cell_size')
        cells[cell]={'parents':64,'choice_changed_base_soft':sum(r['base_choice']!=r['soft_choice'] for r in rs),'choice_changed_hard_soft':sum(r['hard_choice']!=r['soft_choice'] for r in rs),'base_minus_soft':_summary([r['delta_base_minus_soft'] for r in rs]),'hard_minus_soft':_summary([r['delta_hard_minus_soft'] for r in rs])}
    result={'schema':'jass.ed3.transfer_diagnostic.v1','train':train_info,'confirmation':conf_info,'wdl':wdl,
      'counts':{'train_parents':len(train_groups),'train_children':len(local),'train_pairs':len(train_pairs),'confirmation_parents':len(confirmation_groups),'confirmation_children':sum(len(g['rows']) for g in confirmation_groups),'confirmation_pairs':len(conf_pairs),'guard_rows':len(wrows),'opening_groups':len(wopen)},
      'regret':{'base_minus_soft':_summary([r['delta_base_minus_soft'] for r in conf_parents]),'hard_minus_soft':_summary([r['delta_hard_minus_soft'] for r in conf_parents]),'cells':cells}}
    return result,train_pairs,conf_pairs,train_parents+conf_parents,wrows,wopen

def _fetch(identity,names,out,receipt):
    from jobs.tools.fetch_result_files import fetch_files
    job,attempt,code=identity; r=fetch_files(rclone='rclone',prefix=f'r2:jass-data/runs/{job}/{attempt}',selections=names,out_dir=out,expected_state='completed')
    need((r['job_id'],r['attempt_id'],r['code_sha'],r['result_state'],r['exit_code'])==(job,attempt,code,'completed',0),'source_identity')
    atomic_json(receipt,r); return r

def run(result,art,mode,loader=None):
    """Authenticated entrypoint. A loader is only for the hermetic contract fixture."""
    evidence=StageEvidence(art,mode)
    try:
        evidence.begin('authenticate')
        if loader is None:
            from jobs.tools.ed3_transfer_diagnostic_inputs import load_inputs
            loader=load_inputs
        data=loader(result,art,evidence=evidence)
        auth=data['auth']
        # Generic admission names every historical target dereference
        # ``test_target_reads``.  The immutable report separates the archived
        # TRAIN cells from the 12,894 consumed held-out reads.
        need(data['counts']['train_pairs']==17622 and data['counts']['confirmation_parents']==512 and data['counts']['confirmation_children']==4702 and data['counts']['guard_rows']==8192 and data['counts']['opening_groups']==2394,'frozen_counts')
        atomic_json(art/'source-authentication.json',auth); evidence.complete()
        evidence.begin('load-frozen-inputs'); evidence.complete()
        evidence.begin('calculate-twice')
        calculation_inputs=data.get('calculation_inputs') or {k:data[k] for k in ('train_groups','train_scores','train_native','confirmation_groups','confirmation_ref','confirmation_native','guard')}
        a=calculate(**calculation_inputs); b=calculate(**calculation_inputs)
        def payload(x): return json.dumps(x,sort_keys=True,allow_nan=False,separators=(',',':')).encode()
        need(payload(a)==payload(b),'nondeterministic_calculation'); evidence.complete()
        evidence.begin('publish')
        report,tp,cp,pp,wrows,wopen=a
        for key in ('train_parents','train_children','train_pairs','confirmation_parents','confirmation_children','guard_rows','opening_groups'):
            need(report['counts'][key]==data['counts'][key],'computed_count_mismatch')
        # Loader supplies only authenticated historic facts.  Recalculation is
        # deliberately limited to means/counts; old CI fields are echoed.
        old_report=data.get('raw_old_report',data.get('old_report'))
        old=data['old_result']
        confirmation_parents=[r for r in pp if r['population']=='CONFIRMATION']
        aggregates={}
        for arm in ARMS:
            name=arm.lower()
            actual=[dict(parent_id=r['parent_id'],cell=r['cell'],choice=r[name+'_choice'],
                         regret=r[name+'_regret'],hit=int(r[name+'_hit'])) for r in confirmation_parents]
            if 'old_parent_rows' in data:need(actual==data['old_parent_rows'][arm],'old_parent_reproduction')
            aggregates[arm]=dict(regret_mean=float(np.mean([r['regret'] for r in actual])),
                                 top_hit=float(np.mean([r['hit'] for r in actual])))
        need(aggregates==old_report['aggregate'],'old_aggregate_reproduction')
        for contrast,key in (('base_minus_soft','versus_base'),('hard_minus_soft','versus_hard')):
            observed=report['regret'][contrast]
            baseline='base' if contrast=='base_minus_soft' else 'hard'; confirmation_parents=[r for r in pp if r['population']=='CONFIRMATION']
            need(observed['mean']==float(old[key]['mean']) and observed['lt_zero']==int(old[key]['harmed']) and observed['gt_zero']==int(old[key]['improved']) and float(np.mean([r['soft_hit']-r[baseline+'_hit'] for r in confirmation_parents]))==float(old[key]['top_hit_delta']) and sum(r[baseline+'_choice']!=r['soft_choice'] for r in confirmation_parents)==int(old[key]['decision_changes']),'old_result_reproduction')
        need(all(report['wdl'][arm][metric]==float(old_report['wdl'][arm][metric]) for arm in ARMS for metric in ('logloss','brier')),'old_wdl_reproduction')
        need(report['wdl']['row_distributions']['logloss_soft_minus_base']['mean']==float(old.get('wdl_soft_minus_base_mean',old_report['wdl_delta_bootstrap']['mean'])),'old_wdl_delta_reproduction')
        report['old_result_identity']={'versus_base_ci95':old['versus_base']['ci95'],'versus_hard_ci95':old['versus_hard']['ci95'],'wdl_soft_minus_base_ci95':old['wdl_soft_minus_base_ci95'],'ci_method':'authenticated_echo_not_recalculated'}
        report['old_result_identity']['aggregate_recomputed']=aggregates
        ledger=dict(existing_heldout_target_reads=12894,existing_train_label_reads=9952,
                    native_prediction_rows=data['counts']['native_prediction_rows'],new_confirmation_target_reads=0,
                    fits=0,optimizer_calls=0,new_scan_searches=0,new_jass_searches=0,new_positions=0,
                    strength_games=0,selfplay_games=0,promotions=0,bakes=0,automatic_continuations=0)
        report.update(classification='EXPLORATORY_CONSUMED_DATA',models=auth.get('models',MODEL_SHA),
                      next_stage='STOP_ED3',scientific_verdict=None,effect_ledger=ledger,
                      boundaries=['TRAIN retained Q5/Q50 and confirmation all-strict Q200 are different estimands',
                                  'No cross-population subtraction or causal/generalization inference',
                                  'Unrounded logit sensitivity uses already quantized models',
                                  'No inference or model selection; STOP_ED3 remains terminal'])
        atomic_json(art/'ed3-transfer-diagnostic.json',report)
        _write_jsonl(art/'train-pair-transitions.jsonl',tp); _write_jsonl(art/'confirmation-pair-transitions.jsonl',cp); _write_jsonl(art/'parent-transfer.jsonl',pp)
        _write_jsonl(art/'wdl-row-contributions.jsonl',wrows); _write_jsonl(art/'wdl-opening-contributions.jsonl',wopen)
        immutable=['ed3-transfer-diagnostic.json','train-pair-transitions.jsonl','confirmation-pair-transitions.jsonl','parent-transfer.jsonl','wdl-row-contributions.jsonl','wdl-opening-contributions.jsonl','source-authentication.json']
        atomic_json(art/'publication-manifest.json',{'schema':'jass.ed3.transfer_manifest.v1','immutable_sha256':{p:file_sha(art/p) for p in immutable}})
        summary={'schema':'jass.ed3.transfer_terminal.v1','verdict':'ED3_TRANSFER_DIAGNOSTIC_COMPLETE_V1' if mode=='production' else 'ED3_TRANSFER_DIAGNOSTIC_REHEARSAL_COMPLETE_V1','classification':'EXPLORATORY_CONSUMED_DATA','scientific_verdict':None,'next_stage':'STOP_ED3','runtime_authorized':False,'automatic_continuation':False,'effect_ledger':{'existing_heldout_target_reads':12894,'existing_train_label_reads':9952,'fits':0,'optimizer_calls':0,'new_scan_searches':0,'new_jass_searches':0,'strength_games':0,'selfplay_games':0,'promotions':0,'bakes':0}}
        summary['effect_ledger']=ledger
        summary['counts']=report['counts']
        summary['deterministic_full_payload_recalculation']=True
        atomic_json(art/'scientific-summary.json',summary); evidence.complete(); evidence.finish(); return summary
    except BaseException as exc: evidence.fail(exc); raise

def main():
    try: run(Path(os.environ['JASS_RESULT_DIR']),Path(os.environ['JASS_ARTEFACT_DIR']),os.environ['LAUNCH_MODE']); return 0
    except Exception: traceback.print_exc(); return 2
if __name__=='__main__': raise SystemExit(main())
