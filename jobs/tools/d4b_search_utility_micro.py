#!/usr/bin/env python3
"""Frozen D4b cheap search-utility micro-screen tooling."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from jobs.tools import d4_search_utility_offline as d4

ROOT_COUNTS = {"train": 384, "valid": 64, "test": 64}
EXACT_COUNTS = {"train": 8000, "valid": 1000, "test": 1000}
ROOT_PREFIX = "D4B-ROOT-2026090701:"
EXAMPLE_PREFIX = "D4B-EXAMPLE-2026090702:"
BOOTSTRAPS = 20_000
BOOTSTRAP_SEED = 2026090703
TEACHER_NODES = 20_000
SHARDS = 8
FORBIDDEN = (
    "game_outcome_reads", "qscore_reads", "search_decision_trace_reads",
    "full_ladder_1843_reads", "d3_score_reads",
)


def configure_base() -> None:
    d4.EXACT_COUNTS = dict(EXACT_COUNTS)
    d4.EXAMPLE_PREFIX = EXAMPLE_PREFIX
    d4.BOOTSTRAPS = BOOTSTRAPS
    d4.BOOTSTRAP_SEED = BOOTSTRAP_SEED


def read_manifest(path: Path) -> tuple[str, list[list[str]]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    header = "root_index\tsplit\tcanonical_identity\tfen\tselection_digest"
    if not lines or lines[0] != header:
        raise ValueError("D4 root manifest header drift")
    rows: list[list[str]] = []
    seen: set[int] = set()
    counts = {"train": 0, "valid": 0, "test": 0}
    for line in lines[1:]:
        f = line.split("\t")
        if len(f) != 5 or f[1] not in counts:
            raise ValueError("D4 root manifest row drift")
        idx = int(f[0])
        if idx in seen:
            raise ValueError("duplicate D4 root index")
        seen.add(idx); counts[f[1]] += 1; rows.append(f)
    if len(rows) not in (512, 4000):
        raise ValueError(f"unexpected root cardinality {len(rows)}")
    if len(rows) == 4000 and counts != {"train": 3200, "valid": 400, "test": 400}:
        raise ValueError(f"source D4 split drift {counts}")
    if len(rows) == 512 and counts != ROOT_COUNTS:
        raise ValueError(f"D4b split drift {counts}")
    return header, rows


def cmd_select(a: argparse.Namespace) -> int:
    header, rows = read_manifest(a.roots)
    chosen: list[list[str]] = []
    for split, need in ROOT_COUNTS.items():
        pool = [r for r in rows if r[1] == split]
        pool.sort(key=lambda r: (
            hashlib.sha256((ROOT_PREFIX + r[2]).encode("utf-8")).digest(), int(r[0])
        ))
        if len(pool) < need:
            raise ValueError(f"insufficient {split} roots")
        chosen.extend(pool[:need])
    chosen.sort(key=lambda r: int(r[0]))
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(header + "\n" + "\n".join("\t".join(r) for r in chosen) + "\n",
                     encoding="utf-8")
    report = {
        "schema": "jass.d4b.root_selection.v1",
        "verdict": "D4B_ROOTS_READY_V1",
        "source_roots": len(rows), "selected_roots": len(chosen),
        "root_counts": ROOT_COUNTS, "selector_prefix": ROOT_PREFIX,
        "target_blind": True, "selected_sha256": d4.sha_file(a.out),
        "teacher_label_reads": 0, "strength_games": 0,
    }
    a.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, sort_keys=True)); return 0


def cmd_shard(a: argparse.Namespace) -> int:
    header, rows = read_manifest(a.roots)
    if len(rows) != 512 or a.shards != SHARDS:
        raise ValueError("D4b shard contract drift")
    a.out_dir.mkdir(parents=True, exist_ok=True)
    counts = []
    for i in range(SHARDS):
        shard = rows[i::SHARDS]
        if len(shard) != 64:
            raise ValueError("D4b shard must contain 64 roots")
        p = a.out_dir / f"s{i:02d}-roots.tsv"
        p.write_text(header + "\n" + "\n".join("\t".join(r) for r in shard) + "\n",
                     encoding="utf-8")
        counts.append(len(shard))
    print(json.dumps({"shards": SHARDS, "counts": counts}, sort_keys=True)); return 0


def cmd_aggregate(a: argparse.Namespace) -> int:
    if len(a.report_in) != SHARDS:
        raise ValueError(f"expected {SHARDS} teacher reports")
    totals = {"roots": 0, "teacher_searches": 0, "node_overshoot_mismatches": 0,
              "total_nodes": 0, "total_eval_calls": 0, "eligible_cutoff_events": 0}
    splits = {"train": 0, "valid": 0, "test": 0}
    for p in a.report_in:
        row = json.loads(p.read_text(encoding="utf-8"))
        if row.get("schema") != "jass.d4.search_utility_teacher_export.v1":
            raise ValueError("teacher schema drift")
        if row.get("declared_code_sha") != a.code_sha or row.get("model_sha256") != a.model_sha256:
            raise ValueError("teacher provenance drift")
        if row.get("exact_nodes_per_root") != TEACHER_NODES or row.get("threads") != 1 or row.get("book") is not False:
            raise ValueError("teacher search contract drift")
        for key in FORBIDDEN:
            if row.get(key) != 0:
                raise ValueError(f"forbidden teacher read {key}")
        if any(row.get(k) != 0 for k in ("fits", "strength_games", "promotions", "bakes")):
            raise ValueError("teacher side-effect drift")
        for k in totals: totals[k] += int(row.get(k, 0))
        for k in splits: splits[k] += int(row.get("root_splits", {}).get(k, 0))
    if totals["roots"] != 512 or totals["teacher_searches"] != 512 or totals["node_overshoot_mismatches"] != 0:
        raise ValueError(f"teacher cardinality/exactness drift {totals}")
    if splits != ROOT_COUNTS or totals["eligible_cutoff_events"] <= 0:
        raise ValueError(f"teacher split/event drift {splits} events={totals['eligible_cutoff_events']}")
    out = {
        "schema": "jass.d4b.teacher_aggregate.v1", "verdict": "D4B_TEACHER_COMPLETE_V1",
        "code_sha": a.code_sha, "model_sha256": a.model_sha256, "shards": SHARDS,
        **totals, "root_splits": splits, "exact_nodes_per_root": TEACHER_NODES,
        "threads": 1, "book": False, "fits": 0, "strength_games": 0,
        "promotions": 0, "bakes": 0, **{k: 0 for k in FORBIDDEN},
    }
    a.out.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(out, sort_keys=True)); return 0


def phase_counts(path: Path, split: str) -> dict[str, int]:
    configure_base()
    rows = d4.load_selected(path, split)
    out = {name: 0 for name in d4.PHASES}
    for row in rows:
        out[d4.PHASES[d4.phase_for_pieces(int(row["parent_piece_count"]))]] += 1
    return out


def cmd_prepare(a: argparse.Namespace) -> int:
    configure_base()
    tmp_report = a.report.with_name(a.report.name + ".base-d4.json")
    ns = SimpleNamespace(roots=a.roots, teacher=[str(p) for p in a.teacher],
                         train=a.train, valid=a.valid, test=a.test, report=tmp_report)
    rc = d4.prepare(ns)
    files_ready = all(p.exists() and p.stat().st_size > 0 for p in (a.train, a.valid, a.test))
    base = json.loads(tmp_report.read_text(encoding="utf-8")) if tmp_report.exists() else {}
    if not files_ready:
        out = {
            "schema": "jass.d4b.prepare.v1", "verdict": "D4B_MICRO_OFFLINE_INVALID_V1",
            "reason": "exact_example_support_insufficient", "base_prepare": base,
            "exact_counts": EXACT_COUNTS, "phase_quota_gate": False,
            "fits": 0, "strength_games": 0,
        }
        a.report.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps(out, sort_keys=True)); return 4
    for split, path in (("train", a.train), ("valid", a.valid), ("test", a.test)):
        d4.load_selected(path, split)
    out = {
        "schema": "jass.d4b.prepare.v1", "verdict": "D4B_EXAMPLES_READY_V1",
        "teacher_event_rows": int(base.get("teacher_event_rows", 0)),
        "eligible_after_cross_split_filter": base.get("eligible_after_cross_split_filter", {}),
        "cross_split_keys": int(base.get("cross_split_keys", 0)),
        "cross_split_event_occurrences_dropped": int(base.get("cross_split_event_occurrences_dropped", 0)),
        "selected_counts": EXACT_COUNTS,
        "selected_sha256": {"train": d4.sha_file(a.train), "valid": d4.sha_file(a.valid), "test": d4.sha_file(a.test)},
        "phase_counts": {"train": phase_counts(a.train, "train"), "valid": phase_counts(a.valid, "valid"), "test": phase_counts(a.test, "test")},
        "phase_quota_gate": False, "example_selector_prefix": EXAMPLE_PREFIX,
        "features": list(d4.FEATURES), "feature_width": d4.FEATURE_WIDTH,
        "phase_blocks": 4, "model_width": d4.WIDTH,
        "fits": 0, "strength_games": 0, "promotions": 0, "bakes": 0,
        "base_prepare_return_code": rc,
    }
    a.report.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(out, sort_keys=True)); return 0


def cmd_fit(a: argparse.Namespace) -> int:
    configure_base()
    ns = SimpleNamespace(train=a.train, model=a.model, report=a.report)
    return int(d4.fit(ns))


def metric_view(m: dict) -> dict:
    return {"cross_entropy": float(m["cross_entropy"]), "top1": float(m["top1"]), "mrr": float(m["mrr"])}


def cmd_readout(a: argparse.Namespace) -> int:
    configure_base()
    prep = json.loads(a.prepare_report.read_text(encoding="utf-8"))
    fit = json.loads(a.fit_report.read_text(encoding="utf-8"))
    teacher = json.loads(a.teacher_report.read_text(encoding="utf-8"))
    if prep.get("verdict") != "D4B_EXAMPLES_READY_V1" or teacher.get("verdict") != "D4B_TEACHER_COMPLETE_V1":
        raise ValueError("D4b provenance not ready")
    if fit.get("verdict") != "D4_SEARCH_UTILITY_FIT_COMPLETE_V1" or fit.get("fits") != 1:
        raise ValueError("D4b fit provenance drift")
    model = np.load(a.model, allow_pickle=False)
    if model.dtype != np.dtype(np.float64) or model.shape != (d4.WIDTH,) or not np.all(np.isfinite(model)):
        raise ValueError("D4b model shape/dtype drift")
    if fit.get("model", {}).get("sha256") != d4.sha_file(a.model):
        raise ValueError("D4b model SHA drift")
    valid = d4.load_selected(a.valid, "valid"); test = d4.load_selected(a.test, "test")
    zero = np.zeros(d4.WIDTH, dtype=np.float64)
    vb, vd = d4.metrics(zero, valid), d4.metrics(model, valid)
    tb, td = d4.metrics(zero, test), d4.metrics(model, test)
    delta = np.asarray(tb["nll"] - td["nll"], dtype=np.float64)
    boot = d4.bootstrap_mean(delta)
    phase = {}
    for p, name in enumerate(d4.PHASES):
        sel = np.asarray(tb["phase"]) == p
        n = int(np.sum(sel))
        phase[name] = {
            "examples": n,
            "ce_gain": float(np.mean(delta[sel])) if n else None,
            "baseline_top1": float(np.mean(np.asarray(tb["ranks"])[sel] == 1)) if n else None,
            "d4b_top1": float(np.mean(np.asarray(td["ranks"])[sel] == 1)) if n else None,
        }
    valid_gain = float(vb["cross_entropy"] - vd["cross_entropy"])
    supported = valid_gain > 0.0 and boot["mean"] > 0.0 and boot["ci_low"] > 0.0 and td["top1"] > tb["top1"]
    verdict = "D4B_MICRO_OFFLINE_SUPPORTED_V1" if supported else "D4B_MICRO_OFFLINE_NOT_SUPPORTED_V1"
    out = {
        "schema": "jass.d4b.offline_terminal.v1", "verdict": verdict,
        "model_sha256": d4.sha_file(a.model), "value_model_sha256": a.wdl_sha256,
        "teacher_searches": 512, "teacher_nodes_per_root": TEACHER_NODES,
        "valid": {**metric_view(vd), "baseline_cross_entropy": float(vb["cross_entropy"]), "baseline_top1": float(vb["top1"]), "ce_gain": valid_gain},
        "test": {**metric_view(td), "baseline_cross_entropy": float(tb["cross_entropy"]), "baseline_top1": float(tb["top1"]),
                 "ce_gain": float(tb["cross_entropy"] - td["cross_entropy"]), "bootstrap_ce_gain": boot, "by_phase": phase},
        "gates": {"valid_ce_gain_gt_0": valid_gain > 0.0, "test_mean_ce_gain_gt_0": boot["mean"] > 0.0,
                  "test_lcb95_ce_gain_gt_0": boot["ci_low"] > 0.0, "test_top1_gt_baseline": td["top1"] > tb["top1"]},
        "phase_quota_gate": False, "scan_gate0_authorized": supported,
        "strength_games": 0, "selfplay_games": 0, "promotions": 0, "bakes": 0,
        "strength_authorized": False,
    }
    a.report.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(out, sort_keys=True)); return 0


def main() -> int:
    ap = argparse.ArgumentParser(); sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("select"); p.add_argument("--roots", type=Path, required=True); p.add_argument("--out", type=Path, required=True); p.add_argument("--report", type=Path, required=True); p.set_defaults(fn=cmd_select)
    p = sub.add_parser("shard"); p.add_argument("--roots", type=Path, required=True); p.add_argument("--shards", type=int, required=True); p.add_argument("--out-dir", type=Path, required=True); p.set_defaults(fn=cmd_shard)
    p = sub.add_parser("aggregate"); p.add_argument("--report-in", type=Path, action="append", required=True); p.add_argument("--code-sha", required=True); p.add_argument("--model-sha256", required=True); p.add_argument("--out", type=Path, required=True); p.set_defaults(fn=cmd_aggregate)
    p = sub.add_parser("prepare"); p.add_argument("--roots", type=Path, required=True); p.add_argument("--teacher", type=Path, action="append", required=True); p.add_argument("--train", type=Path, required=True); p.add_argument("--valid", type=Path, required=True); p.add_argument("--test", type=Path, required=True); p.add_argument("--report", type=Path, required=True); p.set_defaults(fn=cmd_prepare)
    p = sub.add_parser("fit"); p.add_argument("--train", type=Path, required=True); p.add_argument("--model", type=Path, required=True); p.add_argument("--report", type=Path, required=True); p.set_defaults(fn=cmd_fit)
    p = sub.add_parser("readout"); p.add_argument("--model", type=Path, required=True); p.add_argument("--valid", type=Path, required=True); p.add_argument("--test", type=Path, required=True); p.add_argument("--prepare-report", type=Path, required=True); p.add_argument("--fit-report", type=Path, required=True); p.add_argument("--teacher-report", type=Path, required=True); p.add_argument("--wdl-sha256", required=True); p.add_argument("--report", type=Path, required=True); p.set_defaults(fn=cmd_readout)
    a = ap.parse_args()
    try: return int(a.fn(a))
    except (OSError, ValueError, KeyError, json.JSONDecodeError, d4.D4Error) as exc:
        print(f"d4b_search_utility_micro: {exc}", file=__import__('sys').stderr); return 2


if __name__ == "__main__":
    raise SystemExit(main())
