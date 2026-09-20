#!/usr/bin/env python3
"""Bounded selected-candidate G0 case study, not candidate rescue or promotion."""
from __future__ import annotations
import argparse
from collections import Counter
import csv
import gzip
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import signal
import statistics
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
CAL_JOB = "cpx62-2066-l3-cls-g0-strength-calibration-rehearsal-v1"
CAL_ATTEMPT = "20260920T082643Z-426b9b4b"
CAL_CODE = "426b9b4b7eb4f52b95636610a8f3b051dfe31f86"
CAL_RECEIPT = "4b1a5e0c3829b154392f09ceead987e1013ff256a011b79c9ae0c9f4f8549884"
SEL_JOB = "home-1651-l3-scan-ceiling-selection-v1"
SEL_ATTEMPT = "20260829T133348Z-28e12fba"
SEL_CODE = "28e12fba0ead14def244ffc442b15937f65edc0e"
COHORT_SHA = "478abc0fe2fe1fcd8c2157f532ba796745c645ff4f03dac8fd21c2ff851f137e"
MODELS = {
    "CURRICULUM": "319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1",
    "HIER": "95bed3ac9fac4368809609fb1a981ee863401a30ca623fb7bfa3caf7eaddf628",
}
PAIRS = 288
REPRESENTATIVE_OPENINGS = 8
POOL_SIZE = 1024
POOL_SEED = 2026092007
ORDER_SEED = 2026092008
LOSS_ELO = 100
ALPHA = 0.05
SCORE_BOUNDARY = 1 / (1 + 10 ** (LOSS_ELO / 400))
MOVETIME = 0.1
RESPONSE_LIMIT = 0.120
WORKERS = 4
PAIR_TIMEOUT = 180
GAME_TIMEOUT = 60
MAX_PLIES = 160
MAIN_WORK_CAP = 2700
WARM_FEN = "W:W31-50:B1-20"
PHASES = ["authenticate-study", "build-runtime", "seal-openings", "execute-paired-stage", "publish-study"]
READY = "CLS_G0_STRENGTH_MAIN_REHEARSAL_READY_V1"
COMPLETE = "CLS_G0_STRENGTH_MAIN_COMPLETE_V1"


def helpers():
    from jobs.tools import cls_g0_strength_calibration
    return cls_g0_strength_calibration


def need(ok: bool, reason: str) -> None:
    if not ok:
        raise ValueError(reason)


def sha(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def read(p: Path) -> dict:
    need(p.is_file() and not p.is_symlink(), "REGULAR_JSON_REQUIRED")
    value = json.loads(p.read_text())
    need(isinstance(value, dict), "JSON_OBJECT_REQUIRED")
    return value


def digest(value) -> str:
    return hashlib.sha256((json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)+"\n").encode()).hexdigest()


def write(p: Path, value: dict, replace: bool = False) -> None:
    need(not p.is_symlink() and (replace or not p.exists()), "NO_CLOBBER")
    temp = p.with_name(p.name+".tmp")
    with temp.open("x") as f:
        json.dump(value, f, sort_keys=True, indent=2, allow_nan=False)
        f.write("\n")
    temp.replace(p)


def fen_identity(fen: str) -> str:
    """Same rotate180+colour-exchange identity as tb_frontier_symmetry_dedup."""
    parts = fen.split(":")
    need(len(parts) == 3 and parts[0] in ("W", "B"), "FEN_SHAPE")
    boards = [0, 0, 0, 0]
    occupied = set()
    for part, colour, offset in ((parts[1], "W", 0), (parts[2], "B", 2)):
        need(part.startswith(colour), "FEN_COLOUR")
        for token in filter(None, part[1:].split(",")):
            king = token.startswith("K")
            token = token[1:] if king else token
            nums = token.split("-")
            need(len(nums) in (1, 2) and all(n.isdigit() for n in nums), "FEN_SQUARE")
            low, high = int(nums[0]), int(nums[-1])
            need(1 <= low <= high <= 50, "FEN_RANGE")
            for sq in range(low, high+1):
                need(sq not in occupied, "FEN_OVERLAP")
                occupied.add(sq)
                boards[offset+int(king)] |= 1 << (sq-1)
    stm = int(parts[0] == "B")
    def fmt(b, s):
        return ":".join(f"{v:013x}" for v in b)+f":{s}"
    def rot(v):
        return sum(1 << (49-i) for i in range(50) if v & (1 << i))
    symmetric = [rot(boards[i]) for i in (2, 3, 0, 1)]
    return min(fmt(boards, stm), fmt(symmetric, 1-stm))


