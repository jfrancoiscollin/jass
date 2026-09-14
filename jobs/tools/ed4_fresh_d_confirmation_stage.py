#!/usr/bin/env python3
"""ED4-FRESH D target confirmation under the frozen k=1 campaign contract.

Rehearsal authenticates the exact sealed D source, candidate, controls, native
probe and Scan identity without reading any confirmation target. Production uses
the identical common spec and differs only by LAUNCH_MODE; only production may
run Scan Q200k on the already-sealed decision children.
"""
from __future__ import annotations

import argparse
import csv
import gzip
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

from jobs.tools.launch_runtime_v2 import StageEvidence, atomic_json

D_SOURCE = (
    "cpx62-1937-l3-ed4-fresh-d-source-production-v1",
    "20260913T073800Z-9673030c",
    "9673030cc00b753d919403a0dc08f14d3f4154a0",
)
CANDIDATE_SOURCE = (
    "cpx62-1888-l3-ed4-choice-value-fit-production-v1",
    "20260909T143020Z-93e2fd1f",
    "93e2fd1f19417bb5076e2013830ec77e999d95bf",
)
SOFT_SOURCE = (
    "cpx62-1882-l3-ed3-soft-value-fit-production-v1",
    "20260908T220255Z-20a5e4eb",
    "20a5e4ebebedbf9340eafd3750506c1aed851506",
)
SCAN_SOURCE = ("home-1650-l3-scan-ceiling-preflight-v1", "20260829T132800Z-28e12fba")
SCAN_SHA256 = "96b80c6aec1592f856a78ad7617ca6224b26be926800a6e37ede3b26f4e9cfa1"
CANDIDATE_SHA256 = "2e856652efdd1d2758a949a5d4a29557fa31f4a64d55505ae6dc41482b641f5b"
SOFT_SHA256 = "d8a193de2017a6c156a46d89692245bdc1af00d29d056af3a41e7d6d4f5a486a"
D_MASTER_SEED = 202609120401
NODE_BUDGET = 200000
PARENTS = 512
CELL_QUOTA = 64
WORKERS = 8
FAMILY_ALPHA_K = 0.025
BLOCK_ALPHA = FAMILY_ALPHA_K / 3.0
BOOTSTRAPS = 20000
REFERENCE_BATCH_CAP_SECONDS = 2400.0
PHASES = ["authenticate", "seal-before-target", "native-readout", "score-reference", "statistics", "publish"]
D_FILES = ("parents.jnnw", "children.jnnw", "parents.tsv", "groups.tsv", "source.json")


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


def fetch_exact(identity: tuple[str, str, str], names: list[str], root: Path, receipt: Path) -> None:
    from jobs.tools.fetch_result_files import fetch_files
    job, attempt, code = identity
    result = fetch_files(
        rclone="rclone",
        prefix=f"r2:jass-data/runs/{job}/{attempt}",
        selections=[(f"artefacts/{name}", name) for name in names],
        out_dir=root,
        expected_state="completed",
    )
    observed = (result.get("job_id"), result.get("attempt_id"), result.get("code_sha"), result.get("result_state"), result.get("exit_code"))
    need(observed == (job, attempt, code, "completed", 0), "input_identity")
    atomic_json(receipt, result)


def fetch_scan(root: Path, receipt: Path) -> None:
    from jobs.tools.fetch_result_files import fetch_files
    job, attempt = SCAN_SOURCE
    names = ["scan-build-manifest.json", "scan-home-compiled.gz", "scan-data-eval", "scan.ini"]
    result = fetch_files(
        rclone="rclone",
        prefix=f"r2:jass-data/runs/{job}/{attempt}",
        selections=[(f"artefacts/{name}", name) for name in names],
        out_dir=root,
        expected_state="completed",
    )
    need((result.get("job_id"), result.get("attempt_id"), result.get("result_state"), result.get("exit_code")) == (job, attempt, "completed", 0), "scan_input_identity")
    atomic_json(receipt, result)


def unzip(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(source, "rb") as src, destination.open("xb") as out:
        shutil.copyfileobj(src, out)


def load_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream, delimiter="\t"))


