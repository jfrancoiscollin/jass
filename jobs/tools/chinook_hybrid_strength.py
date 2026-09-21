#!/usr/bin/env python3
"""Causal CHINOOK_HYBRID vs CURRICULUM strength test over fresh sealed openings."""
from __future__ import annotations
from collections import Counter
import argparse, gzip, json, math, os, signal, statistics, subprocess, sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
from jobs.tools import cls_g0_strength_main as base

POOL_SEED=2026092121
ORDER_SEED=2026092122
PAIRS=288
REPRESENTATIVE_OPENINGS=8
ALPHA=0.05
LOSS_ELO=100
SCORE_BOUNDARY=1/(1+10**(LOSS_ELO/400))
READY="CHINOOK_HYBRID_STRENGTH_REHEARSAL_READY_V1"
COMPLETE="CHINOOK_HYBRID_STRENGTH_MAIN_COMPLETE_V1"
PHASES=["authenticate-study","build-runtime","seal-openings","execute-paired-stage","publish-study"]
ARM_HYBRID="CHINOOK_HYBRID"
ARM_CONTROL="CURRICULUM"
CURRICULUM_SHA=base.MODELS["CURRICULUM"]
HIER_SHA=base.MODELS["HIER"]
WORKERS=4
PAIR_TIMEOUT=180

def need(ok,reason):
    if not ok: raise ValueError(reason)

def write(path,value,replace=False): base.write(path,value,replace=replace)

def engine_env(arm,work):
    if arm==ARM_HYBRID: return {"JASS_CHINOOK_HIER_MODEL":str(work/"HIER.pjtw")}
    need(arm==ARM_CONTROL,"UNKNOWN_ARM")
    return {"JASS_CHINOOK_HIER_MODEL":None}

def model_path(arm,work):
    need(arm in (ARM_HYBRID,ARM_CONTROL),"UNKNOWN_ARM")
    return work/"CURRICULUM.pjtw"

def native_game(spec,a_white,counts,save):
    from jobs.tools.calibrate_vs_scan import JassEngine, Referee, play_game
    requests,warm=[],[]
    class Observed(JassEngine):
        warming=True
        def _read_until(self,predicate,timeout_s=60):
            lines=super()._read_until(predicate,timeout_s=timeout_s); need(not lines[-1].startswith("error"),"PROTOCOL_ERROR"); return lines
        def go_verbose(self,depth=None,movetime=None):
            counts["searches_started"]+=1; save(); t=time.monotonic()
            move,lines=super().go_verbose(depth=depth,movetime=movetime); elapsed=time.monotonic()-t
            import re
            fields={k:int(v) for k,v in re.findall(r"\b([A-Za-z][A-Za-z0-9_]*)=(-?\d+)\b",lines[-1])}
            need({"nodes","depth","evalcalls"}<=fields.keys(),"TELEMETRY_MISSING")
            q={"side":self.label,"nodes":fields["nodes"],"depth":fields["depth"],"eval_calls":fields["evalcalls"],"wall_seconds":elapsed,"move":None if move is None else move.jass_apply_str()}
            (warm if self.warming else requests).append(q)
            if not self.warming: need(elapsed<=base.RESPONSE_LIMIT,"WARM_MATCH_RESPONSE_OVERRUN")
            return move,lines
    class StrictReferee(Referee):
        def apply_move(self,move): need(super().apply_move(move),"ILLEGAL_MOVE"); return True
    opened=[]
    try:
        work=Path(spec["work"])
        for label,arm in (("A",spec["arm_a"]),("B",spec["arm_b"])):
            eng=Observed(spec["exe"],label=label,pattern_path=str(model_path(arm,work)),enforce_no_book=True,search_params=None,threads=1,env_overrides=engine_env(arm,work))
            opened.append(eng); eng.new_game(); eng.set_position_fen(base.WARM_FEN); eng.go(depth=1); eng.warming=False
        opened.append(StrictReferee(spec["exe"])); a,b,ref=opened
        counts["games_started"]+=1; save(); start=time.monotonic()
        result=play_game(a if a_white else b,b if a_white else a,ref,spec["opening"],depth=None,movetime=base.MOVETIME,max_plies=base.MAX_PLIES,game_timeout_s=base.GAME_TIMEOUT)
        if result.reason=="ply cap" and not ref.has_legal_moves():
            result.outcome="L" if result.fens[-1].startswith("W") else "W"; result.reason="no legal move from cap-terminal"
        score=.5 if result.outcome=="D" else float((result.outcome=="W")==a_white)
        row={"opening":spec["opening"],"a_is_white":a_white,"outcome":result.outcome,"score_a":score,"reason":result.reason,"plies":result.plies,"fens":result.fens,"moves":result.moves,"requests":requests,"warmup_requests":warm,"game_wall_seconds":time.monotonic()-start}
        base.helpers().validate_game(row); need(len(warm)==2 and {q["side"] for q in warm}=={"A","B"},"WARMUP_COVERAGE"); return row
    finally:
        for eng in reversed(opened): eng.close()

