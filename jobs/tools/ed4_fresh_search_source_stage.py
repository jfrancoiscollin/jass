#!/usr/bin/env python3
from __future__ import annotations
import os, subprocess, sys, time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from jobs.tools.launch_runtime_v2 import StageEvidence, atomic_json
from jobs.tools import ed4_fresh_decision_source_stage as d
PRIMARY=202609120403
RESERVE=202609120413
FORCED_SEED=RESERVE
FILES=d.FILES

def main():
    art=Path(os.environ['JASS_ARTEFACT_DIR']); result=Path(os.environ['JASS_RESULT_DIR'])
    mode=os.environ['LAUNCH_MODE']; ev=StageEvidence(art,mode)
    try:
        if mode not in ('rehearsal','production'): raise ValueError('launch_mode')
        seed=int(os.environ.get('ED4_FRESH_S_MASTER_SEED',str(FORCED_SEED)))
        if seed!=RESERVE: raise ValueError('s_reserve_required_by_d_substream_collision')
        ev.begin('build-seeded-source')
        w=result/'work'; src=w/'src'; build=w/'build'; source=art/'source'; w.mkdir(parents=True,exist_ok=True)
        subprocess.run(['git','archive','HEAD'],cwd=ROOT,stdout=(w/'repo.tar').open('wb'),check=True)
        src.mkdir(); subprocess.run(['tar','-xf',str(w/'repo.tar'),'-C',str(src)],check=True)
        with (src/'CMakeLists.txt').open('a') as f:
            f.write('\nadd_executable(jass_ed4_fresh_source jobs/tools/ed4_fresh_source.cpp)\ntarget_link_libraries(jass_ed4_fresh_source PRIVATE jass_lib)\n')
        subprocess.run(['cmake','-S',str(src),'-B',str(build),'-DCMAKE_BUILD_TYPE=Release','-DJASS_ENDGAME_FEATURES=ON','-DJASS_KING_MOBILITY=ON','-DJASS_SCAN_PARITY=ON','-DJASS_TEMPO_STAGE=ON'],check=True,timeout=180)
        subprocess.run(['cmake','--build',str(build),'-j2','--target','jass_ed4_fresh_source'],check=True,timeout=180)
        binary=build/'jass_ed4_fresh_source'; ev.complete()
        ev.begin('generate-score-free-source')
        exclusions=w/'exclusions.txt'; exclusions.write_text('')
        generator_mode='production' if mode=='production' else 'smoke'
        subprocess.run([str(binary),str(exclusions),str(source),generator_mode,str(seed)],check=True,timeout=240)
        ev.complete()
        ev.begin('validate-and-seal')
        v=d.validate(source,mode,seed)
        seal={'schema':'jass.ed4.fresh_s_source_seal.v1','state':'completed','terminal':'ED4_FRESH_S_SOURCE_SEALED_V1','mode':mode,'parent_preregistered_seed':PRIMARY,'master_seed':seed,'reserve_seed_used':True,'reserve_reason':'PRIMARY_S_SEED_COLLIDES_WITH_D_1937_RESERVED_SUBSTREAM_PRE_TARGET','generator_sha256':d.sha(binary),'code_sha':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'created_at_unix':int(time.time()),'files':{f:d.sha(source/f) for f in FILES},**v,'confirmation_roots':512 if mode=='production' else 16,'scan_searches':0,'jass_searches':0,'fits':0,'strength_games':0,'alpha_spent':0,'confirmation_target_consumed':False,'automatic_target_scoring':False,'next_stage':'AUTHENTICATE_D_W_S_DISJOINTNESS_BEFORE_TARGET_READ'}
        atomic_json(art/'cohort-seal.json',seal); atomic_json(art/'scientific-summary.json',seal)
        ev.complete(); ev.finish(); return 0
    except Exception as exc:
        ev.fail(exc)
        atomic_json(art/'scientific-summary.json',{'schema':'jass.ed4.fresh_s_source_failure.v1','state':'failed','terminal':'ED4_FRESH_S_SOURCE_TECHNICAL_FAILURE_V1','error_type':type(exc).__name__,'target_reads':0,'alpha_spent':0,'confirmation_target_consumed':False})
        return 2
if __name__=='__main__': raise SystemExit(main())
