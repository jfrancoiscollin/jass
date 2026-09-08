#!/usr/bin/env python3
"""Frozen ED2 240-coordinate value residual and parent/cluster statistics."""
from __future__ import annotations
import hashlib
import itertools
import json
from pathlib import Path
import struct
import numpy as np
from scipy.optimize import minimize
from scipy.special import expit

WIDTH=240
L2=0.001
BOOTSTRAPS=20000
RECIPE=dict(width=WIDTH,l2=L2,wdl_coefficient=1.0,pair_coefficient=1.0,
            maxiter=500,maxcor=10,gtol=1e-6,ftol=1e-12,maxls=30,
            initialization='zero_residual',parent_normalizer=512)
BASE_SHA='e4d510fbb9b81cbe74574d92da48e8de6f61d8f98de6472eeb409713785f0de0'

def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda:f.read(1<<20),b''): h.update(b)
    return h.hexdigest()

def write_new(p,obj):
    with Path(p).open('x') as f:
        json.dump(obj,f,sort_keys=True,indent=2,allow_nan=False); f.write('\n')

def read_model(p):
    raw=Path(p).read_bytes()
    if len(raw)<20: raise ValueError('short PJTW')
    magic,ver,scale,npat,next_=struct.unpack_from('<5I',raw)
    if magic!=0x57544a50 or ver&255!=3 or ver&256 or scale!=1000 or next_!=120 or npat<=0 or len(raw)!=20+8*(npat+next_):
        raise ValueError('PJTW v3 architecture mismatch')
    offset=20+8*npat
    weights=np.frombuffer(raw,dtype='<i4',offset=offset).astype(np.float64)/scale
    return raw,offset,weights

def quantize(base,beta,out):
    raw,offset,w=read_model(base)
    if np.shape(beta)!=(WIDTH,) or not np.all(np.isfinite(beta)): raise ValueError('bad beta')
    q=np.rint((w+beta)*1000.0)
    if np.any(np.abs(q)>np.iinfo(np.int32).max): raise ValueError('quantization overflow')
    result=raw[:offset]+q.astype('<i4').tobytes()
    with Path(out).open('xb') as f: f.write(result)
    loaded,off,v=read_model(out)
    if loaded!=result or loaded[:off]!=raw[:offset]: raise ValueError('serialization drift')
    return dict(sha256=sha(out),base_sha256=sha(base),frozen_prefix_sha256=hashlib.sha256(raw[:offset]).hexdigest(),
                changed_extra_coefficients=int(np.count_nonzero(v!=w)),width=WIDTH,scale=1000)

def pair_edges(groups,low,arm):
    if arm not in ('POINT','PARTIAL'): raise ValueError('unknown arm')
    win=[];lose=[];weight=[];signed=[];support={};fractions=[]
    for g in groups:
        # Exact rule-terminal decisions are never learned from a static surrogate.
        rows=[r for r in g['rows'] if r not in g['terminals']]
        all_pairs=[];retained=[]
        for a,b in itertools.combinations(rows,2):
            a50,b50=low[a,50000],low[b,50000]
            if a50==b50: continue
            w,l=(a,b) if a50>b50 else (b,a)
            all_pairs.append((w,l))
            if min(low[w,5000],low[w,50000])>max(low[l,5000],low[l,50000]): retained.append((w,l))
        fractions.append(len(retained)/len(all_pairs) if all_pairs else 0.0)
        edges=all_pairs if arm=='POINT' else retained
        if edges: support[g['cell']]=support.get(g['cell'],0)+1
        for w,l in edges:
            win.append(w);lose.append(l);signed.append(1.0 if g['stm']==1 else -1.0)
            weight.append(1.0/(len(groups)*len(edges)))
    arrays=tuple(np.asarray(x,dtype=d) for x,d in ((win,int),(lose,int),(weight,float),(signed,float)))
    return arrays,dict(parents=len(groups),supported_parents=sum(support.values()),cells=support,
                       pairs=len(win),mean_retained_coverage=float(np.mean(fractions)))

def objective(beta,phi,z,edges,replay_x,replay_z,y):
    w,l,wt,sign=edges
    delta=sign*(z[w]-z[l]+(phi[w]-phi[l])@beta)
    loss=float(np.dot(wt,np.logaddexp(0,-delta)))
    grad=(phi[w]-phi[l]).T@(-wt*sign*expit(-delta))
    pred=replay_z+replay_x@beta
    loss+=float(np.mean(np.logaddexp(0,pred)-y*pred))+0.5*L2*float(beta@beta)
    grad+=replay_x.T@(expit(pred)-y)/len(y)+L2*beta
    return loss,grad

