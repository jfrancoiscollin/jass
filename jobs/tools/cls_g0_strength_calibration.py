#!/usr/bin/env python3
"""G0 strength-validation preparation only; no HIER-vs-CURRICULUM test here."""
from __future__ import annotations
import argparse
from collections import Counter
import gzip
import hashlib
import json
import math
import os
from pathlib import Path
import re
import signal
import statistics
import subprocess
import sys
import time
import shutil

ROOT = Path(__file__).resolve().parents[2]
BASE_CODE = "7b789a0c675ce08868fe4a8fcef0becaa4193286"
PARENT_SHA = "319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1"
HIER_SHA = "95bed3ac9fac4368809609fb1a981ee863401a30ca623fb7bfa3caf7eaddf628"
MODEL_SHA = {"CURRICULUM": PARENT_SHA, "HIER": HIER_SHA}
HIER_JOB = "cpx62-2062-l3-cls-hier-l2-hier-candidate-rehearsal-v1"
HIER_ATTEMPT = "20260919T142226Z-a28f1049"
HIER_CODE = "a28f10491d94ca451932b0e7b46df7cdf3b7e1c8"
HIER_RECEIPT = "68203e5cd3fe40ea92c24bc2dfdc83c94cc52c257bbea871ed4e149b0873194e"
PARENT_JOB = "home-1650-l3-scan-ceiling-preflight-v1"
PARENT_ATTEMPT = "20260829T132800Z-28e12fba"
PARENT_CODE = "28e12fba0ead14def244ffc442b15937f65edc0e"
TERMINAL = "CLS_G0_STRENGTH_CALIBRATION_COMPLETE_V1"
PHASES = ["authenticate-models", "build-and-load-check", "seal-calibration-openings",
          "deterministic-self-pair-sanity", "timed-self-pair-calibration", "publish-calibration"]
EGDB = "/root/egdb_extracted/app"
EGDB_SRC = "/root/egdb_intl"
MOVETIME = 0.1
MAX_PLIES = 160
WORKERS = 4
GAME_TIMEOUT = 60
PAIR_TIMEOUT = 180
MAX_GAMES = 44
MAX_SEARCHES = MAX_GAMES * MAX_PLIES
FIRST_MOVES = ((31,26),(31,27),(32,27),(32,28),(33,28),(33,29),(34,29),(34,30),(35,30))


def need(ok: bool, reason: str) -> None:
    if not ok:
        raise ValueError(reason)


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def read(path: Path) -> dict:
    obj = json.loads(path.read_text(encoding="utf-8"))
    need(isinstance(obj, dict), "JSON_OBJECT_REQUIRED")
    return obj