def audit_cold(pairs: list[dict]) -> dict:
    need(len(pairs) == 22, "CAL_PAIR_COUNT")
    counts = Counter()
    for pair in pairs:
        if pair["kind"] != "timing":
            continue
        for game in pair["games"]:
            seen = set()
            for q in game["requests"]:
                first = q["side"] not in seen
                seen.add(q["side"])
                counts["requests"] += 1
                if q["wall_seconds"] > .25:
                    counts["over250_first" if first else "over250_later"] += 1
            counts["games"] += 1
    need(counts["games"] == 36, "CAL_TIMED_COUNT")
    return {**counts, "causal_initialization_attribution_proven": False}


def fetch_source(work: Path, label: str, job: str, attempt: str, code: str, names: list[str]):
    from jobs.tools import fetch_result_files as fetch
    prefix = f"r2:jass-data/runs/{job}/{attempt}"
    rclone = os.environ.get("RCLONE_BIN", "rclone")
    inv = fetch.inspect_result_inventory(rclone=rclone, prefix=prefix)
    need(tuple(inv[k] for k in ("job_id", "attempt_id", "code_sha", "result_state", "exit_code")) ==
         (job, attempt, code, "completed", 0), "UPSTREAM_IDENTITY")
    sizes = {i["path"]: int(i["size_bytes"]) for i in inv["files"]}
    need(all(0 < sizes.get("artefacts/"+n, 0) <= 16*1024**2 for n in names), "BOUNDED_SOURCE")
    out = work / label
    auth = fetch.fetch_files(rclone=rclone, prefix=prefix,
        selections=[("artefacts/"+n, n) for n in names], out_dir=out)
    return out, auth


def fetch_study(work: Path):
    cal, a = fetch_source(work, "cal2066", CAL_JOB, CAL_ATTEMPT, CAL_CODE,
        ["calibration-games.json", "scientific-summary.json", "launch-receipt.json"])
    need(sha(cal/"launch-receipt.json") == CAL_RECEIPT, "CAL_RECEIPT")
    summary = read(cal/"scientific-summary.json")
    need(summary.get("terminal") == "CLS_G0_STRENGTH_CALIBRATION_COMPLETE_V1" and
         summary.get("cross_model_games") == 0 and summary.get("models") == MODELS, "CAL_BOUNDARY")
    pairs = read(cal/"calibration-games.json")["pairs"]
    old = audit_cold(pairs)
    exclusion = {fen_identity(fen) for p in pairs for g in p["games"] for fen in g["fens"]}
    sel, b = fetch_source(work, "selection", SEL_JOB, SEL_ATTEMPT, SEL_CODE,
        ["parents.tsv", "selection-report.json"])
    report = read(sel/"selection-report.json")
    need(report.get("cohort_identity_sha256") == COHORT_SHA and report.get("passed") is True,
         "COHORT_IDENTITY")
    need(sha(sel/"parents.tsv") == report.get("parents_tsv_sha256"), "PARENT_TABLE_SHA")
    with (sel/"parents.tsv").open() as f:
        rows = list(csv.DictReader(f, delimiter="\t"))
    need(len(rows) == 2000 and len({r["parent_id"] for r in rows}) == 2000, "DIAGNOSTIC_EXCLUSION_COUNT")
    exclusion.update(r["canonical_fingerprint"] for r in rows)
    exclusion.add(fen_identity(WARM_FEN))
    return exclusion, old, {"calibration": a, "diagnostic_exclusions": b}


