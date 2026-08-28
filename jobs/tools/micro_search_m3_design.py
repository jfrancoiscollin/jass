#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Build the frozen M3 teacher preferences and exact production PatternEval rows.

This is deliberately not a learner.  It consumes only the target-blind M3 child
positions, the exact B*=1000 scores, and the production `--dump-eval-features`
sidecar.  Pattern geometry/fold/tempo are imported from the existing production
train.py/train_stream.py stack; no parallel feature implementation exists here.

The compact design artefact is a lossless representation of the full production
linear row:
  canonical pattern columns + antisymmetry signs + exact tempo wmg + all raw
  production dense extras + parent-POV sign.
It is sufficient to materialise any pairwise row exactly as X_good-X_bad while
avoiding a gigantic mostly-zero 34M-column CSR on disk.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import struct
import sys

import numpy as np

TOOLS = Path(__file__).resolve().parents[2] / "pattern_jass" / "tools"
sys.path.insert(0, str(TOOLS))
import master_loader  # type: ignore  # noqa: E402
import patterns  # type: ignore  # noqa: E402
import train  # type: ignore  # noqa: E402
import train_stream  # type: ignore  # noqa: E402

EXPECTED_BUDGET = 1000
EXPECTED_EXTRAS = 120
PAIR_SEED = 2026090211


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def read_groups(path: Path) -> dict[str, np.ndarray]:
    parent, parent_stm, score, t0, row_index = [], [], [], [], []
    with path.open(newline="", encoding="utf-8") as f:
        rd = csv.DictReader(f, delimiter="\t")
        required = {"row_index", "parent_id", "parent_stm", "micro1000_parent", "t0_parent"}
        if rd.fieldnames is None or not required.issubset(rd.fieldnames):
            raise SystemExit(f"{path}: missing frozen M3 columns")
        for r in rd:
            row_index.append(int(r["row_index"]))
            parent.append(int(r["parent_id"]))
            parent_stm.append(int(r["parent_stm"]))
            score.append(int(r["micro1000_parent"]))
            t0.append(int(r["t0_parent"]))
    n = len(parent)
    if row_index != list(range(n)):
        raise SystemExit("groups row_index is not contiguous/aligned")
    return {
        "parent_id": np.asarray(parent, dtype=np.int32),
        "parent_stm": np.asarray(parent_stm, dtype=np.int8),
        "teacher": np.asarray(score, dtype=np.int32),
        "t0_parent": np.asarray(t0, dtype=np.int32),
    }


def load_raw_pjtw(path: Path) -> tuple[int, int, int, np.ndarray]:
    raw = path.read_bytes()
    if len(raw) < 20:
        raise SystemExit("CURRICULUM PJTW too short")
    magic, ver, scale, n_pat, n_ext = struct.unpack_from("<IIIII", raw, 0)
    if magic != train.WEIGHTS_MAGIC or (ver & 0xFF) != train.WEIGHTS_VERSION_V3:
        raise SystemExit("CURRICULUM is not linear PJTW v3")
    total = 2 * (n_pat + n_ext)
    if len(raw) != 20 + 4 * total:
        raise SystemExit("CURRICULUM PJTW size/layout drift")
    w = np.frombuffer(raw, dtype="<i4", offset=20, count=total).astype(np.int64)
    return int(scale), int(n_pat), int(n_ext), w


