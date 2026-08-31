#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, math
from pathlib import Path
import numpy as np
BOOTSTRAP_SEED=2026100103; BOOTSTRAP=200000; E1_RATIO=2.023410

def elo(p):
    if not 0.0 < p < 1.0: raise ValueError('Elo probability at boundary')
    return 400.0*math.log10(p/(1.0-p))
def load_pairs(paths, expected_openings):
    legs={}
    for path in paths:
        for line in path.read_text().splitlines():
            if not line.strip(): continue
            r=json.loads(line); key=int(r['opening_index']); leg=int(r['leg']); score=float(r['a_score'])
            if leg not in (0,1) or score not in (0.0,0.5,1.0): raise ValueError('bad E2 game row')
            if (key,leg) in legs: raise ValueError('duplicate E2 game leg')
            legs[(key,leg)]=score
    indices=sorted({k for k,_ in legs})
    if len(indices)!=expected_openings or indices!=list(range(expected_openings)): raise ValueError('E2 opening coverage drift')
    return np.array([(legs[(i,0)]+legs[(i,1)])/2.0 for i in indices],dtype=np.float64)

def sum_reports(paths, cell):
    total={'games':0,'skipped':0,'complement':0}
    for p in paths:
        r=json.loads(p.read_text())
        if r.get('schema')!='jass.t3_f6_e2_equal_nodes.v1' or r.get('mode')!='cell_run' or r.get('cell')!=cell: raise ValueError('E2 shard report drift')
        total['games']+=int(r['games']); total['skipped']+=int(r['game_skipped']); total['complement']+=int(r['paired_complementarity_failures'])
    return total

def e1_rows(path):
    r=json.loads(path.read_text()); rows=r.get('root_rows',[])
    if len(rows)!=128: raise ValueError('E1 root rows drift')
    t=np.array([int(x['t3_nodes']) for x in rows],dtype=np.float64); c=np.array([int(x['curriculum_nodes']) for x in rows],dtype=np.float64)
    ratio=t.sum()/c.sum()
    if not math.isfinite(ratio) or abs(ratio-E1_RATIO)>5e-7: raise ValueError(f'E1 ratio drift {ratio}')
    return t,c,ratio

def bootstrap(c1,c2,t,c,samples=BOOTSTRAP,seed=BOOTSTRAP_SEED):
    rng=np.random.Generator(np.random.PCG64(seed)); n1=len(c1); n2=len(c2); nr=len(t)
    elo1=np.empty(samples); slope=np.empty(samples); ratio=np.empty(samples); delta=np.empty(samples); invalid=0
    chunk=2000
    for start in range(0,samples,chunk):
        m=min(chunk,samples-start)
        i1=rng.integers(0,n1,size=(m,n1),endpoint=False)
        i2=rng.integers(0,n2,size=(m,n2),endpoint=False)
        ir=rng.integers(0,nr,size=(m,nr),endpoint=False)
        p1=c1[i1].mean(axis=1); p2=c2[i2].mean(axis=1); rr=t[ir].sum(axis=1)/c[ir].sum(axis=1)
        valid=(p1>0)&(p1<1)&(p2>0)&(p2<1)&np.isfinite(rr)&(rr>0); invalid += int((~valid).sum())
        p1=np.clip(p1,1e-300,1-1e-16); p2=np.clip(p2,1e-300,1-1e-16)
        e1=400*np.log10(p1/(1-p1)); e2=400*np.log10(p2/(1-p2)); d=e1+np.log2(rr)*e2
        sl=slice(start,start+m); elo1[sl]=e1; slope[sl]=e2; ratio[sl]=rr; delta[sl]=d
    def ci(x): return [float(np.percentile(x,2.5)),float(np.percentile(x,97.5))]
    return {'samples':samples,'seed':seed,'prng':'NumPy PCG64','subflow_order':['C1','C2','E1'],'invalid_replicates':invalid,'invalid_fraction':invalid/samples,'elo_c1_ci95':ci(elo1),'slope_c2_ci95':ci(slope),'r_nodes_ci95':ci(ratio),'delta_info_ci95':ci(delta)}