def worker(path):
    s=base.read(path); expected=(s["arm_a"],s["arm_b"])
    need(expected in ((ARM_CONTROL,ARM_CONTROL),(ARM_HYBRID,ARM_HYBRID)) if s["mode"]=="rehearsal" else expected==(ARM_HYBRID,ARM_CONTROL),"WORKER_ARMS")
    work=Path(s["work"]); need(base.sha(work/"CURRICULUM.pjtw")==CURRICULUM_SHA,"CURRICULUM_IDENTITY"); need(base.sha(work/"HIER.pjtw")==HIER_SHA,"HIER_IDENTITY")
    counts={"games_started":0,"searches_started":0}
    def save(): write(Path(s["counts"]),counts,replace=True)
    save(); games=[native_game(s,c,counts,save) for c in (True,False)]
    write(Path(s["output"]),{"task_id":s["task_id"],"opening":s["opening"],"arm_a":s["arm_a"],"arm_b":s["arm_b"],"games":games})

def make_tasks(work,exe,seal,mode):
    rows=seal["representative"] if mode=="rehearsal" else seal["main"]
    arms=[(ARM_CONTROL,ARM_CONTROL),(ARM_HYBRID,ARM_HYBRID)] if mode=="rehearsal" else [(ARM_HYBRID,ARM_CONTROL)]
    out=[]
    for i,row in enumerate(rows):
        for a,b in arms:
            key=f"pair-{i:04d}-{a}"
            out.append({"task_id":key,"mode":mode,"opening":row["fen"],"exe":str(exe),"arm_a":a,"arm_b":b,"work":str(work),"counts":str(work/(key+".counts.json")),"output":str(work/(key+".json"))})
    return out

def validate_pairs(rows,tasks):
    need(len(rows)==len(tasks)>0,"PAIRED_COUNT")
    for row,task in zip(rows,tasks):
        need(all(row[k]==task[k] for k in ("task_id","opening","arm_a","arm_b")),"PAIRED_IDENTITY")
        need(len(row["games"])==2 and [g["a_is_white"] for g in row["games"]]==[True,False],"PAIRED_COLOURS")
        for g in row["games"]:
            base.helpers().validate_game(g); need(all(q["wall_seconds"]<=base.RESPONSE_LIMIT for q in g["requests"]),"CADENCE_INVALID")

def run_tasks(items,work,art,evidence):
    active={}; index=0
    def progress():
        counts=[base.read(Path(s["counts"])) for s in items if Path(s["counts"]).exists()]
        totals={"strength_games":sum(c["games_started"] for c in counts),"new_jass_searches":sum(c["searches_started"] for c in counts)}
        for k,v in totals.items():
            old=evidence.value["actual_side_effects"][k]
            if v>old: evidence.record_effect(k,v-old)
        write(art/"progress.json",{"stage":evidence.value["phase"],"pairs_planned":len(items),"pairs_completed":sum(Path(s["output"]).exists() for s in items),**totals},replace=True)
    try:
        while active or index<len(items):
            while len(active)<WORKERS and index<len(items):
                s=items[index]; index+=1; pth=work/(s["task_id"]+".spec.json"); write(pth,s); log=(work/(s["task_id"]+".log")).open("xb")
                p=subprocess.Popen([sys.executable,str(Path(__file__).resolve()),"--worker",str(pth)],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,start_new_session=True,env=base.helpers().worker_env())
                active[p.pid]=(p,log,time.monotonic())
            for pid,(p,log,t) in list(active.items()):
                need(time.monotonic()-t<=PAIR_TIMEOUT,"PAIR_TIMEOUT")
                if p.poll() is not None:
                    rc=p.returncode; log.close(); base.helpers().kill_group(p); del active[pid]; need(rc==0,"MATCH_WORKER_FAILED")
            progress()
            if active: time.sleep(1)
        rows=[base.read(Path(s["output"])) for s in items]; validate_pairs(rows,items); return rows
    finally:
        for p,log,_ in active.values(): base.helpers().kill_group(p); log.close()
        progress()

