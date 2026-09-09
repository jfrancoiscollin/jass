"""Frozen ED4 choice-set objective; no data loading or engine path."""
from __future__ import annotations
import itertools
import numpy as np
from scipy.optimize import minimize
from scipy.special import expit

WIDTH=240; RIDGE=.0005
OPTIONS={'method':'trust-exact','options':{'maxiter':500,'gtol':1e-6,'initial_trust_radius':1.,'max_trust_radius':1000.,'eta':.15}}

class NumericalFailure(RuntimeError):
    def __init__(self, report): super().__init__('ED4_NUMERICAL_FAILURE'); self.report=report
def need(ok, code):
    if not ok: raise ValueError(code)

def groups_from_labels(groups, low):
    """Build V and maximal A from exact PARTIAL arrows, preserving row order."""
    out=[]
    for g in groups:
        rows=list(g['rows']); terminals=set(g.get('terminals',()))
        need(type(g.get('id')) is int and type(g.get('stm')) is int and g['stm'] in (0,1) and rows==sorted(rows) and len(set(rows))==len(rows) and all(type(r) is int for r in rows) and terminals<=set(rows),'group_ownership')
        v=[r for r in rows if r not in terminals]; incoming=set(); edges=[]
        need(all((r,k) in low and np.isfinite(low[r,k]) for r in v for k in (5000,50000)), 'nonfinite_or_missing_label')
        for a,b in itertools.combinations(v,2):
            qa,qb=low[a,50000],low[b,50000]
            if qa==qb: continue
            w,l=(a,b) if qa>qb else (b,a)
            if min(low[w,5000],low[w,50000])>max(low[l,5000],low[l,50000]): edges.append((w,l)); incoming.add(l)
        A=[r for r in v if r not in incoming]
        need(not v or A,'empty_admissible_set')
        out.append({'id':g['id'],'stm':g['stm'],'rows':rows,'V':v,'A':A,'edges':edges})
    return out

def design(phi,z,groups,replay_x,replay_z,y):
    phi=np.asarray(phi,float); z=np.asarray(z,float); rx=np.asarray(replay_x,float); rz=np.asarray(replay_z,float); y=np.asarray(y,float)
    need(phi.ndim==2 and phi.shape[1]==WIDTH and z.shape==(len(phi),) and np.isfinite(phi).all() and np.isfinite(z).all(),'train_shape')
    need(rx.ndim==2 and rx.shape[1]==WIDTH and rz.shape==(len(rx),) and y.shape==(len(rx),) and len(y)>0 and np.isfinite(rx).all() and np.isfinite(rz).all() and np.isfinite(y).all() and ((y>=0)&(y<=1)).all(),'replay_shape')
    need(len(groups) in (24,512),'parent_normalizer')
    used=[]; identifiers=[]
    for g in groups:
        rows,V,A=g['rows'],g['V'],g['A']; identifiers.append(g['id'])
        need(type(g.get('id')) is int and type(g.get('stm')) is int and g['stm'] in (0,1) and all(type(r) is int for r in rows+V+A) and rows==sorted(rows) and len(set(rows))==len(rows) and V==[r for r in rows if r in set(V)] and A==[r for r in V if r in set(A)] and set(V)<=set(rows) and set(A)<=set(V) and (not V or A),'group_schema')
        used.extend(g['rows'])
    need(len(identifiers)==len(set(identifiers)) and len(used)==len(phi) and len(used)==len(set(used)) and used==list(range(len(phi))),'row_ownership')
    return {'phi':phi,'z':z,'groups':groups,'replay_x':rx,'replay_z':rz,'y':y,'normalizer':len(groups)}

def _term(u,x,idx):
    if not idx: return 0.,np.zeros(WIDTH),np.zeros((WIDTH,WIDTH))
    q=u[idx]; shift=float(np.max(q)); p=np.exp(q-shift); p/=p.sum(); xx=x[idx]; mean=p@xx
    return float(shift+np.log(np.exp(q-shift).sum())),mean,(xx.T*p)@xx-np.outer(mean,mean)

def derivatives(beta,d):
    beta=np.asarray(beta,float); need(beta.shape==(WIDTH,) and np.isfinite(beta).all(),'beta')
    x,z=d['phi'],d['z']; value=0.; grad=np.zeros(WIDTH); H=np.zeros((WIDTH,WIDTH))
    for g in d['groups']:
        V,A=g['V'],g['A']
        if not V or A==V: continue
        sign=1. if g['stm']==1 else -1.; u=sign*(z+x@beta)
        lv,gv,hv=_term(u,x,V); la,ga,ha=_term(u,x,A)
        value+=lv-la; grad+=sign*(gv-ga); H+=hv-ha
    value/=d['normalizer']; grad/=d['normalizer']; H/=d['normalizer']
    zz=d['replay_z']+d['replay_x']@beta; p=expit(zz)
    value+=float(np.mean(np.logaddexp(0,zz)-d['y']*zz)); grad+=d['replay_x'].T@(p-d['y'])/len(zz); H+=(d['replay_x'].T*p*(1-p))@d['replay_x']/len(zz)
    value+=RIDGE*float(beta@beta); grad+=2*RIDGE*beta; H+=2*RIDGE*np.eye(WIDTH)
    return float(value),grad,H

def fit(d):
    zero=np.zeros(WIDTH); L0,_,_=derivatives(zero,d)
    result=minimize(lambda b:derivatives(b,d)[0],zero,jac=lambda b:derivatives(b,d)[1],hess=lambda b:derivatives(b,d)[2],**OPTIONS)
    base={'success':bool(getattr(result,'success',False)),'initial_value':L0,'nit':getattr(result,'nit',None),'nfev':getattr(result,'nfev',None),'njev':getattr(result,'njev',None),'nhev':getattr(result,'nhev',None),'message':str(getattr(result,'message','missing solver result'))}
    if not hasattr(result,'x') or np.shape(result.x)!=(WIDTH,) or not np.isfinite(result.x).all():
        base.update(final_value=None,gradient_l2=None,hessian_asymmetry=None,minimum_hessian_eigenvalue=None); raise NumericalFailure(base)
    try: value,grad,H=derivatives(result.x,d)
    except Exception:
        base.update(final_value=None,gradient_l2=None,hessian_asymmetry=None,minimum_hessian_eigenvalue=None); raise NumericalFailure(base)
    if not np.isfinite(value) or not np.isfinite(grad).all() or not np.isfinite(H).all():
        base.update(final_value=None,gradient_l2=None,hessian_asymmetry=None,minimum_hessian_eigenvalue=None); raise NumericalFailure(base)
    report={**base,'final_value':value,'gradient_l2':float(np.linalg.norm(grad)),'hessian_asymmetry':float(np.max(abs(H-H.T))),'minimum_hessian_eigenvalue':float(np.linalg.eigvalsh((H+H.T)/2).min())}
    ok=result.success and np.isfinite(value) and np.isfinite(grad).all() and np.isfinite(H).all() and report['gradient_l2']<=1e-6 and report['hessian_asymmetry']<=1e-10 and report['minimum_hessian_eigenvalue']>=-1e-8 and value<=L0+1e-12
    if not ok: raise NumericalFailure(report)
    report['classification']='APPROXIMATE_SECOND_ORDER_STATIONARY_POINT_ONLY'; return result.x,report