def select_openings(lines: list[str], excluded: set[str]) -> dict:
    unique = {}
    for line in lines:
        fen = line.split("#", 1)[0].strip()
        if not fen:
            continue
        fp = fen_identity(fen)
        if fp not in excluded:
            unique.setdefault(fp, fen)
    need(len(unique) >= PAIRS+REPRESENTATIVE_OPENINGS, "INSUFFICIENT_INDEPENDENT_OPENINGS")
    ordered = sorted(unique, key=lambda fp: (digest([ORDER_SEED, fp]), fp))
    chosen = [{"canonical": fp, "fen": unique[fp]} for fp in ordered[:PAIRS+REPRESENTATIVE_OPENINGS]]
    seal = {"schema": "jass.cls_g0_strength_openings.v1", "pool_seed": POOL_SEED,
        "order_seed": ORDER_SEED, "main": chosen[:PAIRS], "representative": chosen[PAIRS:],
        "excluded_count": len(excluded), "exclusion_sha256": digest(sorted(excluded)),
        "eligible_unique_count": len(unique), "score_reads_for_selection": 0,
        "freshness_scope": "starts disjoint from 1651 and all 2066 trajectories; not a training-corpus audit"}
    seal["selection_sha256"] = digest({k: v for k, v in seal.items()})
    return seal


def validate_seal(seal: dict) -> None:
    need(seal["selection_sha256"] == digest({k:v for k,v in seal.items() if k != "selection_sha256"}), "SEAL_HASH")
    need(len(seal["main"]) == PAIRS and len(seal["representative"]) == REPRESENTATIVE_OPENINGS, "SEAL_COUNTS")
    rows = seal["main"] + seal["representative"]
    need(len({r["canonical"] for r in rows}) == len(rows) and
         all(fen_identity(r["fen"]) == r["canonical"] for r in rows), "SEAL_IDENTITIES")
    need(seal["pool_seed"] == POOL_SEED and seal["order_seed"] == ORDER_SEED and
         seal["score_reads_for_selection"] == 0, "SEAL_RECIPE")


def generate_openings(exe: Path, work: Path, excluded: set[str]) -> dict:
    paths = [work/"pool-a.fen", work/"pool-b.fen"]
    for p in paths:
        helpers().command([str(exe), "--gen-opening-pool", str(POOL_SIZE), str(p),
            "8", "32", "20", str(POOL_SEED)], work/(p.stem+".log"), 120,
            env=helpers().worker_env())
    need(paths[0].read_bytes() == paths[1].read_bytes(), "OPENING_REPLAY")
    seal = select_openings(paths[0].read_text().splitlines(), excluded)
    validate_seal(seal)
    return seal