def decision_groups(source: Path) -> list[dict]:
    parents = {int(row["parent_id"]): row for row in load_rows(source / "parents.tsv") if row["split"] == "decision"}
    grouped: dict[int, dict] = {}
    for row in load_rows(source / "groups.tsv"):
        if row["split"] != "decision":
            continue
        pid = int(row["parent_id"])
        parent = parents.get(pid)
        need(parent is not None, "decision_parent_metadata")
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
    need(len(groups) == PARENTS and len(parents) == PARENTS, "decision_parent_count")
    cells: dict[str, int] = {}
    for group in groups:
        need(2 <= len(group["rows"]) <= 16, "decision_sibling_support")
        cells[group["cell"]] = cells.get(group["cell"], 0) + 1
    need(len(cells) == 8 and set(cells.values()) == {CELL_QUOTA}, "decision_cell_quota")
    return groups


def verify_d_source(root: Path) -> tuple[dict, list[dict]]:
    from jobs.tools.ed4_fresh_decision_source_stage import records
    seal = read_json(root / "cohort-seal.json")
    need(seal.get("schema") == "jass.ed4.fresh_d_source_seal.v1", "d_seal_schema")
    need(seal.get("terminal") == "ED4_FRESH_D_SOURCE_SEALED_V1" and seal.get("state") == "completed" and seal.get("mode") == "production", "d_seal_state")
    need(seal.get("master_seed") == D_MASTER_SEED and seal.get("reserve_seed_used") is False, "d_seed")
    need(seal.get("target_reads") == 0 and seal.get("fits") == 0 and seal.get("scan_searches") == 0 and seal.get("jass_searches") == 0 and seal.get("alpha_spent") == 0, "d_information_boundary")
    need(seal.get("confirmation_target_consumed") is False, "d_consumed")
    for name in D_FILES:
        need(sha(root / "source" / name) == seal["files"][name], "d_source_hash")
    records(root / "source" / "parents.jnnw")
    children = records(root / "source" / "children.jnnw")
    groups = decision_groups(root / "source")
    need(max(r for group in groups for r in group["rows"]) < len(children), "decision_row_bounds")
    return seal, groups


