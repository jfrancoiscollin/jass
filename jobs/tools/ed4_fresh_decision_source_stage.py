#!/usr/bin/env python3
from __future__ import annotations
import csv, hashlib, json, os, shutil, struct, subprocess, sys, tempfile, time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from jobs.tools.launch_runtime_v2 import StageEvidence, atomic_json

MASTER=202609120401
RESERVE=202609120411
FILES=('parents.jnnw','children.jnnw','parents.tsv','groups.tsv','source.json')
QUOTAS={'production':{'calibration':2,'decision':64,'reserved':32},'rehearsal':{'calibration':1,'decision':2,'reserved':1}}

def sha(p:Path):
 h=hashlib.sha256();
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1<<20),b''): h.update(b)
 return h.hexdigest()

def records(p:Path):
 raw=p.read_bytes()
 if len(raw)<8 or raw[:4]!=b'JNNW': raise ValueError('bad_jnnw')
 n=struct.unpack_from('<I',raw,4)[0]
 if n==0 or len(raw)!=8+38*n: raise ValueError('jnnw_cardinality')
 out=[raw[8+38*i:8+38*(i+1)] for i in range(n)]
 for r in out:
  if r[32] not in (0,1) or r[33:]!=b'\0'*5: raise ValueError('target_boundary')
  b=struct.unpack_from('<4Q',r)
  if any(x>>50 for x in b) or any(b[i]&b[j] for i in range(4) for j in range(i)): raise ValueError('board_invalid')
 return out

def rot(b): return sum(1<<(49-i) for i in range(50) if b&(1<<i))
def canon(r):
 wm,wk,bm,bk=struct.unpack_from('<4Q',r); stm=r[32]
 f=lambda a,b,c,d,s:f'{a:013x}:{b:013x}:{c:013x}:{d:013x}:{s}'
 return min(f(wm,wk,bm,bk,stm),f(rot(bm),rot(bk),rot(wm),rot(wk),1-stm))
def load_tsv(p):
 with p.open(newline='',encoding='utf-8') as f:return list(csv.DictReader(f,delimiter='\t'))
def validate(source:Path,mode:str,master:int):
 q=QUOTAS[mode]; pr,cr=records(source/'parents.jnnw'),records(source/'children.jnnw'); ps=load_tsv(source/'parents.tsv'); gs=load_tsv(source/'groups.tsv'); meta=json.loads((source/'source.json').read_text())
 expected_mode='production' if mode=='production' else 'smoke'; seeds=[master,master+1,master+2]
 if (meta.get('schema'),meta.get('mode'),meta.get('master_seed'),meta.get('split_seeds'))!=('jass.ed4.fresh_scorefree_source.v1',expected_mode,master,seeds): raise ValueError('source_meta')
 if any(meta.get(k)!=0 for k in ('evaluations','searches','fits','scores_generated','target_reads')): raise ValueError('information_boundary')
 if len(ps)!=len(pr) or len(gs)!=len(cr) or len(pr)!=8*sum(q.values()): raise ValueError('cardinality')
 by={i:[] for i in range(len(pr))}
 for g in gs: by[int(g['parent_id'])].append(g)
 counts={s:{f'P{p}_stm{x}':0 for p in range(4) for x in (0,1)} for s in q}; seen=set(); traj=set(); split_seed=dict(zip(('calibration','decision','reserved'),seeds))
 for i,(p,r) in enumerate(zip(ps,pr)):
  wm,wk,bm,bk=struct.unpack_from('<4Q',r); n=sum(x.bit_count() for x in (wm,wk,bm,bk)); ph='P'+str(0 if n>=30 else 1 if n>=20 else 2 if n>=12 else 3); split=p['split']; stm=r[32]
  if split not in q or int(p['seed'])!=split_seed[split] or p['parent_phase']!=ph or int(p['parent_stm'])!=stm: raise ValueError('parent_contract')
  t=(int(p['seed']),int(p['trajectory_index']))
  if t in traj: raise ValueError('trajectory_duplicate')
  traj.add(t); counts[split][f'{ph}_stm{stm}']+=1
  sib=by[i]
  if not 2<=len(sib)<=16: raise ValueError('siblings')
  footprint={canon(r)}
  for g in sib: footprint.add(canon(cr[int(g['row_index'])]))
  if footprint&seen: raise ValueError('canonical_duplicate')
  seen|=footprint
 if any(v!=q[s] for s,c in counts.items() for v in c.values()): raise ValueError('quota')
 return {'parents':len(pr),'children':len(cr),'cells':counts,'unique_canonical_identities':len(seen),'canonical_identity_digest':hashlib.sha256(('\n'.join(sorted(seen))+'\n').encode()).hexdigest(),'split_seeds':seeds,'target_reads':0}