def native_game(s: dict, a_white: bool, counts: dict, save) -> dict:
    from jobs.tools.calibrate_vs_scan import JassEngine, Referee, play_game
    requests, warm = [], []
    class Observed(JassEngine):
        warming = True
        def _read_until(self, predicate, timeout_s=60):
            lines = super()._read_until(predicate, timeout_s=timeout_s)
            need(not lines[-1].startswith("error"), "PROTOCOL_ERROR")
            return lines
        def go_verbose(self, depth=None, movetime=None):
            counts["searches_started"] += 1
            save()
            t = time.monotonic()
            move, lines = super().go_verbose(depth=depth, movetime=movetime)
            elapsed = time.monotonic()-t
            fields = {k:int(v) for k,v in re.findall(r"\b([A-Za-z][A-Za-z0-9_]*)=(-?\d+)\b", lines[-1])}
            need({"nodes", "depth", "evalcalls"} <= fields.keys(), "TELEMETRY_MISSING")
            q = {"side": self.label, "nodes": fields["nodes"], "depth": fields["depth"],
                "eval_calls": fields["evalcalls"], "wall_seconds": elapsed,
                "move": None if move is None else move.jass_apply_str()}
            (warm if self.warming else requests).append(q)
            if not self.warming:
                need(elapsed <= RESPONSE_LIMIT, "WARM_MATCH_RESPONSE_OVERRUN")
            return move, lines
    class StrictReferee(Referee):
        def apply_move(self, move):
            need(super().apply_move(move), "ILLEGAL_MOVE")
            return True
    opened = []
    try:
        for label, model in (("A", s["model_a"]), ("B", s["model_b"])):
            eng = Observed(s["exe"], label=label, pattern_path=model,
                           enforce_no_book=True, search_params=None, threads=1)
            opened.append(eng)
            eng.new_game()
            eng.set_position_fen(WARM_FEN)
            eng.go(depth=1)
            eng.warming = False
        opened.append(StrictReferee(s["exe"]))
        a, b, ref = opened
        counts["games_started"] += 1
        save()
        start = time.monotonic()
        result = play_game(a if a_white else b, b if a_white else a, ref, s["opening"],
            depth=None, movetime=MOVETIME, max_plies=MAX_PLIES, game_timeout_s=GAME_TIMEOUT)
        if result.reason == "ply cap" and not ref.has_legal_moves():
            result.outcome = "L" if result.fens[-1].startswith("W") else "W"
            result.reason = "no legal move from cap-terminal"
        score = .5 if result.outcome == "D" else float((result.outcome == "W") == a_white)
        row = {"opening": s["opening"], "a_is_white": a_white, "outcome": result.outcome,
            "score_a": score, "reason": result.reason, "plies": result.plies,
            "fens": result.fens, "moves": result.moves, "requests": requests,
            "warmup_requests": warm, "game_wall_seconds": time.monotonic()-start}
        helpers().validate_game(row)
        need(len(warm) == 2 and {q["side"] for q in warm} == {"A", "B"}, "WARMUP_COVERAGE")
        return row
    finally:
        for eng in reversed(opened):
            eng.close()


def worker(path: Path) -> None:
    s = read(path)
    need(s["mode"] in ("rehearsal", "production"), "WORKER_MODE")
    expected = (s["arm_a"], s["arm_b"])
    need(expected in (("CURRICULUM", "CURRICULUM"), ("HIER", "HIER")) if s["mode"] == "rehearsal"
         else expected == ("HIER", "CURRICULUM"), "WORKER_ARMS")
    for role in ("a", "b"):
        need(sha(Path(s["model_"+role])) == MODELS[s["arm_"+role]], "MODEL_IDENTITY")
    counts = {"games_started": 0, "searches_started": 0}
    def save():
        write(Path(s["counts"]), counts, replace=True)
    save()
    games = [native_game(s, colour, counts, save) for colour in (True, False)]
    for role in ("a", "b"):
        need(sha(Path(s["model_"+role])) == MODELS[s["arm_"+role]], "MODEL_MUTATION")
    write(Path(s["output"]), {"task_id": s["task_id"], "opening": s["opening"],
        "arm_a": s["arm_a"], "arm_b": s["arm_b"], "games": games})


def make_tasks(work: Path, exe: Path, seal: dict, mode: str) -> list[dict]:
    result = []
    rows = seal["representative"] if mode == "rehearsal" else seal["main"]
    arms = [(a,a) for a in MODELS] if mode == "rehearsal" else [("HIER", "CURRICULUM")]
    for i, row in enumerate(rows):
        for a,b in arms:
            key = f"pair-{i:04d}-{a}"
            result.append({"task_id": key, "mode": mode, "opening": row["fen"],
                "exe": str(exe), "arm_a": a, "arm_b": b,
                "model_a": str(work/(a+".pjtw")), "model_b": str(work/(b+".pjtw")),
                "counts": str(work/(key+".counts.json")), "output": str(work/(key+".json"))})
    return result


