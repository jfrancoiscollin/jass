#!/usr/bin/env python3
"""Execute one sealed phase of the CLS G0 panel admission amendment.

There is deliberately no queueing, retry or promotion path here.  The launch
gate materialises and signs the context first; this stage re-validates that
context immediately before it constructs players or starts a game.
"""
from __future__ import annotations

import csv
import hashlib
import gzip
import json
import math
import multiprocessing as mp
import os
import signal
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from jobs.tools import cls_g0_panel_readiness as ready
from jobs.tools.launch_runtime_v2 import StageEvidence, atomic_json

PHASES = ("authenticate", "build", "seal", "execute", "validate", "publish")
CONTEXT_SCHEMA = "jass.cls_panel_admission_context.v1"
STAGE_SCHEMA = "jass.cls_g0_panel_stage.v1"
OUTPUTS = ("source-authentication.json", "runtime-identity.json", "opening-freeze.json",
           "stage-games.json.gz", "study-report.json", "progress.json", "scientific-summary.json",
           "manifest.json", "RESULTS.md")


def need(ok: bool, reason: str) -> None:
    if not ok:
        raise ValueError(reason)


def canonical(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()


def sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha(path: Path) -> str:
    need(path.is_file() and not path.is_symlink(), "REGULAR_FILE:" + path.name)
    h = hashlib.sha256()
    with path.open("rb") as src:
        for block in iter(lambda: src.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def read_json(path: Path) -> dict:
    need(path.is_file() and not path.is_symlink(), "CONTEXT_REGULAR_FILE")
    value = json.loads(path.read_text(encoding="utf-8"))
    need(isinstance(value, dict), "CONTEXT_OBJECT")
    return value


def load_context(result: Path, *, allow_bound_readiness: bool = False) -> dict:
    """Read the gate-owned admission context and bind every declared input."""
    path = result / "panel-admission-context.json"
    ctx = read_json(path)
    required = {"schema", "phase", "common_plan", "common_plan_sha256", "materialized_spec",
                "materialized_spec_sha256", "profile_sha256", "code_sha", "command",
                "runtime_identity", "opening_selection_sha256", "authenticated_dependencies", "paths"}
    need(ctx.get("schema") == CONTEXT_SCHEMA and required <= set(ctx), "ADMISSION_CONTEXT_SCHEMA")
    need(ctx["phase"] in ("readiness", "local", "wdl"), "ADMISSION_PHASE")
    need(sha_bytes(canonical(ctx["common_plan"])) == ctx["common_plan_sha256"], "COMMON_PLAN_HASH")
    need(sha_bytes(canonical(ctx["materialized_spec"])) == ctx["materialized_spec_sha256"], "MATERIALIZED_SPEC_HASH")
    need(isinstance(ctx["paths"], dict) and isinstance(ctx["runtime_identity"], dict), "ADMISSION_CONTEXT_TYPES")
    for name in ("common_plan", "spec", "profile"):
        value = ctx["paths"].get(name)
        need(isinstance(value, str), "CONTEXT_PATH:" + name)
        p = Path(value)
        need(p.is_file() and not p.is_symlink(), "CONTEXT_PATH_REGULAR:" + name)
    need(sha(Path(ctx["paths"]["profile"])) == ctx["profile_sha256"], "PROFILE_HASH")
    need(ctx["common_plan"] == read_json(Path(ctx["paths"]["common_plan"])), "COMMON_PLAN_PATH_DRIFT")
    need(ctx["materialized_spec"] == read_json(Path(ctx["paths"]["spec"])), "SPEC_PATH_DRIFT")
    need(isinstance(ctx["command"], list) and all(isinstance(x, str) for x in ctx["command"]), "COMMAND_IDENTITY")
    from jobs.tools import cls_g0_panel_gate_v1 as gate
    profile = read_json(Path(ctx["paths"]["profile"]))
    gate.validate_profile(profile); gate.validate_plan(ctx["common_plan"], profile, ctx["profile_sha256"])
    dependencies = {} if ctx["phase"] == "readiness" else {"authenticated_readiness": ctx["authenticated_dependencies"]["authenticated_readiness"]}
    need(ctx["materialized_spec"] == gate.materialize(ctx["common_plan"], ctx["phase"], dependencies), "CONTEXT_CLOSED_PROJECTION")
    need(ctx["code_sha"] == ctx["common_plan"]["code_sha"] and ctx["command"] == profile["command"] and
         ctx["runtime_identity"] == ctx["common_plan"]["runtime_identity"], "CONTEXT_COMMON_IDENTITY")
    selection = ctx["opening_selection_sha256"]
    if ctx["phase"] == "readiness":
        need(selection is None or (allow_bound_readiness and isinstance(selection, str) and len(selection) == 64), "READINESS_SELECTION_MUST_BE_UNBOUND")
    else:
        need(isinstance(selection, str) and len(selection) == 64, "MAIN_SELECTION_REQUIRED")
    return ctx


def authenticate_dependencies(ctx: dict) -> dict:
    """Fail closed on the immutable 2072 admission and typed late inputs."""
    dep = ctx["authenticated_dependencies"]
    need(isinstance(dep, dict), "DEPENDENCY_OBJECT")
    audit = dep.get("authenticated_readiness")
    if ctx["phase"] == "readiness":
        # The gate's R2 reader may retain a full authenticated readback.  When
        # it does, parse it again rather than trusting a summary projection.
        if isinstance(audit, dict) and ("readback" in audit or "summary" in audit):
            ready.require_authenticated_audit_2072(audit)
        else:
            need(isinstance(audit, dict), "AUDIT_2072_DEPENDENCY")
            need((audit.get("job_id"), audit.get("attempt_id"), audit.get("launch_receipt_sha256")) ==
                 (ready.AUDIT_2072_JOB, ready.AUDIT_2072_ATTEMPT, ready.AUDIT_2072_LAUNCH_RECEIPT), "AUDIT_2072_PIN")
    else:
        required = ("job_id", "attempt_id", "launch_receipt_sha256", "publisher_manifest_sha256", "opening_selection_sha256")
        need(isinstance(audit, dict) and all(isinstance(audit.get(k), str) and audit[k] for k in required), "READINESS_TYPED_DEPENDENCY")
        need(audit["opening_selection_sha256"] == ctx["opening_selection_sha256"], "READINESS_OPENING_BINDING")
    if ctx["phase"] == "wdl":
        local = dep.get("local_technical_completion")
        need(isinstance(local, dict), "WDL_LOCAL_TECHNICAL_DEPENDENCY")
        need(all(isinstance(local.get(k), str) and local[k] for k in
                 ("prebound_local_job_id", "prebound_local_admission_sha256", "job_id", "attempt_id", "launch_receipt_sha256")), "WDL_LOCAL_TYPED_DEPENDENCY")
        need(local.get("scientific_verdict") in (None, "null"), "WDL_LOCAL_TECHNICAL_ONLY")
    return {"schema": "jass.cls_panel_source_authentication.v1", "phase": ctx["phase"],
            "authenticated_dependencies": dep, "audit_2072_pinned": ctx["phase"] == "readiness"}


def _trajectory_fens(value: object) -> set[str]:
    """Read declared trajectory/start fields only; never recurse into score data."""
    out: set[str] = set()
    if isinstance(value, str):
        try:
            ready.canonical_identity(value)
        except ValueError:
            pass
        else:
            out.add(value)
    elif isinstance(value, dict):
        for key in ("opening", "fens"):
            if key in value: out.update(_trajectory_fens(value[key]))
        for key in ("pairs", "games"):
            if key in value: out.update(_trajectory_fens(value[key]))
    elif isinstance(value, list):
        for item in value: out.update(_trajectory_fens(item))
    return out


def _fetch_2072(work: Path) -> dict:
    """Freshly fetch the exact published audit receipt and raw-audit payload."""
    from jobs.tools import fetch_result_files as transport
    prefix = f"r2:jass-data/runs/{ready.AUDIT_2072_JOB}/{ready.AUDIT_2072_ATTEMPT}"
    inv = transport.inspect_result_inventory(rclone=os.environ.get("RCLONE_BIN", "rclone"), prefix=prefix)
    need(tuple(inv.get(k) for k in ("job_id", "attempt_id", "code_sha", "result_state", "exit_code")) ==
         (ready.AUDIT_2072_JOB, ready.AUDIT_2072_ATTEMPT, ready.AUDIT_2072_CODE, "completed", 0), "AUDIT_2072_SOURCE_DRIFT")
    names = ("launch-receipt.json", "historical-2069-raw-audit.json", "scientific-summary.json", "execution-evidence.json")
    files = {x.get("path"): x for x in inv.get("files", [])}
    need(all("artefacts/" + n in files for n in names), "AUDIT_2072_ARTIFACT_MISSING")
    out = work / "audit-2072"
    proof = transport.fetch_files(rclone=os.environ.get("RCLONE_BIN", "rclone"), prefix=prefix, out_dir=out,
                                  selections=[("artefacts/" + n, n) for n in names])
    need(all(sha(out / n) == files["artefacts/" + n]["sha256"] for n in names), "AUDIT_2072_CHECKSUM")
    need(sha(out / "launch-receipt.json") == ready.AUDIT_2072_LAUNCH_RECEIPT, "AUDIT_2072_RECEIPT_PIN")
    raw, summary = read_json(out / "historical-2069-raw-audit.json"), read_json(out / "scientific-summary.json")
    need(raw.get("passed") is True and raw.get("historical_requests_verified") == 62005, "AUDIT_2072_RAW")
    need(summary.get("terminal") == ready.AUDIT_2072_TERMINAL and summary.get("historical_2069_raw_audit_passed") is True, "AUDIT_2072_SUMMARY")
    return {"inventory": {k: inv[k] for k in ("job_id", "attempt_id", "code_sha", "result_state", "exit_code")}, "proof": proof,
            "receipt_sha256": sha(out / "launch-receipt.json")}


def authenticated_sources(work: Path, ctx: dict) -> tuple[dict, set[str], dict[str, Path]]:
    """Fetch frozen R2 objects, verify inventories/checksums, and derive exclusions.

    This reuses the independent audit transport rather than trusting a gate map.
    The parser only visits trajectory/start FEN fields; it deliberately never
    reads score, verdict, or evaluation fields for opening selection.
    """
    from jobs.tools import cls_g0_panel_audit_stage as historical
    contract = historical.get_contract()
    audit_2072 = _fetch_2072(work)
    fetched, proof = historical.authenticate(work / "audited", contract, lambda _x: None)
    extra = {}
    for label in ("selection1651", "calibration2066", "rehearsal2067", "rehearsal2068"):
        source = contract["sources"][label]
        extra[label], extra_proof = historical.fetch_source(work / "audited", label, source, [source["artifact"]] + (["selection-report.json"] if label == "selection1651" else []))
        proof[label] = extra_proof
    forbidden = {ready.canonical_identity(ready.WARM_FEN)}
    source_counts = {}
    # Only the five preregistered historical trajectories contribute positions.
    for label, expected_games in (("calibration2066", 44), ("rehearsal2067", 32), ("rehearsal2068", 32), ("historical_match", 576)):
        directory = fetched[label] if label in fetched else extra[label]
        name = "stage-games.json.gz" if label == "historical_match" else contract["sources"][label]["artifact"]
        payload = historical.audit.read(directory / name)
        pairs = payload.get("pairs", [])
        need(len(pairs) * 2 == expected_games and all(len(row.get("games", [])) == 2 for row in pairs), "HISTORICAL_GAME_COVERAGE:" + label)
        positions = set()
        for pair in pairs:
            for game in pair["games"]:
                fens = game.get("fens")
                need(isinstance(fens, list) and len(fens) == game.get("plies", -1) + 1 and fens[0] == game.get("opening"),
                     "HISTORICAL_TRAJECTORY_MISSING:" + label)
                positions.update(ready.canonical_identity(fen) for fen in fens)
        need(positions, "HISTORICAL_EXCLUSION_EMPTY:" + label)
        forbidden.update(positions); source_counts[label] = {"games": expected_games, "positions": len(positions)}
    old_seal = historical.audit.read(fetched["historical_match"] / "opening-freeze.json")
    starts = old_seal.get("main", []) + old_seal.get("representative", [])
    need(len(old_seal.get("main", [])) == 288 and len(old_seal.get("representative", [])) == 8, "HISTORICAL_START_COVERAGE")
    forbidden.update(ready.canonical_identity(row["fen"]) for row in starts)
    selection = extra["selection1651"]
    report = historical.audit.read(selection / "selection-report.json")
    need(report.get("passed") is True and report.get("cohort_identity_sha256") == contract["sources"]["selection1651"]["cohort_identity_sha256"] and
         report.get("parents_tsv_sha256") == sha(selection / "parents.tsv"), "SELECTION1651_IDENTITY")
    with (selection / "parents.tsv").open(encoding="utf-8", newline="") as src:
        parents = list(csv.DictReader(src, delimiter="\t"))
    need(len(parents) == 2000 and len({r["parent_id"] for r in parents}) == 2000, "SELECTION1651_PARENT_COUNT")
    import re
    need(all(re.fullmatch(r"[0-9a-f]{13}(?::[0-9a-f]{13}){3}:[01]", r["canonical_fingerprint"]) for r in parents), "SELECTION1651_CANONICALS")
    forbidden.update(r["canonical_fingerprint"] for r in parents)
    model_paths = {arm: work / "audited" / (arm + ".pjtw") for arm in ready.MODELS}
    need(all(p.is_file() and sha(p) == ready.MODELS[arm] for arm, p in model_paths.items()), "HISTORICAL_MODEL_BYTES")
    return {"schema": "jass.cls_panel_source_authentication.v2", "audit_2072": audit_2072,
            "historical_transport": proof, "trajectory_coverage": source_counts, "historical_start_count": len(starts), "parent_count": len(parents), "exclusion_count": len(forbidden), "selection_reads_scores": False}, forbidden, model_paths


def native_command(argv: list[str], log: Path, timeout: int, *, stdin: bytes | None = None) -> bytes:
    need(not log.exists() and not log.is_symlink(), "NATIVE_LOG_NO_CLOBBER")
    with log.open("xb") as output:
        process = subprocess.Popen(argv, cwd=ROOT, env=worker_env(), stdin=subprocess.PIPE if stdin is not None else subprocess.DEVNULL,
            stdout=output, stderr=subprocess.STDOUT, start_new_session=os.name != "nt")
        try:
            process.communicate(stdin, timeout=timeout)
            need(process.returncode == 0, "NATIVE_COMMAND_FAILED:" + log.name)
        finally:
            if os.name != "nt":
                try: os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError: pass
            elif process.poll() is None: process.kill()
            process.wait(timeout=10)
    need(log.stat().st_size <= 64 * 1024**2, "NATIVE_LOG_BOUND")
    return log.read_bytes()


def verify_native(ctx: dict, work: Path) -> tuple[Path, dict]:
    """Build only the frozen native tree and bind the binary byte identity."""
    anchor = ready.NATIVE_SOURCE_ANCHOR
    tree = subprocess.run(["git", "-C", str(ROOT), "diff", "--quiet", anchor, "HEAD", "--", "src", "pattern_jass", "CMakeLists.txt"], timeout=30).returncode
    need(tree == 0, "NATIVE_CONTINUITY_DRIFT")
    need(Path("/root/egdb_extracted/app").is_dir() and Path("/root/egdb_intl").is_dir(), "REAL_EGDB_REQUIRED")
    build = work / "build"; build.mkdir(parents=True, exist_ok=False)
    flags = ["-DCMAKE_BUILD_TYPE=Release", "-DJASS_EGDB=ON", "-DJASS_EGDB_SRC_DIR=/root/egdb_intl",
             "-DJASS_ENDGAME_FEATURES=ON", "-DJASS_KING_MOBILITY=ON", "-DJASS_SCAN_PARITY=ON",
             "-DJASS_TEMPO_STAGE=ON", "-DJASS_TIME_BREAKDOWN=OFF"]
    expected_flags = ctx["runtime_identity"].get("cmake_flags")
    if expected_flags is not None:
        need(expected_flags == flags, "FROZEN_NATIVE_FLAGS")
    for args, timeout in ((["/usr/bin/cmake", "-S", str(ROOT), "-B", str(build), "-G", "Unix Makefiles", *flags], 180),
                          (["cmake", "--build", str(build), "--target", "jass", "-j", "4"], 480)):
        native_command(args, work / ("configure.log" if "-S" in args else "build.log"), timeout)
    exe = build / "jass"; need(exe.is_file(), "NATIVE_BINARY_MISSING")
    native_command([str(exe), "--egdb-selfcheck", "/root/egdb_extracted/app", "8", "256"], work / "egdb-selfcheck.log", 120)
    for arm in ready.MODELS:
        model = work / "audited" / (arm + ".pjtw")
        need(sha(model) == ready.MODELS[arm], "NATIVE_MODEL_PIN")
        output = native_command([str(exe), "--no-book", "--pattern", str(model)], work / ("load-" + arm + ".log"), 60, stdin=b"hello\nquit\n")
        need(any(line.startswith(b"ready") for line in output.splitlines()), "NATIVE_MODEL_LOAD")
    actual = sha(exe)
    expected = ctx["runtime_identity"].get("binary_sha256")
    if expected is not None:
        need(actual == expected, "NATIVE_BINARY_IDENTITY")
    identity = {"schema": "jass.cls_panel_runtime_identity.v1", "native_source_anchor": anchor,
                "binary_sha256": actual, "native_egdb_selfcheck_exit_code": 0, "cmake_flags": flags, "tt_mb": 16, "egdb_cache_mb": 256, "workers": 4,
                "movetime_ms": 100, "response_ceiling_ms": 120, "book": False,
                "models": ready.MODELS, "context_runtime_identity": ctx["runtime_identity"]}
    return exe, identity


def _forbidden(ctx: dict) -> set[str]:
    values = set(ctx.get("_historical_forbidden", []))
    need(len(values) > 1, "EXCLUSION_SET_MISSING")
    return values


def generate_and_seal(exe: Path, ctx: dict, art: Path) -> dict:
    if ctx["phase"] != "readiness":
        seal = read_json(Path(ctx["paths"]["opening_seal"]))
        ready.validate_seal(seal, _forbidden(ctx))
        need(seal["selection_sha256"] == ctx["opening_selection_sha256"], "OPENING_SELECTION_BINDING")
        return seal
    raw = []
    for index in range(2):
        out = art / f"opening-pool-{index}.txt"
        native_command([str(exe), "--gen-opening-pool", str(ready.POOL_SIZE), str(out), "8", "32", "20", str(ready.POOL_SEED)], art / f"opening-pool-{index}.log", 180)
        need(out.is_file(), "OPENING_POOL_GENERATION")
        raw.append(out.read_bytes())
    seal = ready.seal_openings(raw[0], raw[1], _forbidden(ctx))
    return seal


def bind_readiness_selection(result: Path, ctx: dict, seal: dict) -> None:
    """Atomically bind the real score-blind seal before any player is created."""
    need(ctx["phase"] == "readiness" and ctx["opening_selection_sha256"] is None, "READINESS_BINDING_STATE")
    ctx["opening_selection_sha256"] = seal["selection_sha256"]
    published = {k: v for k, v in ctx.items() if not k.startswith("_")}
    atomic_json(result / "panel-admission-context.json", published)
    rebound = load_context(result, allow_bound_readiness=True)
    need(rebound["opening_selection_sha256"] == seal["selection_sha256"], "READINESS_BINDING_DRIFT")


def model_paths(ctx: dict, work: Path, authenticated: dict[str, Path] | None = None) -> dict[str, Path]:
    if authenticated is not None:
        return authenticated
    supplied = ctx["paths"].get("models") or ctx["materialized_spec"].get("models")
    need(isinstance(supplied, dict), "MODEL_PATHS_MISSING")
    result = {}
    for arm, expected in ready.MODELS.items():
        p = Path(supplied.get(arm, "")); need(p.is_file() and not p.is_symlink() and sha(p) == expected, "MODEL_IDENTITY:" + arm)
        local = work / (arm + ".pjtw"); shutil.copyfile(p, local); need(sha(local) == expected, "MODEL_COPY_IDENTITY:" + arm)
        result[arm] = local
    return result


def tasks_for(phase: str, work: Path, exe: Path, seal: dict, forbidden: set[str]) -> list[dict]:
    if phase == "readiness":
        return ready.make_readiness_tasks(work, exe, seal, forbidden)
    arm = "LOCAL" if phase == "local" else "WDL"
    return [{"task_id": f"{phase}-{i:03d}", "mode": "production", "kind": "timed", "opening": row["fen"],
             "arm_a": arm, "arm_b": "CURRICULUM", "exe": str(exe),
             "model_a": str(work / (arm + ".pjtw")), "model_b": str(work / "CURRICULUM.pjtw")}
            for i, row in enumerate(seal["main"])]


def worker_env() -> dict:
    env = {k: os.environ[k] for k in ("PATH", "HOME", "LANG", "LC_ALL", "LD_LIBRARY_PATH", "SYSTEMROOT", "WINDIR") if k in os.environ}
    env.update(JASS_EGDB_PATH="/root/egdb_extracted/app", JASS_EGDB_CACHE_MB="256", OMP_NUM_THREADS="1",
               OPENBLAS_NUM_THREADS="1", MKL_NUM_THREADS="1", PYTHONDONTWRITEBYTECODE="1")
    return env


def durable_counts(path: Path, counts: dict) -> None:
    atomic_json(path, counts)
    with path.open("rb+") as src: os.fsync(src.fileno())


def _pair_worker(task: dict) -> None:
    if os.name != "nt": os.setsid()
    env = worker_env(); os.environ.clear(); os.environ.update(env)
    counts = {"strength_games": 0, "new_jass_searches": 0}
    path = Path(task["count_file"])
    def persist(): durable_counts(path, counts)
    persist()
    try:
        row = ready.run_pair(task, counts, persist)
        atomic_json(Path(task["result_file"]), {"state": "completed", "row": row, "counts": counts})
    except BaseException as exc:
        persist()
        atomic_json(Path(task["result_file"]), {"state": "failed", "error_type": type(exc).__name__, "counts": counts})


def execute(tasks: list[dict], phase: str, art: Path, evidence: StageEvidence,
            *, worker=None, pair_timeout: float = ready.PAIR_TIMEOUT) -> list[dict]:
    limits = {"readiness": (56, 9072, 1800), "local": (576, 93312, 3600), "wdl": (576, 93312, 3600)}[phase]
    context = mp.get_context("spawn")
    started, last_progress = time.monotonic(), 0.
    work = art / "worker-counts"; work.mkdir(exist_ok=False)
    counts_files, results = {}, []
    need(len({t["task_id"] for t in tasks}) == len(tasks), "DUPLICATE_TASK")
    def persist():
        nonlocal last_progress
        counts = {"strength_games": 0, "new_jass_searches": 0}
        for path in counts_files.values():
            if path.exists():
                value = read_json(path)
                need(set(value) == set(counts) and all(type(x) is int and x >= 0 for x in value.values()), "WORKER_COUNTERS")
                need(value["strength_games"] <= 2 and value["new_jass_searches"] <= 324, "PAIR_EFFECT_LIMIT")
                for key in counts: counts[key] += value[key]
        need(counts["strength_games"] <= limits[0] and counts["new_jass_searches"] <= limits[1], "CUMULATIVE_EFFECT_LIMIT")
        evidence.value["actual_side_effects"].update(counts); evidence.save()
        if time.monotonic() - last_progress >= 30:
            atomic_json(art / "progress.json", {"phase": phase, "elapsed_seconds": time.monotonic()-started,
                "completed_pairs": len(results), "actual_side_effects": evidence.value["actual_side_effects"]})
            last_progress = time.monotonic()
    def kill(process):
        if os.name != "nt":
            try: os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError: pass
        elif process.is_alive(): process.terminate()
        process.join(5)
    def block(group):
        pending, active = list(group), {}
        try:
            while pending or active:
                # Observe all completions/failures before issuing any further work.
                for task_id, (process, since, out) in list(active.items()):
                    need(time.monotonic() - since <= pair_timeout, "PAIR_TIMEOUT")
                    if process.is_alive(): continue
                    process.join()
                    need(out.is_file(), "WORKER_EXITED_WITHOUT_RESULT")
                    answer = read_json(out)
                    need(answer.get("state") == "completed" and process.exitcode == 0, "PAIR_WORKER_FAILED")
                    need(answer["row"].get("task_id") == task_id, "WORKER_TASK_IDENTITY")
                    results.append(answer["row"]); kill(process); del active[task_id]
                persist()
                need(time.monotonic() - started < limits[2], "STAGE_TIMEOUT")
                while pending and len(active) < ready.WORKERS:
                    task = pending.pop(0).copy(); task_id = task["task_id"]
                    count = work / (task_id + ".counts.json"); out = work / (task_id + ".result.json")
                    task.update(count_file=str(count), result_file=str(out)); counts_files[task_id] = count
                    durable_counts(count, {"strength_games": 0, "new_jass_searches": 0})
                    process = context.Process(target=worker or _pair_worker, args=(task,))
                    process.start(); active[task_id] = (process, time.monotonic(), out)
                if active: time.sleep(.05)
        finally:
            for process, _, _ in active.values(): kill(process)
            persist()
    block([t for t in tasks if t.get("kind") == "deterministic"])
    timed = time.monotonic(); block([t for t in tasks if t.get("kind") != "deterministic"])
    evidence.value["timed_block_wall_seconds"] = time.monotonic() - timed
    persist()
    return sorted(results, key=lambda row: row["task_id"])


def contrast_report(rows: list[dict], candidate: str) -> dict:
    need(len(rows) == 288 and all(len(r.get("games", [])) == 2 for r in rows), "CONTRAST_PAIR_COVERAGE")
    need(candidate in ("LOCAL", "WDL") and len({r.get("task_id") for r in rows}) == 288, "CONTRAST_IDENTITIES")
    need(all(r.get("arm_a") == candidate and r.get("arm_b") == "CURRICULUM" and
             [g.get("a_is_white") for g in r["games"]] == [True, False] for r in rows), "CONTRAST_COLOURS")
    lower, upper = [], []
    for row in rows:
        bounds = [(0.0, 1.0) if game["reason"] == "ply cap" else (game["score_a"], game["score_a"])
                  for game in row["games"]]
        lower.append(sum(x[0] for x in bounds) / 2); upper.append(sum(x[1] for x in bounds) / 2)
    radius = math.sqrt(math.log(2 / .025) / (2 * 288))
    interval = [max(0., sum(lower) / 288 - radius), min(1., sum(upper) / 288 + radius)]
    boundary = 1 / (1 + 10 ** (100 / 400))
    verdict = "SUBSTANTIAL_LOSS_SUPPORTED" if interval[1] < boundary else ("SUBSTANTIAL_LOSS_EXCLUDED" if interval[0] > boundary else "INDETERMINATE")
    return {"pairs": 288, "games": 576, "candidate": candidate, "pair_lower_mean": sum(lower)/288,
            "pair_upper_mean": sum(upper)/288, "hoeffding_radius": radius, "interval": interval,
            "logistic_100_elo_boundary": boundary, "contrast_verdict": verdict,
            "analysis": "frozen_independent_paired_censoring_hoeffding_bonferroni"}


def validate(phase: str, rows: list[dict], tasks: list[dict], seal: dict, started: float) -> dict:
    if phase == "readiness":
        report = ready.validate_readiness_rows(rows, tasks, timed_block_wall_seconds=max(.001, started))
        ready.validate_freshness(seal, report)
        return report
    need(len(rows) == len(tasks) == 288 and all(len(r.get("games", [])) == 2 for r in rows), "MAIN_PAIR_COVERAGE")
    need(len({row["task_id"] for row in rows}) == 288, "MAIN_DUPLICATE_PAIR")
    for row, task in zip(rows, tasks):
        need([g.get("a_is_white") for g in row["games"]] == [True, False], "MAIN_COLOUR_BALANCE")
        need(row.get("opening") == task["opening"] and 0 < row.get("pair_wall_seconds", 0) <= ready.PAIR_TIMEOUT, "MAIN_PAIR_WALL_OR_OPENING")
        need(row["task_id"] == task["task_id"] and row["arm_a"] == task["arm_a"] and row["arm_b"] == "CURRICULUM", "MAIN_PAIR_IDENTITY")
        for game in row["games"]: ready.validate_game(game, task)
    if phase == "local":
        return {"pairs": 288, "games": 576, "candidate": "LOCAL", "analysis": "technical_only_no_scientific_inference"}
    return contrast_report(rows, "WDL")


def joint_readout(ctx: dict, wdl_report: dict) -> dict:
    """Open LOCAL outcomes only after the WDL cell completes validation."""
    path = Path(ctx["paths"].get("local_stage_games", ""))
    need(path.is_file() and not path.is_symlink(), "LOCAL_GAMES_FOR_JOINT_READOUT")
    need(sha(path) == ctx["authenticated_dependencies"]["local_technical_completion"]["stage_games_sha256"], "LOCAL_GAMES_CHANGED")
    from jobs.tools.cls_g0_panel_raw_audit import read as bounded_read
    local = contrast_report(bounded_read(path).get("pairs", []), "LOCAL")
    verdicts = {local["contrast_verdict"], wdl_report["contrast_verdict"]}
    terminal = "G0_PANEL_LARGE_LOSS_DISCORDANCE_REPLICATED_V1" if "SUBSTANTIAL_LOSS_EXCLUDED" in verdicts else ("G0_PANEL_LOSS_CONCORDANT_ON_TWO_CASES_V1" if verdicts == {"SUBSTANTIAL_LOSS_SUPPORTED"} else "G0_PANEL_INDETERMINATE_V1")
    return {"local": local, "wdl": wdl_report, "terminal": terminal}


def put_final_summary(path: Path, value: dict, evidence: StageEvidence) -> None:
    previous = read_json(path)
    expected = {"schema": "jass.launch_progress.v2", "state": "running", "phase": "publish",
                "completed_phases": list(PHASES[:-1]), "scientific_verdict": None,
                "actual_side_effects": evidence.value["actual_side_effects"]}
    need(path == evidence.path.parent / "scientific-summary.json" and all(previous.get(k) == v for k, v in expected.items()), "SUMMARY_OWNERSHIP")
    atomic_json(path, value)


def put_gzip_json(path: Path, value: dict) -> None:
    need(not path.exists() and not path.is_symlink(), "GAMES_NO_CLOBBER")
    with gzip.open(path, "xb") as out:
        out.write(canonical(value))


def run(result: Path, art: Path, *, context: dict | None = None) -> dict:
    ctx = load_context(result) if context is None else context
    work = result / "work" / ("cls-panel-" + ctx["phase"])
    need(not work.resolve().is_relative_to(ROOT.resolve()), "SCRATCH_OUTSIDE_REPO")
    need(shutil.disk_usage(result).free >= 3 * 1024**3, "FREE_DISK_GUARD")
    work.mkdir(parents=True, exist_ok=False); art.mkdir(parents=True, exist_ok=True)
    evidence = StageEvidence(art, os.environ.get("LAUNCH_MODE", "production"))
    try:
        atomic_json(art / "progress.json", {"phase": "initialize", "actual_side_effects": evidence.value["actual_side_effects"]})
        evidence.begin("authenticate"); authenticate_dependencies(ctx)
        source, forbidden, authenticated_models = authenticated_sources(work, ctx); ctx["_historical_forbidden"] = sorted(forbidden)
        atomic_json(art / "source-authentication.json", source); evidence.complete()
        evidence.begin("build"); exe, identity = verify_native(ctx, work)
        if ctx["phase"] != "readiness":
            need(identity == read_json(Path(ctx["paths"]["readiness_runtime"])), "READINESS_RUNTIME_DRIFT")
        atomic_json(art / "runtime-identity.json", identity); evidence.complete()
        evidence.begin("seal"); seal = generate_and_seal(exe, ctx, art); atomic_json(art / "opening-freeze.json", seal)
        if ctx["phase"] == "readiness": bind_readiness_selection(result, ctx, seal)
        evidence.complete()
        evidence.begin("execute"); models = model_paths(ctx, work, authenticated_models); tasks = tasks_for(ctx["phase"], work, exe, seal, _forbidden(ctx));
        for task in tasks: task["model_a"] = str(models[task["arm_a"]]); task["model_b"] = str(models[task["arm_b"]])
        rows = execute(tasks, ctx["phase"], art, evidence); put_gzip_json(art / "stage-games.json.gz", {"phase": ctx["phase"], "pairs": rows}); evidence.complete()
        evidence.begin("validate"); report = validate(ctx["phase"], rows, tasks, seal, evidence.value.get("timed_block_wall_seconds", .001))
        if ctx["phase"] == "wdl": report = joint_readout(ctx, report)
        if "trajectory_canonicals" in report: report["trajectory_canonicals"] = sorted(report["trajectory_canonicals"])
        atomic_json(art / "study-report.json", report); evidence.complete()
        evidence.begin("publish"); verdict = report.get("terminal") if ctx["phase"] == "wdl" else None
        summary = {"schema": STAGE_SCHEMA, "state": "completed", "phase": ctx["phase"], "scientific_verdict": verdict,
                   "terminal": verdict or ("CLS_G0_PANEL_READINESS_COMPLETE_V1" if ctx["phase"] == "readiness" else "CLS_G0_PANEL_LOCAL_TECHNICAL_COMPLETE_V1"),
                   "technical_completion": True, "promotion_authorized": False, "bake_authorized": False,
                   "automatic_retry": False, "report": report, "opening_selection_sha256": seal["selection_sha256"],
                   "actual_side_effects": evidence.value["actual_side_effects"]}
        put_final_summary(art / "scientific-summary.json", summary, evidence)
        (art / "RESULTS.md").write_text("# CLS panel " + ctx["phase"] + "\n\n" + json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        evidence.complete(); evidence.finish()
        atomic_json(art / "progress.json", {"phase": "completed", "actual_side_effects": evidence.value["actual_side_effects"],
                                              "completed_phases": evidence.value["completed_phases"]})
        atomic_json(art / "manifest.json", {"schema": "jass.cls_panel_manifest.v1", "phase": ctx["phase"], "output_sha256": {n: sha(art / n) for n in OUTPUTS if n != "manifest.json"}})
        return summary
    except BaseException as exc:
        evidence.fail(exc)
        atomic_json(art / "panel-failure.json", {"classification": "TECHNICAL_OR_APPARATUS_FAILURE", "error_type": type(exc).__name__, "reason": str(exc)[:200], "joint_terminal": "G0_PANEL_BLOCKED_NO_JOINT_VERDICT_V1", "automatic_retry": False})
        raise


def main() -> int:
    result = Path(os.environ["JASS_RESULT_DIR"]); art = Path(os.environ["JASS_ARTEFACT_DIR"])
    run(result, art); return 0


if __name__ == "__main__":
    def terminate(signum, frame):
        raise KeyboardInterrupt("TERMINATED")
    signal.signal(signal.SIGTERM, terminate)
    raise SystemExit(main())
