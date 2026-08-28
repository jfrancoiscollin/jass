#!/usr/bin/env python3
"""Preregistered M5 fresh deep transfer confirmation readout.

Consumes only frozen fresh parents, their 50k/200k deep sibling labels, and
scalar scores from byte-frozen T0/T1 PJTW evaluators.  It performs no fit,
retuning, game play, or runtime micro-search.
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import numpy as np

PHASES = ("P0", "P1", "P2", "P3")
EXACT_SENTINEL = 2
BOOTSTRAP_SAMPLES = 100_000
BOOTSTRAP_SEED = 2026090221


@dataclass(frozen=True)
class Parent:
    parent_id: int
    stm: int
    phase: str
    pieces: int
    legal_moves: int


@dataclass(frozen=True)
class Sibling:
    row_index: int
    parent_id: int
    parent_stm: int
    exact_parent_utility: int
    t_baseline_parent: float
    q50_parent: float
    q200_parent: float


def load_parents(path: Path) -> dict[int, Parent]:
    out: dict[int, Parent] = {}
    with path.open(newline="", encoding="utf-8") as f:
        rd = csv.DictReader(f, delimiter="\t")
        req = {"parent_id", "parent_stm", "phase", "pieces", "legal_moves"}
        if rd.fieldnames is None or not req.issubset(rd.fieldnames):
            raise ValueError(f"M5 parent metadata drift: {rd.fieldnames!r}")
        for r in rd:
            p = Parent(int(r["parent_id"]), int(r["parent_stm"]), r["phase"],
                       int(r["pieces"]), int(r["legal_moves"]))
            if p.parent_id in out or p.stm not in (0, 1) or p.phase not in PHASES:
                raise ValueError("invalid/duplicate M5 parent metadata")
            if not (9 <= p.pieces <= 40 and 2 <= p.legal_moves <= 16):
                raise ValueError("M5 parent outside frozen support")
            out[p.parent_id] = p
    if sorted(out) != list(range(len(out))):
        raise ValueError("M5 parent ids must be contiguous")
    if len(out) != 4000:
        raise ValueError(f"M5 requires exactly 4000 parents, got {len(out)}")
    phase_counts = {ph: sum(p.phase == ph for p in out.values()) for ph in PHASES}
    if phase_counts != {ph: 1000 for ph in PHASES}:
        raise ValueError(f"M5 phase quota drift: {phase_counts}")
    return out


def load_groups(path: Path, parents: dict[int, Parent]) -> list[Sibling]:
    out: list[Sibling] = []
    with path.open(newline="", encoding="utf-8") as f:
        rd = csv.DictReader(f, delimiter="\t")
        req = {"row_index", "parent_id", "parent_stm", "exact_parent_utility",
               "t_baseline_parent", "q50_parent", "q200_parent"}
        if rd.fieldnames is None or not req.issubset(rd.fieldnames):
            raise ValueError(f"M5 teacher group fields drift: {rd.fieldnames!r}")
        for r in rd:
            s = Sibling(int(r["row_index"]), int(r["parent_id"]), int(r["parent_stm"]),
                        int(r["exact_parent_utility"]), float(r["t_baseline_parent"]),
                        float(r["q50_parent"]), float(r["q200_parent"]))
            p = parents.get(s.parent_id)
            if p is None or p.stm != s.parent_stm:
                raise ValueError("M5 teacher/parent identity drift")
            if s.exact_parent_utility not in (-1, 0, 1, EXACT_SENTINEL):
                raise ValueError("invalid exact utility")
            out.append(s)
    if [s.row_index for s in out] != list(range(len(out))):
        raise ValueError("M5 sibling row_index drift")
    return out


def stable_relation(a: Sibling, b: Sibling) -> int:
    if a.parent_id != b.parent_id:
        raise ValueError("stable relation across parents")
    if (a.exact_parent_utility != EXACT_SENTINEL and
            b.exact_parent_utility != EXACT_SENTINEL and
            a.exact_parent_utility != b.exact_parent_utility):
        return 1 if a.exact_parent_utility > b.exact_parent_utility else -1
    d50 = a.q50_parent - b.q50_parent
    d200 = a.q200_parent - b.q200_parent
    if d50 == 0 or d200 == 0 or ((d50 > 0) != (d200 > 0)):
        return 0
    if abs(d50) < 10 or abs(d200) < 30:
        return 0
    return 1 if d200 > 0 else -1


def accepted_pairs(parent_rows: dict[int, list[int]], meta: list[Sibling]) -> dict[int, list[tuple[int, int]]]:
    out: dict[int, list[tuple[int, int]]] = {}
    for pid in sorted(parent_rows):
        rows = sorted(parent_rows[pid])
        pairs: list[tuple[int, int]] = []
        for pos, i in enumerate(rows):
            for j in rows[pos + 1:]:
                rel = stable_relation(meta[i], meta[j])
                if rel > 0:
                    pairs.append((i, j))
                elif rel < 0:
                    pairs.append((j, i))
        if pairs:
            out[pid] = pairs
    return out


def load_scores(path: Path, report_path: Path, meta: list[Sibling]) -> tuple[np.ndarray, np.ndarray, dict]:
    rep = json.loads(report_path.read_text(encoding="utf-8"))
    if rep.get("schema") != "jass.micro_search_m5_scalar_score.v1":
        raise ValueError("M5 scalar score report drift")
    if rep.get("rows") != len(meta) or rep.get("score_convention") != "higher_is_better_for_parent":
        raise ValueError("M5 scalar score row/convention drift")
    if not rep.get("t0_t1_serialize_reload"):
        raise ValueError("T0/T1 were not serialize/reloaded")
    if rep.get("d_present_at_inference") or rep.get("micro_search_present_at_inference") or rep.get("runtime_micro_search"):
        raise ValueError("forbidden inference dependency in M5 scalar scorer")
    t0 = np.empty(len(meta), dtype=np.float64)
    t1 = np.empty(len(meta), dtype=np.float64)
    seen = 0
    with path.open(newline="", encoding="utf-8") as f:
        rd = csv.DictReader(f, delimiter="\t")
        if rd.fieldnames != ["row_index", "t0_parent", "t1_parent"]:
            raise ValueError(f"M5 scalar score fields drift: {rd.fieldnames!r}")
        for r in rd:
            i = int(r["row_index"])
            if i != seen or i >= len(meta):
                raise ValueError("M5 scalar score row ordering drift")
            t0[i] = float(r["t0_parent"])
            t1[i] = float(r["t1_parent"])
            seen += 1
    if seen != len(meta) or not np.all(np.isfinite(t0)) or not np.all(np.isfinite(t1)):
        raise ValueError("M5 scalar score count/finite drift")
    teacher_t0 = np.asarray([m.t_baseline_parent for m in meta], dtype=np.float64)
    mismatch = int(np.count_nonzero(t0 != teacher_t0))
    if mismatch:
        raise ValueError(f"T0 scoring convention differs from deep teacher on {mismatch} rows")
    return t0, t1, rep


def parent_metrics(rows: list[int], pairs: list[tuple[int, int]], score: np.ndarray) -> tuple[float, float]:
    acc: list[float] = []
    incoming: set[int] = set()
    participating: set[int] = set()
    for good, bad in pairs:
        participating.update((good, bad))
        incoming.add(bad)
        if score[good] > score[bad]:
            acc.append(1.0)
        elif score[good] == score[bad]:
            acc.append(0.5)
        else:
            acc.append(0.0)
    teacher_top = participating - incoming
    if not acc or not teacher_top:
        raise ValueError("invalid M5 stable-pair graph")
    vals = np.asarray([score[i] for i in rows], dtype=np.float64)
    mx = np.max(vals)
    model_top = [rows[k] for k, v in enumerate(vals) if v == mx]
    return float(np.mean(acc)), float(np.mean([i in teacher_top for i in model_top]))


def metrics(parent_rows: dict[int, list[int]], pairs: dict[int, list[tuple[int, int]]],
            ids: list[int], score: np.ndarray) -> dict[str, np.ndarray]:
    pp, tt = [], []
    for pid in ids:
        a, b = parent_metrics(parent_rows[pid], pairs[pid], score)
        pp.append(a); tt.append(b)
    return {"pairwise": np.asarray(pp, dtype=np.float64),
            "top_hit": np.asarray(tt, dtype=np.float64)}


def bootstrap_delta(a: dict[str, np.ndarray], b: dict[str, np.ndarray], samples: int, seed: int) -> dict:
    pd = a["pairwise"] - b["pairwise"]
    td = a["top_hit"] - b["top_hit"]
    if len(pd) == 0 or len(pd) != len(td):
        raise ValueError("M5 bootstrap requires nonempty parent deltas")
    rng = np.random.default_rng(seed)
    n = len(pd)
    pb = np.empty(samples, dtype=np.float64)
    tb = np.empty(samples, dtype=np.float64)
    batch = 128
    for start in range(0, samples, batch):
        stop = min(samples, start + batch)
        idx = rng.integers(0, n, size=(stop - start, n))
        pb[start:stop] = pd[idx].mean(axis=1)
        tb[start:stop] = td[idx].mean(axis=1)
    def one(v: np.ndarray, boot: np.ndarray) -> dict:
        return {"mean": float(v.mean()), "ci_low": float(np.quantile(boot, 0.025)),
                "ci_high": float(np.quantile(boot, 0.975)),
                "probability_gt_zero": float(np.mean(boot > 0)),
                "samples": samples, "seed": seed, "cluster": "parent"}
    return {"pairwise": one(pd, pb), "top_hit": one(td, tb)}


def summarize(m: dict[str, np.ndarray]) -> dict[str, float]:
    return {k: float(v.mean()) for k, v in m.items()}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--parents", type=Path, required=True)
    ap.add_argument("--groups", type=Path, required=True)
    ap.add_argument("--scores", type=Path, required=True)
    ap.add_argument("--score-report", type=Path, required=True)
    ap.add_argument("--m4-summary", type=Path, required=True)
    ap.add_argument("--anchor-report", type=Path, required=True)
    ap.add_argument("--t1-sha", required=True)
    ap.add_argument("--report", type=Path, required=True)
    ap.add_argument("--bootstrap-samples", type=int, default=BOOTSTRAP_SAMPLES)
    ap.add_argument("--bootstrap-seed", type=int, default=BOOTSTRAP_SEED)
    args = ap.parse_args()

    if args.bootstrap_samples != BOOTSTRAP_SAMPLES or args.bootstrap_seed != BOOTSTRAP_SEED:
        raise SystemExit("M5 bootstrap science is frozen at 100000 / seed 2026090221")

    m4 = json.loads(args.m4_summary.read_text(encoding="utf-8"))
    if m4.get("verdict") != "MICRO_SEARCH_M4_T1_FROZEN" or m4.get("passed") is not True:
        raise ValueError("M4 T1 is not frozen PASS")
    if m4.get("t1_raw_sha256") != args.t1_sha:
        raise ValueError("M5 T1 SHA does not match frozen M4")
    if m4.get("d_present_at_inference") or m4.get("micro_search_present_at_inference") or m4.get("runtime_micro_search"):
        raise ValueError("forbidden M4 inference dependency")

    anchor = json.loads(args.anchor_report.read_text(encoding="utf-8"))
    anchor_ok = (anchor.get("schema") == "jass.micro_search_m4_anchor_drift.v1" and
                 anchor.get("states") == 500000 and anchor.get("serialize_reload") is True and
                 float(anchor.get("rms_abs_cp", 1e100)) <= 12.0 and
                 float(anchor.get("p99_abs_cp", 1e100)) <= 35.0 and
                 anchor.get("runtime_micro_search") is False)
    if not anchor_ok:
        raise ValueError("M5 serialize/reload anchor guard failed")

    parents = load_parents(args.parents)
    meta = load_groups(args.groups, parents)
    t0, t1, score_rep = load_scores(args.scores, args.score_report, meta)

    parent_rows: dict[int, list[int]] = defaultdict(list)
    for i, m in enumerate(meta):
        parent_rows[m.parent_id].append(i)
    if set(parent_rows) != set(parents):
        raise ValueError("deep teacher did not emit siblings for every M5 parent")
    pairs = accepted_pairs(parent_rows, meta)
    accepted = sorted(pairs)
    if not accepted:
        raise ValueError("M5 has no stable-pair support")

    m0 = metrics(parent_rows, pairs, accepted, t0)
    m1 = metrics(parent_rows, pairs, accepted, t1)
    boot = bootstrap_delta(m1, m0, args.bootstrap_samples, args.bootstrap_seed)

    phase = {}
    represented_phases: list[str] = []
    for ph in PHASES:
        ids = [p for p in accepted if parents[p].phase == ph]
        if ids:
            represented_phases.append(ph)
            a = metrics(parent_rows, pairs, ids, t1)["pairwise"]
            b = metrics(parent_rows, pairs, ids, t0)["pairwise"]
            phase[ph] = {"accepted_parents": len(ids), "t1_pairwise": float(a.mean()),
                         "t0_pairwise": float(b.mean()), "pairwise_delta": float((a-b).mean())}
        else:
            phase[ph] = {"accepted_parents": 0, "t1_pairwise": None,
                         "t0_pairwise": None, "pairwise_delta": None}

    colour = {}
    colour_ok = True
    for stm, name in ((0, "white"), (1, "black")):
        ids = [p for p in accepted if parents[p].stm == stm]
        if ids:
            a = metrics(parent_rows, pairs, ids, t1)["pairwise"]
            b = metrics(parent_rows, pairs, ids, t0)["pairwise"]
            d = float((a-b).mean())
            colour[name] = {"accepted_parents": len(ids), "t1_pairwise": float(a.mean()),
                            "t0_pairwise": float(b.mean()), "pairwise_delta": d}
            colour_ok = colour_ok and d > 0
        else:
            colour[name] = {"accepted_parents": 0, "t1_pairwise": None,
                            "t0_pairwise": None, "pairwise_delta": None}
            colour_ok = False

    gates = {
        "t1_minus_t0_pairwise_ci95_low_gt_zero": bool(boot["pairwise"]["ci_low"] > 0),
        "t1_minus_t0_top_hit_ci95_low_gt_zero": bool(boot["top_hit"]["ci_low"] > 0),
        "positive_pairwise_delta_every_represented_phase": bool(represented_phases and all(phase[p]["pairwise_delta"] > 0 for p in represented_phases)),
        "positive_pairwise_delta_both_colours": bool(colour_ok),
        "anchor_guards_survive_serialize_reload": bool(anchor_ok),
        "d_and_micro_search_absent_during_t1_scoring": bool(not score_rep["d_present_at_inference"] and not score_rep["micro_search_present_at_inference"] and not score_rep["runtime_micro_search"]),
    }
    passed = all(gates.values())
    verdict = "MICRO_SEARCH_TO_T_TRANSFER_ESTABLISHED" if passed else "MICRO_SEARCH_TO_T_TRANSFER_NOT_ESTABLISHED"
    report = {
        "schema": "jass.micro_search_m5_transfer_confirmation.v1",
        "verdict": verdict,
        "passed": passed,
        "experiment_terminal": not passed,
        "next_stage": "M6_strength_T1_alone" if passed else None,
        "t1_raw_sha256": args.t1_sha,
        "selected_parents": len(parents),
        "phase_selected": {ph: sum(p.phase == ph for p in parents.values()) for ph in PHASES},
        "accepted_parents": len(accepted),
        "accepted_by_phase": {ph: phase[ph]["accepted_parents"] for ph in PHASES},
        "accepted_by_colour": {k: v["accepted_parents"] for k, v in colour.items()},
        "stable_pairs": int(sum(len(v) for v in pairs.values())),
        "represented_phases": represented_phases,
        "metrics": {"t0": summarize(m0), "t1": summarize(m1)},
        "delta_t1_minus_t0": boot,
        "phase_deltas": phase,
        "colour_deltas": colour,
        "bootstrap": {"cluster": "parent", "samples": args.bootstrap_samples, "seed": args.bootstrap_seed},
        "stable_pair_rule": {"same_sign_50k_200k": True, "min_abs_d50_cp": 10,
                             "min_abs_d200_cp": 30, "exact_terminal_tb_wdl_precedence": True,
                             "teacher_target": "q200_parent"},
        "t0_score_matches_deep_teacher_all_rows": True,
        "anchor": {"states": anchor["states"], "rms_abs_cp": anchor["rms_abs_cp"],
                   "p99_abs_cp": anchor["p99_abs_cp"], "serialize_reload": anchor["serialize_reload"]},
        "gates": gates,
        "fits": 0,
        "pattern_eval_fits": 0,
        "t_refits": 0,
        "strength_games": 0,
        "runtime_micro_search": False,
        "micro_search_present_at_inference": False,
        "d_present_at_inference": False,
        "promotion_authorized": False,
        "automatic_promotion": False,
    }
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"verdict": verdict, "accepted_parents": len(accepted),
                      "pairwise_delta": boot["pairwise"], "top_hit_delta": boot["top_hit"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