def authenticate(result: Path, art: Path) -> dict:
    from jobs.tools import ed3_label_pressure as audit
    from jobs.tools.ed2_value_math import read_model
    work = result / "work"
    work.mkdir(parents=True, exist_ok=True)
    roots = {name: result / "inputs" / name for name in ("D", "candidate", "base", "n1", "soft", "scan")}
    fetch_exact(D_SOURCE, ["cohort-seal.json"] + [f"source/{name}" for name in D_FILES], roots["D"], art / "verified-d.json")
    fetch_exact(CANDIDATE_SOURCE, ["ED4_CHOICE.pjtw", "candidate-seal.json"], roots["candidate"], art / "verified-candidate.json")
    fetch_exact(audit.BASE, ["WDL_CONTROL.pjtw.gz"], roots["base"], art / "verified-base.json")
    fetch_exact(audit.N1, ["PARTIAL.pjtw", "build-outputs/jass_ed2_value_probe.gz", "scratch-cleanup.json"], roots["n1"], art / "verified-n1.json")
    fetch_exact(SOFT_SOURCE, ["SOFT.pjtw", "candidate-seal.json"], roots["soft"], art / "verified-soft.json")
    fetch_scan(roots["scan"], art / "verified-scan.json")

    d_seal, groups = verify_d_source(roots["D"])
    candidate_seal = read_json(roots["candidate"] / "candidate-seal.json")
    need(candidate_seal.get("schema") == "jass.ed4.choice_candidate_seal.v1" and candidate_seal.get("role") == "candidate", "candidate_seal")
    need(candidate_seal.get("model_sha256") == CANDIDATE_SHA256 and sha(roots["candidate"] / "ED4_CHOICE.pjtw") == CANDIDATE_SHA256, "candidate_identity")
    need(candidate_seal.get("test_target_reads") == 0 and candidate_seal.get("runtime_authorized") is False, "candidate_boundary")

    unzip(roots["base"] / "WDL_CONTROL.pjtw.gz", work / "BASE.pjtw")
    models = {
        "BASE": work / "BASE.pjtw",
        "HARD": roots["n1"] / "PARTIAL.pjtw",
        "SOFT": roots["soft"] / "SOFT.pjtw",
        "CANDIDATE": roots["candidate"] / "ED4_CHOICE.pjtw",
    }
    expected = {
        "BASE": audit.MODEL_HASH["BASE"],
        "HARD": audit.MODEL_HASH["PARTIAL"],
        "SOFT": SOFT_SHA256,
        "CANDIDATE": CANDIDATE_SHA256,
    }
    need({name: sha(path) for name, path in models.items()} == expected, "model_identity")
    base_raw, base_offset, _ = read_model(models["BASE"])
    for model in models.values():
        raw, offset, _ = read_model(model)
        need(offset == base_offset and raw[:offset] == base_raw[:base_offset], "model_pattern_prefix")

    cleanup = read_json(roots["n1"] / "scratch-cleanup.json")["retained_binaries"]["jass_ed2_value_probe"]
    archive = roots["n1"] / "build-outputs/jass_ed2_value_probe.gz"
    need(sha(archive) == cleanup["archive_sha256"], "probe_archive")
    unzip(archive, work / "native-probe")
    need(sha(work / "native-probe") == cleanup["sha256"], "probe_identity")
    (work / "native-probe").chmod(0o500)

    scan_root = work / "scan"
    (scan_root / "data").mkdir(parents=True, exist_ok=True)
    unzip(roots["scan"] / "scan-home-compiled.gz", scan_root / "scan")
    (scan_root / "scan").chmod(0o500)
    shutil.copyfile(roots["scan"] / "scan-data-eval", scan_root / "data" / "eval")
    shutil.copyfile(roots["scan"] / "scan.ini", scan_root / "scan.ini")
    scan_manifest = read_json(roots["scan"] / "scan-build-manifest.json")
    need(scan_manifest.get("scan_binary_sha256") == SCAN_SHA256 and sha(scan_root / "scan") == SCAN_SHA256, "scan_identity")

    source_art = art / "source"
    source_art.mkdir()
    for name in D_FILES:
        shutil.copyfile(roots["D"] / "source" / name, source_art / name)
    shutil.copyfile(roots["D"] / "cohort-seal.json", art / "source-cohort-seal.json")
    auth = {
        "schema": "jass.ed4.fresh_d_confirmation_auth.v1",
        "d_source": {"job_id": D_SOURCE[0], "attempt_id": D_SOURCE[1], "code_sha": D_SOURCE[2], "seal_sha256": sha(roots["D"] / "cohort-seal.json")},
        "candidate": {"job_id": CANDIDATE_SOURCE[0], "attempt_id": CANDIDATE_SOURCE[1], "code_sha": CANDIDATE_SOURCE[2], "sha256": CANDIDATE_SHA256},
        "models": expected,
        "native_probe_sha256": cleanup["sha256"],
        "scan_sha256": SCAN_SHA256,
        "decision_parents": len(groups),
        "node_budget": NODE_BUDGET,
        "family_alpha_k": FAMILY_ALPHA_K,
        "block_alpha": BLOCK_ALPHA,
        "source_files": {name: sha(source_art / name) for name in D_FILES},
        "target_reads": 0,
        "alpha_spent_before_target": 0,
    }
    atomic_json(art / "cohort-authentication.json", auth)
    return {"groups": groups, "models": models, "probe": work / "native-probe", "scan": scan_root / "scan", "auth": auth, "d_seal": d_seal}


def verify_sealed_source(art: Path) -> dict:
    auth = read_json(art / "cohort-authentication.json")
    need(auth.get("schema") == "jass.ed4.fresh_d_confirmation_auth.v1", "auth_schema")
    for name, digest in auth["source_files"].items():
        need(sha(art / "source" / name) == digest, "sealed_source_mutation")
    need(auth["candidate"]["sha256"] == CANDIDATE_SHA256 and auth["scan_sha256"] == SCAN_SHA256, "sealed_identity_mutation")
    return auth


def native_readout(d: dict, result: Path, art: Path) -> dict[str, np.ndarray]:
    from jobs.tools.ed3_soft_value_fit import run_probe
    from jobs.tools.ed4_fresh_decision_source_stage import records
    children = art / "source" / "children.jnnw"
    n = len(records(children))
    scores: dict[str, np.ndarray] = {}
    base_features = None
    for arm, model in d["models"].items():
        table = run_probe(d["probe"], children, model, result / "work" / f"{arm}-d.tsv")
        features, logits, cp = table
        need(cp.shape == (n,), "native_score_shape")
        if base_features is None:
            base_features = features
        else:
            need(np.array_equal(features, base_features), "native_features_differ")
        scores[arm] = cp.astype(int, copy=False)
    repeated = run_probe(d["probe"], children, d["models"]["BASE"], result / "work" / "BASE-repeat-d.tsv")[2]
    need(np.array_equal(repeated, scores["BASE"]), "base_repeat_sanity")
    return scores