def analyze_main(rows):
    need(len(rows)==PAIRS,"MAIN_COMPLETE_REQUIRED"); low=[]; high=[]; scored=[]; capped=0
    for r in rows:
        need((r["arm_a"],r["arm_b"])==(ARM_HYBRID,ARM_CONTROL),"MAIN_CONTRAST")
        capped+=sum(g["reason"]=="ply cap" for g in r["games"])
        low.append(sum(0 if g["reason"]=="ply cap" else g["score_a"] for g in r["games"])/2)
        high.append(sum(1 if g["reason"]=="ply cap" else g["score_a"] for g in r["games"])/2)
        scored.append(sum(g["score_a"] for g in r["games"])/2)
    radius=math.sqrt(math.log(2/ALPHA)/(2*PAIRS)); lo=max(0,statistics.fmean(low)-radius); hi=min(1,statistics.fmean(high)+radius)
    verdict="SUBSTANTIAL_LOSS_SUPPORTED" if hi<SCORE_BOUNDARY else ("SUBSTANTIAL_LOSS_EXCLUDED" if lo>SCORE_BOUNDARY else "INDETERMINATE")
    return {"pairs":PAIRS,"games":2*PAIRS,"loss_margin_elo":LOSS_ELO,"score_boundary":SCORE_BOUNDARY,"simultaneous_confidence":1-ALPHA,"score_interval":[lo,hi],"hoeffding_radius":radius,"statistical_verdict":verdict,"administratively_censored_games":capped,"descriptive_half_point_ply_cap_score":statistics.fmean(scored),"descriptive_pentanomial_counts":dict(Counter(str(2*x) for x in scored)),"no_superiority_or_promotion_claim":True}

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--worker",type=Path); args=ap.parse_args()
    if args.worker: worker(args.worker); return 0
    from jobs.tools.launch_runtime_v2 import StageEvidence, atomic_json
    result=Path(os.environ["JASS_RESULT_DIR"]); art=Path(os.environ["JASS_ARTEFACT_DIR"]); mode=os.environ["LAUNCH_MODE"]; need(mode in ("rehearsal","production"),"STAGE_MODE")
    work=result/"work"/"chinook-hybrid-strength"; work.mkdir(parents=True,exist_ok=False); art.mkdir(parents=True,exist_ok=True); evidence=StageEvidence(art,mode)
    try:
        evidence.begin(PHASES[0]); excluded,cold,auth=base.fetch_study(work); need(base.helpers().MODEL_SHA==base.MODELS,"HELPER_MODEL_DRIFT"); auth["models"]=base.helpers().fetch_models(work); write(art/"source-authentication.json",auth); write(art/"calibration-review.json",cold); evidence.complete()
        evidence.begin(PHASES[1]); exe=base.helpers().build(work); runtime={"binary_sha256":base.sha(exe),"curriculum_sha256":CURRICULUM_SHA,"hier_sha256":HIER_SHA,"hybrid_gate":{"total_pieces":[9,19],"legal_moves":[5,8],"stm_material_status":"behind"},"movetime_ms":100,"response_limit_ms":120,"book":False,"threads":1,"workers":WORKERS}; write(art/"runtime-identity.json",runtime); evidence.complete()
        evidence.begin(PHASES[2]); old_pool,old_order=base.POOL_SEED,base.ORDER_SEED; base.POOL_SEED,base.ORDER_SEED=POOL_SEED,ORDER_SEED
        try:
            if mode=="rehearsal": seal=base.generate_openings(exe,work,excluded)
            else:
                proof=base.read(result/"launch-prerequisite.json"); need(proof.get("verdict")=="FULL_PIPELINE_REHEARSAL_PASS" and proof.get("published_roundtrip") is True,"REAL_REHEARSAL_REQUIRED"); prev=result/"launch-prerequisite"; ready=base.read(prev/"study-report.json"); need(ready.get("terminal")==READY and ready.get("production_ready") is True and ready.get("cross_model_games")==0,"MAIN_NOT_ADMITTED"); need(base.read(prev/"runtime-identity.json")==runtime,"RUNTIME_ROUNDTRIP"); seal=base.read(prev/"opening-freeze.json")
            base.validate_seal(seal)
        finally: base.POOL_SEED,base.ORDER_SEED=old_pool,old_order
        write(art/"opening-freeze.json",seal); evidence.complete()
        evidence.begin(PHASES[3]); tasks=make_tasks(work,exe,seal,mode); started=time.monotonic(); rows=run_tasks(tasks,work,art,evidence); elapsed=time.monotonic()-started; evidence.complete()
        evidence.begin(PHASES[4])
        if mode=="rehearsal":
            traj={base.fen_identity(f) for r in rows for g in r["games"] for f in g["fens"]}; overlaps=sum(r["canonical"] in traj for r in seal["main"]); projected=PAIRS*elapsed/len(rows); report={"terminal":READY,"production_ready":overlaps==0 and projected<=base.MAIN_WORK_CAP,"representative_pairs":len(rows),"representative_games":2*len(rows),"cross_model_games":0,"main_start_overlap_rehearsal_trajectories":overlaps,"representative_block_seconds":elapsed,"projected_main_work_seconds":projected,"main_work_ceiling_seconds":base.MAIN_WORK_CAP,"clock_checks_passed":True,"scientific_verdict":None}
        else: report={"terminal":COMPLETE,"cross_model_games":2*PAIRS,**analyze_main(rows)}
        report.update(mode=mode,arms=[ARM_HYBRID,ARM_CONTROL],opening_selection_sha256=seal["selection_sha256"]); write(art/"study-report.json",report)
        raw=json.dumps({"mode":mode,"pairs":rows},sort_keys=True,allow_nan=False).encode()
        with (art/"stage-games.json.gz").open("xb") as f:
            with gzip.GzipFile(fileobj=f,mode="wb",mtime=0) as z: z.write(raw)
        summary={"schema":"jass.chinook_hybrid_strength.v1","state":"completed",**report,"classification":"TECHNICAL_REPRESENTATIVE_REHEARSAL" if mode=="rehearsal" else "CAUSAL_STRENGTH_CASE_STUDY","scientific_verdict":None if mode=="rehearsal" else report["statistical_verdict"],"promotion_authorized":False,"bake_authorized":False,"alpha_spent":0 if mode=="rehearsal" else ALPHA,"actual_side_effects":evidence.value["actual_side_effects"],"next_stage":"ADMIT_EXACT_MAIN_AFTER_PUBLISHED_REHEARSAL" if mode=="rehearsal" and report["production_ready"] else "INTERPRET_NO_AUTOMATIC_PROMOTION"}
        atomic_json(art/"scientific-summary.json",summary); (art/"RESULTS.md").write_text("# CHINOOK_HYBRID vs CURRICULUM\n\n"+json.dumps(summary,indent=2)+"\n"); write(art/"manifest.json",{"curriculum_sha256":CURRICULUM_SHA,"hier_sha256":HIER_SHA,"selection_sha256":seal["selection_sha256"],"output_sha256":{n:base.sha(art/n) for n in ("stage-games.json.gz","opening-freeze.json","study-report.json")}}); evidence.complete(); evidence.finish(); return 0
    except BaseException as exc: evidence.fail(exc); raise

if __name__=="__main__":
    signal.signal(signal.SIGTERM,lambda s,f: (_ for _ in ()).throw(KeyboardInterrupt("TERMINATED")))
    raise SystemExit(main())