def run_tasks(items: list[dict], work: Path, art: Path, evidence) -> list[dict]:
    active, index = {}, 0
    def progress():
        counts = [read(Path(s["counts"])) for s in items if Path(s["counts"]).exists()]
        totals = {"strength_games": sum(c["games_started"] for c in counts),
                  "new_jass_searches": sum(c["searches_started"] for c in counts)}
        need(totals["strength_games"] <= len(items)*2 and
             totals["new_jass_searches"] <= len(items)*2*(MAX_PLIES+2), "EFFECT_CEILING")
        for k,v in totals.items():
            old = evidence.value["actual_side_effects"][k]
            if v > old:
                evidence.record_effect(k, v-old)
        write(art/"progress.json", {"stage": evidence.value["phase"], "pairs_planned": len(items),
              "pairs_completed": sum(Path(s["output"]).exists() for s in items), **totals}, replace=True)
    try:
        while active or index < len(items):
            while len(active) < WORKERS and index < len(items):
                s = items[index]
                index += 1
                pth = work/(s["task_id"]+".spec.json")
                write(pth, s)
                log = (work/(s["task_id"]+".log")).open("xb")
                p = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "--worker", str(pth)],
                    cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, start_new_session=True, env=helpers().worker_env())
                active[p.pid] = (p, log, time.monotonic())
            for pid,(p,log,t) in list(active.items()):
                need(time.monotonic()-t <= PAIR_TIMEOUT, "PAIR_TIMEOUT")
                if p.poll() is not None:
                    rc = p.returncode
                    log.close()
                    helpers().kill_group(p)
                    del active[pid]
                    need(rc == 0, "MATCH_WORKER_FAILED")
            progress()
            if active:
                time.sleep(1)
        output = [read(Path(s["output"])) for s in items]
        validate_pairs(output, items)
        return output
    finally:
        for p,log,_ in active.values():
            helpers().kill_group(p)
            log.close()
        progress()


def validate_pairs(rows: list[dict], tasks: list[dict]) -> None:
    need(len(rows) == len(tasks) > 0, "PAIRED_COUNT")
    for row, task in zip(rows, tasks):
        need(all(row[k] == task[k] for k in ("task_id", "opening", "arm_a", "arm_b")), "PAIRED_IDENTITY")
        need(len(row["games"]) == 2 and [g["a_is_white"] for g in row["games"]] == [True, False], "PAIRED_COLOURS")
        for g in row["games"]:
            need(g["opening"] == task["opening"], "GAME_START")
            helpers().validate_game(g)
            need(all(q["wall_seconds"] <= RESPONSE_LIMIT for q in g["requests"]), "CADENCE_INVALID")