def score_worker(art: Path, scan: Path, shard: int, output: Path) -> None:
    from jobs.tools.ed4_fresh_decision_source_stage import records
    from jobs.tools.scan_ceiling_scan_score import NodeScanEngine, record_to_scan_pos, terminal_observation
    verify_sealed_source(art)
    need(0 <= shard < WORKERS, "worker_shard")
    groups = decision_groups(art / "source")
    children = records(art / "source" / "children.jnnw")
    wanted = sorted(r for group in groups for r in group["rows"] if r % WORKERS == shard)
    terminals = {r for group in groups for r in group["terminals"]}
    engine = NodeScanEngine(str(scan.resolve()), label=f"ED4-FRESH-D-{shard}")
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


def load_reference(paths: list[Path], groups: list[dict]) -> tuple[dict[tuple[int, int], int], int]:
    wanted = {r for group in groups for r in group["rows"]}
    terminals = {r for group in groups for r in group["terminals"]}
    values: dict[int, int] = {}
    calls = 0
    for path in paths:
        for line in path.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            rid = row["row"]
            need(rid in wanted and rid not in values and row["budget"] == NODE_BUDGET, "reference_coverage")
            need(type(row["score"]) is int and type(row["terminal"]) is bool and row["terminal"] == (rid in terminals), "reference_role")
            need(math.isfinite(row["elapsed_seconds"]) and row["elapsed_seconds"] >= 0, "reference_clock")
            if row["terminal"]:
                need(row["last_info_nodes"] == 0 and row["score"] == 10000, "terminal_reference")
            else:
                need(0 < row["last_info_nodes"] <= NODE_BUDGET, "scan_reference_snapshot")
                calls += 1
            values[rid] = row["score"]
    need(set(values) == wanted, "incomplete_reference_no_partial_harvest")
    return {(rid, NODE_BUDGET): value for rid, value in values.items()}, calls


def reference(d: dict, art: Path, result: Path, evidence: StageEvidence) -> tuple[dict[tuple[int, int], int], dict]:
    paths = [art / f"reference-{i}.jsonl" for i in range(WORKERS)]
    nonterminal = sum(r not in group["terminals"] for group in d["groups"] for r in group["rows"])
    total_rows = sum(len(group["rows"]) for group in d["groups"])
    evidence.value["actual_side_effects"]["new_scan_searches"] += nonterminal
    evidence.value["actual_side_effects"]["test_target_reads"] += total_rows
    evidence.value["side_effect_counters_upper_bounds_until_workers_complete"] = True
    evidence.save()
    logs = []
    processes = []
    start = time.monotonic()
    try:
        for shard, path in enumerate(paths):
            log = (result / "work" / f"reference-{shard}.log").open("xb")
            logs.append(log)
            command = [sys.executable, str(Path(__file__).resolve()), "score", "--art", str(art), "--scan", str(d["scan"]), "--shard", str(shard), "--out", str(path)]
            processes.append(subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT, start_new_session=True))
        while any(process.poll() is None for process in processes):
            need(not any(process.poll() not in (None, 0) for process in processes), "reference_worker_failed")
            if time.monotonic() - start > REFERENCE_BATCH_CAP_SECONDS:
                raise TimeoutError("ED4_FRESH_D_REFERENCE_BATCH_CAP")
            time.sleep(0.2)
        need(all(process.returncode == 0 for process in processes), "reference_worker_failed")
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
    high, calls = load_reference(paths, d["groups"])
    need(calls == nonterminal, "reference_call_accounting")
    evidence.value["side_effect_counters_upper_bounds_until_workers_complete"] = False
    evidence.value["actual_side_effects"]["new_scan_searches"] = calls
    evidence.value["actual_side_effects"]["test_target_reads"] = total_rows
    evidence.save()
    return high, {
        "workers": WORKERS,
        "decision_rows": total_rows,
        "scan_calls": calls,
        "requested_nodes": calls * NODE_BUDGET,
        "wall_seconds": time.monotonic() - start,
        "batch_cap_seconds": REFERENCE_BATCH_CAP_SECONDS,
    }


