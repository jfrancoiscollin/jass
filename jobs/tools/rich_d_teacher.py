#!/usr/bin/env python3
"""Deterministic offline Rich-D teacher for L3_RICH_D_TEACHER_TO_T_V1_20260827.

Scientific contract:
- exactly 333 static inputs:
  120 production extras + 200 board-plane bits + 6 move features
  + 1 CURRICULUM parent-POV child scalar + 4 phase one-hot + 2 context.
- q5k/q50/q200/WDL are NEVER model inputs.
- separate white-parent / black-parent MLP banks, 333->384->192->96->1.
- deterministic NumPy Adam, fixed seeds and schedule.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

import numpy as np

INPUT_WIDTH = 333
EVAL_WIDTH = 120
BOARD_WIDTH = 200
MOVE_WIDTH = 6
PHASE_WIDTH = 4
CONTEXT_WIDTH = 2
HIDDEN = (384, 192, 96)

INIT_SEED = 2026090101
PAIR_ORDER_SEED = 2026090102
BATCH_SIZE = 4096
EPOCHS = 80
LR0 = 1e-3
WEIGHT_DECAY = 1e-5
GRAD_CLIP = 5.0
PAIR_CAP_PER_COLOUR = 500_000

JNNW_MAGIC = b"JNNW"
JNNW_HEADER = 8
JNNW_RECORD = 38
JNNW_DTYPE = np.dtype([
    ("wm", "<u8"), ("wk", "<u8"), ("bm", "<u8"), ("bk", "<u8"),
    ("stm", "u1"), ("score", "<i4"), ("wdl", "i1"),
])
assert JNNW_DTYPE.itemsize == JNNW_RECORD

PHASES = ("P0", "P1", "P2", "P3")
FORBIDDEN_INPUT_NAMES = frozenset({
    "q5k_parent", "q50_parent", "q200_parent", "wdl",
    "exact_parent_utility", "source", "partition", "holdout",
})

MOVE_NAMES = (
    "num_captures", "captured_kings", "promotes",
    "moving_king", "from_norm", "to_norm",
)

@dataclass(frozen=True)
class StaticMeta:
    parent_id: int
    parent_stm: int
    phase: str
    pieces: int
    legal_moves: int
    from_sq: int
    to_sq: int
    num_captures: int
    captured_kings: int
    promotes: int
    moving_king: int
    t_baseline_parent: float

@dataclass(frozen=True)
class Pair:
    parent_id: int
    colour: int
    good: int
    bad: int

def read_jnnw(path: Path) -> np.ndarray:
    raw_size = path.stat().st_size
    if raw_size < JNNW_HEADER:
        raise ValueError("JNNW truncated header")
    with path.open("rb") as f:
        hdr = f.read(JNNW_HEADER)
    if hdr[:4] != JNNW_MAGIC:
        raise ValueError("JNNW bad magic")
    n = struct.unpack_from("<I", hdr, 4)[0]
    body = raw_size - JNNW_HEADER
    if body != n * JNNW_RECORD:
        raise ValueError(f"JNNW size/count drift: n={n}, body={body}")
    if n == 0:
        return np.empty(0, dtype=JNNW_DTYPE)
    return np.memmap(path, dtype=JNNW_DTYPE, mode="r", offset=JNNW_HEADER, shape=(n,))

def read_feat(path: Path) -> np.ndarray:
    raw = path.read_bytes()
    if len(raw) < 12 or raw[:4] != b"FEAT":
        raise ValueError("bad FEAT header")
    n, k = struct.unpack_from("<II", raw, 4)
    if k != EVAL_WIDTH:
        raise ValueError(f"eval feature width drift: {k}")
    expected = 12 + n * k * 4
    if len(raw) != expected:
        raise ValueError("FEAT size drift")
    return np.frombuffer(raw, dtype="<f4", offset=12, count=n*k).reshape(n, k).astype(np.float64)

def board_planes(records: np.ndarray) -> np.ndarray:
    """Return four 50-square 0/1 planes in fixed wm,wk,bm,bk order."""
    out = np.empty((len(records), BOARD_WIDTH), dtype=np.float64)
    for pidx, field in enumerate(("wm", "wk", "bm", "bk")):
        vals = np.asarray(records[field], dtype=np.uint64)
        for sq in range(50):
            out[:, pidx * 50 + sq] = ((vals >> np.uint64(sq)) & np.uint64(1)).astype(np.float64)
    return out

def phase_one_hot(phase: str) -> np.ndarray:
    if phase not in PHASES:
        raise ValueError(f"invalid phase {phase!r}")
    a = np.zeros(PHASE_WIDTH, dtype=np.float64)
    a[PHASES.index(phase)] = 1.0
    return a

def build_static_features(
    eval_features: np.ndarray,
    records: np.ndarray,
    meta: Sequence[StaticMeta],
) -> np.ndarray:
    """Build exactly 333 allowed static model inputs.

    Deliberately accepts no q5k/q50/q200/WDL argument.
    """
    n = len(meta)
    if eval_features.shape != (n, EVAL_WIDTH):
        raise ValueError("eval feature geometry drift")
    if len(records) != n:
        raise ValueError("JNNW/meta length drift")
    b = board_planes(records)
    x = np.empty((n, INPUT_WIDTH), dtype=np.float64)
    x[:, :EVAL_WIDTH] = eval_features
    x[:, EVAL_WIDTH:EVAL_WIDTH + BOARD_WIDTH] = b
    for i, m in enumerate(meta):
        if m.parent_stm not in (0, 1):
            raise ValueError("invalid parent colour")
        x[i, 320:326] = (
            float(m.num_captures),
            float(m.captured_kings),
            float(m.promotes),
            float(m.moving_king),
            float(m.from_sq) / 50.0,
            float(m.to_sq) / 50.0,
        )
        x[i, 326] = float(m.t_baseline_parent)
        x[i, 327:331] = phase_one_hot(m.phase)
        x[i, 331] = float(m.pieces) / 40.0
        x[i, 332] = float(m.legal_moves) / 16.0
    if x.shape[1] != INPUT_WIDTH or not np.all(np.isfinite(x)):
        raise ValueError("nonfinite or width-drifted Rich-D input")
    return x

def load_static_meta(path: Path) -> list[StaticMeta]:
    out: list[StaticMeta] = []
    with path.open(newline="", encoding="utf-8") as f:
        rd = csv.DictReader(f, delimiter="\t")
        required = {
            "parent_id","parent_stm","phase","pieces","legal_moves","from","to",
            "num_captures","captured_kings","promotes","moving_king","t_baseline_parent",
        }
        if rd.fieldnames is None or not required.issubset(rd.fieldnames):
            raise ValueError(f"static meta fields drift: {rd.fieldnames!r}")
        if FORBIDDEN_INPUT_NAMES.intersection(required):
            raise AssertionError("forbidden model input slipped into required set")
        for r in rd:
            out.append(StaticMeta(
                parent_id=int(r["parent_id"]),
                parent_stm=int(r["parent_stm"]),
                phase=r["phase"],
                pieces=int(r["pieces"]),
                legal_moves=int(r["legal_moves"]),
                from_sq=int(r["from"]),
                to_sq=int(r["to"]),
                num_captures=int(r["num_captures"]),
                captured_kings=int(r["captured_kings"]),
                promotes=int(r["promotes"]),
                moving_king=int(r["moving_king"]),
                t_baseline_parent=float(r["t_baseline_parent"]),
            ))
    return out

def load_pairs(path: Path) -> list[Pair]:
    """Load already-accepted good>bad constraints.

    q50/q200 are used upstream to construct this file and are not consumed here.
    """
    out: list[Pair] = []
    with path.open(newline="", encoding="utf-8") as f:
        rd = csv.DictReader(f, delimiter="\t")
        required = {"parent_id", "parent_stm", "good_row", "bad_row"}
        if rd.fieldnames is None or not required.issubset(rd.fieldnames):
            raise ValueError("pair file fields drift")
        for r in rd:
            c = int(r["parent_stm"])
            if c not in (0,1):
                raise ValueError("invalid colour in pair file")
            out.append(Pair(int(r["parent_id"]), c, int(r["good_row"]), int(r["bad_row"])))
    return out

def cap_pairs(pairs: Sequence[Pair], colour: int, cap: int = PAIR_CAP_PER_COLOUR) -> list[Pair]:
    seq = [p for p in pairs if p.colour == colour]
    if len(seq) <= cap:
        return sorted(seq, key=lambda p: (p.parent_id, p.good, p.bad))
    def key(p: Pair) -> tuple[bytes,int,int,int]:
        h = hashlib.sha256(f"{PAIR_ORDER_SEED}:{p.parent_id}:{p.good}:{p.bad}".encode()).digest()
        return h, p.parent_id, p.good, p.bad
    return sorted(seq, key=key)[:cap]

def fit_normalization(x: np.ndarray, row_ids: Iterable[int]) -> tuple[np.ndarray, np.ndarray]:
    ids = np.asarray(sorted(set(int(i) for i in row_ids)), dtype=np.int64)
    if len(ids) == 0:
        raise ValueError("no training rows for normalization")
    z = x[ids]
    mean = z.mean(axis=0)
    std = z.std(axis=0)
    std[std < 1e-8] = 1.0
    return mean, std

def init_bank(seed: int = INIT_SEED) -> dict[str, np.ndarray]:
    rng = np.random.default_rng(seed)
    dims = (INPUT_WIDTH,) + HIDDEN + (1,)
    bank: dict[str,np.ndarray] = {}
    for i in range(len(dims)-1):
        fan_in = dims[i]
        bank[f"W{i}"] = rng.standard_normal((dims[i], dims[i+1])) * math.sqrt(2.0 / fan_in)
        bank[f"b{i}"] = np.zeros(dims[i+1], dtype=np.float64)
    return bank

def forward(bank: dict[str,np.ndarray], x: np.ndarray) -> tuple[np.ndarray, list[tuple[np.ndarray,np.ndarray]]]:
    a = x
    cache: list[tuple[np.ndarray,np.ndarray]] = []
    nlayers = len(HIDDEN) + 1
    for i in range(nlayers):
        z = a @ bank[f"W{i}"] + bank[f"b{i}"]
        cache.append((a,z))
        a = np.maximum(z, 0.0) if i < nlayers-1 else z
    return a[:,0], cache

def backward(bank: dict[str,np.ndarray], cache: list[tuple[np.ndarray,np.ndarray]], grad_score: np.ndarray) -> dict[str,np.ndarray]:
    nlayers = len(HIDDEN) + 1
    g = grad_score[:,None]
    grads: dict[str,np.ndarray] = {}
    for i in reversed(range(nlayers)):
        a_prev, z = cache[i]
        if i < nlayers-1:
            g = g * (z > 0.0)
        grads[f"W{i}"] = a_prev.T @ g
        grads[f"b{i}"] = g.sum(axis=0)
        g = g @ bank[f"W{i}"].T
    return grads

def merge_grads(a: dict[str,np.ndarray], b: dict[str,np.ndarray]) -> dict[str,np.ndarray]:
    return {k: a[k] + b[k] for k in a}

def clip_grads(grads: dict[str,np.ndarray]) -> float:
    norm = math.sqrt(sum(float(np.sum(g*g)) for g in grads.values()))
    if norm > GRAD_CLIP:
        scale = GRAD_CLIP / norm
        for k in grads:
            grads[k] *= scale
    return norm

def lr_for_epoch(epoch: int) -> float:
    lr = LR0
    if epoch >= 40:
        lr *= 0.3
    if epoch >= 60:
        lr *= 0.3
    return lr

def train_colour(
    x: np.ndarray, pairs: Sequence[Pair], colour: int, mean: np.ndarray, std: np.ndarray
) -> tuple[dict[str,np.ndarray], dict]:
    ps = cap_pairs(pairs, colour)
    if not ps:
        raise ValueError(f"no pairs for colour {colour}")
    xn = (x - mean) / std
    bank = init_bank(INIT_SEED)
    m = {k: np.zeros_like(v) for k,v in bank.items()}
    v = {k: np.zeros_like(vv) for k,vv in bank.items()}
    rng = np.random.default_rng(INIT_SEED)
    beta1,beta2,eps = 0.9,0.999,1e-8
    step = 0
    history = []
    base_order = np.arange(len(ps), dtype=np.int64)
    for epoch in range(EPOCHS):
        order = base_order.copy()
        rng.shuffle(order)
        total_loss = 0.0
        seen = 0
        max_preclip = 0.0
        for start in range(0, len(order), BATCH_SIZE):
            idx = order[start:start+BATCH_SIZE]
            good = np.asarray([ps[int(j)].good for j in idx], dtype=np.int64)
            bad = np.asarray([ps[int(j)].bad for j in idx], dtype=np.int64)
            sg,cg = forward(bank, xn[good])
            sb,cb = forward(bank, xn[bad])
            d = sg - sb
            loss_vec = np.logaddexp(0.0, -d)
            total_loss += float(loss_vec.sum())
            seen += len(d)
            gd = -1.0 / (1.0 + np.exp(np.clip(d, -60.0, 60.0)))
            gd /= float(len(d))
            gg = backward(bank, cg, gd)
            gb = backward(bank, cb, -gd)
            grads = merge_grads(gg, gb)
            for k in grads:
                if k.startswith("W"):
                    grads[k] += WEIGHT_DECAY * bank[k]
            max_preclip = max(max_preclip, clip_grads(grads))
            step += 1
            lr = lr_for_epoch(epoch)
            for k in bank:
                m[k] = beta1*m[k] + (1-beta1)*grads[k]
                v[k] = beta2*v[k] + (1-beta2)*(grads[k]*grads[k])
                mh = m[k] / (1-beta1**step)
                vh = v[k] / (1-beta2**step)
                bank[k] -= lr * mh / (np.sqrt(vh) + eps)
        history.append({
            "epoch": epoch+1,
            "lr": lr_for_epoch(epoch),
            "pairwise_logloss": total_loss / max(seen,1),
            "pairs": seen,
            "max_preclip_grad_norm": max_preclip,
        })
        if not all(np.all(np.isfinite(a)) for a in bank.values()):
            raise FloatingPointError("nonfinite Rich-D parameters")
    return bank, {
        "colour": colour, "epochs": EPOCHS, "batch_size": BATCH_SIZE,
        "pairs": len(ps), "seed": INIT_SEED, "pair_order_seed": PAIR_ORDER_SEED,
        "history": history,
    }

def score_bank(bank: dict[str,np.ndarray], x: np.ndarray, mean: np.ndarray, std: np.ndarray) -> np.ndarray:
    s,_ = forward(bank, (x-mean)/std)
    return s

def artifact_payload(
    banks: dict[str,dict[str,np.ndarray]],
    norms: dict[str,tuple[np.ndarray,np.ndarray]],
    receipts: dict[str,dict],
) -> dict:
    def arr(a: np.ndarray):
        return a.tolist()
    return {
        "schema":"jass.rich_d_teacher.v1",
        "input_width":INPUT_WIDTH,
        "input_contract":{
            "eval_extras":120,"board_planes":200,"move":6,"curriculum_scalar":1,
            "phase_one_hot":4,"parent_context":2,
            "forbidden_inputs":sorted(FORBIDDEN_INPUT_NAMES),
        },
        "architecture":[333,384,192,96,1],
        "activation":"relu",
        "separate_parent_colour_banks":True,
        "optimization":{
            "optimizer":"adam","init_seed":INIT_SEED,"pair_order_seed":PAIR_ORDER_SEED,
            "batch_size":BATCH_SIZE,"epochs":EPOCHS,"lr0":LR0,
            "lr_multiplier_after_epochs":{"40":0.3,"60":0.3},
            "weight_decay":WEIGHT_DECAY,"grad_clip":GRAD_CLIP,
            "pair_cap_per_colour":PAIR_CAP_PER_COLOUR,
        },
        "banks":{
            name:{
                "mean":arr(norms[name][0]),"std":arr(norms[name][1]),
                "params":{k:arr(v) for k,v in sorted(banks[name].items())},
                "receipt":receipts[name],
            } for name in ("white_parent","black_parent")
        },
    }

def save_artifact(path: Path, payload: dict) -> str:
    raw = (json.dumps(payload, sort_keys=True, separators=(",",":"), allow_nan=False) + "\n").encode("utf-8")
    path.write_bytes(raw)
    return hashlib.sha256(raw).hexdigest()

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--feat", type=Path, required=True)
    ap.add_argument("--children", type=Path, required=True)
    ap.add_argument("--static-meta", type=Path, required=True)
    ap.add_argument("--pairs", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--receipt", type=Path, required=True)
    args = ap.parse_args()

    feat = read_feat(args.feat)
    rec = read_jnnw(args.children)
    meta = load_static_meta(args.static_meta)
    if not (len(feat)==len(rec)==len(meta)):
        raise ValueError("input row count drift")
    x = build_static_features(feat, rec, meta)
    pairs = load_pairs(args.pairs)

    banks = {}
    norms = {}
    receipts = {}
    for colour,name in ((0,"white_parent"),(1,"black_parent")):
        ps = cap_pairs(pairs, colour)
        train_rows = [p.good for p in ps] + [p.bad for p in ps]
        mean,std = fit_normalization(x, train_rows)
        bank,receipt = train_colour(x,pairs,colour,mean,std)
        banks[name] = bank
        norms[name] = (mean,std)
        receipts[name] = receipt

    payload = artifact_payload(banks,norms,receipts)
    sha = save_artifact(args.output,payload)
    args.receipt.write_text(json.dumps({
        "schema":"jass.rich_d_teacher_train_receipt.v1",
        "artifact_sha256":sha,
        "rows":len(x),
        "pairs_white":receipts["white_parent"]["pairs"],
        "pairs_black":receipts["black_parent"]["pairs"],
        "input_width":INPUT_WIDTH,
    },sort_keys=True,indent=2)+"\n",encoding="utf-8")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