def production_score_check(ds, extras: np.ndarray, groups: dict[str, np.ndarray],
                           raw_cols: np.ndarray, wmg: np.ndarray,
                           scale: int, n_pat: int, n_ext: int, w: np.ndarray) -> dict:
    """Reconstruct the production linear scalar from exact raw production rows.

    All pattern terms are integer sums. Dense extras are the C++-dumped float32
    values converted to float64, and tempo_wmg comes from the shared production
    Python phase helper. The final conversion mirrors ScanEvalNetwork's normal
    truncating cp path. Every M3 child must reproduce the C++ t0_parent emitted
    by the scorer; otherwise M4 is forbidden.
    """
    pat_mg = w[:n_pat]
    pat_eg = w[n_pat:2 * n_pat]
    ext_mg = w[2 * n_pat:2 * n_pat + n_ext]
    ext_eg = w[2 * n_pat + n_ext:]
    n, npat = raw_cols.shape
    smg = np.zeros(n, dtype=np.int64)
    seg = np.zeros(n, dtype=np.int64)
    for p in range(npat):
        smg += pat_mg[raw_cols[:, p]]
        seg += pat_eg[raw_cols[:, p]]
    # Raw extras are the production C++ values. numpy's double dot is only an
    # implementation detail; all present 120 features are integer/half-integer
    # valued and the int32 coefficients keep this exactly representable here.
    emg = extras.astype(np.float64, copy=False) @ ext_mg.astype(np.float64)
    eeg = extras.astype(np.float64, copy=False) @ ext_eg.astype(np.float64)
    weg = 1.0 - wmg
    black_cp = 100.0 * (wmg * (smg.astype(np.float64) + emg)
                        + weg * (seg.astype(np.float64) + eeg)) / float(scale)
    parent_sign = np.where(groups["parent_stm"] == 1, 1.0, -1.0)
    pred = np.trunc(parent_sign * black_cp).astype(np.int64)
    pred = np.clip(pred, -20000, 20000)
    target = groups["t0_parent"].astype(np.int64)
    diff = pred - target
    mism = int(np.count_nonzero(diff))
    max_abs = int(np.max(np.abs(diff))) if n else 0
    if mism:
        first = int(np.flatnonzero(diff)[0])
        raise SystemExit(
            f"production design equivalence failed: {mism}/{n} rows, "
            f"max_abs_cp={max_abs}, first={first} pred={pred[first]} t0={target[first]}"
        )
    return {
        "rows_checked": int(n),
        "rows_exact": int(n),
        "mismatches": 0,
        "max_abs_cp": 0,
        "production_t0_integer_score_exact": True,
    }