def bootstrap_parent_one_sided(delta: np.ndarray, cells: list[str], seed: int, alpha: float = BLOCK_ALPHA) -> dict:
    need(len(delta) == len(cells) and len(delta) > 0, "bootstrap_alignment")
    values = np.asarray(delta, dtype=float)
    labels = np.asarray(cells)
    rng = np.random.default_rng(seed)
    boots = np.zeros(BOOTSTRAPS, dtype=float)
    for cell in sorted(set(cells)):
        x = values[labels == cell]
        need(len(x) == CELL_QUOTA, "bootstrap_cell_quota")
        for start in range(0, BOOTSTRAPS, 250):
            end = min(start + 250, BOOTSTRAPS)
            sample = rng.integers(0, len(x), size=(end - start, len(x)))
            boots[start:end] += x[sample].sum(axis=1) / len(values)
    return {
        "mean": float(values.mean()),
        "lower": float(np.quantile(boots, alpha)),
        "upper": float(np.quantile(boots, 1.0 - alpha)),
        "one_sided_alpha": float(alpha),
        "bootstrap_replicates": BOOTSTRAPS,
        "cluster_unit": "parent",
        "strata": "phase_x_stm",
    }


def comparison(base: list[dict], candidate: list[dict], seed: int) -> dict:
    need([row["parent_id"] for row in base] == [row["parent_id"] for row in candidate], "parent_population_mismatch")
    delta = np.asarray([a["regret"] - b["regret"] for a, b in zip(base, candidate)], dtype=float)
    cells = [row["cell"] for row in base]
    out = bootstrap_parent_one_sided(delta, cells, seed)
    hit_delta = np.asarray([b["hit"] - a["hit"] for a, b in zip(base, candidate)], dtype=float)
    out.update(
        top_hit_delta=float(hit_delta.mean()),
        improved=int(np.sum(delta > 0)),
        harmed=int(np.sum(delta < 0)),
        unchanged=int(np.sum(delta == 0)),
        decision_changes=sum(a["choice"] != b["choice"] for a, b in zip(base, candidate)),
    )
    return out


def statistics(groups: list[dict], high: dict[tuple[int, int], int], scores: dict[str, np.ndarray]) -> tuple[dict, dict[str, list[dict]]]:
    from jobs.tools.ed2_value_math import decision_rows
    rows = {arm: decision_rows(groups, high, cp) for arm, cp in scores.items()}
    need(rows["BASE"] == decision_rows(groups, high, scores["BASE"]), "base_identity_sanity")
    vs_base = comparison(rows["BASE"], rows["CANDIDATE"], 202609140901)
    vs_hard = comparison(rows["HARD"], rows["CANDIDATE"], 202609140902)
    vs_soft = comparison(rows["SOFT"], rows["CANDIDATE"], 202609140903)
    gates = {
        "regret_beats_base_positive_lower_bound": vs_base["lower"] > 0.0,
        "regret_beats_hard_positive_lower_bound": vs_hard["lower"] > 0.0,
        "top_hit_not_lower_than_base_and_hard": vs_base["top_hit_delta"] >= 0.0 and vs_hard["top_hit_delta"] >= 0.0,
        "harms_not_more_than_improvements_vs_base": vs_base["harmed"] <= vs_base["improved"],
    }
    aggregates = {
        arm: {
            "regret_mean": float(np.mean([row["regret"] for row in arm_rows])),
            "top_hit": float(np.mean([row["hit"] for row in arm_rows])),
        }
        for arm, arm_rows in rows.items()
    }
    report = {
        "schema": "jass.ed4.fresh_d_confirmation_readout.v1",
        "gates": gates,
        "versus_base": vs_base,
        "versus_hard": vs_hard,
        "versus_soft_descriptive": vs_soft,
        "aggregate": aggregates,
        "parents": len(groups),
        "teacher": {"engine": "Scan", "node_budget": NODE_BUDGET},
        "multiplicity": {"attempt_k": 1, "family_alpha_k": FAMILY_ALPHA_K, "block_alpha": BLOCK_ALPHA, "one_sided_interval_level": 1.0 - BLOCK_ALPHA},
        "group_unit": "parent",
        "bootstrap_strata": "phase_x_stm",
        "soft_role": "descriptive_only",
        "scan_is_reference_teacher_not_exact_truth": True,
    }
    return report, rows


def rehearsal_report(d: dict) -> dict:
    return {
        "schema": "jass.ed4.fresh_d_confirmation_readout.v1",
        "mode": "rehearsal",
        "target_read": False,
        "decision_parents": len(d["groups"]),
        "node_budget": NODE_BUDGET,
        "candidate_sha256": CANDIDATE_SHA256,
        "multiplicity": {"attempt_k": 1, "family_alpha_k": FAMILY_ALPHA_K, "block_alpha": BLOCK_ALPHA},
        "gates": None,
    }


