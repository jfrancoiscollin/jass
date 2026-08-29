#!/usr/bin/env python3
"""Deterministic T3 RF1 joint A/B residual students.

Scientific contract: docs/experiments/L3_T3_RF1_JOINT_AB_V1_20260829.md
A uses exact F6 width 66; B uses the same F6 plus one sealed-D1 scalar.
Both rank siblings with parent_score = T0_parent + residual.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

import numpy as np

from jobs.tools import residual_feature_probe as rf

F6_WIDTH = 66
A_WIDTH = 66
B_WIDTH = 67
HIDDEN = (256, 128, 64)
INIT_SEED = 2026090801
ORDER_SEED = 2026090802
PAIR_CAP_SEED = 2026090803
D1_INIT_SEED = 2026090804
BATCH_SIZE = 4096
EPOCHS = 80
LR0 = 1e-3
WEIGHT_DECAY = 1e-5
GRAD_CLIP = 5.0
PAIR_CAP_PER_CELL = 150_000
PHASES = ("P0", "P1", "P2", "P3")
SCHEMA = "jass.t3_rf1_joint_ab.v1"
FORBIDDEN_INPUT_NAMES = frozenset({
    "t2", "q1000", "q5k", "q50", "q200", "wdl", "result", "source",
    "split", "partition", "holdout", "parent_id", "q1", "rf1_fresh",
})


@dataclass(frozen=True)
class StaticMeta:
    parent_id: int
    parent_stm: int
    parent_phase: str
    t_baseline_parent: float
    d1_parent: float


@dataclass(frozen=True)
class Pair:
    parent_id: int
    parent_stm: int
    parent_phase: str
    good: int
    bad: int


def _seed_for(name: str, base: int = INIT_SEED) -> int:
    raw = hashlib.sha256(f"{SCHEMA}:{base}:{name}".encode()).digest()
    return int.from_bytes(raw[:8], "little")


def _he(shape: tuple[int, ...], fan_in: int, name: str, base: int = INIT_SEED) -> np.ndarray:
    rng = np.random.default_rng(_seed_for(name, base))
    return rng.standard_normal(shape) * math.sqrt(2.0 / fan_in)


def init_paired_models() -> tuple[dict[str, np.ndarray], dict[str, np.ndarray], dict]:
    """Nested deterministic init: all F6/shared blocks are byte-identical."""
    common_w0 = _he((F6_WIDTH, HIDDEN[0]), F6_WIDTH, "W0_F6")
    common_w1 = _he((HIDDEN[0], HIDDEN[1]), HIDDEN[0], "W1")
    common_w2 = _he((HIDDEN[1], HIDDEN[2]), HIDDEN[1], "W2")
    common_w3 = _he((HIDDEN[2], 1), HIDDEN[2], "W3")
    extra_rng = np.random.default_rng(D1_INIT_SEED)
    d1_row = extra_rng.standard_normal((1, HIDDEN[0])) * math.sqrt(2.0 / B_WIDTH)
    a = {
        "W0": common_w0.copy(), "b0": np.zeros(HIDDEN[0]),
        "W1": common_w1.copy(), "b1": np.zeros(HIDDEN[1]),
        "W2": common_w2.copy(), "b2": np.zeros(HIDDEN[2]),
        "W3": common_w3.copy(), "b3": np.zeros(1),
    }
    b = {
        "W0": np.vstack([common_w0, d1_row]), "b0": np.zeros(HIDDEN[0]),
        "W1": common_w1.copy(), "b1": np.zeros(HIDDEN[1]),
        "W2": common_w2.copy(), "b2": np.zeros(HIDDEN[2]),
        "W3": common_w3.copy(), "b3": np.zeros(1),
    }
    receipt = {
        "schema": "jass.t3_nested_init.v1",
        "global_seed": INIT_SEED,
        "d1_extra_row_seed": D1_INIT_SEED,
        "layer_seed_derivation": f"uint64_le(sha256('{SCHEMA}:<base>:<layer>')[:8])",
        "shared_f6_w0_sha256": hashlib.sha256(common_w0.tobytes()).hexdigest(),
        "shared_w1_sha256": hashlib.sha256(common_w1.tobytes()).hexdigest(),
        "shared_w2_sha256": hashlib.sha256(common_w2.tobytes()).hexdigest(),
        "shared_w3_sha256": hashlib.sha256(common_w3.tobytes()).hexdigest(),
    }
    return a, b, receipt


def load_static_meta(path: Path) -> list[StaticMeta]:
    out: list[StaticMeta] = []
    with path.open(newline="", encoding="utf-8") as f:
        rd = csv.DictReader(f, delimiter="\t")
        req = {"parent_id", "parent_stm", "phase", "t_baseline_parent", "d1_parent"}
        if rd.fieldnames is None or not req.issubset(rd.fieldnames):
            raise ValueError(f"static-meta fields drift: {rd.fieldnames!r}")
        for r in rd:
            stm = int(r["parent_stm"]); phase = r["phase"]
            if stm not in (0, 1) or phase not in PHASES:
                raise ValueError("invalid parent cell metadata")
            out.append(StaticMeta(int(r["parent_id"]), stm, phase,
                                  float(r["t_baseline_parent"]), float(r["d1_parent"])))
    return out


def load_pairs(path: Path, meta: Sequence[StaticMeta]) -> list[Pair]:
    out: list[Pair] = []
    with path.open(newline="", encoding="utf-8") as f:
        rd = csv.DictReader(f, delimiter="\t")
        req = {"parent_id", "parent_stm", "good_row", "bad_row"}
        if rd.fieldnames is None or not req.issubset(rd.fieldnames):
            raise ValueError("pair fields drift")
        for r in rd:
            pid, stm = int(r["parent_id"]), int(r["parent_stm"])
            g, b = int(r["good_row"]), int(r["bad_row"])
            if not (0 <= g < len(meta) and 0 <= b < len(meta)):
                raise ValueError("pair row out of range")
            mg, mb = meta[g], meta[b]
            if (mg.parent_id, mb.parent_id, mg.parent_stm, mb.parent_stm) != (pid, pid, stm, stm):
                raise ValueError("pair/static metadata mismatch")
            if mg.parent_phase != mb.parent_phase:
                raise ValueError("cross-phase sibling pair")
            out.append(Pair(pid, stm, mg.parent_phase, g, b))
    return out


def pair_cell(p: Pair) -> tuple[str, int]:
    return p.parent_phase, p.parent_stm


def cap_and_weight_pairs(pairs: Sequence[Pair], cap: int = PAIR_CAP_PER_CELL) -> tuple[list[Pair], np.ndarray, dict[str, int]]:
    cells: dict[tuple[str, int], list[Pair]] = {}
    for p in pairs:
        cells.setdefault(pair_cell(p), []).append(p)
    if not cells:
        raise ValueError("no T3 training pairs")
    selected: list[Pair] = []
    per_cell: dict[tuple[str, int], int] = {}
    counts: dict[str, int] = {}
    for cell in sorted(cells):
        def key(p: Pair):
            return (hashlib.sha256(f"{PAIR_CAP_SEED}:{p.parent_id}:{p.good}:{p.bad}".encode()).digest(),
                    p.parent_id, p.good, p.bad)
        seq = sorted(cells[cell], key=key)[:cap]
        selected.extend(seq); per_cell[cell] = len(seq)
        counts[f"{cell[0]}_{'white' if cell[1] == 0 else 'black'}"] = len(seq)
    ncell = len(per_cell)
    weights = np.asarray([1.0 / (ncell * per_cell[pair_cell(p)]) for p in selected], dtype=np.float64)
    if not np.isclose(weights.sum(), 1.0, rtol=0, atol=1e-12):
        raise AssertionError("balanced pair weights drift")
    return selected, weights, counts


def fit_normalization(x: np.ndarray, row_ids: Iterable[int]) -> tuple[np.ndarray, np.ndarray]:
    ids = np.asarray(sorted(set(map(int, row_ids))), dtype=np.int64)
    if len(ids) == 0:
        raise ValueError("no normalization rows")
    mean = x[ids].mean(axis=0); std = x[ids].std(axis=0)
    std[std < 1e-8] = 1.0
    return mean, std


def forward(model: dict[str, np.ndarray], x: np.ndarray):
    z0 = x @ model["W0"] + model["b0"]; a0 = np.maximum(z0, 0)
    z1 = a0 @ model["W1"] + model["b1"]; a1 = np.maximum(z1, 0)
    z2 = a1 @ model["W2"] + model["b2"]; a2 = np.maximum(z2, 0)
    out = (a2 @ model["W3"] + model["b3"])[:, 0]
    return out, (x, z0, a0, z1, a1, z2, a2)


def backward(model: dict[str, np.ndarray], cache, grad_out: np.ndarray) -> dict[str, np.ndarray]:
    x, z0, a0, z1, a1, z2, a2 = cache
    go = grad_out[:, None]
    g: dict[str, np.ndarray] = {}
    g["W3"] = a2.T @ go; g["b3"] = go.sum(0)
    gz2 = (go @ model["W3"].T) * (z2 > 0)
    g["W2"] = a1.T @ gz2; g["b2"] = gz2.sum(0)
    gz1 = (gz2 @ model["W2"].T) * (z1 > 0)
    g["W1"] = a0.T @ gz1; g["b1"] = gz1.sum(0)
    gz0 = (gz1 @ model["W1"].T) * (z0 > 0)
    g["W0"] = x.T @ gz0; g["b0"] = gz0.sum(0)
    return g


def _is_weight(k: str) -> bool:
    return k.startswith("W")


def _clip(grads: dict[str, np.ndarray]) -> float:
    norm = math.sqrt(sum(float(np.sum(v * v)) for v in grads.values()))
    if norm > GRAD_CLIP:
        s = GRAD_CLIP / norm
        for k in grads: grads[k] *= s
    return norm


def lr_for_epoch(epoch: int) -> float:
    lr = LR0
    if epoch >= 40: lr *= 0.3
    if epoch >= 60: lr *= 0.3
    return lr


def train_model(model: dict[str, np.ndarray], x: np.ndarray, base_parent: np.ndarray,
                pairs: Sequence[Pair], mean: np.ndarray, std: np.ndarray) -> tuple[dict[str, np.ndarray], dict]:
    ps, w, counts = cap_and_weight_pairs(pairs)
    xn = (x - mean) / std
    am = {k: np.zeros_like(v) for k, v in model.items()}; av = {k: np.zeros_like(v) for k, v in model.items()}
    rng = np.random.default_rng(ORDER_SEED); base_order = np.arange(len(ps)); step = 0; history = []
    beta1, beta2, eps = 0.9, 0.999, 1e-8
    for epoch in range(EPOCHS):
        order = base_order.copy(); rng.shuffle(order); weighted_loss = 0.0; maxnorm = 0.0
        for start in range(0, len(order), BATCH_SIZE):
            ii = order[start:start+BATCH_SIZE]
            good = np.asarray([ps[int(j)].good for j in ii], dtype=np.int64)
            bad = np.asarray([ps[int(j)].bad for j in ii], dtype=np.int64)
            bw = w[ii]; rows = np.concatenate([good, bad])
            rr, cache = forward(model, xn[rows]); n = len(good)
            d = (base_parent[good] + rr[:n]) - (base_parent[bad] + rr[n:])
            weighted_loss += float(np.dot(bw, np.logaddexp(0.0, -d)))
            dd = -1.0 / (1.0 + np.exp(np.clip(d, -60, 60)))
            fac = bw * len(ps) / BATCH_SIZE
            grad = np.concatenate([dd * fac, -dd * fac])
            grads = backward(model, cache, grad)
            for k in grads:
                if _is_weight(k): grads[k] += WEIGHT_DECAY * model[k]
            maxnorm = max(maxnorm, _clip(grads)); step += 1; lr = lr_for_epoch(epoch)
            for k in model:
                am[k] = beta1 * am[k] + (1-beta1) * grads[k]
                av[k] = beta2 * av[k] + (1-beta2) * (grads[k] * grads[k])
                mh = am[k] / (1-beta1**step); vh = av[k] / (1-beta2**step)
                model[k] -= lr * mh / (np.sqrt(vh) + eps)
        if not all(np.all(np.isfinite(v)) for v in model.values()):
            raise FloatingPointError("nonfinite T3 parameters")
        history.append({"epoch": epoch+1, "lr": lr_for_epoch(epoch),
                        "weighted_pairwise_logloss": weighted_loss,
                        "pairs": len(ps), "max_preclip_grad_norm": maxnorm})
    return model, {"pairs": len(ps), "cell_counts": counts, "history": history}


def _model_json(model: dict[str, np.ndarray]) -> dict:
    return {k: v.tolist() for k, v in sorted(model.items())}


def _save(path: Path, payload: dict) -> str:
    raw = (json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()
    path.write_bytes(raw)
    return hashlib.sha256(raw).hexdigest()


def build_inputs(rffd: Path, meta: Sequence[StaticMeta]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    allf = rf.read_rffd(rffd); f6 = rf.family_matrix(allf, "F6_ALL_NEW")
    if f6.shape != (len(meta), F6_WIDTH):
        raise ValueError(f"F6 geometry drift: {f6.shape}")
    d1 = np.asarray([m.d1_parent for m in meta], dtype=np.float64)
    b = np.concatenate([f6, d1[:, None]], axis=1)
    base_parent = np.asarray([m.t_baseline_parent for m in meta], dtype=np.float64)
    if not np.all(np.isfinite(f6)) or not np.all(np.isfinite(b)) or not np.all(np.isfinite(base_parent)):
        raise ValueError("nonfinite T3 input")
    return f6, b, base_parent


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rffd", type=Path, required=True)
    ap.add_argument("--static-meta", type=Path, required=True)
    ap.add_argument("--pairs", type=Path, required=True)
    ap.add_argument("--output-a", type=Path, required=True)
    ap.add_argument("--output-b", type=Path, required=True)
    ap.add_argument("--receipt", type=Path, required=True)
    ap.add_argument("--t0-sha", required=True)
    ap.add_argument("--d1-sha", required=True)
    ap.add_argument("--rf1-sha", required=True)
    args = ap.parse_args()

    meta = load_static_meta(args.static_meta); pairs = load_pairs(args.pairs, meta)
    xa, xb, base_parent = build_inputs(args.rffd, meta)
    selected, _, cell_counts = cap_and_weight_pairs(pairs)
    rows = [p.good for p in selected] + [p.bad for p in selected]
    mean_f6, std_f6 = fit_normalization(xa, rows)
    d1col = xb[:, 66:67]; d1mean, d1std = fit_normalization(d1col, rows)
    mean_b = np.concatenate([mean_f6, d1mean]); std_b = np.concatenate([std_f6, d1std])
    ma, mb, init_receipt = init_paired_models()
    ma, ra = train_model(ma, xa, base_parent, pairs, mean_f6, std_f6)
    mb, rb = train_model(mb, xb, base_parent, pairs, mean_b, std_b)
    common = {
        "schema": SCHEMA,
        "base_score": "T0_parent = -T0_child",
        "score_convention": "higher_is_better_for_parent",
        "architecture": {"hidden": list(HIDDEN), "relu_hidden": True, "linear_output": True},
        "optimization": {"optimizer": "adam", "init_seed": INIT_SEED, "order_seed": ORDER_SEED,
                         "pair_cap_seed": PAIR_CAP_SEED, "d1_init_seed": D1_INIT_SEED,
                         "batch_size": BATCH_SIZE, "epochs": EPOCHS, "lr0": LR0,
                         "lr_multiplier_after_epochs": {"40": 0.3, "60": 0.3},
                         "weight_decay": WEIGHT_DECAY, "grad_clip": GRAD_CLIP,
                         "pair_cap_per_phase_colour_cell": PAIR_CAP_PER_CELL,
                         "equal_cell_total_weight": True},
        "provenance": {"t0_sha256": args.t0_sha, "d1_sha256": args.d1_sha, "rf1_sha256": args.rf1_sha},
        "nested_initialization": init_receipt,
        "forbidden_inputs": sorted(FORBIDDEN_INPUT_NAMES),
    }
    pa = dict(common); pa.update({"arm": "T3_F6_ONLY", "input_width": 66,
                                  "input_names": list(rf.family_names("F6_ALL_NEW")),
                                  "normalization": {"mean": mean_f6.tolist(), "std": std_f6.tolist()},
                                  "params": _model_json(ma), "training": ra})
    pb = dict(common); pb.update({"arm": "T3_JOINT_D1_F6", "input_width": 67,
                                  "input_names": list(rf.family_names("F6_ALL_NEW")) + ["sealed_d1_parent_score"],
                                  "normalization": {"mean": mean_b.tolist(), "std": std_b.tolist()},
                                  "params": _model_json(mb), "training": rb})
    sha_a = _save(args.output_a, pa); sha_b = _save(args.output_b, pb)
    receipt = {"schema": "jass.t3_rf1_joint_ab_train_receipt.v1", "artifact_a_sha256": sha_a,
               "artifact_b_sha256": sha_b, "pairs": len(selected), "cell_counts": cell_counts,
               "shared_f6_normalization": True, "shared_pair_list_and_order": True,
               "q1_label_reads": 0, "q1_score_reads": 0, "t2_fresh_label_reads": 0,
               "t2_fresh_score_reads": 0, "rf1_fresh_label_reads": 0, "rf1_fresh_score_reads": 0}
    args.receipt.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