def make_preferences(parent: np.ndarray, teacher: np.ndarray) -> tuple[dict[str, np.ndarray], dict]:
    if len(parent) == 0:
        raise SystemExit("empty M3 siblings")
    # Merged M3 rows are required to be grouped by parent and stable semantic
    # move order. Ties are resolved by the first pre-score semantic row, a purely
    # mechanical deterministic rule; no margin threshold/filter is introduced.
    boundaries = np.r_[0, np.flatnonzero(parent[1:] != parent[:-1]) + 1, len(parent)]
    good: list[int] = []
    bad: list[int] = []
    par: list[int] = []
    margin: list[int] = []
    tie_parents = 0
    for a, b in zip(boundaries[:-1], boundaries[1:]):
        if b - a < 2 or b - a > 16:
            raise SystemExit(f"parent {int(parent[a])} has {b-a} siblings outside 2..16")
        scores = teacher[a:b]
        top = int(np.max(scores))
        winners = np.flatnonzero(scores == top)
        if len(winners) > 1:
            tie_parents += 1
        g = a + int(winners[0])
        for j in range(a, b):
            if j == g:
                continue
            good.append(g); bad.append(j); par.append(int(parent[a])); margin.append(int(top - teacher[j]))
    out = {
        "good": np.asarray(good, dtype=np.int32),
        "bad": np.asarray(bad, dtype=np.int32),
        "parent_id": np.asarray(par, dtype=np.int32),
        "teacher_margin": np.asarray(margin, dtype=np.int32),
    }
    report = {
        "parents": int(len(boundaries) - 1),
        "constraints": int(len(good)),
        "tie_parents": int(tie_parents),
        "tie_break": "first_pre_score_semantic_move_order",
        "margin_filter": None,
        "top_vs_rest": True,
    }
    return out, report


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--children", required=True)
    ap.add_argument("--groups", required=True)
    ap.add_argument("--feat", required=True)
    ap.add_argument("--curriculum", required=True)
    ap.add_argument("--design-out", required=True)
    ap.add_argument("--constraints-out", required=True)
    ap.add_argument("--report", required=True)
    args = ap.parse_args()

    children = Path(args.children); groups_path = Path(args.groups); feat_path = Path(args.feat)
    curriculum = Path(args.curriculum); design_out = Path(args.design_out)
    constraints_out = Path(args.constraints_out); report_path = Path(args.report)

    ds = master_loader.load(str(children))
    g = read_groups(groups_path)
    n = ds.n_records
    if any(len(v) != n for v in g.values()):
        raise SystemExit("children/groups alignment drift")
    if not np.all((g["parent_stm"] == 0) | (g["parent_stm"] == 1)):
        raise SystemExit("invalid parent_stm")
    if np.any(ds.score != 0) or np.any(ds.wdl != 0):
        raise SystemExit("M3 child source target bytes are nonzero")

    extras = train.load_feature_file(str(feat_path), n, standardise=False)
    if extras.shape != (n, EXPECTED_EXTRAS):
        raise SystemExit(f"production extras drift: {extras.shape}, expected ({n},{EXPECTED_EXTRAS})")

    # Exact production 8cf geometry is injected through JASS_PATTERNS_DIR by the
    # job, and Folder('exact') is the same exact-fold mapper used by train_stream.
    folder = train_stream.Folder("exact")
    canonical_cols, signs = folder.cols_signs(ds.black_men, ds.white_men)
    if signs is None:
        raise SystemExit("exact fold unexpectedly produced no antisymmetry signs")
    raw_idx = patterns.extract_indices(ds.black_men, ds.white_men)
    raw_cols = patterns.flat_feature_columns(raw_idx).astype(np.int64, copy=False)
    wmg = train.tempo_wmg(ds).astype(np.float64, copy=False)
    if np.any(wmg < 0.0) or np.any(wmg > 1.0):
        raise SystemExit("tempo phase outside [0,1]")

    scale, n_pat, n_ext, w = load_raw_pjtw(curriculum)
    if n_pat != patterns.TOTAL_BUCKETS or n_ext != EXPECTED_EXTRAS:
        raise SystemExit(f"CURRICULUM geometry drift n_pat={n_pat} n_ext={n_ext}")

    # Prove the folded sparse representation equals the production full-table
    # pattern row on EVERY M3 sibling and in both phase banks.
    pat_mg, pat_eg = w[:n_pat], w[n_pat:2*n_pat]
    s64 = signs.astype(np.int64)
    folded_mg = s64 * pat_mg[canonical_cols]
    folded_eg = s64 * pat_eg[canonical_cols]
    raw_mg = pat_mg[raw_cols]
    raw_eg = pat_eg[raw_cols]
    fold_mismatch = int(np.count_nonzero(folded_mg != raw_mg) + np.count_nonzero(folded_eg != raw_eg))
    if fold_mismatch:
        raise SystemExit(f"exact-fold production mapping mismatch: {fold_mismatch} coefficient visits")

    score_proof = production_score_check(ds, extras, g, raw_cols, wmg, scale, n_pat, n_ext, w)
    prefs, pref_report = make_preferences(g["parent_id"], g["teacher"])
    if pref_report["parents"] != 100000:
        raise SystemExit(f"M3 parent support drift: {pref_report['parents']} != 100000")

    parent_sign = np.where(g["parent_stm"] == 1, 1, -1).astype(np.int8)
    np.savez_compressed(
        design_out,
        canonical_cols=canonical_cols.astype(np.int32),
        signs=signs.astype(np.int8),
        tempo_wmg=wmg,
        extras=extras.astype(np.float32),
        parent_pov_sign=parent_sign,
        parent_id=g["parent_id"],
        teacher_micro1000=g["teacher"],
        t0_parent=g["t0_parent"],
    )
    np.savez_compressed(constraints_out, **prefs)

    # Every pairwise row is now exactly the subtraction of two individually
    # proven production rows by construction. No score-dependent filter exists.
    report = {
        "schema": "jass.micro_search_m3_pattern_design.v1",
        "passed": True,
        "budget_nodes": EXPECTED_BUDGET,
        "rows": int(n),
        "full_pattern_buckets": int(n_pat),
        "patterns_per_row": int(canonical_cols.shape[1]),
        "dense_extras": int(n_ext),
        "fold": "exact_rot180_colour_swap",
        "phase": "production_tempo_stage",
        "pattern_semantics": "men_only_8cf",
        "compact_row_is_full_production_design": True,
        "fold_coefficient_visits_checked": int(2 * canonical_cols.size),
        "fold_coefficient_visit_mismatches": 0,
        "production_score_proof": score_proof,
        "pairwise_mapping": {
            "operation": "X_good_minus_X_bad",
            "algebraically_exact_from_proven_rows": True,
            "constraints_checked_by_construction": int(len(prefs["good"])),
        },
        "preferences": pref_report,
        "pair_order_seed_reserved_for_m4": PAIR_SEED,
        "source_labels_read": False,
        "deep_scores_read": 0,
        "fits": 0,
        "t_refits": 0,
        "strength_games": 0,
        "runtime_micro_search": False,
        "promotion_authorized": False,
        "inputs": {
            "children_sha256": sha256(children),
            "groups_sha256": sha256(groups_path),
            "feat_sha256": sha256(feat_path),
            "curriculum_sha256": sha256(curriculum),
        },
    }
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