def write(path: Path, obj: dict, *, replace: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    need(not path.is_symlink(), "OUTPUT_SYMLINK")
    need(replace or not path.exists(), "NO_CLOBBER")
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("x", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, sort_keys=True, allow_nan=False)
        f.write("\n")
    tmp.replace(path)


def openings() -> list[str]:
    result = []
    for origin, dest in FIRST_MOVES:
        men = sorted((set(range(31,51)) - {origin}) | {dest})
        result.append("B:W" + ",".join(map(str, men)) + ":B1-20")
    need(len(set(result)) == 9, "OPENING_IDENTITY")
    return result


def worker_env() -> dict[str,str]:
    env = {k: os.environ[k] for k in ("PATH", "HOME", "LANG", "LC_ALL", "LD_LIBRARY_PATH") if k in os.environ}
    env.update(JASS_EGDB_PATH=EGDB, JASS_EGDB_CACHE_MB="256", OMP_NUM_THREADS="1",
               OPENBLAS_NUM_THREADS="1", MKL_NUM_THREADS="1", PYTHONDONTWRITEBYTECODE="1")
    return env


def kill_group(p: subprocess.Popen) -> None:
    # The process group is owned by this invocation, never another runner/job.
    try:
        os.killpg(p.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    p.wait(timeout=10)


def command(argv: list[str], log: Path, timeout: float, *, env=None, stdin=None) -> None:
    with log.open("xb") as f:
        p = subprocess.Popen(argv, cwd=ROOT, stdout=f, stderr=subprocess.STDOUT,
                             stdin=subprocess.PIPE if stdin is not None else subprocess.DEVNULL,
                             start_new_session=True, env=env)
        try:
            p.communicate(input=stdin, timeout=timeout)
            need(p.returncode == 0, "COMMAND_FAILED:" + log.name)
        finally:
            kill_group(p)


def fetch_models(work: Path) -> dict:
    from jobs.tools import fetch_result_files as fetch
    sources = [
        ("CURRICULUM", PARENT_JOB, PARENT_ATTEMPT, PARENT_CODE, ["curriculum.pjtw"]),
        ("HIER", HIER_JOB, HIER_ATTEMPT, HIER_CODE,
         ["model.pjtw.gz", "scientific-summary.json", "launch-receipt.json"]),
    ]
    auth = {}
    for arm, job, attempt, code, names in sources:
        prefix = f"r2:jass-data/runs/{job}/{attempt}"
        rclone = os.environ.get("RCLONE_BIN", "rclone")
        inventory = fetch.inspect_result_inventory(rclone=rclone, prefix=prefix)
        need((inventory["job_id"], inventory["attempt_id"], inventory["code_sha"],
              inventory["result_state"], inventory["exit_code"]) ==
             (job, attempt, code, "completed", 0), "SOURCE_IDENTITY")
        size = {i["path"]: i["size_bytes"] for i in inventory["files"]}
        need(all(0 < size.get("artefacts/"+n, 0) <= 256 * 1024**2 for n in names), "SOURCE_SIZE")
        dest = work / arm
        auth[arm] = fetch.fetch_files(rclone=rclone, prefix=prefix,
            selections=[("artefacts/"+n,n) for n in names], out_dir=dest)
        model = work / (arm + ".pjtw")
        if arm == "HIER":
            need(sha(dest / "launch-receipt.json") == HIER_RECEIPT, "HIER_RECEIPT")
            s = read(dest / "scientific-summary.json")
            for key, val in {"terminal":"CLS_HIER_CANDIDATE_FIT_READY_V1", "arm":"HIER",
                "model_sha256":HIER_SHA, "direct_parent_sha256":PARENT_SHA,
                "hier_l2":1e-5, "promotion_authorized":False}.items():
                need(s.get(key) == val, "HIER_SOURCE:"+key)
            with gzip.open(dest / "model.pjtw.gz", "rb") as f, model.open("xb") as g:
                total = 0
                for block in iter(lambda: f.read(1 << 20), b""):
                    total += len(block)
                    need(total <= 512 * 1024**2, "EXPANDED_MODEL_SIZE")
                    g.write(block)
        else:
            shutil.copyfile(dest / "curriculum.pjtw", model)
        need(sha(model) == MODEL_SHA[arm], "MODEL_SHA:"+arm)
        model.chmod(0o444)
    return auth


def build(work: Path) -> Path:
    need(Path(EGDB).is_dir() and Path(EGDB_SRC).is_dir(), "REAL_EGDB_REQUIRED")
    command(["git", "diff", "--exit-code", BASE_CODE, "HEAD", "--", "src", "pattern_jass", "CMakeLists.txt"],
            work / "native-source-identity.log", 20)
    b = work / "build"
    command(["cmake", "-S", str(ROOT), "-B", str(b), "-G", "Unix Makefiles",
        "-DCMAKE_BUILD_TYPE=Release", "-DJASS_EGDB=ON", "-DJASS_EGDB_SRC_DIR="+EGDB_SRC,
        "-DJASS_ENDGAME_FEATURES=ON", "-DJASS_KING_MOBILITY=ON", "-DJASS_SCAN_PARITY=ON",
        "-DJASS_TEMPO_STAGE=ON", "-DJASS_TIME_BREAKDOWN=OFF"], work / "configure.log", 180)
    command(["cmake", "--build", str(b), "--target", "jass", "-j", "4"], work / "build.log", 900)
    exe = b / "jass"
    need(exe.is_file(), "BINARY_MISSING")
    command([str(exe), "--egdb-selfcheck", EGDB, "8", "256"],
            work / "egdb-selfcheck.log", 120, env=worker_env())
    for arm in MODEL_SHA:
        log = work / ("load-"+arm+".log")
        command([str(exe), "--no-book", "--pattern", str(work/(arm+".pjtw"))],
                log, 60, env=worker_env(), stdin=b"hello\nquit\n")
        need(any(l.startswith("ready") for l in log.read_text().splitlines()), "LOAD_HANDSHAKE")
    return exe


def validate_game(row: dict) -> None:
    need(row["outcome"] in ("W","D","L") and row["score_a"] in (0,0.5,1), "GAME_OUTCOME")
    need(row["reason"] != "game time cap" and not row["reason"].startswith("illegal move"), "TECHNICAL_GAME_NOT_DRAW")
    allowed = row["reason"] in ("25-move rule", "3-fold repetition", "ply cap") or row["reason"].startswith("no legal move from ")
    need(allowed and 0 < row["plies"] <= MAX_PLIES, "END_REASON_OR_PLIES")
    need(len(row["fens"]) == len(row["moves"])+1 == row["plies"]+1, "TRAJECTORY")
    need(row["fens"][0] == row["opening"], "OPENING_TRAJECTORY")
    expected = .5 if row["outcome"] == "D" else float((row["outcome"] == "W") == row["a_is_white"])
    need(row["score_a"] == expected, "COLOUR_SCORE")
    need(row["requests"] and len(row["requests"]) <= MAX_PLIES, "SEARCH_COUNT")
    need(all(x["wall_seconds"] > 0 and math.isfinite(x["wall_seconds"]) and
             x["nodes"] >= 0 and x["depth"] >= 0 for x in row["requests"]), "TELEMETRY")


def native_game(exe: str, model: str, opening: str, a_white: bool, timed: bool,
                counter, save_counts) -> dict:
    from jobs.tools.calibrate_vs_scan import JassEngine, Referee, play_game
    requests = []
    class Observed(JassEngine):
        def _read_until(self, predicate, timeout_s=60.0):
            lines = super()._read_until(predicate, timeout_s=timeout_s)
            need(not lines[-1].startswith("error"), "ENGINE_PROTOCOL_ERROR")
            return lines
        def go_verbose(self, depth=None, movetime=None):
            counter["searches_started"] += 1
            save_counts()
            t = time.monotonic()
            move, lines = super().go_verbose(depth=depth, movetime=movetime)
            fields = {k:int(v) for k,v in re.findall(r"\b([A-Za-z][A-Za-z0-9_]*)=(-?\d+)\b", lines[-1])}
            need({"depth","nodes","evalcalls"} <= fields.keys(), "NATIVE_TELEMETRY_MISSING")
            requests.append({"side":self.label,"depth":fields["depth"],"nodes":fields["nodes"],
                "eval_calls":fields["evalcalls"], "wall_seconds":time.monotonic()-t,
                "requested_movetime_ms":100 if timed else None,
                "move":None if move is None else move.jass_apply_str()})
            return move, lines
    class StrictReferee(Referee):
        def apply_move(self, m):
            need(super().apply_move(m), "ILLEGAL_MOVE")
            return True
    opened = []
    try:
        for label in ("A", "B"):
            opened.append(Observed(exe, label=label, pattern_path=model,
                enforce_no_book=True, search_params=None, threads=1))
        opened.append(StrictReferee(exe))
        a,b,ref = opened
        t = time.monotonic()
        counter["games_started"] += 1
        save_counts()
        result = play_game(a if a_white else b, b if a_white else a, ref, opening,
            depth=None if timed else 3, movetime=MOVETIME if timed else None,
            max_plies=MAX_PLIES, game_timeout_s=GAME_TIMEOUT)
        if result.reason == "ply cap" and not ref.has_legal_moves():
            result.outcome = "L" if result.fens[-1].startswith("W") else "W"
            result.reason = "no legal move from cap-terminal"
        score = .5 if result.outcome == "D" else float((result.outcome == "W") == a_white)
        row = {"opening":opening,"a_is_white":a_white,"outcome":result.outcome,"score_a":score,
            "plies":result.plies,"reason":result.reason,"moves":result.moves,"fens":result.fens,
            "requests":requests,"game_wall_seconds":time.monotonic()-t}
        validate_game(row)
        return row
    finally:
        for engine in reversed(opened):
            engine.close()


def worker(spec_path: Path) -> None:
    s = read(spec_path)
    need(s["arm"] in MODEL_SHA and s["kind"] in ("sanity","timing"), "CALIBRATION_ONLY")
    need(s["opening"] in openings(), "CALIBRATION_OPENING")
    model = Path(s["model"])
    need(sha(model) == MODEL_SHA[s["arm"]], "WORKER_MODEL_SHA")
    counts = {"games_started":0,"searches_started":0}
    def save():
        write(Path(s["counts"]), counts, replace=True)
    save()
    rows = [native_game(s["exe"],str(model),s["opening"],colour,s["kind"]=="timing",counts,save)
            for colour in (True,False)]
    if s["kind"] == "sanity":
        need(sum(r["score_a"] for r in rows) == 1, "SELF_PAIR_ASYMMETRY")
        need(rows[0]["fens"] == rows[1]["fens"], "DETERMINISTIC_TRAJECTORY_DRIFT")
    need(sha(model) == MODEL_SHA[s["arm"]], "MODEL_MUTATED")
    write(Path(s["output"]), {"task_id":s["task_id"],"arm":s["arm"],"kind":s["kind"],
                              "model_sha256":MODEL_SHA[s["arm"]],"games":rows})


def tasks(work: Path, exe: Path, kind: str) -> list[dict]:
    pool = openings()[:2] if kind == "sanity" else openings()
    result = []
    for arm in MODEL_SHA:
        for index, opening in enumerate(pool):
            name = f"{kind}-{arm}-{index}"
            result.append({"task_id":name,"arm":arm,"kind":kind,"opening":opening,"exe":str(exe),
                "model":str(work/(arm+".pjtw")),"counts":str(work/(name+".counts.json")),
                "output":str(work/(name+".result.json"))})
    return result


def run_tasks(items: list[dict], work: Path, art: Path, evidence) -> list[dict]:
    active = {}
    remaining = iter(items)
    exhausted = False
    def counts():
        result = {"strength_games":0,"new_jass_searches":0}
        for p in work.glob("*.counts.json"):
            c = read(p)
            result["strength_games"] += c["games_started"]
            result["new_jass_searches"] += c["searches_started"]
        for k,v in result.items():
            old = evidence.value["actual_side_effects"][k]
            if v > old:
                evidence.record_effect(k, v-old)
        need(result["strength_games"] <= MAX_GAMES and result["new_jass_searches"] <= MAX_SEARCHES,
             "CALIBRATION_EFFECT_BOUND")
        return result
    try:
        while active or not exhausted:
            while len(active) < WORKERS and not exhausted:
                s = next(remaining, None)
                if s is None:
                    exhausted = True
                    break
                sp = work / (s["task_id"]+".spec.json")
                write(sp,s)
                log = (work/(s["task_id"]+".log")).open("xb")
                p = subprocess.Popen([sys.executable,str(Path(__file__).resolve()),"--worker",str(sp)],
                    cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,start_new_session=True,env=worker_env())
                active[p.pid] = (p,log,time.monotonic())
            for pid,(p,log,start) in list(active.items()):
                need(time.monotonic()-start <= PAIR_TIMEOUT, "PAIR_TIMEOUT")
                rc = p.poll()
                if rc is not None:
                    log.close()
                    kill_group(p)
                    del active[pid]
                    need(rc == 0, "CALIBRATION_WORKER_FAILED")
            c = counts()
            write(art/"calibration-progress.json", {"phase":evidence.value["phase"],**c}, replace=True)
            if active:
                time.sleep(1)
        return [read(Path(s["output"])) for s in items]
    finally:
        for p,log,_ in active.values():
            kill_group(p)
            log.close()
        counts()


def summarize(results: list[dict]) -> dict:
    need(len(results)==22 and len({r["task_id"] for r in results})==22, "PAIR_COVERAGE")
    expected = {f"{kind}-{arm}-{index}" for kind in ("sanity","timing")
                for arm in MODEL_SHA for index in range(2 if kind=="sanity" else 9)}
    need({r["task_id"] for r in results} == expected, "TASK_IDENTITIES")
    summary = {}
    for kind,n in (("sanity",4),("timing",18)):
        block = [r for r in results if r["kind"]==kind]
        need(len(block)==n, "BLOCK_COVERAGE")
        for arm in MODEL_SHA:
            selected = [r for r in block if r["arm"]==arm]
            need(len(selected)==n//2 and all(r["model_sha256"]==MODEL_SHA[arm] for r in selected), "ARM_IDENTITY")
            games = [g for r in selected for g in r["games"]]
            need(len(games)==n, "GAME_COVERAGE")
            for r in selected:
                index = int(r["task_id"].rsplit("-",1)[1])
                need(all(g["opening"] == openings()[index] for g in r["games"]), "TASK_OPENING")
                need([g["a_is_white"] for g in r["games"]]==[True,False], "PAIR_COLOURS")
                if kind=="sanity":
                    need(sum(g["score_a"] for g in r["games"])==1, "SANITY_SCORE")
            for g in games:
                validate_game(g)
            reqs = [q for g in games for q in g["requests"]]
            wall = sum(q["wall_seconds"] for q in reqs)
            summary[kind+"_"+arm] = {"games":len(games),"pairs":len(selected),"searches":len(reqs),
                "search_wall_seconds":wall,"nodes":sum(q["nodes"] for q in reqs),
                "move_wall_median":statistics.median(q["wall_seconds"] for q in reqs),
                "move_wall_max":max(q["wall_seconds"] for q in reqs),
                "moves_above_250ms":sum(q["wall_seconds"]>.25 for q in reqs) if kind=="timing" else None,
                "pair_game_wall_median":statistics.median(sum(g["game_wall_seconds"] for g in r["games"]) for r in selected),
                "reason_counts":dict(Counter(g["reason"] for g in games)),
                "nonempty_telemetry":len(reqs)>0 and wall>0}
    return summary


def main() -> int:
    if str(ROOT) not in sys.path:
        sys.path.insert(0,str(ROOT))
    ap=argparse.ArgumentParser()
    ap.add_argument("--worker",type=Path)
    args=ap.parse_args()
    if args.worker:
        worker(args.worker)
        return 0
    from jobs.tools.launch_runtime_v2 import StageEvidence, atomic_json
    art=Path(os.environ["JASS_ARTEFACT_DIR"])
    work=Path(os.environ["JASS_RESULT_DIR"])/"work"/"strength-calibration"
    work.mkdir(parents=True,exist_ok=False)
    art.mkdir(parents=True,exist_ok=True)
    evidence=StageEvidence(art,os.environ["LAUNCH_MODE"])
    def phase(i):
        evidence.begin(PHASES[i])
    try:
        need(not work.resolve().is_relative_to(ROOT.resolve()), "SCRATCH_MUST_BE_OUTSIDE_REPO")
        need(shutil.disk_usage(work).free >= 3*1024**3, "SCRATCH_SPACE")
        phase(0)
        auth=fetch_models(work)
        write(art/"source-authentication.json",auth)
        evidence.complete()
        phase(1)
        exe=build(work)
        write(art/"runtime-identity.json",{"binary_sha256":sha(exe),"models":MODEL_SHA,
            "native_source_base":BASE_CODE,"search_params":"compiled defaults","book":False,
            "threads_per_player":1,"tt_mb":16,"egdb_path":EGDB,"egdb_cache_mb":256,
            "workers":WORKERS,"fresh_processes_per_game":True,
            "native_egdb_selfcheck_exit_code":0,"egdb_selfcheck_log_sha256":sha(work/"egdb-selfcheck.log")})
        evidence.complete()
        phase(2)
        write(art/"calibration-openings.json",{"openings":openings(),"source":"nine standard legal first moves",
            "confirmation_allowed":False,"fresh_sample_claim":False})
        evidence.complete()
        phase(3)
        t=time.monotonic()
        a=run_tasks(tasks(work,exe,"sanity"),work,art,evidence)
        sanity_seconds=time.monotonic()-t
        evidence.complete()
        phase(4)
        t=time.monotonic()
        b=run_tasks(tasks(work,exe,"timing"),work,art,evidence)
        timing_seconds=time.monotonic()-t
        evidence.complete()
        phase(5)
        report=summarize(a+b)
        write(art/"calibration-games.json",{"pairs":a+b})
        write(art/"calibration-report.json",{"cells":report,"sanity_block_seconds":sanity_seconds,
            "timing_block_seconds":timing_seconds,"observed_timed_pairs_per_hour":18*3600/timing_seconds,
            "representative_main_opening_rate":False,"main_match_admitted":False})
        summary={"schema":"jass.cls_g0_strength_calibration.v1","terminal":TERMINAL,"state":"completed",
            "classification":"TECHNICAL_CALIBRATION_ONLY","scientific_verdict":None,
            "frozen_g0_verdict":"FAIL","models":MODEL_SHA,"calibration_games":MAX_GAMES,
            "cross_model_games":0,"cells":report,"timing_block_seconds":timing_seconds,
            "observed_timed_pairs_per_hour":18*3600/timing_seconds,
            "main_match_admitted":False,"main_sizing_finalized":False,
            "next_stage":"FREEZE_INDEPENDENT_MAIN_OPENINGS_AND_STATISTICAL_CONTRACT",
            "alpha_spent":0,"promotions":0,"bakes":0,"fits":0,
            "promotion_authorized":False,"bake_authorized":False,
            "actual_side_effects":evidence.value["actual_side_effects"]}
        atomic_json(art/"scientific-summary.json",summary)
        write(art/"manifest.json",{"models":MODEL_SHA,"calibration_only":True,"main_match_admitted":False,
            "output_sha256":{p.name:sha(p) for p in art.iterdir() if p.is_file() and p.name in
                ("calibration-games.json","calibration-report.json","runtime-identity.json","calibration-openings.json")}})
        (art/"RESULTS.md").write_text("# G0 strength validation: calibration only\n\n"
            "44 same-model games. No HIER/CURRICULUM comparison, inference, promotion or G0 retry.\n\n"
            +json.dumps(summary,indent=2,sort_keys=True)+"\n",encoding="utf-8")
        evidence.complete()
        evidence.finish()
        return 0
    except BaseException as exc:
        evidence.fail(exc)
        raise


if __name__ == "__main__":
    def terminate(signum, frame):
        raise KeyboardInterrupt("TERMINATED")
    signal.signal(signal.SIGTERM,terminate)
    raise SystemExit(main())
