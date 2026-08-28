#!/usr/bin/env python3
import numpy as np
from jobs.tools import residual_feature_historical_screen as hs
from jobs.tools import residual_feature_probe as rf

def sib(i,p,q50,q200,exact=2):
    return hs.Sibling(i,p,0,1,2,0,0,0,0,exact,q50,q200)

def main():
    a=sib(0,0,20,60); b=sib(1,0,0,0)
    assert hs.stable_relation(a,b)==1
    assert hs.stable_relation(sib(0,0,5,60),b)==0
    assert hs.stable_relation(sib(0,0,20,-60),b)==0
    x=hs.bootstrap(np.array([.1,.2,.3]),np.array([.0,.1,.2]),samples=1000,seed=2026090702)
    y=hs.bootstrap(np.array([.1,.2,.3]),np.array([.0,.1,.2]),samples=1000,seed=2026090702)
    assert x==y and x['pairwise']['mean']>0
    assert hs.BOOTSTRAP_SAMPLES==100000 and hs.BOOTSTRAP_SEED==2026090702
    assert rf.PAIR_ORDER_SEED==2026090701 and rf.SHAM_SEED_BASE==2026090703
    assert rf.ALL_NEW_WIDTH==66 and tuple(rf.ELIGIBLE_FAMILIES)==(
        'F1_CAPTURE_GEOMETRY','F2_RESPONSE_FRONTIER','F3_PROMOTION_RACE',
        'F4_STRUCTURE_GRAPH','F5_KING_GEOMETRY_PLUS','F6_ALL_NEW')
    print('RESIDUAL_FEATURE_HISTORICAL_SCREEN_TEST_OK')
if __name__=='__main__': main()
