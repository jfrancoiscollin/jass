"""Formula-only ED4 synthetic fixture frozen by the P0 protocol."""
from __future__ import annotations
import hashlib, json
import numpy as np
from scipy.special import expit
from jobs.tools import ed4_choice_math as m
def fixture():
    rng=np.random.default_rng(910); raw=rng.integers(0,2,size=(288,120)); raw[:,:100]*=rng.random((288,100))>=.05
    raw[:,100:120]*=np.array([1,20,60,150,2]*4); raw[:,101]=2*raw[:,100]
    phase=rng.choice([0,.05,.2,.65,1],size=288); phi=np.hstack((raw*phase[:,None],raw*(1-phase[:,None]))).astype(float)
    z=rng.standard_normal(96); rz=rng.standard_normal(192); y=expit(rz+.1*rng.standard_normal(192))
    base=[]; low={}
    for p in range(24):
        rows=list(range(4*p,4*p+4)); q=([1,0,0,0],[2,2,1,0],[0,0,0,0],[0,0,0,0])[p%4]
        base.append({'id':p,'stm':p%2,'rows':rows,'terminals':rows if p%4==3 else []})
        for r,v in zip(rows,q): low[r,5000]=low[r,50000]=float(v)
    gs=m.groups_from_labels(base,low); d=m.design(phi[:96],z,gs,phi[96:],rz,y)
    meta={'seed':910,'parents':24,'train_rows':96,'replay_rows':192,'width':240,'normalizer':24,'future_production_normalizer':512,'phi_sha256':hashlib.sha256(phi.tobytes()).hexdigest(),'groups':gs}
    return d,meta
