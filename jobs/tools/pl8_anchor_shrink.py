#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Apply the preregistered PL8 500k target-blind anchor shrink after the single fit."""
from __future__ import annotations
import argparse,hashlib,json,struct,subprocess,tempfile
from pathlib import Path

SEED=2026103102
STATES=500000
ITER=30
RMS_MAX=12.0
P99_MAX=35.0
SHRINK_OFFSET=84

def sha(p:Path)->str:return hashlib.sha256(p.read_bytes()).hexdigest()
def with_shrink(src:bytes,s:float)->bytes:
    if src[:4]!=b'PL8P' or len(src)<SHRINK_OFFSET+8:raise ValueError('bad PL8 model')
    out=bytearray(src);struct.pack_into('<d',out,SHRINK_OFFSET,float(s));return bytes(out)
def run(exe:Path,states:Path,curr:Path,raw:bytes,td:Path,label:str):
    model=td/f'{label}.pl8p';report=td/f'{label}.json';model.write_bytes(raw)
    subprocess.run([str(exe),str(states),str(curr),str(model),str(report)],check=True)
    r=json.loads(report.read_text());
    if r.get('schema')!='jass.pl8_anchor_eval.v1' or r.get('states')!=STATES or r.get('serialize_reload') is not True:raise RuntimeError('anchor evaluator contract drift')
    ok=float(r['rms_abs_cp'])<=RMS_MAX and float(r['p99_abs_cp'])<=P99_MAX
    return ok,r

def main()->int:
    ap=argparse.ArgumentParser();ap.add_argument('--model-in',type=Path,required=True);ap.add_argument('--states',type=Path,required=True);ap.add_argument('--curriculum',type=Path,required=True);ap.add_argument('--anchor-exe',type=Path,required=True);ap.add_argument('--model-out',type=Path,required=True);ap.add_argument('--report',type=Path,required=True);a=ap.parse_args()
    base=a.model_in.read_bytes();history=[]
    with tempfile.TemporaryDirectory(prefix='pl8-anchor-') as t:
        td=Path(t);ok0,r0=run(a.anchor_exe,a.states,a.curriculum,with_shrink(base,0.0),td,'s0')
        if not ok0:raise RuntimeError('PL8 s=0 must satisfy anchor')
        lo,hi=0.0,1.0
        for i in range(ITER):
            mid=(lo+hi)/2.0;ok,r=run(a.anchor_exe,a.states,a.curriculum,with_shrink(base,mid),td,f'b{i:02d}')
            history.append({'iteration':i+1,'s':mid,'rms_abs_cp':float(r['rms_abs_cp']),'p99_abs_cp':float(r['p99_abs_cp']),'pass':ok})
            if ok:lo=mid
            else:hi=mid
        ok1,r1=run(a.anchor_exe,a.states,a.curriculum,with_shrink(base,1.0),td,'s1')
        final_s=1.0 if ok1 else lo
        final_raw=with_shrink(base,final_s);okf,rf=run(a.anchor_exe,a.states,a.curriculum,final_raw,td,'final')
        if not okf:raise RuntimeError('final PL8 anchor guard failed')
    a.model_out.write_bytes(final_raw)
    p={'schema':'jass.pl8_anchor.v1','verdict':'PL8_ANCHOR_ESTABLISHED','passed':True,'states':STATES,'seed':SEED,'bisection_iterations':ITER,'selection_target_blind':True,'shrink':final_s,'rms_abs_cp':float(rf['rms_abs_cp']),'p99_abs_cp':float(rf['p99_abs_cp']),'max_abs_cp':int(rf['max_abs_cp']),'guard_rms_abs_cp_max':RMS_MAX,'guard_p99_abs_cp_max':P99_MAX,'serialize_reload':True,'source_fit_model_sha256':sha(a.model_in),'anchored_model_sha256':sha(a.model_out),'curriculum_sha256':sha(a.curriculum),'history':history,'source_labels_read':False,'deep_scores_read':0,'fresh_labels':0,'fit_runs_this_stage':0,'strength_games':0,'runtime_micro_search':False,'f6_present_at_inference':False,'d_present_at_inference':False,'d1_present_at_inference':False,'rich_d_present_at_inference':False,'promotion_authorized':False}
    a.report.write_text(json.dumps(p,indent=2,sort_keys=True)+'\n');print(json.dumps({'verdict':p['verdict'],'shrink':final_s,'rms_abs_cp':p['rms_abs_cp'],'p99_abs_cp':p['p99_abs_cp']},sort_keys=True));return 0
if __name__=='__main__':raise SystemExit(main())