def main():
    p=argparse.ArgumentParser()
    for cell in ('c1','c2','c3'):
        p.add_argument(f'--{cell}-games',type=Path,action='append',required=True); p.add_argument(f'--{cell}-report',type=Path,action='append',required=True)
    p.add_argument('--e1-profile',type=Path,required=True); p.add_argument('--pool-provenance',type=Path,required=True); p.add_argument('--code-sha',required=True); p.add_argument('--out',type=Path,required=True); a=p.parse_args()
    prov=json.loads(a.pool_provenance.read_text())
    if prov.get('verdict')!='E2_FRESH_POOL_READY' or prov.get('selected_openings')!=1350 or prov.get('forbidden_overlap')!=0 or prov.get('inter_cell_overlap')!=0: raise ValueError('E2 pool provenance drift')
    c1=load_pairs(a.c1_games,750); c2=load_pairs(a.c2_games,400); c3=load_pairs(a.c3_games,200)
    s1=sum_reports(a.c1_report,'C1'); s2=sum_reports(a.c2_report,'C2'); s3=sum_reports(a.c3_report,'C3')
    if (s1['games'],s2['games'],s3['games'])!=(1500,800,400): raise ValueError('E2 game volume drift')
    if s1['skipped'] or s2['skipped'] or s3['skipped']:
        verdict='E2_INCONCLUSIVE_HARNESS'; reason='GAME_SKIPPED_NONZERO'; payload=None
    elif s3['complement'] or not np.all(c3==0.5) or float(c3.mean())!=0.5:
        verdict='E2_INCONCLUSIVE_HARNESS'; reason='C3_HARNESS_GUARD_FAILED'; payload=None
    else:
        t,c,r=e1_rows(a.e1_profile); b=bootstrap(c1,c2,t,c)
        p1=float(c1.mean()); p2=float(c2.mean())
        if not (0.0 < p1 < 1.0 and 0.0 < p2 < 1.0):
            verdict='E2_INCONCLUSIVE_HARNESS'; reason='OBSERVED_CELL_SCORE_AT_BOUNDARY'; elo_c1=slope_c2=h0=delta=float('nan')
        else:
            elo_c1=elo(p1); slope_c2=elo(p2); h0=-math.log2(r)*slope_c2; delta=elo_c1-h0
            if b['invalid_fraction']>0.025: verdict='E2_INCONCLUSIVE_HARNESS'; reason='BOOTSTRAP_BOUNDARY_FRACTION_GT_2P5'
            elif b['slope_c2_ci95'][0] <= 0: verdict='E2_INCONCLUSIVE_HARNESS'; reason='C2_SLOPE_CI_LOW_NOT_POSITIVE'
            elif b['delta_info_ci95'][0] > 0: verdict='E2_F6_INFORMATION_VALUE_ESTABLISHED'; reason='DELTA_INFO_CI_LOW_POSITIVE'
            else: verdict='E2_F6_INFORMATION_VALUE_NOT_ESTABLISHED'; reason='DELTA_INFO_CI_LOW_NOT_POSITIVE'
        payload={'schema':'jass.t3_f6_e2_terminal.v1','code_sha':a.code_sha,'verdict':verdict,'reason':reason,'e3_authorized_by_e2':verdict=='E2_F6_INFORMATION_VALUE_ESTABLISHED','cells':{'C1':{'openings':750,'games':1500,'a_score':p1,'elo':elo_c1},'C2':{'openings':400,'games':800,'hi_score':p2,'slope_elo':slope_c2},'C3':{'openings':200,'games':400,'a_score':float(c3.mean()),'paired_complementarity_failures':s3['complement']}},'r_nodes':r,'h0_c1':h0,'delta_info':delta,'bootstrap':b,'game_skipped_total':s1['skipped']+s2['skipped']+s3['skipped'],'strength_games':2700,'fit_runs':0,'bake':False,'promotion_authorized':False,'pool2_v4_authorized':False}
    if payload is None:
        payload={'schema':'jass.t3_f6_e2_terminal.v1','code_sha':a.code_sha,'verdict':verdict,'reason':reason,'e3_authorized_by_e2':False,'strength_games':2700,'fit_runs':0,'bake':False,'promotion_authorized':False,'pool2_v4_authorized':False}
    a.out.write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n'); print(json.dumps(payload,sort_keys=True)); return 0
if __name__=='__main__': raise SystemExit(main())