def main():
 art=Path(os.environ['JASS_ARTEFACT_DIR']); result=Path(os.environ['JASS_RESULT_DIR']); mode=os.environ['LAUNCH_MODE']; ev=StageEvidence(art,mode)
 try:
  if mode not in ('rehearsal','production'): raise ValueError('launch_mode')
  master=int(os.environ.get('ED4_FRESH_D_MASTER_SEED',str(MASTER)))
  if master not in (MASTER,RESERVE): raise ValueError('seed_not_preregistered')
  ev.begin('build-seeded-source')
  w=result/'work'; src=w/'src'; build=w/'build'; source=art/'source'; w.mkdir(parents=True,exist_ok=True)
  subprocess.run(['git','archive','HEAD'],cwd=ROOT,stdout=(w/'repo.tar').open('wb'),check=True)
  src.mkdir(); subprocess.run(['tar','-xf',str(w/'repo.tar'),'-C',str(src)],check=True)
  with (src/'CMakeLists.txt').open('a') as f:f.write('\nadd_executable(jass_ed4_fresh_source jobs/tools/ed4_fresh_source.cpp)\ntarget_link_libraries(jass_ed4_fresh_source PRIVATE jass_lib)\n')
  subprocess.run(['cmake','-S',str(src),'-B',str(build),'-DCMAKE_BUILD_TYPE=Release','-DJASS_ENDGAME_FEATURES=ON','-DJASS_KING_MOBILITY=ON','-DJASS_SCAN_PARITY=ON','-DJASS_TEMPO_STAGE=ON'],check=True,timeout=180)
  subprocess.run(['cmake','--build',str(build),'-j2','--target','jass_ed4_fresh_source'],check=True,timeout=180)
  binary=build/'jass_ed4_fresh_source'; ev.complete()
  ev.begin('generate-score-free-source'); exclusions=w/'exclusions.txt'; exclusions.write_text('')
  generator_mode='production' if mode=='production' else 'smoke'
  subprocess.run([str(binary),str(exclusions),str(source),generator_mode,str(master)],check=True,timeout=240); ev.complete()
  ev.begin('validate-and-seal'); v=validate(source,mode,master)
  seal={'schema':'jass.ed4.fresh_d_source_seal.v1','state':'completed','terminal':'ED4_FRESH_D_SOURCE_SEALED_V1','mode':mode,'master_seed':master,'reserve_seed_used':master==RESERVE,'generator_sha256':sha(binary),'code_sha':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'created_at_unix':int(time.time()),'files':{f:sha(source/f) for f in FILES},**v,'scan_searches':0,'jass_searches':0,'fits':0,'strength_games':0,'alpha_spent':0,'confirmation_target_consumed':False,'automatic_target_scoring':False,'next_stage':'GENERATE_AND_SEAL_W_AND_S_SOURCES_OR_AUTHENTICATE_CROSS_BLOCK_DISJOINTNESS'}
  atomic_json(art/'cohort-seal.json',seal); atomic_json(art/'scientific-summary.json',seal); ev.complete(); ev.finish(); return 0
 except Exception as exc:
  ev.fail(exc); atomic_json(art/'scientific-summary.json',{'schema':'jass.ed4.fresh_d_source_failure.v1','state':'failed','terminal':'ED4_FRESH_D_SOURCE_TECHNICAL_FAILURE_V1','error_type':type(exc).__name__,'target_reads':0,'alpha_spent':0,'confirmation_target_consumed':False}); return 2
if __name__=='__main__': raise SystemExit(main())
