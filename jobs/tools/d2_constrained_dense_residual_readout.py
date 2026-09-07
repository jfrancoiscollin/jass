#!/usr/bin/env python3
"""Terminal offline readout for sealed D2 constrained dense residual candidate."""
from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
import math
from pathlib import Path
import struct
import sys
from typing import Any, Mapping, Sequence

import numpy as np
import scipy.sparse as sp

ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "pattern_jass" / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import patterns  # noqa: E402
import train  # noqa: E402
import train_stream as ts  # noqa: E402
from jobs.tools import d2_constrained_dense_residual_fit as fitmod  # noqa: E402

SCHEMA = "jass.d2.constrained_dense_residual_readout.v1"
VERDICT_PASS = "D2_CONSTRAINED_DENSE_RESIDUAL_ESTABLISHED_V1"
VERDICT_FAIL = "D2_CONSTRAINED_DENSE_RESIDUAL_NOT_ESTABLISHED_V1"
VERDICT_INVALID = "D2_CONSTRAINED_DENSE_RESIDUAL_INVALID_V1"
SEED = 2026111001
BOOTSTRAPS = 200_000
MIN_TEST_ELIGIBLE = 300
MIN_CELL_ELIGIBLE = 25


class D2ReadoutError(RuntimeError):
    pass


def _json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise D2ReadoutError(f"cannot read {path}: {exc}") from exc
    if type(value) is not dict:
        raise D2ReadoutError(f"JSON object required: {path}")
    return value


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def _open_model(path: Path) -> tuple[np.ndarray, int, int]:
    weights, scale, n_pat, n_ext = train.load_v3_weights_float(str(path))
    if scale != fitmod.SCALE or n_ext != fitmod.EXTRAS or n_pat != patterns.NUM_PATTERNS * patterns.BUCKETS_PER_PATTERN:
        raise D2ReadoutError("PatternEval model layout drift")
    return np.asarray(weights, dtype=np.float64), int(n_pat), int(n_ext)


def _predict(data: Path, feat_path: Path, model: Path, lo: int = 0, hi: int | None = None,
             chunk: int = 20_000) -> np.ndarray:
    mm, n = ts.open_jnnw(str(data)); feat, k = ts.open_feat(str(feat_path), n)
    if hi is None:
        hi = n
    if not 0 <= lo <= hi <= n:
        raise D2ReadoutError("prediction slice drift")
    weights, n_pat, n_ext = _open_model(model)
    if k != n_ext:
        raise D2ReadoutError("model/extras feature count drift")
    folder = ts.Folder("none")
    pred = np.empty(hi - lo, dtype=np.float64)
    for a in range(lo, hi, chunk):
        b = min(hi, a + chunk); rec = mm[a:b]
        wm = np.ascontiguousarray(rec["wm"]); bm = np.ascontiguousarray(rec["bm"])
        cols, signs = folder.cols_signs(bm, wm)
        wmg = ts._tempo_wmg_bb(wm, bm).astype(np.float64); weg = 1.0 - wmg
        xpat = train.build_sparse_X_phased(cols, wmg, weg, n_pat, signs)
        xext = train.build_extras_phased(np.asarray(feat[a:b], dtype=np.float64), wmg, weg)
        pred[a - lo:b - lo] = np.asarray(sp.hstack([xpat, xext], format="csr") @ weights).ravel()
    return pred


def _sigmoid(z: np.ndarray) -> np.ndarray:
    return 0.5 * (np.tanh(0.5 * z) + 1.0)


def _load_groups(path: Path) -> list[dict[str, Any]]:
    groups, _ = fitmod.load_groups(path)
    return groups


def _action_band(count: int) -> str:
    if count <= 4:
        return "2-4"
    if count <= 8:
        return "5-8"
    return "9-16"


