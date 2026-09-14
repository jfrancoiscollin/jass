#!/usr/bin/env python3
"""ED5 k=2 TRAIN Q200k teacher preflight/production stage.

This stage never reads an ED5 confirmation target. Rehearsal authenticates the
frozen TRAIN512 source and Scan runtime, executes synthetic contract checks, and
publishes bounded sizing only. Production may generate Q200k labels on TRAIN512
and seal the exact-max admissible sets for the later, separately launched fit.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time
import traceback

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from jobs.tools import ed3_label_pressure as audit
from jobs.tools import ed4_choice_math as ed4
from jobs.tools import ed5_q200k_choice as qchoice
from jobs.tools.ed4_fresh_d_confirmation_stage import (
    SCAN_SHA256,
    WORKERS,
    fetch_scan,
    unzip,
)
from jobs.tools.launch_runtime_v2 import StageEvidence, atomic_json

PROTOCOL = "docs/experiments/L3_ED5_Q200K_TEACHER_CHOICE_SET_PREREG_V1_20260914.md"
NODE_BUDGET = 200000
TRAIN_PARENTS = 512
TRAIN_ROWS = 4976
CELL_QUOTA = 64
BATCH_CAP_SECONDS = 2400.0
STAGE_CAP_SECONDS = 2700.0
CPU_MAX = 16
MIN_FREE_BYTES = 3 * 1024**3
SOURCE_FILES = ("groups.tsv", "children.jnnw")
PHASES = ["authenticate", "verify-train-boundary", "synthetic-contract", "teacher-or-sizing", "seal-and-publish"]


def need(ok: bool, code: str) -> None:
    if not ok:
        raise ValueError(code)


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def canonical(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def load_train_groups(source: Path) -> list[dict]:
    with (source / "groups.tsv").open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream, delimiter="\t"))
    grouped: dict[int, dict] = {}
    for row in rows:
        if row["split"] != "train":
            continue
        pid = int(row["parent_id"])
        item = grouped.setdefault(
            pid,
            {
                "id": pid,
                "cell": row["parent_phase"] + "_stm" + row["parent_stm"],
                "stm": int(row["parent_stm"]),
                "rows": [],
                "terminals": [],
            },
        )
        rid = int(row["row_index"])
        item["rows"].append(rid)
        if int(row["child_rule_terminal"]):
            item["terminals"].append(rid)
    groups = [grouped[key] for key in sorted(grouped)]
    need(len(groups) == TRAIN_PARENTS, "train_parent_support")
    need(sum(len(group["rows"]) for group in groups) == TRAIN_ROWS, "train_row_support")
    cells: dict[str, int] = {}
    for group in groups:
        need(group["rows"] == sorted(group["rows"]), "train_row_order")
        need(2 <= len(group["rows"]) <= 16, "train_sibling_support")
        cells[group["cell"]] = cells.get(group["cell"], 0) + 1
    need(len(cells) == 8 and set(cells.values()) == {CELL_QUOTA}, "train_cell_quota")
    return groups


def authenticate(result: Path, art: Path) -> dict:
    from jobs.tools.ed4_fresh_decision_source_stage import records

    work = result / "work"
    work.mkdir(parents=True, exist_ok=True)
    roots = {"p0": result / "inputs" / "p0", "scan": result / "inputs" / "scan"}
    audit.fetch_existing(
        audit.P0,
        ["ed2-source-seal.json"] + [f"source/{name}" for name in SOURCE_FILES],
        roots["p0"],
        art / "verified-p0.json",
    )
    fetch_scan(roots["scan"], art / "verified-scan.json")

    source_seal = read_json(roots["p0"] / "ed2-source-seal.json")
    need(sha(roots["p0"] / "ed2-source-seal.json") == audit.SOURCE_SEAL, "source_seal_identity")
    for name in SOURCE_FILES:
        need(sha(roots["p0"] / "source" / name) == source_seal["files"][name], "source_bytes")
    children = records(roots["p0"] / "source" / "children.jnnw")
    groups = load_train_groups(roots["p0"] / "source")
    need(max(r for group in groups for r in group["rows"]) < len(children), "train_row_bounds")

    scan_root = work / "scan"
    (scan_root / "data").mkdir(parents=True, exist_ok=True)
    unzip(roots["scan"] / "scan-home-compiled.gz", scan_root / "scan")
    (scan_root / "scan").chmod(0o500)
    shutil.copyfile(roots["scan"] / "scan-data-eval", scan_root / "data" / "eval")
    shutil.copyfile(roots["scan"] / "scan.ini", scan_root / "scan.ini")
    manifest = read_json(roots["scan"] / "scan-build-manifest.json")
    need(manifest.get("scan_binary_sha256") == SCAN_SHA256 and sha(scan_root / "scan") == SCAN_SHA256, "scan_identity")

    source_art = art / "source"
    source_art.mkdir()
    for name in SOURCE_FILES:
        shutil.copyfile(roots["p0"] / "source" / name, source_art / name)
    shutil.copyfile(roots["p0"] / "ed2-source-seal.json", art / "source-seal.json")
    auth = {
        "schema": "jass.ed5.q200k_teacher_auth.v1",
        "protocol": PROTOCOL,
        "p0": {"job_id": audit.P0[0], "attempt_id": audit.P0[1], "code_sha": audit.P0[2], "seal_sha256": audit.SOURCE_SEAL},
        "scan_sha256": SCAN_SHA256,
        "node_budget": NODE_BUDGET,
        "train_parents": len(groups),
        "train_rows": sum(len(group["rows"]) for group in groups),
        "source_files": {name: sha(source_art / name) for name in SOURCE_FILES},
        "confirmation_target_reads": 0,
        "candidate_reads": 0,
        "alpha_spent": 0.0,
    }
    atomic_json(art / "teacher-authentication.json", auth)
    return {"groups": groups, "scan": scan_root / "scan", "auth": auth}


def verify_boundary(art: Path) -> dict:
    auth = read_json(art / "teacher-authentication.json")
    need(auth["schema"] == "jass.ed5.q200k_teacher_auth.v1", "auth_schema")
    need(auth["confirmation_target_reads"] == 0 and auth["candidate_reads"] == 0 and auth["alpha_spent"] == 0.0, "confirmation_barrier")
    need(auth["p0"]["seal_sha256"] == audit.SOURCE_SEAL and auth["scan_sha256"] == SCAN_SHA256, "auth_identity")
    for name, digest in auth["source_files"].items():
        need(sha(art / "source" / name) == digest, "source_mutation")
    return auth


def synthetic_contract() -> dict:
    base_groups = []
    scores = {}
    for pid in range(24):
        rows = [2 * pid, 2 * pid + 1]
        terminals = rows[:] if pid == 23 else []
        base_groups.append({"id": pid, "stm": pid % 2, "rows": rows, "terminals": terminals})
        if not terminals:
            if pid % 3 == 0:
                scores[rows[0], NODE_BUDGET] = 17
                scores[rows[1], NODE_BUDGET] = 17
            else:
                scores[rows[0], NODE_BUDGET] = 20
                scores[rows[1], NODE_BUDGET] = -5
    groups = qchoice.groups_from_q200k(base_groups, scores)
    need(groups[0]["A"] == [0, 1], "synthetic_tie")
    need(groups[1]["A"] == [2], "synthetic_unique_max")
    need(groups[-1]["V"] == [] and groups[-1]["A"] == [], "synthetic_terminal_exclusion")

    phi = np.zeros((48, ed4.WIDTH), dtype=float)
    z = np.linspace(-0.2, 0.2, 48)
    replay_x = np.zeros((32, ed4.WIDTH), dtype=float)
    replay_z = np.linspace(-0.1, 0.1, 32)
    y = np.linspace(0.2, 0.8, 32)
    d = ed4.design(phi, z, groups, replay_x, replay_z, y)
    beta = np.linspace(-1e-4, 1e-4, ed4.WIDTH)
    a = ed4.derivatives(beta, d)
    b = qchoice.derivatives(beta, d)
    need(a[0] == b[0] and np.array_equal(a[1], b[1]) and np.array_equal(a[2], b[2]), "choice_math_changed")

    # Parent-POV sign remains exactly the ED4 rule: same rows/A, opposite STM flips
    # only the learned choice gradient contribution. Replay/ridge are removed here.
    x = np.zeros((2, ed4.WIDTH)); x[0, 0] = 1.0; x[1, 0] = -1.0
    zz = np.array([0.3, -0.1])
    rx = np.zeros((1, ed4.WIDTH)); rz = np.zeros(1); yy = np.array([0.5])
    g1 = [{"id": 0, "stm": 1, "rows": [0, 1], "V": [0, 1], "A": [0], "edges": []}] + [
        {"id": i, "stm": i % 2, "rows": [], "V": [], "A": [], "edges": []} for i in range(1, 24)
    ]
    g0 = [dict(group) for group in g1]; g0[0] = dict(g0[0], stm=0)
    # design requires complete contiguous ownership; use 24 one-row neutral terminal groups
    # instead of empty rows for the 23 fillers.
    def pov_design(stm: int):
        pphi = np.zeros((25, ed4.WIDTH)); pphi[:2] = x
        pz = np.zeros(25); pz[:2] = zz
        gs = [{"id": 0, "stm": stm, "rows": [0, 1], "V": [0, 1], "A": [0], "edges": []}]
        for i in range(1, 24):
            row = i + 1
            gs.append({"id": i, "stm": i % 2, "rows": [row], "V": [], "A": [], "edges": []})
        return ed4.design(pphi, pz, gs, rx, rz, yy)
    grad_black = ed4.derivatives(np.zeros(ed4.WIDTH), pov_design(1))[1][0]
    grad_white = ed4.derivatives(np.zeros(ed4.WIDTH), pov_design(0))[1][0]
    need(grad_black * grad_white < 0, "parent_pov_sign")
    return {
        "schema": "jass.ed5.q200k_teacher_synthetic_contract.v1",
        "unique_max": True,
        "exact_tie_preserved": True,
        "terminal_exclusion": True,
        "ed4_choice_math_byte_path_reused": True,
        "parent_pov_sign_verified": True,
        "confirmation_target_reads": 0,
    }


def score_worker(art: Path, scan: Path, shard: int, output: Path) -> None:
    from jobs.tools.ed4_fresh_decision_source_stage import records
    from jobs.tools.scan_ceiling_scan_score import NodeScanEngine, record_to_scan_pos, terminal_observation

    verify_boundary(art)
    need(0 <= shard < WORKERS, "worker_shard")
    groups = load_train_groups(art / "source")
    children = records(art / "source" / "children.jnnw")
    wanted = sorted(r for group in groups for r in group["rows"] if r % WORKERS == shard)
    terminals = {r for group in groups for r in group["terminals"]}
    engine = NodeScanEngine(str(scan.resolve()), label=f"ED5-Q200K-TRAIN-{shard}")
    try:
        with output.open("x", encoding="utf-8") as stream:
            for rid in wanted:
                obs = terminal_observation() if rid in terminals else engine.search_nodes(record_to_scan_pos(children[rid]), NODE_BUDGET, 30)
                row = {
                    "row": rid,
                    "budget": NODE_BUDGET,
                    "score": int(obs["parent_score_centi"]),
                    "terminal": rid in terminals,
                    "elapsed_seconds": float(obs["elapsed_seconds"]),
                    "last_info_nodes": int(obs["last_info_nodes"]),
                }
                stream.write(json.dumps(row, sort_keys=True) + "\n")
                stream.flush()
    finally:
        engine.close()


def load_teacher(paths: list[Path], groups: list[dict]) -> tuple[dict[tuple[int, int], int], int]:
    wanted = {r for group in groups for r in group["rows"]}
    terminals = {r for group in groups for r in group["terminals"]}
    values: dict[int, int] = {}
    calls = 0
    for path in paths:
        for line in path.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            rid = row["row"]
            need(rid in wanted and rid not in values and row["budget"] == NODE_BUDGET, "teacher_coverage")
            need(type(row["score"]) is int and type(row["terminal"]) is bool and row["terminal"] == (rid in terminals), "teacher_schema")
            need(math.isfinite(row["elapsed_seconds"]) and row["elapsed_seconds"] >= 0.0, "teacher_clock")
            if row["terminal"]:
                need(row["last_info_nodes"] == 0 and row["score"] == 10000, "terminal_teacher")
            else:
                need(0 < row["last_info_nodes"] <= NODE_BUDGET, "scan_snapshot")
                calls += 1
            values[rid] = row["score"]
    need(set(values) == wanted, "incomplete_teacher_no_partial_harvest")
    return {(rid, NODE_BUDGET): score for rid, score in values.items()}, calls


def generate_teacher(d: dict, art: Path, result: Path, evidence: StageEvidence) -> tuple[dict, dict]:
    paths = [art / f"train-q200k-{i}.jsonl" for i in range(WORKERS)]
    nonterminal = sum(r not in group["terminals"] for group in d["groups"] for r in group["rows"])
    evidence.value["actual_side_effects"]["new_scan_searches"] += nonterminal
    evidence.save()
    logs = []
    processes = []
    start = time.monotonic()
    try:
        for shard, path in enumerate(paths):
            log = (result / "work" / f"train-q200k-{shard}.log").open("xb")
            logs.append(log)
            command = [sys.executable, str(Path(__file__).resolve()), "score", "--art", str(art), "--scan", str(d["scan"]), "--shard", str(shard), "--out", str(path)]
            processes.append(subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT, start_new_session=True))
        while any(process.poll() is None for process in processes):
            need(not any(process.poll() not in (None, 0) for process in processes), "teacher_worker_failed")
            if time.monotonic() - start > BATCH_CAP_SECONDS:
                raise TimeoutError("ED5_Q200K_TRAIN_BATCH_CAP")
            time.sleep(0.2)
        need(all(process.returncode == 0 for process in processes), "teacher_worker_failed")
    finally:
        for process in processes:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        for process in processes:
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait()
        for log in logs:
            log.close()
    high, calls = load_teacher(paths, d["groups"])
    need(calls == nonterminal, "teacher_call_accounting")
    choices = qchoice.groups_from_q200k(d["groups"], high)
    sets = [
        {"parent_id": group["id"], "stm": group["stm"], "V": group["V"], "A": group["A"]}
        for group in choices
    ]
    atomic_json(art / "choice-sets.json", {"schema": "jass.ed5.q200k_choice_sets.v1", "node_budget": NODE_BUDGET, "parents": sets})
    cost = {
        "workers": WORKERS,
        "train_rows": TRAIN_ROWS,
        "scan_calls": calls,
        "requested_nodes": calls * NODE_BUDGET,
        "wall_seconds": time.monotonic() - start,
        "batch_cap_seconds": BATCH_CAP_SECONDS,
    }
    return high, cost


def sizing(groups: list[dict], free_bytes: int) -> dict:
    nonterminal = sum(r not in group["terminals"] for group in groups for r in group["rows"])
    need(WORKERS <= CPU_MAX, "cpu_cap")
    need(BATCH_CAP_SECONDS <= STAGE_CAP_SECONDS <= 45 * 60, "stage_cap")
    need(free_bytes >= MIN_FREE_BYTES, "disk_space_below_3gib")
    return {
        "schema": "jass.ed5.q200k_teacher_sizing.v1",
        "workers": WORKERS,
        "cpu_max": CPU_MAX,
        "planned_scan_calls": nonterminal,
        "planned_requested_nodes": nonterminal * NODE_BUDGET,
        "node_budget": NODE_BUDGET,
        "batch_hard_cap_seconds": BATCH_CAP_SECONDS,
        "stage_hard_cap_seconds": STAGE_CAP_SECONDS,
        "within_45_minute_contract": True,
        "free_bytes_observed": free_bytes,
        "minimum_free_bytes": MIN_FREE_BYTES,
        "confirmation_target_reads": 0,
    }


def run(result: Path, art: Path, mode: str) -> dict:
    need(mode in ("rehearsal", "production"), "launch_mode")
    evidence = StageEvidence(art, mode)
    try:
        free_bytes = shutil.disk_usage(result).free
        need(free_bytes >= MIN_FREE_BYTES, "disk_space_below_3gib")
        evidence.begin(PHASES[0])
        d = authenticate(result, art)
        evidence.complete()

        evidence.begin(PHASES[1])
        verify_boundary(art)
        need(evidence.value["actual_side_effects"]["test_target_reads"] == 0, "confirmation_target_read")
        evidence.complete()

        evidence.begin(PHASES[2])
        preflight = synthetic_contract()
        atomic_json(art / "synthetic-contract.json", preflight)
        evidence.complete()

        evidence.begin(PHASES[3])
        size = sizing(d["groups"], free_bytes)
        atomic_json(art / "sizing.json", size)
        if mode == "production":
            _, cost = generate_teacher(d, art, result, evidence)
        else:
            cost = {
                "workers": WORKERS,
                "planned_scan_calls": size["planned_scan_calls"],
                "planned_requested_nodes": size["planned_requested_nodes"],
                "teacher_calls_executed": 0,
            }
        atomic_json(art / "teacher-cost.json", cost)
        evidence.complete()

        evidence.begin(PHASES[4])
        verify_boundary(art)
        if mode == "production":
            label_files = {f"train-q200k-{i}.jsonl": sha(art / f"train-q200k-{i}.jsonl") for i in range(WORKERS)}
            seal = {
                "schema": "jass.ed5.q200k_teacher_seal.v1",
                "role": "train_teacher_only",
                "mode": mode,
                "source_seal_sha256": audit.SOURCE_SEAL,
                "scan_sha256": SCAN_SHA256,
                "node_budget": NODE_BUDGET,
                "train_parents": TRAIN_PARENTS,
                "train_rows": TRAIN_ROWS,
                "teacher_files": label_files,
                "choice_sets_sha256": sha(art / "choice-sets.json"),
                "confirmation_target_reads": 0,
                "candidate_reads": 0,
                "fits": 0,
                "new_jass_searches": 0,
                "alpha_spent": 0.0,
                "runtime_authorized": False,
                "promotion_authorized": False,
            }
            atomic_json(art / "teacher-seal.json", seal)
            terminal = "ED5_Q200K_TRAIN_TEACHER_SEALED_V1"
            next_stage = "RUN_ED5_Q200K_CHOICE_FIT_REHEARSAL"
        else:
            seal = None
            terminal = "ED5_Q200K_TEACHER_PREFLIGHT_COMPLETE_V1"
            next_stage = "RUN_ED5_Q200K_TRAIN_TEACHER_PRODUCTION"
        summary = {
            "schema": "jass.ed5.q200k_teacher_terminal.v1",
            "state": "completed",
            "terminal": terminal,
            "mode": mode,
            "scientific_verdict": None,
            "preflight": preflight,
            "sizing": size,
            "teacher_cost": cost,
            "teacher_seal": seal,
            "train_teacher_reads": TRAIN_ROWS if mode == "production" else 0,
            "new_scan_searches": int(evidence.value["actual_side_effects"]["new_scan_searches"]),
            "confirmation_target_reads": 0,
            "fits": 0,
            "candidate_reads": 0,
            "new_jass_searches": 0,
            "strength_games": 0,
            "selfplay_games": 0,
            "promotions": 0,
            "bakes": 0,
            "alpha_spent": 0.0,
            "confirmation_target_consumed": False,
            "next_stage": next_stage,
        }
        atomic_json(art / "scientific-summary.json", summary)
        evidence.complete()
        evidence.finish()
        return summary
    except BaseException as exc:
        evidence.fail(exc)
        if not (art / "scientific-summary.json").exists():
            atomic_json(
                art / "scientific-summary.json",
                {
                    "schema": "jass.ed5.q200k_teacher_failure.v1",
                    "state": "failed",
                    "terminal": "CAMPAIGN_ATTEMPT_TECHNICAL_FAILURE_V1",
                    "mode": mode,
                    "error_type": type(exc).__name__,
                    "confirmation_target_reads": 0,
                    "alpha_spent": 0.0,
                    "confirmation_target_consumed": False,
                    "next_stage": "REPAIR_SAME_FROZEN_ED5_TEACHER_CONTRACT",
                },
            )
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command")
    worker = sub.add_parser("score")
    worker.add_argument("--art", type=Path, required=True)
    worker.add_argument("--scan", type=Path, required=True)
    worker.add_argument("--shard", type=int, required=True)
    worker.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "score":
        score_worker(args.art, args.scan, args.shard, args.out)
        return 0
    from jobs.tools.ed2_value_entrypoint import install_shutdown_handlers
    install_shutdown_handlers()
    run(Path(os.environ["JASS_RESULT_DIR"]), Path(os.environ["JASS_ARTEFACT_DIR"]), os.environ["LAUNCH_MODE"])
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        traceback.print_exc()
        raise SystemExit(2)