def run(result: Path, art: Path, mode: str) -> dict:
    need(mode in ("rehearsal", "production"), "launch_mode")
    evidence = StageEvidence(art, mode)
    target_started = False
    try:
        need(shutil.disk_usage(result).free > 3_000_000_000, "disk_space")
        evidence.begin(PHASES[0])
        d = authenticate(result, art)
        evidence.complete()

        evidence.begin(PHASES[1])
        verify_sealed_source(art)
        need(d["auth"]["target_reads"] == 0 and d["auth"]["alpha_spent_before_target"] == 0, "pretarget_boundary")
        evidence.complete()

        evidence.begin(PHASES[2])
        scores = native_readout(d, result, art)
        evidence.complete()

        evidence.begin(PHASES[3])
        if mode == "production":
            target_started = True
            high, cost = reference(d, art, result, evidence)
        else:
            high, cost = None, {"workers": WORKERS, "planned_node_budget": NODE_BUDGET, "planned_maximum_scan_calls": PARENTS * 16, "target_reads": 0}
        atomic_json(art / "teacher-cost.json", cost)
        evidence.complete()

        evidence.begin(PHASES[4])
        if mode == "production":
            report, rows = statistics(d["groups"], high, scores)  # type: ignore[arg-type]
            report["mode"] = mode
            success = all(report["gates"].values())
            atomic_json(art / "parent-readout.json", rows)
        else:
            report = rehearsal_report(d)
            success = False
        atomic_json(art / "confirmation-readout.json", report)
        evidence.complete()

        evidence.begin(PHASES[5])
        verify_sealed_source(art)
        if mode == "production":
            block_verdict = "ED4_FRESH_D_CONFIRMATION_SUPPORTED_V1" if success else "ED4_FRESH_D_CONFIRMATION_NOT_SUPPORTED_V1"
            terminal = block_verdict if success else "CAMPAIGN_ATTEMPT_SCIENTIFIC_NOT_SUPPORTED_V1"
            next_stage = "RUN_ED4_FRESH_W_CONFIRMATION_TARGET" if success else "STOP_ED4_K1_SCIENTIFIC_NOT_SUPPORTED"
            scientific_verdict = terminal
            alpha_spent = BLOCK_ALPHA
        else:
            block_verdict = "ED4_FRESH_D_CONFIRMATION_REHEARSAL_COMPLETE_V1"
            terminal = block_verdict
            next_stage = "RUN_AUTHENTICATED_D_CONFIRMATION_PRODUCTION"
            scientific_verdict = None
            alpha_spent = 0.0
        summary = {
            "schema": "jass.ed4.fresh_d_confirmation_terminal.v1",
            "state": "completed",
            "terminal": terminal,
            "block_verdict": block_verdict,
            "mode": mode,
            "scientific_verdict": scientific_verdict,
            "candidate_sha256": CANDIDATE_SHA256,
            "parents": len(d["groups"]),
            "node_budget": NODE_BUDGET,
            "result": report,
            "teacher_cost": cost,
            "target_reads": int(evidence.value["actual_side_effects"]["test_target_reads"]),
            "new_scan_searches": int(evidence.value["actual_side_effects"]["new_scan_searches"]),
            "candidate_reads": 0,
            "control_evaluations": 0,
            "fits": 0,
            "new_jass_searches": 0,
            "strength_games": 0,
            "selfplay_games": 0,
            "promotions": 0,
            "bakes": 0,
            "alpha_spent": alpha_spent,
            "confirmation_target_consumed": mode == "production",
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
                    "schema": "jass.ed4.fresh_d_confirmation_failure.v1",
                    "state": "failed",
                    "terminal": "CAMPAIGN_ATTEMPT_TECHNICAL_FAILURE_V1",
                    "mode": mode,
                    "error_type": type(exc).__name__,
                    "target_phase_started": target_started,
                    "target_reads": int(evidence.value["actual_side_effects"]["test_target_reads"]),
                    "alpha_spent": BLOCK_ALPHA if target_started else 0.0,
                    "confirmation_target_consumed": target_started,
                    "next_stage": "REPAIR_SAME_FROZEN_D_CONTRACT_NO_REPLACEMENT" if target_started else "REPAIR_PRETARGET_D_STAGE",
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