def parent_rows(z: np.ndarray, groups: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    if z.shape != (fitmod.ACTIONS,):
        raise D2ReadoutError("decision prediction cardinality drift")
    rows: list[dict[str, Any]] = []
    for g in groups:
        start = int(g["start"]); count = int(g["count"]); sel = int(g["selected_local_action_index"])
        pov = 1.0 if int(g["parent_stm"]) == 1 else -1.0
        q = pov * z[start:start + count]
        qmax = float(np.max(q)); ex = np.exp(q - qmax); probs = ex / float(np.sum(ex))
        full_ce = (qmax + math.log(float(np.sum(ex)))) - float(q[sel])
        order = np.argsort(-q, kind="stable")
        eligible = bool(g["d2_eligible"])
        pair_loss = None; pair_acc = None
        if eligible:
            hard = list(g["hard_competitor_local_action_indices"])
            margins = np.asarray([q[sel] - q[j] for j in hard], dtype=np.float64)
            pair_loss = float(np.mean(np.logaddexp(0.0, -margins)))
            pair_acc = float(np.mean(margins > 0.0))
        rows.append({
            "action_band": _action_band(count),
            "cell": str(g["cell"]),
            "eligible": eligible,
            "full_ce": float(full_ce),
            "pairwise_accuracy": pair_acc,
            "pairwise_loss": pair_loss,
            "parent_id": int(g["parent_id"]),
            "selected_probability": float(probs[sel]),
            "split": str(g["split"]),
            "top1": float(order[0] == sel),
            "top2": float(sel in order[:2]),
        })
    return rows


def aggregate(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    if not rows:
        raise D2ReadoutError("empty aggregate")
    eligible = [r for r in rows if bool(r["eligible"])]
    out = {
        "eligible_parents": len(eligible),
        "full_cross_entropy": float(np.mean([float(r["full_ce"]) for r in rows])),
        "parents": len(rows),
        "selected_probability_mean": float(np.mean([float(r["selected_probability"]) for r in rows])),
        "top1": float(np.mean([float(r["top1"]) for r in rows])),
        "top2": float(np.mean([float(r["top2"]) for r in rows])),
    }
    if eligible:
        out["survived5_pairwise_accuracy"] = float(np.mean([float(r["pairwise_accuracy"]) for r in eligible]))
        out["survived5_pairwise_loss"] = float(np.mean([float(r["pairwise_loss"]) for r in eligible]))
    else:
        out["survived5_pairwise_accuracy"] = None
        out["survived5_pairwise_loss"] = None
    return out


def grouped(rows: Sequence[Mapping[str, Any]], key: str) -> dict[str, Any]:
    d: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for r in rows:
        d[str(r[key])].append(r)
    return {k: aggregate(v) for k, v in sorted(d.items())}


def split_report(rows: Sequence[Mapping[str, Any]], split: str) -> dict[str, Any]:
    selected = [r for r in rows if r["split"] == split]
    if len(selected) != 400:
        raise D2ReadoutError(f"{split} must contain 400 parents")
    return {
        "by_action_band": grouped(selected, "action_band"),
        "by_cell": grouped(selected, "cell"),
        "global": aggregate(selected),
    }


def bootstrap_delta(base_rows: Sequence[Mapping[str, Any]], cand_rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    b = {int(r["parent_id"]): r for r in base_rows if r["split"] == "test" and bool(r["eligible"])}
    c = {int(r["parent_id"]): r for r in cand_rows if r["split"] == "test" and bool(r["eligible"])}
    if b.keys() != c.keys():
        raise D2ReadoutError("eligible test parent identity drift")
    ids = sorted(b)
    delta = np.asarray([float(b[i]["pairwise_loss"]) - float(c[i]["pairwise_loss"]) for i in ids], dtype=np.float64)
    if len(delta) < MIN_TEST_ELIGIBLE:
        raise D2ReadoutError("insufficient eligible test parents")
    rng = np.random.default_rng(SEED)
    vals = np.empty(BOOTSTRAPS, dtype=np.float64)
    cursor = 0; batch = 1000
    while cursor < BOOTSTRAPS:
        take = min(batch, BOOTSTRAPS - cursor)
        idx = rng.integers(0, len(delta), size=(take, len(delta)), endpoint=False)
        vals[cursor:cursor + take] = np.mean(delta[idx], axis=1)
        cursor += take
    return {
        "eligible_test_parents": len(delta),
        "lcb95": float(np.quantile(vals, 0.025, method="linear")),
        "mean": float(np.mean(delta)),
        "replications": BOOTSTRAPS,
        "seed": SEED,
        "ucb95": float(np.quantile(vals, 0.975, method="linear")),
    }


def wdl_holdout(data: Path, feat: Path, targets_path: Path, model: Path) -> dict[str, float]:
    targets = np.load(targets_path, allow_pickle=False, mmap_mode="r")
    if targets.dtype != np.dtype(np.float32) or targets.shape != (fitmod.RECORDS,):
        raise D2ReadoutError("WDL target sidecar drift")
    z = _predict(data, feat, model, fitmod.TRAIN, fitmod.RECORDS)
    y = np.asarray(targets[fitmod.TRAIN:], dtype=np.float64); p = _sigmoid(z); eps = 1e-12
    ce = -(y * np.log(p + eps) + (1.0 - y) * np.log(1.0 - p + eps))
    return {
        "brier": float(np.mean((p - y) ** 2)),
        "logloss": float(np.mean(ce)),
        "prediction_mean": float(np.mean(p)),
        "target_mean": float(np.mean(y)),
    }


def _pattern_identity(base: Path, candidate: Path) -> dict[str, Any]:
    hb, ib = fitmod._read_raw_pjtw(base); hc, ic = fitmod._read_raw_pjtw(candidate)
    if hb != hc:
        raise D2ReadoutError("base/candidate header drift")
    n_pat = int(hb[3])
    changed_pattern = int(np.count_nonzero(ic[:2 * n_pat] - ib[:2 * n_pat]))
    changed_extra = int(np.count_nonzero(ic[2 * n_pat:] - ib[2 * n_pat:]))
    return {"changed_extra_slots": changed_extra, "changed_pattern_slots": changed_pattern,
            "pattern_coefficients_identical": changed_pattern == 0}


def run(args: argparse.Namespace) -> dict[str, Any]:
    fit = _json(args.fit_report); seal = _json(args.seal)
    if fit.get("schema") != fitmod.REPORT_SCHEMA or seal.get("schema") != fitmod.SEAL_SCHEMA:
        raise D2ReadoutError("fit/seal schema drift")
    if seal.get("candidate_sha256") != _sha(args.candidate_model) or seal.get("base_model_sha256") != _sha(args.base_model):
        raise D2ReadoutError("sealed model SHA drift")
    if seal.get("decision_valid_reads") != 0 or seal.get("decision_test_reads") != 0 or seal.get("wdl_holdout_reads") != 0:
        raise D2ReadoutError("heldout data read before seal")
    if float(seal.get("wdl_train_delta", 99.0)) > fitmod.WDL_TOLERANCE:
        raise D2ReadoutError("sealed candidate violates WDL-train constraint")

    groups = _load_groups(args.decision_groups)
    z_base = _predict(args.decision_data, args.decision_feat, args.base_model)
    z_cand = _predict(args.decision_data, args.decision_feat, args.candidate_model)
    rows_base = parent_rows(z_base, groups); rows_cand = parent_rows(z_cand, groups)
    valid_base = split_report(rows_base, "valid"); valid_cand = split_report(rows_cand, "valid")
    test_base = split_report(rows_base, "test"); test_cand = split_report(rows_cand, "test")

    eligible_cells = test_cand["by_cell"]
    support = (test_cand["global"]["eligible_parents"] >= MIN_TEST_ELIGIBLE
               and len(eligible_cells) == 8
               and all(int(v["eligible_parents"]) >= MIN_CELL_ELIGIBLE for v in eligible_cells.values()))
    boot = bootstrap_delta(rows_base, rows_cand) if support else None
    wdl_base = wdl_holdout(args.wdl_data, args.wdl_feat, args.target_values, args.base_model)
    wdl_cand = wdl_holdout(args.wdl_data, args.wdl_feat, args.target_values, args.candidate_model)
    delta_wdl = wdl_cand["logloss"] - wdl_base["logloss"]
    identity = _pattern_identity(args.base_model, args.candidate_model)

    established = bool(
        support and boot is not None and boot["lcb95"] > 0.0
        and test_cand["global"]["full_cross_entropy"] <= test_base["global"]["full_cross_entropy"]
        and test_cand["global"]["top1"] >= test_base["global"]["top1"]
        and delta_wdl <= fitmod.WDL_TOLERANCE
        and identity["pattern_coefficients_identical"]
    )
    verdict = VERDICT_PASS if established else VERDICT_FAIL
    publication = {
        "bootstrap": boot,
        "candidate_sha256": _sha(args.candidate_model),
        "decision_test": {"CONTROL": test_base, "D2": test_cand},
        "decision_valid": {"CONTROL": valid_base, "D2": valid_cand},
        "delta_wdl_holdout": float(delta_wdl),
        "equal_node_gate_authorized": established,
        "fits": 1,
        "model_identity": identity,
        "model_searches": 0,
        "next_stage": "D2_EQUAL_NODE_CAUSAL_PREREGISTRATION" if established else "STOP",
        "promotion_authorized": False,
        "schema": SCHEMA,
        "strength_games": 0,
        "support": {
            "min_cell_eligible": MIN_CELL_ELIGIBLE,
            "min_test_eligible": MIN_TEST_ELIGIBLE,
            "pass": support,
            "test_eligible_by_cell": {k: int(v["eligible_parents"]) for k, v in eligible_cells.items()},
            "test_eligible_parents": int(test_cand["global"]["eligible_parents"]),
        },
        "verdict": verdict,
        "wdl_holdout": {"CONTROL": wdl_base, "D2": wdl_cand},
        "wdl_noninferiority_tolerance": fitmod.WDL_TOLERANCE,
    }
    if args.out.exists() or args.out.is_symlink():
        raise D2ReadoutError(f"refusing existing output {args.out}")
    args.out.write_text(json.dumps(publication, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    return publication


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--wdl-data", type=Path, required=True)
    p.add_argument("--wdl-feat", type=Path, required=True)
    p.add_argument("--target-values", type=Path, required=True)
    p.add_argument("--decision-data", type=Path, required=True)
    p.add_argument("--decision-feat", type=Path, required=True)
    p.add_argument("--decision-groups", type=Path, required=True)
    p.add_argument("--base-model", type=Path, required=True)
    p.add_argument("--candidate-model", type=Path, required=True)
    p.add_argument("--fit-report", type=Path, required=True)
    p.add_argument("--seal", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    return p.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    try:
        r = run(parse_args(argv))
    except (D2ReadoutError, fitmod.D2FitError, OSError, ValueError, MemoryError) as exc:
        print(f"{VERDICT_INVALID}: {exc}", file=sys.stderr)
        return 2
    print(r["verdict"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
