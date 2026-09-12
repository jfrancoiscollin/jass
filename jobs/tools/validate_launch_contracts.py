#!/usr/bin/env python3
from __future__ import annotations
import argparse, importlib.util, json, re, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from jobs.tools.launch_runtime_v2 import EFFECTS

BASE_REG={'jobs.tests.test_launch_gate_v2','jobs.tests.test_launch_gate_pipeline_v2'}
REQ={'schema','campaign','stage','command','evidence_outputs','production_max_effects','rehearsal_max_effects','regressions','required_phases'}
HEX64=re.compile(r'^[0-9a-f]{64}$')

class ContractError(RuntimeError): pass

def need(ok,msg):
    if not ok: raise ContractError(msg)

def load(path:Path):
    need(path.is_file() and not path.is_symlink(),f'missing:{path}')
    try:return json.loads(path.read_text())
    except Exception as e: raise ContractError(f'json:{path}:{type(e).__name__}')

def validate_profile(path:Path):
    p=load(path)
    missing=REQ-set(p)
    need(not missing,f'profile_fields:{path}:{sorted(missing)}')
    need(p['schema']=='jass.launch_profile.v2',f'profile_schema:{path}')
    need(isinstance(p['campaign'],str) and p['campaign'],f'campaign:{path}')
    need(isinstance(p['stage'],str) and p['stage'],f'stage:{path}')
    need(isinstance(p['command'],list) and len(p['command'])>=2 and all(isinstance(x,str) and x for x in p['command']),f'command:{path}')
    entry=Path(p['command'][1])
    need(not entry.is_absolute() and '..' not in entry.parts and (ROOT/entry).is_file(),f'entrypoint:{path}:{entry}')
    regs=p['regressions']; need(isinstance(regs,list) and len(regs)==len(set(regs)) and BASE_REG<=set(regs),f'regressions:{path}')
    for mod in regs:
        need(isinstance(mod,str) and mod.startswith('jobs.tests.'),f'regression_name:{path}:{mod}')
        need(importlib.util.find_spec(mod) is not None,f'regression_missing:{path}:{mod}')
    phases=p['required_phases']; need(isinstance(phases,list) and phases and len(phases)==len(set(phases)) and all(isinstance(x,str) and x for x in phases),f'phases:{path}')
    outs=p['evidence_outputs']; need(isinstance(outs,list) and len(outs)==len(set(outs)) and all(isinstance(x,str) and x and not Path(x).is_absolute() and '..' not in Path(x).parts for x in outs),f'evidence_outputs:{path}')
    for key in ('rehearsal_max_effects','production_max_effects'):
        v=p[key]; need(isinstance(v,dict) and set(v)==set(EFFECTS),f'effects_keys:{path}:{key}')
        need(all(type(v[k]) is int and v[k]>=0 for k in EFFECTS),f'effects_values:{path}:{key}')
    return p

def validate_all(root:Path):
    files=sorted((root/'jobs/launch_profiles').glob('*.json'))
    need(files,'no_profiles')
    for f in files: validate_profile(f)
    return len(files)

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--root',type=Path,default=ROOT); ap.add_argument('--profile',type=Path)
    a=ap.parse_args()
    try:
        if a.profile:
            validate_profile(a.profile); print(f'OK {a.profile}')
        else:
            n=validate_all(a.root); print(f'OK {n} launch profiles')
        return 0
    except ContractError as e:
        print(f'LAUNCH_CONTRACT_INVALID {e}')
        return 2

if __name__=='__main__': raise SystemExit(main())
