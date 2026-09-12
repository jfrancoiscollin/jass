#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json, re, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from jobs.tools.validate_launch_contracts import validate_profile, ContractError

HEX40=re.compile(r'^[0-9a-f]{40}$')

def sha_bytes(data:bytes): return hashlib.sha256(data).hexdigest()
def canon(obj): return (json.dumps(obj,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n').encode()

def build(job_id,code_sha,profile_path,spec_template,mode='rehearsal',rehearsal=None):
    if not HEX40.fullmatch(code_sha): raise ContractError('code_sha')
    profile=validate_profile(profile_path)
    spec=json.loads(spec_template.read_text())
    spec['code_sha']=code_sha
    spec['campaign']=profile['campaign']; spec['stage']=profile['stage']; spec['command']=profile['command']
    env=spec.setdefault('environment',{}).setdefault('set',{}); env['LAUNCH_MODE']=mode
    timeout=spec.get('timeouts',{}).get('stage_seconds')
    if not isinstance(timeout,int) or timeout<=0: raise ContractError('stage_timeout')
    required=set(profile['evidence_outputs'])|{'execution-evidence.json','scientific-summary.json'}
    declared={x.get('path') for x in spec.get('outputs',[]) if isinstance(x,dict) and x.get('required') is True and x.get('nonempty') is True and x.get('scope')=='artifact'}
    if not required<=declared: raise ContractError('output_contract')
    sb=canon(spec); spec_sha=sha_bytes(sb); pb=profile_path.read_bytes(); profile_sha=sha_bytes(pb)
    admission={'schema':'jass.launch_admission.v2','job_id':job_id,'profile':str(profile_path.relative_to(Path.cwd())),'profile_sha256':profile_sha,'spec_sha256':spec_sha,'rehearsal':rehearsal}
    if mode=='rehearsal' and rehearsal is not None: raise ContractError('rehearsal_mode_conflict')
    if mode=='production' and not isinstance(rehearsal,dict): raise ContractError('production_rehearsal_required')
    ab=canon(admission); admission_sha=sha_bytes(ab)
    shell='\n'.join(['#!/usr/bin/env bash','set -Eeuo pipefail',f'export EXPECTED_CODE_SHA="{code_sha}"',f'export EXPECTED_STAGE_SPEC_SHA256="{spec_sha}"','export JASS_STAGE_SPEC_REL="__SPEC_REL__"',f'export EXPECTED_LAUNCH_ADMISSION_SHA256="{admission_sha}"','export JASS_LAUNCH_ADMISSION_REL="__ADMISSION_REL__"',f'export EXPECTED_LAUNCH_TIMEOUT_SECONDS="{timeout+600}"','exec /usr/bin/bash "${JASS_CONTROL_REPO_DIR:-/srv/jass/control}/templates/run-stage-v1.sh"',''])
    return sb,ab,shell

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--job-id',required=True); ap.add_argument('--code-sha',required=True); ap.add_argument('--profile',type=Path,required=True); ap.add_argument('--spec-template',type=Path,required=True); ap.add_argument('--out-dir',type=Path,required=True); ap.add_argument('--stem',required=True); ap.add_argument('--mode',choices=('rehearsal','production'),default='rehearsal'); ap.add_argument('--rehearsal-json')
    a=ap.parse_args(); r=json.loads(a.rehearsal_json) if a.rehearsal_json else None
    try: sb,ab,sh=build(a.job_id,a.code_sha,a.profile,a.spec_template,a.mode,r)
    except (ContractError,ValueError,json.JSONDecodeError) as e: print(f'LAUNCH_BUNDLE_INVALID {e}'); return 2
    a.out_dir.mkdir(parents=True,exist_ok=True); sp=a.out_dir/(a.stem+'.json'); ad=a.out_dir/(a.stem+'.admission.json'); qp=a.out_dir/(a.job_id+'.sh')
    sp.write_bytes(sb); ad.write_bytes(ab)
    sh=sh.replace('__SPEC_REL__',str(sp)).replace('__ADMISSION_REL__',str(ad)); qp.write_text(sh); qp.chmod(0o755)
    print(json.dumps({'spec':str(sp),'admission':str(ad),'queue':str(qp)},sort_keys=True)); return 0

if __name__=='__main__': raise SystemExit(main())