def analyze_main(rows: list[dict]) -> dict:
    need(len(rows) == PAIRS and len({r["task_id"] for r in rows}) == PAIRS, "MAIN_COMPLETE_REQUIRED")
    need(all((r["arm_a"],r["arm_b"]) == ("HIER","CURRICULUM") for r in rows), "MAIN_CONTRAST")
    low, high, scored = [], [], []
    capped = 0
    for r in rows:
        need(len(r["games"]) == 2 and [g["a_is_white"] for g in r["games"]] == [True, False], "MAIN_PAIR")
        for g in r["games"]:
            need(g["score_a"] in (0, .5, 1), "MAIN_SCORE")
        capped += sum(g["reason"] == "ply cap" for g in r["games"])
        low.append(sum(0 if g["reason"] == "ply cap" else g["score_a"] for g in r["games"])/2)
        high.append(sum(1 if g["reason"] == "ply cap" else g["score_a"] for g in r["games"])/2)
        scored.append(sum(g["score_a"] for g in r["games"])/2)
    radius = math.sqrt(math.log(2/ALPHA)/(2*PAIRS))
    lo, hi = max(0, statistics.fmean(low)-radius), min(1, statistics.fmean(high)+radius)
    verdict = "SUBSTANTIAL_LOSS_SUPPORTED" if hi < SCORE_BOUNDARY else (
        "SUBSTANTIAL_LOSS_EXCLUDED" if lo > SCORE_BOUNDARY else "INDETERMINATE")
    return {"pairs": PAIRS, "games": 2*PAIRS, "loss_margin_elo": LOSS_ELO,
        "score_boundary": SCORE_BOUNDARY, "simultaneous_confidence": 1-ALPHA,
        "method": "fixed_N_Hoeffding_pair_bounds_with_ply_cap_partial_identification",
        "score_interval": [lo,hi], "hoeffding_radius": radius, "statistical_verdict": verdict,
        "administratively_censored_games": capped, "censored_pair_mean_bounds": [statistics.fmean(low),statistics.fmean(high)],
        "descriptive_half_point_ply_cap_score": statistics.fmean(scored),
        "descriptive_pentanomial_counts": dict(Counter(str(2*x) for x in scored)),
        "no_superiority_or_promotion_claim": True}


