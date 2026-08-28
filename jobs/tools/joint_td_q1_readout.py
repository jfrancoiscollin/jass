#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Terminal preregistered Joint T+D Q1 deep-fresh readout.

No fit or candidate selection is possible here.  The script consumes the frozen
Q1 parent cohort, q1000/q50/q200 teacher rows, and inference-only scores from
S0..S4.  Stable-pair semantics are identical to the proven M5 contract, while
support and decision gates are exactly those preregistered for Q1.
"""
from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path

import numpy as np

PREREG_SHA = "b280fc1f4878133a41168f4bbc6a537eec526cdc"
T0_SHA = "319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1"
D1_SHA = "e91a55500713154f50be74db5d699b64d7684e1c078725d09e1d15e713549b49"
A6_SHA = "271733adb8441630e1bae77b85951c05caa452107d3e8af4782f577347be06ed"
B1_MANIFEST_SHA = "052090887dd45f40f14cdb2a336c34b3c5d27c61dd483f82349c3086cd9577c7"
C0_ARTIFACT_SHA = "2b51e8d36f3d0241ca5254de68a686808b6dbf619211c5bbdcc02879921493ba"
PHASES = ("P0", "P1", "P2", "P3")
EXACT_SENTINEL = 2
BOOTSTRAP_SAMPLES = 100_000
BOOTSTRAP_SEED = 2026090421


@dataclass(frozen=True)
class Parent:
    parent_id: int
    stm: int
    phase: str
    pieces: int
    legal_moves: int
    canonical: str


@dataclass(frozen=True)
class Sibling:
    row_index: int
    parent_id: int
    parent_stm: int
    exact_parent_utility: int
    t0: float
    q1000: float
    q50: float
    q200: float


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def load_parents(path: Path) -> dict[int, Parent]:
    out: dict[int, Parent] = {}
    with path.open(newline="", encoding="utf-8") as f:
        rd = csv.DictReader(f, delimiter="\t")
        req = {"parent_id", "parent_stm", "phase", "pieces", "legal_moves", "canonical_fingerprint"}
        if rd.fieldnames is None or not req.issubset(rd.fieldnames):
            raise ValueError(f"Q1 parent metadata drift: {rd.fieldnames!r}")
        for r in rd:
            p = Parent(int(r["parent_id"]), int(r["parent_stm"]), r["phase"], int(r["pieces"]),
                       int(r["legal_moves"]), r["canonical_fingerprint"].strip())
            if p.parent_id in out or p.stm not in (0, 1) or p.phase not in PHASES:
                raise ValueError("invalid/duplicate Q1 parent metadata")
            if not (9 <= p.pieces <= 40 and 2 <= p.legal_moves <= 16) or not p.canonical:
                raise ValueError("Q1 parent outside frozen support")
            out[p.parent_id] = p
    if sorted(out) != list(range(len(out))) or len(out) != 4000:
        raise ValueError(f"Q1 requires contiguous exactly 4000 parents, got {len(out)}")
    phase = {ph: sum(p.phase == ph for p in out.values()) for ph in PHASES}
    if phase != {ph: 1000 for ph in PHASES}:
        raise ValueError(f"Q1 phase quota drift: {phase}")
    if len({p.canonical for p in out.values()}) != 4000:
        raise ValueError("Q1 selected canonical fingerprints are not unique")
    return out


def load_groups(path: Path, parents: dict[int, Parent]) -> list[Sibling]:
    out: list[Sibling] = []
    with path.open(newline="", encoding="utf-8") as f:
        rd = csv.DictReader(f, delimiter="\t")
        req = {"row_index", "parent_id", "parent_stm", "exact_parent_utility",
               "t_baseline_parent", "q1000_parent", "q50_parent", "q200_parent"}
        if rd.fieldnames is None or not req.issubset(rd.fieldnames):
            raise ValueError(f"Q1 teacher group fields drift: {rd.fieldnames!r}")
        for r in rd:
            x = Sibling(int(r["row_index"]), int(r["parent_id"]), int(r["parent_stm"]),
                        int(r["exact_parent_utility"]), float(r["t_baseline_parent"]),
                        float(r["q1000_parent"]), float(r["q50_parent"]), float(r["q200_parent"]))
            p = parents.get(x.parent_id)
            if p is None or p.stm != x.parent_stm:
                raise ValueError("Q1 teacher/parent identity drift")
            if x.exact_parent_utility not in (-1, 0, 1, EXACT_SENTINEL):
                raise ValueError("invalid Q1 exact utility")
            out.append(x)
    if [x.row_index for x in out] != list(range(len(out))) or not out:
        raise ValueError("Q1 sibling row ordering/empty drift")
    return out


def stable_relation(a: Sibling, b: Sibling) -> int:
    """Exact M5 semantics: terminal/TB W>D>L first, otherwise q50/q200 stability."""
    if a.parent_id != b.parent_id:
        raise ValueError("stable relation across parents")
    if (a.exact_parent_utility != EXACT_SENTINEL and b.exact_parent_utility != EXACT_SENTINEL
            and a.exact_parent_utility != b.exact_parent_utility):
        return 1 if a.exact_parent_utility > b.exact_parent_utility else -1
    d50 = a.q50 - b.q50
    d200 = a.q200 - b.q200
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
                if rel > 0: pairs.append((i, j))
                elif rel < 0: pairs.append((j, i))
        if pairs: out[pid] = pairs
    return out


def load_scalar(path: Path, report_path: Path, meta: list[Sibling]) -> tuple[np.ndarray, np.ndarray, dict]:
    rep = json.loads(report_path.read_text(encoding="utf-8"))
    if rep.get("schema") != "jass.micro_search_m5_scalar_score.v1" or rep.get("rows") != len(meta):
        raise ValueError("Q1 T0/A6 scalar score report drift")
    if rep.get("score_convention") != "higher_is_better_for_parent" or not rep.get("t0_t1_serialize_reload"):
        raise ValueError("Q1 T0/A6 score semantics drift")
    if rep.get("fits") != 0 or rep.get("strength_games") != 0 or rep.get("promotion_authorized") is not False:
        raise ValueError("forbidden scalar scorer activity")
    t0 = np.empty(len(meta)); a6 = np.empty(len(meta)); seen = 0
    with path.open(newline="", encoding="utf-8") as f:
        rd = csv.DictReader(f, delimiter="\t")
        if rd.fieldnames != ["row_index", "t0_parent", "t1_parent"]:
            raise ValueError("Q1 T0/A6 scalar TSV fields drift")
        for r in rd:
            i = int(r["row_index"])
            if i != seen: raise ValueError("Q1 scalar row ordering drift")
            t0[i] = float(r["t0_parent"]); a6[i] = float(r["t1_parent"]); seen += 1
    if seen != len(meta) or not np.all(np.isfinite(t0)) or not np.all(np.isfinite(a6)):
        raise ValueError("Q1 scalar score count/finite drift")
    teacher_t0 = np.asarray([x.t0 for x in meta], dtype=np.float64)
    if np.count_nonzero(t0 != teacher_t0):
        raise ValueError("production T0 differs from teacher t_baseline_parent")
    return t0, a6, rep


def load_static(path: Path, report_path: Path, meta: list[Sibling]) -> tuple[dict[str, np.ndarray], dict]:
    rep = json.loads(report_path.read_text(encoding="utf-8"))
    if rep.get("schema") != "jass.joint_td_q1_static_score.v1" or rep.get("rows") != len(meta):
        raise ValueError("Q1 frozen static score report drift")
    ids = rep.get("candidate_identities", {})
    expected = {"S0_T0": T0_SHA, "S1_D1": D1_SHA, "S2_A6_G0": A6_SHA,
                "S3_B1_manifest": B1_MANIFEST_SHA, "S4_C0_artifact": C0_ARTIFACT_SHA}
    if ids != expected or rep.get("freeze_verdict") != "JOINT_TD_CANDIDATE_FREEZE_READY":
        raise ValueError("Q1 candidate identities changed after freeze")
    for k in ("d1_refits", "b1_refits", "c0_refits", "post_freeze_fits", "selfplay", "strength_games"):
        if rep.get(k) != 0: raise ValueError(f"forbidden Q1 activity: {k}")
    if rep.get("promotion_authorized") is not False:
        raise ValueError("Q1 promotion must be false")
    out = {k: np.empty(len(meta), dtype=np.float64) for k in ("D1", "B1", "C0")}
    seen = 0
    with path.open(newline="", encoding="utf-8") as f:
        rd = csv.DictReader(f, delimiter="\t")
        if rd.fieldnames != ["row_index", "d1_parent", "b1_parent", "c0_parent"]:
            raise ValueError("Q1 frozen static TSV fields drift")
        for r in rd:
            i = int(r["row_index"])
            if i != seen: raise ValueError("Q1 frozen static row ordering drift")
            out["D1"][i] = float(r["d1_parent"]); out["B1"][i] = float(r["b1_parent"]); out["C0"][i] = float(r["c0_parent"])
            seen += 1
    if seen != len(meta) or not all(np.all(np.isfinite(v)) for v in out.values()):
        raise ValueError("Q1 frozen static score count/finite drift")
    return out, rep


def parent_metric(rows: list[int], pairs: list[tuple[int, int]], score: np.ndarray) -> tuple[float, float, int]:
    wins: list[float] = []; incoming: set[int] = set(); participating: set[int] = set()
    for good, bad in pairs:
        participating.update((good, bad)); incoming.add(bad)
        wins.append(1.0 if score[good] > score[bad] else 0.5 if score[good] == score[bad] else 0.0)
    teacher_top = participating - incoming
    if not wins or not teacher_top: raise ValueError("invalid Q1 stable-pair graph")
    vals = np.asarray([score[i] for i in rows]); mx = np.max(vals)
    model_top = [rows[k] for k, v in enumerate(vals) if v == mx]
    return float(np.mean(wins)), float(np.mean([i in teacher_top for i in model_top])), len(pairs)


def metric_arrays(parent_rows: dict[int, list[int]], pairs: dict[int, list[tuple[int, int]]], ids: list[int], score: np.ndarray) -> dict[str, np.ndarray]:
    pw, th, npairs = [], [], []
    for pid in ids:
        a, b, c = parent_metric(parent_rows[pid], pairs[pid], score)
        pw.append(a); th.append(b); npairs.append(c)
    return {"pairwise": np.asarray(pw), "top_hit": np.asarray(th), "stable_pairs": np.asarray(npairs, dtype=np.int64)}


def summarize(m: dict[str, np.ndarray]) -> dict:
    return {"pairwise": float(m["pairwise"].mean()), "top_hit": float(m["top_hit"].mean()),
            "parents": int(len(m["pairwise"])), "stable_pairs": int(m["stable_pairs"].sum())}


def bootstrap_delta(a: dict[str, np.ndarray], b: dict[str, np.ndarray], samples: int, seed: int) -> dict:
    if len(a["pairwise"]) != len(b["pairwise"]) or len(a["pairwise"]) == 0:
        raise ValueError("Q1 bootstrap alignment/empty drift")
    pd = a["pairwise"] - b["pairwise"]; td = a["top_hit"] - b["top_hit"]
    rng = np.random.default_rng(seed); n = len(pd)
    pb = np.empty(samples); tb = np.empty(samples); batch = 128
    for st in range(0, samples, batch):
        en = min(samples, st + batch); ix = rng.integers(0, n, size=(en - st, n))
        pb[st:en] = pd[ix].mean(axis=1); tb[st:en] = td[ix].mean(axis=1)
    def one(point: np.ndarray, boot: np.ndarray) -> dict:
        return {"mean": float(point.mean()), "ci_low": float(np.quantile(boot, .025)),
                "ci_high": float(np.quantile(boot, .975)), "p_gt_0": float(np.mean(boot > 0)),
                "samples": samples, "seed": seed, "cluster": "parent"}
    return {"pairwise": one(pd, pb), "top_hit": one(td, tb)}


def ratio(num: float, den: float) -> dict:
    if den <= 0:
        return {"value": None, "numerator": num, "denominator": den, "guard": "denominator_must_be_positive", "defined": False}
    return {"value": num / den, "numerator": num, "denominator": den, "guard": "denominator_positive", "defined": True}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--parents", type=Path, required=True)
    ap.add_argument("--groups", type=Path, required=True)
    ap.add_argument("--scalar-scores", type=Path, required=True)
    ap.add_argument("--scalar-report", type=Path, required=True)
    ap.add_argument("--static-scores", type=Path, required=True)
    ap.add_argument("--static-report", type=Path, required=True)
    ap.add_argument("--candidate-freeze", type=Path, required=True)
    ap.add_argument("--selection-summary", type=Path, required=True)
    ap.add_argument("--overlap-proof", type=Path, required=True)
    ap.add_argument("--teacher-report", type=Path, required=True)
    ap.add_argument("--report", type=Path, required=True)
    ap.add_argument("--bootstrap-samples", type=int, default=BOOTSTRAP_SAMPLES)
    ap.add_argument("--bootstrap-seed", type=int, default=BOOTSTRAP_SEED)
    args = ap.parse_args()
    if args.bootstrap_samples != BOOTSTRAP_SAMPLES or args.bootstrap_seed != BOOTSTRAP_SEED:
        raise SystemExit("Q1 bootstrap is frozen at 100000 / seed 2026090421")

    freeze = json.loads(args.candidate_freeze.read_text(encoding="utf-8"))
    if freeze.get("verdict") != "JOINT_TD_CANDIDATE_FREEZE_READY" or freeze.get("prereg_sha") != PREREG_SHA:
        raise ValueError("Q1 candidate freeze auth failed")
    selection = json.loads(args.selection_summary.read_text(encoding="utf-8"))
    overlap = json.loads(args.overlap_proof.read_text(encoding="utf-8"))
    teacher = json.loads(args.teacher_report.read_text(encoding="utf-8"))
    if selection.get("verdict") != "JOINT_TD_Q1_SELECTION_READY" or selection.get("selection_seed") != 2026090420:
        raise ValueError("Q1 target-blind selection auth failed")
    if overlap.get("passed") is not True or overlap.get("m3_canonical_overlap") != 0 or overlap.get("m5_canonical_overlap") != 0:
        raise ValueError("Q1 forbidden cohort overlap")
    if teacher.get("input_parents") != 4000 or teacher.get("cheap_budget_nodes") != 1000 or teacher.get("screen_budget_nodes") != 50000 or teacher.get("teacher_budget_nodes") != 200000:
        raise ValueError("Q1 deep teacher budget/support receipt drift")
    if teacher.get("stable_pairs_selected") is not False or teacher.get("fits") != 0 or teacher.get("strength_games") != 0 or teacher.get("promotion_authorized") is not False:
        raise ValueError("Q1 teacher crossed forbidden surface")

    parents = load_parents(args.parents); meta = load_groups(args.groups, parents)
    t0, a6, _ = load_scalar(args.scalar_scores, args.scalar_report, meta)
    frozen, static_rep = load_static(args.static_scores, args.static_report, meta)
    scores: dict[str, np.ndarray] = {
        "T0": t0, "D1": frozen["D1"], "A6_G0": a6, "B1": frozen["B1"], "C0": frozen["C0"],
        "q1000": np.asarray([x.q1000 for x in meta], dtype=np.float64),
    }
    if not np.all(np.isfinite(scores["q1000"])):
        raise ValueError("non-finite q1000 diagnostic")

    parent_rows: dict[int, list[int]] = defaultdict(list)
    for i, x in enumerate(meta): parent_rows[x.parent_id].append(i)
    if set(parent_rows) != set(parents):
        raise ValueError("Q1 teacher did not emit siblings for every selected parent")
    pairs = accepted_pairs(parent_rows, meta); accepted = sorted(pairs)

    accepted_phase = {ph: sum(parents[p].phase == ph for p in accepted) for ph in PHASES}
    accepted_colour = {name: sum(parents[p].stm == stm for p in accepted) for stm, name in ((0, "white"), (1, "black"))}
    support_gates = {
        "selected_exactly_4000": len(parents) == 4000,
        "selected_1000_each_phase": {ph: sum(p.phase == ph for p in parents.values()) for ph in PHASES} == {ph: 1000 for ph in PHASES},
        "accepted_at_least_3000": len(accepted) >= 3000,
        "accepted_each_phase_at_least_500": all(accepted_phase[ph] >= 500 for ph in PHASES),
        "accepted_each_colour_at_least_1200": all(accepted_colour[c] >= 1200 for c in ("white", "black")),
        "each_accepted_parent_has_stable_pair": all(len(pairs[p]) >= 1 for p in accepted),
        "forbidden_overlap_zero": overlap.get("m3_canonical_overlap") == 0 and overlap.get("m5_canonical_overlap") == 0,
        "candidate_freeze_auth_pass": freeze.get("verdict") == "JOINT_TD_CANDIDATE_FREEZE_READY",
    }
    support_pass = all(support_gates.values())

    base = {
        "schema": "jass.joint_td_q1_deep_fresh_confirmation.v1",
        "prereg_sha": PREREG_SHA,
        "experiment_terminal": True,
        "selected_parents": len(parents),
        "phase_selected": {ph: sum(p.phase == ph for p in parents.values()) for ph in PHASES},
        "accepted_parents": len(accepted),
        "accepted_by_phase": accepted_phase,
        "accepted_by_colour": accepted_colour,
        "stable_pairs": int(sum(len(pairs[p]) for p in accepted)),
        "support_gates": support_gates,
        "support_pass": support_pass,
        "selection_seed": 2026090420,
        "bootstrap": {"cluster": "parent", "samples": BOOTSTRAP_SAMPLES, "seed": BOOTSTRAP_SEED},
        "candidate_identities": {"S0_T0": T0_SHA, "S1_D1": D1_SHA, "S2_A6_G0": A6_SHA,
                                 "S3_B1_manifest": B1_MANIFEST_SHA, "S4_C0_artifact": C0_ARTIFACT_SHA},
        "candidate_freeze_sha256": sha256(args.candidate_freeze),
        "selection_summary_sha256": sha256(args.selection_summary),
        "overlap_proof": overlap,
        "teacher_contract": {"q1000": 1000, "q50": 50000, "q200": 200000, "q1000_controls_acceptance": False},
        "post_freeze_fits": int(static_rep.get("post_freeze_fits", -1)),
        "d1_refits": int(static_rep.get("d1_refits", -1)),
        "b1_refits": int(static_rep.get("b1_refits", -1)),
        "c0_refits": int(static_rep.get("c0_refits", -1)),
        "selfplay": int(static_rep.get("selfplay", -1)),
        "strength_games": int(static_rep.get("strength_games", -1)),
        "promotion_authorized": bool(static_rep.get("promotion_authorized", True)),
        "runtime_or_elo_authorized": False,
    }

    if not support_pass:
        base.update({"passed": False, "verdict": "JOINT_TD_DEEP_FRESH_SUPPORT_NOT_ESTABLISHED",
                     "metrics": None, "principal_bootstrap_cis": None,
                     "secondary_a6_g0_deep_transfer_confirmed": False,
                     "next_stage": "STOP_no_runtime_or_elo"})
        args.report.write_text(json.dumps(base, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps({"verdict": base["verdict"], "accepted_parents": len(accepted)}, sort_keys=True))
        return 0

    # All metrics use exactly the same accepted parents and stable-pair graph.
    arrays = {name: metric_arrays(parent_rows, pairs, accepted, score) for name, score in scores.items()}
    metrics = {name: {"global": summarize(arrays[name]), "phase": {}, "colour": {}} for name in scores}
    for ph in PHASES:
        ids = [p for p in accepted if parents[p].phase == ph]
        for name, score in scores.items(): metrics[name]["phase"][ph] = summarize(metric_arrays(parent_rows, pairs, ids, score))
    for stm, colour in ((0, "white"), (1, "black")):
        ids = [p for p in accepted if parents[p].stm == stm]
        for name, score in scores.items(): metrics[name]["colour"][colour] = summarize(metric_arrays(parent_rows, pairs, ids, score))

    comparisons = [
        ("C0_minus_D1", "C0", "D1"), ("C0_minus_T0", "C0", "T0"),
        ("A6_G0_minus_T0", "A6_G0", "T0"), ("B1_minus_T0", "B1", "T0"),
        ("B1_minus_D1", "B1", "D1"), ("C0_minus_B1", "C0", "B1"),
        ("q1000_minus_C0", "q1000", "C0"),
    ]
    cis = {label: bootstrap_delta(arrays[a], arrays[b], BOOTSTRAP_SAMPLES, BOOTSTRAP_SEED) for label, a, b in comparisons}

    def point_delta(a: str, b: str, dimension: str, key: str) -> float:
        return float(metrics[a][dimension][key]["pairwise"] - metrics[b][dimension][key]["pairwise"])
    c0d_phase = {ph: point_delta("C0", "D1", "phase", ph) for ph in PHASES}
    c0d_colour = {c: point_delta("C0", "D1", "colour", c) for c in ("white", "black")}
    a6t_phase = {ph: point_delta("A6_G0", "T0", "phase", ph) for ph in PHASES}
    a6t_colour = {c: point_delta("A6_G0", "T0", "colour", c) for c in ("white", "black")}

    identities_unchanged = (
        static_rep.get("candidate_identities") == {"S0_T0": T0_SHA, "S1_D1": D1_SHA, "S2_A6_G0": A6_SHA,
                                                   "S3_B1_manifest": B1_MANIFEST_SHA, "S4_C0_artifact": C0_ARTIFACT_SHA}
        and freeze["candidates"]["S0_T0"]["sha256"] == T0_SHA
        and freeze["candidates"]["S1_D1"]["sha256"] == D1_SHA
        and freeze["candidates"]["S2_A6_G0"]["sha256"] == A6_SHA
        and freeze["candidates"]["S3_B1"]["manifest_sha256"] == B1_MANIFEST_SHA
        and freeze["candidates"]["S4_C0"]["artifact_sha256"] == C0_ARTIFACT_SHA
    )
    clean = (base["post_freeze_fits"] == base["d1_refits"] == base["b1_refits"] == base["c0_refits"] == 0
             and base["selfplay"] == base["strength_games"] == 0 and base["promotion_authorized"] is False)
    primary_gates = {
        "support": True,
        "c0_minus_d1_pairwise_ci95_low_gt_zero": cis["C0_minus_D1"]["pairwise"]["ci_low"] > 0,
        "c0_minus_d1_top_hit_ci95_low_gt_zero": cis["C0_minus_D1"]["top_hit"]["ci_low"] > 0,
        "c0_minus_t0_pairwise_ci95_low_gt_zero": cis["C0_minus_T0"]["pairwise"]["ci_low"] > 0,
        "c0_minus_d1_positive_pairwise_delta_p0_p1_p2_p3": all(v > 0 for v in c0d_phase.values()),
        "c0_minus_d1_positive_pairwise_delta_both_colours": all(v > 0 for v in c0d_colour.values()),
        "all_candidate_identities_unchanged": identities_unchanged,
        "zero_post_freeze_fit_refit_selfplay_strength_promotion": clean,
    }
    passed = all(primary_gates.values())
    a6_gates = {
        "a6_minus_t0_pairwise_ci95_low_gt_zero": cis["A6_G0_minus_T0"]["pairwise"]["ci_low"] > 0,
        "a6_minus_t0_top_hit_ci95_low_gt_zero": cis["A6_G0_minus_T0"]["top_hit"]["ci_low"] > 0,
        "positive_pairwise_delta_p0_p1_p2_p3": all(v > 0 for v in a6t_phase.values()),
        "positive_pairwise_delta_both_colours": all(v > 0 for v in a6t_colour.values()),
    }
    a6_confirmed = all(a6_gates.values())

    A = {name: metrics[name]["global"]["pairwise"] for name in metrics}
    ratios = {
        "R_C0_from_D": ratio(A["C0"] - A["D1"], A["q1000"] - A["D1"]),
        "R_C0_from_T": ratio(A["C0"] - A["T0"], A["q1000"] - A["T0"]),
    }
    base.update({
        "passed": passed,
        "verdict": "JOINT_TD_DEEP_FRESH_CONFIRMED" if passed else "JOINT_TD_DEEP_FRESH_NOT_CONFIRMED",
        "metrics": metrics,
        "principal_bootstrap_cis": cis,
        "disagreements": {"C0_minus_D1_pairwise_by_phase": c0d_phase, "C0_minus_D1_pairwise_by_colour": c0d_colour,
                          "A6_G0_minus_T0_pairwise_by_phase": a6t_phase, "A6_G0_minus_T0_pairwise_by_colour": a6t_colour},
        "ratios": ratios,
        "primary_gates": primary_gates,
        "secondary_a6_g0_deep_transfer_confirmed": a6_confirmed,
        "secondary_a6_gates": a6_gates,
        "b1_role": "diagnostic_only",
        "next_stage": "STOP_before_runtime_or_elo_separate_prereg_required",
    })
    args.report.write_text(json.dumps(base, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"verdict": base["verdict"], "accepted_parents": len(accepted),
                      "C0": metrics["C0"]["global"], "D1": metrics["D1"]["global"],
                      "C0_minus_D1": cis["C0_minus_D1"], "A6_confirmed": a6_confirmed}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
