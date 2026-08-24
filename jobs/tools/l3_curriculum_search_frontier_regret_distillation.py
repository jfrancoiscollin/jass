#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Leakage-safe cross-pool screen for shallow search-frontier regret signal.

Consumes the already sealed 1549 label shards. It does not compute new search
labels and never fits PatternEval. A fixed ridge model is trained on shallow
(target-blind) frontier features in one pool and tested on the other, then the
direction is reversed. The only target is the already sealed d12 regret of the
historical action.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np

SCHEMA = "jass.l3_curriculum_search_frontier_regret_distillation.v1"
PASS = "JASS_CURRICULUM_SEARCH_FRONTIER_REGRET_DISTILLATION_SUPPORTED"
FAIL = "JASS_CURRICULUM_SEARCH_FRONTIER_REGRET_DISTILLATION_NOT_SUPPORTED"

CATEGORIES = {
    "phase": ("opening", "midgame", "endgame"),
    "kings": ("no_kings", "kings"),
    "tactical": ("quiet", "capture"),
    "branching_bin": ("b01_02", "b03_05", "b06_plus"),
}


def canonical(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def digest(value: object) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def rankdata(values: np.ndarray) -> np.ndarray:
    values = np.asarray(values, dtype=float)
    order = np.argsort(values, kind="mergesort")
    ranks = np.empty(len(values), dtype=float)
    i = 0
    while i < len(values):
        j = i + 1
        while j < len(values) and values[order[j]] == values[order[i]]:
            j += 1
        ranks[order[i:j]] = 0.5 * (i + j - 1) + 1.0
        i = j
    return ranks


def corr(x: np.ndarray, y: np.ndarray) -> float:
    x = np.asarray(x, dtype=float); y = np.asarray(y, dtype=float)
    if len(x) < 3:
        return 0.0
    x = x - x.mean(); y = y - y.mean()
    denom = float(np.sqrt(np.dot(x, x) * np.dot(y, y)))
    return 0.0 if denom <= 1e-15 else float(np.dot(x, y) / denom)


def spearman(pred: np.ndarray, y: np.ndarray) -> float:
    return corr(rankdata(pred), rankdata(y))


def feature_vector(row: dict[str, Any]) -> tuple[list[float], list[str]]:
    shallow = row["baseline_shallow_scores_cp"]
    sym = {str(k): float(v) for k, v in shallow["symmetrised"].items()}
    orig = {str(k): float(v) for k, v in shallow["original"].items()}
    image = {str(k): float(v) for k, v in shallow["exact_image"].items()}
    hist = str(row["historical_action"])
    if hist not in sym or hist not in orig or hist not in image:
        raise ValueError("historical action missing from shallow scores")
    inst = row["instability"]; structural = row["structural"]
    values = [
        max(sym.values()) - sym[hist],
        max(orig.values()) - orig[hist],
        max(image.values()) - image[hist],
        abs(orig[hist] - image[hist]),
        float(inst["depth_flips"]),
        float(inst["orientation_disagreements"]),
        float(inst["historical_mean_rank_fraction"]),
        min(400.0, float(inst["score_volatility_cp"])),
        min(400.0, float(inst["minimum_d9_margin_cp"])),
        float(structural["legal_action_count"]),
        float(structural["piece_count"]),
        float(structural["king_count"]),
    ]
    names = [
        "d9_historical_gap_sym_cp", "d9_historical_gap_original_cp",
        "d9_historical_gap_image_cp", "d9_orientation_historical_absdiff_cp",
        "instability_depth_flips", "instability_orientation_disagreements",
        "instability_historical_mean_rank_fraction", "instability_score_volatility_cp",
        "instability_minimum_d9_margin_cp_capped400", "legal_action_count",
        "piece_count", "king_count",
    ]
    for key, cats in CATEGORIES.items():
        val = str(structural[key])
        if val not in cats:
            raise ValueError(f"unexpected {key}={val!r}")
        for cat in cats:
            values.append(1.0 if val == cat else 0.0)
            names.append(f"{key}={cat}")
    return values, names


def load_rows(paths: list[Path]) -> list[dict[str, Any]]:
    if len(paths) != 16:
        raise ValueError("requires exactly 16 sealed label shards")
    rows: list[dict[str, Any]] = []
    seen = set()
    identities = {"champion_sha256": set(), "jass_sha256": set(), "search_params_sha256": set()}
    for path in paths:
        shard = json.loads(path.read_text(encoding="utf-8"))
        idx = int(shard.get("shard", -1))
        if idx in seen or not 0 <= idx < 16 or int(shard.get("nshards", -1)) != 16:
            raise ValueError("label shard identity drift")
        seen.add(idx)
        for key in identities:
            identities[key].add(str(shard.get(key, "")))
        rows.extend(shard.get("rows", []))
    if seen != set(range(16)) or any(len(v) != 1 or not next(iter(v)) for v in identities.values()):
        raise ValueError("sealed label shard identity mismatch")
    rows.sort(key=lambda r: int(r["label_ordinal"]))
    if len(rows) != 768 or [int(r["label_ordinal"]) for r in rows] != list(range(768)):
        raise ValueError("expected exact 768-row sealed corpus")
    if {int(r["pool"]) for r in rows} != {1, 2}:
        raise ValueError("expected exactly two pools")
    if any(sum(int(r["pool"]) == pool for r in rows) != 384 for pool in (1, 2)):
        raise ValueError("expected 384 rows per pool")
    return rows


def matrix(rows: list[dict[str, Any]]) -> tuple[np.ndarray, np.ndarray, list[str]]:
    feats=[]; targets=[]; names_ref=None
    for row in rows:
        vals, names = feature_vector(row)
        if names_ref is None:
            names_ref = names
        elif names != names_ref:
            raise ValueError("feature schema drift")
        regret = float(row["regret_cp_by_depth"]["12"])
        feats.append(vals); targets.append(min(200.0, max(0.0, regret)))
    return np.asarray(feats, dtype=float), np.asarray(targets, dtype=float), list(names_ref or [])


def fit_predict(x_train: np.ndarray, y_train: np.ndarray, x_test: np.ndarray, lam: float) -> tuple[np.ndarray, dict[str, Any]]:
    mean = x_train.mean(axis=0); sd = x_train.std(axis=0)
    sd = np.where(sd > 1e-9, sd, 1.0)
    ztr = (x_train - mean) / sd; zte = (x_test - mean) / sd
    a = np.column_stack([np.ones(len(ztr)), ztr])
    penalty = np.eye(a.shape[1]) * lam; penalty[0, 0] = 0.0
    beta = np.linalg.solve(a.T @ a + penalty, a.T @ y_train)
    pred = np.column_stack([np.ones(len(zte)), zte]) @ beta
    return pred, {"intercept": float(beta[0]), "coefficients_standardized": [float(v) for v in beta[1:]]}


def ci95(values: np.ndarray) -> list[float]:
    return [float(np.quantile(values, .025)), float(np.quantile(values, .975))]


def evaluate_direction(train_rows: list[dict[str, Any]], test_rows: list[dict[str, Any]], *, lam: float, bootstrap: int, seed: int, top_fraction: float) -> dict[str, Any]:
    xtr, ytr, names = matrix(train_rows); xte, yte, names2 = matrix(test_rows)
    if names != names2:
        raise ValueError("cross-pool feature schema drift")
    pred, model = fit_predict(xtr, ytr, xte, lam)
    rho = spearman(pred, yte)
    ranks_p = rankdata(pred); ranks_y = rankdata(yte)
    cutoff = float(np.quantile(pred, 1.0 - top_fraction))
    top = pred >= cutoff
    uplift = float(yte[top].mean() - yte.mean())
    rng = np.random.default_rng(seed)
    boot_rho = np.empty(bootstrap, dtype=float); boot_uplift = np.empty(bootstrap, dtype=float)
    n = len(yte)
    for i in range(bootstrap):
        idx = rng.integers(0, n, n)
        boot_rho[i] = corr(ranks_p[idx], ranks_y[idx])
        mask = top[idx]
        boot_uplift[i] = float(yte[idx][mask].mean() - yte[idx].mean()) if mask.any() else -1e9
    return {
        "n_train": len(ytr), "n_test": len(yte), "feature_names": names,
        "target_mean_cp": float(yte.mean()), "target_median_cp": float(np.median(yte)),
        "target_ge50": int(np.sum(yte >= 50.0)), "spearman": rho,
        "spearman_bootstrap_ci95": ci95(boot_rho), "top_fraction": top_fraction,
        "top_n": int(top.sum()), "top_true_regret_mean_cp": float(yte[top].mean()),
        "top_true_regret_uplift_cp": uplift, "top_uplift_bootstrap_ci95": ci95(boot_uplift),
        "model": model, "predictions_sha256": hashlib.sha256(np.asarray(pred, dtype="<f8").tobytes()).hexdigest(),
    }


def sham_threshold(rows1: list[dict[str, Any]], rows2: list[dict[str, Any]], *, lam: float, shams: int, seed: int) -> dict[str, Any]:
    x1, y1, _ = matrix(rows1); x2, y2, _ = matrix(rows2)
    rng = np.random.default_rng(seed); minima = np.empty(shams, dtype=float)
    for i in range(shams):
        sy1 = rng.permutation(y1); sy2 = rng.permutation(y2)
        p12, _ = fit_predict(x1, sy1, x2, lam); p21, _ = fit_predict(x2, sy2, x1, lam)
        minima[i] = min(spearman(p12, y2), spearman(p21, y1))
    return {
        "shams": shams, "seed": seed, "min_direction_spearman_p99": float(np.quantile(minima, .99)),
        "min_direction_spearman_mean": float(minima.mean()),
    }


def main() -> int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--label-shard", action="append", type=Path, required=True)
    p.add_argument("--prereg", type=Path, required=True); p.add_argument("--out", type=Path, required=True)
    args=p.parse_args()
    prereg=json.loads(args.prereg.read_text(encoding="utf-8"))
    if prereg.get("schema") != "jass.l3_curriculum_search_frontier_regret_distillation_prereg.v1":
        raise ValueError("preregistration schema drift")
    lam=float(prereg["model"]["lambda"]); bootstrap=int(prereg["statistics"]["bootstrap_samples"])
    bseed=int(prereg["statistics"]["bootstrap_seed"]); shams=int(prereg["statistics"]["label_shams"])
    sseed=int(prereg["statistics"]["sham_seed"]); top_fraction=float(prereg["statistics"]["top_fraction"])
    rows=load_rows(args.label_shard); pool1=[r for r in rows if int(r["pool"])==1]; pool2=[r for r in rows if int(r["pool"])==2]
    d12=evaluate_direction(pool1,pool2,lam=lam,bootstrap=bootstrap,seed=bseed+12,top_fraction=top_fraction)
    d21=evaluate_direction(pool2,pool1,lam=lam,bootstrap=bootstrap,seed=bseed+21,top_fraction=top_fraction)
    sham=sham_threshold(pool1,pool2,lam=lam,shams=shams,seed=sseed)
    directions={"pool1_to_pool2":d12,"pool2_to_pool1":d21}
    min_rho=min(d["spearman"] for d in directions.values())
    gates={
        "both_spearman_point_positive": all(d["spearman"]>0.0 for d in directions.values()),
        "both_spearman_ci95_low_positive": all(d["spearman_bootstrap_ci95"][0]>0.0 for d in directions.values()),
        "both_top_uplift_ci95_low_positive": all(d["top_uplift_bootstrap_ci95"][0]>0.0 for d in directions.values()),
        "familywise_sham": min_rho > float(sham["min_direction_spearman_p99"]),
    }
    passed=all(gates.values()); verdict=PASS if passed else FAIL
    payload={
        "schema":SCHEMA,"verdict":verdict,"passed":passed,"preregistration_sha256":digest(prereg),
        "source_job":prereg["source"],"directions":directions,"sham":sham,"gates":gates,
        "min_direction_spearman":min_rho,
        "next_stage":"fresh_disjoint_search_frontier_confirmation" if passed else None,
        "new_exact_targets":0,"pattern_eval_fits":0,"production_model_fits":0,"strength_games":0,
        "new_selfplay_games":0,"frozen_reads":0,"promotion_authorized":False,
        "fresh_confirmation_authorized":passed,"pattern_eval_refit_authorized":False,
    }
    if args.out.exists():
        raise FileExistsError(args.out)
    args.out.parent.mkdir(parents=True,exist_ok=True); args.out.write_bytes(canonical(payload))
    print(json.dumps({"verdict":verdict,"passed":passed,"min_direction_spearman":min_rho,"sham_p99":sham["min_direction_spearman_p99"]},sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