def main(*, projected_work_ceiling: int = MAIN_WORK_CAP, expected_selection_sha: str | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--worker", type=Path)
    args = ap.parse_args()
    if args.worker:
        worker(args.worker)
        return 0
    from jobs.tools.launch_runtime_v2 import StageEvidence, atomic_json
    result = Path(os.environ["JASS_RESULT_DIR"])
    art = Path(os.environ["JASS_ARTEFACT_DIR"])
    mode = os.environ["LAUNCH_MODE"]
    need(projected_work_ceiling in (MAIN_WORK_CAP, 3000), "REGISTERED_RESOURCE_CEILING_REQUIRED")
    need(mode in ("rehearsal", "production"), "STAGE_MODE")
    work = result/"work"/"strength-main"
    work.mkdir(parents=True, exist_ok=False)
    art.mkdir(parents=True, exist_ok=True)
    evidence = StageEvidence(art, mode)
    try:
        need(not work.resolve().is_relative_to(ROOT.resolve()) and shutil.disk_usage(work).free >= 3*1024**3, "SCRATCH_BOUNDARY")
        evidence.begin(PHASES[0])
        excluded, cold, auth = fetch_study(work)
        need(helpers().MODEL_SHA == MODELS, "HELPER_MODEL_DRIFT")
        auth["models"] = helpers().fetch_models(work)
        write(art/"source-authentication.json", auth)
        write(art/"calibration-review.json", cold)
        evidence.complete()
        evidence.begin(PHASES[1])
        exe = helpers().build(work)
        runtime = {"binary_sha256": sha(exe), "models": MODELS, "native_source": helpers().BASE_CODE,
            "movetime_ms": 100, "response_limit_ms": 120, "warmup": "startpos_depth1_each_player_then_reset",
            "book": False, "threads": 1, "tt_mb": 16, "egdb_cache_mb": 256, "workers": WORKERS}
        write(art/"runtime-identity.json", runtime)
        evidence.complete()
        evidence.begin(PHASES[2])
        if mode == "rehearsal":
            seal = generate_openings(exe, work, excluded)
        else:
            proof = read(result/"launch-prerequisite.json")
            need(proof.get("verdict") == "FULL_PIPELINE_REHEARSAL_PASS" and proof.get("published_roundtrip") is True, "REAL_REHEARSAL_REQUIRED")
            previous = result/"launch-prerequisite"
            ready = read(previous/"study-report.json")
            need(ready.get("terminal") == READY and ready.get("production_ready") is True and
                 ready.get("cross_model_games") == 0, "MAIN_NOT_ADMITTED")
            need(read(previous/"runtime-identity.json") == runtime, "RUNTIME_ROUNDTRIP")
            seal = read(previous/"opening-freeze.json")
        validate_seal(seal)
        if expected_selection_sha is not None:
            need(seal["selection_sha256"] == expected_selection_sha, "ORIGINAL_2067_SELECTION_DRIFT")
        need(seal["exclusion_sha256"] == digest(sorted(excluded)) and
             all(r["canonical"] not in excluded for r in seal["main"]+seal["representative"]), "EXCLUSION_DRIFT")
        write(art/"opening-freeze.json", seal)
        evidence.complete()
        evidence.begin(PHASES[3])
        tasks = make_tasks(work, exe, seal, mode)
        started = time.monotonic()
        rows = run_tasks(tasks, work, art, evidence)
        elapsed = time.monotonic()-started
        evidence.complete()
        evidence.begin(PHASES[4])
        if mode == "rehearsal":
            trajectory = {fen_identity(f) for r in rows for g in r["games"] for f in g["fens"]}
            overlaps = sum(r["canonical"] in trajectory for r in seal["main"])
            projected = PAIRS*elapsed/len(rows)
            report = {"terminal": READY, "production_ready": overlaps == 0 and projected <= projected_work_ceiling,
                "representative_pairs": len(rows), "representative_games": 2*len(rows), "cross_model_games": 0,
                "main_start_overlap_rehearsal_trajectories": overlaps, "representative_block_seconds": elapsed,
                "projected_main_work_seconds": projected, "main_work_ceiling_seconds": projected_work_ceiling,
                "clock_checks_passed": True, "scientific_verdict": None}
            if not report["production_ready"]:
                report["terminal"] = "CLS_G0_STRENGTH_MAIN_PREPARATION_BLOCKED_V1"
        else:
            report = {"terminal": COMPLETE, "cross_model_games": 2*PAIRS, **analyze_main(rows)}
        report.update(mode=mode, models=MODELS, opening_selection_sha256=seal["selection_sha256"])
        write(art/"study-report.json", report)
        raw = json.dumps({"mode": mode, "pairs": rows}, sort_keys=True, allow_nan=False).encode()
        with (art/"stage-games.json.gz").open("xb") as f:
            with gzip.GzipFile(fileobj=f, mode="wb", mtime=0) as z:
                z.write(raw)
        summary = {"schema": "jass.cls_g0_strength_main.v1", "state": "completed", **report,
            "classification": "TECHNICAL_REPRESENTATIVE_REHEARSAL" if mode == "rehearsal" else "SELECTED_CANDIDATE_CASE_STUDY",
            "scientific_verdict": None if mode == "rehearsal" else report["statistical_verdict"],
            "frozen_g0_verdict": "FAIL", "promotion_authorized": False, "bake_authorized": False,
            "alpha_spent": 0 if mode == "rehearsal" else ALPHA,
            "actual_side_effects": evidence.value["actual_side_effects"],
            "next_stage": "ADMIT_EXACT_MAIN_AFTER_PUBLISHED_REHEARSAL" if mode == "rehearsal" and report["production_ready"] else "INTERPRET_NO_AUTOMATIC_PROMOTION"}
        atomic_json(art/"scientific-summary.json", summary)
        (art/"RESULTS.md").write_text("# Selected HIER/CURRICULUM strength case study\n\n"+json.dumps(summary,indent=2)+"\n")
        write(art/"manifest.json", {"models":MODELS, "selection_sha256":seal["selection_sha256"],
            "output_sha256":{n:sha(art/n) for n in ("stage-games.json.gz","opening-freeze.json","study-report.json")}})
        evidence.complete()
        evidence.finish()
        return 0
    except BaseException as exc:
        evidence.fail(exc)
        raise


if __name__ == "__main__":
    def terminate(signum, frame):
        raise KeyboardInterrupt("TERMINATED")
    signal.signal(signal.SIGTERM, terminate)
    raise SystemExit(main())