def fit(phi,z,edges,replay_x,replay_z,y):
    if phi.shape[1]!=WIDTH or replay_x.shape[1]!=WIDTH or not len(y): raise ValueError('fit dimensions/support')
    args=(phi,z,edges,replay_x,replay_z,y)
    result=minimize(objective,np.zeros(WIDTH),args=args,method='L-BFGS-B',jac=True,
                    options={k:RECIPE[k] for k in ('maxiter','maxcor','gtol','ftol','maxls')})
    if not result.success or not np.all(np.isfinite(result.x)):
        raise ValueError('optimizer did not converge: '+str(result.message))
    return result.x,dict(recipe=RECIPE,success=bool(result.success),iterations=int(result.nit),
                         function_calls=int(result.nfev),objective=float(result.fun),
                         gradient_max=float(np.max(np.abs(result.jac))))

def native_table(path,n):
    a=np.loadtxt(path,delimiter='\t',skiprows=1,ndmin=2)
    if a.shape!=(n,124) or not np.all(np.isfinite(a)) or not np.array_equal(a[:,0],np.arange(n)):
        raise ValueError('native table shape/nonfinite/order')
    if np.any((a[:,3]<0)|(a[:,3]>1)) or np.any(a[:,2]!=np.trunc(a[:,2])): raise ValueError('native score/phase')
    return np.hstack((a[:,4:]*a[:,3,None],a[:,4:]*(1-a[:,3,None]))),a[:,1],a[:,2].astype(int)

def bootstrap_parent(delta,cells,seed):
    if not len(delta) or len(delta)!=len(cells): raise ValueError('empty/misaligned bootstrap')
    rng=np.random.default_rng(seed); boots=np.zeros(BOOTSTRAPS)
    for cell in sorted(set(cells)):
        x=np.asarray(delta)[np.asarray(cells)==cell]
        for i in range(0,BOOTSTRAPS,250):
            end=min(i+250,BOOTSTRAPS)
            boots[i:end]+=x[rng.integers(0,len(x),size=(end-i,len(x)))].sum(axis=1)/len(delta)
    return dict(mean=float(np.mean(delta)),ci95=np.quantile(boots,[.025,.975]).tolist())

def bootstrap_opening(delta,ids,seed):
    keys,inv=np.unique(ids,return_inverse=True)
    if len(keys)<32: raise ValueError('WDL opening cluster support insufficient')
    sums=np.bincount(inv,weights=delta); counts=np.bincount(inv)
    rng=np.random.default_rng(seed); boots=np.empty(BOOTSTRAPS)
    for i in range(0,BOOTSTRAPS,250):
        end=min(i+250,BOOTSTRAPS); j=rng.integers(0,len(keys),size=(end-i,len(keys)))
        boots[i:end]=sums[j].sum(axis=1)/counts[j].sum(axis=1)
    return dict(mean=float(np.mean(delta)),ci95=np.quantile(boots,[.025,.975]).tolist(),clusters=len(keys))

def decision_rows(groups,reference,native_cp):
    rows=[]
    for g in groups:
        q={r:reference[r,200000] for r in g['rows']}
        # The child has the opposite STM, so the parent score is its negation.
        choice=min(g['terminals']) if g['terminals'] else max(g['rows'],key=lambda r:(-int(native_cp[r]),-r))
        best=max(q.values()); value=q[choice]
        rows.append(dict(parent_id=g['id'],cell=g['cell'],choice=choice,regret=best-value,hit=int(value==best)))
    return rows

def compare_decisions(base,candidate,seed):
    if [r['parent_id'] for r in base]!=[r['parent_id'] for r in candidate]: raise ValueError('parent population mismatch')
    delta=np.array([a['regret']-b['regret'] for a,b in zip(base,candidate)],float)
    boot=bootstrap_parent(delta,[r['cell'] for r in base],seed)
    return dict(**boot,top_hit_delta=float(np.mean([b['hit']-a['hit'] for a,b in zip(base,candidate)])),
                improved=int(np.sum(delta>0)),harmed=int(np.sum(delta<0)),
                decision_changes=sum(a['choice']!=b['choice'] for a,b in zip(base,candidate)))
