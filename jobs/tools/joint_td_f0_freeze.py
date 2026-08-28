#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Freeze/replay the preregistered Joint T+D candidates before any fresh read.

This tool is deliberately M3-only.  It reconstructs the already-selected B1 and
C0 candidates from the immutable 1614 implementation, serializes their exact
state, and proves deterministic DEV replay.  It never exposes a fresh cohort,
q50/q200 labels, M5/1612 data, strength, self-play, or promotion surfaces.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import math
from pathlib import Path
import sys

import numpy as np
from scipy.special import expit

TOOLS = Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

PREREG_SHA = "ffa7d7c802bc2f50731a6d3bb32e80a4c02567d8"
SCREEN_CODE_SHA = "d8241edc680eb50f324b2440fbde2bdadad29178"
CURRICULUM_SHA = "319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1"
D1_SHA = "e91a55500713154f50be74db5d699b64d7684e1c078725d09e1d15e713549b49"
A6_G0_SHA = "271733adb8441630e1bae77b85951c05caa452107d3e8af4782f577347be06ed"
SPLIT_SEED = 2026090401
B1_SEED = 2026090402
REPLAY_METRIC_TOL = 1e-9
REPLAY_SCORE_TOL = 1e-12
EXPECTED = {
    "T0": (0.6142493325839539, 0.26753149088174466),
    "D1": (0.6569985012411597, 0.23622006870737836),
    "A6_G0": (0.6197133623717859, 0.2733767454579637),
    "B1": (0.6532855603952976, 0.26667692149925654),
    "C0": (0.6726851201348883, 0.3072860585550941),
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_screen(path: Path) -> dict:
    """Compile the exact d824 source with only its documented bracket shim."""
    src = path.read_text(encoding="utf-8")
    old = 'mask=np.asarray([int(p) in ids for p in allm["pid"])'
    new = 'mask=np.asarray([int(p) in ids for p in allm["pid"]])'
    if src.count(old) != 1:
        raise SystemExit(f"exact 1614 source shim mismatch: {src.count(old)}")
    code = compile(src.replace(old, new), str(path), "exec")
    ns = {"__name__": "joint_td_f0_screen", "__file__": str(path), "__package__": None}
    exec(code, ns, ns)
    if ns["SPLIT_SEED"] != SPLIT_SEED or ns["B1_SEED"] != B1_SEED:
        raise SystemExit("frozen 1614 seed drift")
    return ns


def _pack_array(a: np.ndarray) -> dict:
    a = np.asarray(a)
    if a.dtype.kind == "f":
        b = np.ascontiguousarray(a.astype("<f8", copy=False))
    elif a.dtype.kind in "iu":
        b = np.ascontiguousarray(a.astype("<i4", copy=False))
    else:
        raise TypeError(f"unsupported bundle dtype {a.dtype}")
    return {
        "dtype": b.dtype.str,
        "shape": list(b.shape),
        "data_b64": base64.b64encode(b.tobytes(order="C")).decode("ascii"),
    }


def write_bundle(path: Path, schema: str, arrays: dict[str, np.ndarray], metadata: dict) -> str:
    payload = {
        "schema": schema,
        "format": "canonical-json-base64-little-endian-v1",
        "arrays": {name: _pack_array(arrays[name]) for name in sorted(arrays)},
        "metadata": metadata,
    }
    raw = (json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")
    path.write_bytes(raw)
    return hashlib.sha256(raw).hexdigest()


def read_bundle(path: Path) -> dict:
    j = json.loads(path.read_text(encoding="utf-8"))
    arrays = {}
    for name, d in j["arrays"].items():
        raw = base64.b64decode(d["data_b64"].encode("ascii"))
        arrays[name] = np.frombuffer(raw, dtype=np.dtype(d["dtype"])).reshape(d["shape"]).copy()
    return {"schema": j["schema"], "metadata": j["metadata"], "arrays": arrays}


def phase_matrix(pieces: np.ndarray) -> np.ndarray:
    out = np.zeros((len(pieces), 4), dtype=np.float64)
    for i, p in enumerate(pieces):
        out[i, 0 if p >= 30 else 1 if p >= 20 else 2 if p >= 12 else 3] = 1.0
    return out


def train_b1_exact(screen: dict, design: dict, groups: dict, pmeta: dict, good: np.ndarray, bad: np.ndarray):
    """Byte-for-byte algorithmic copy of d824 b1_probe, plus state capture."""
    cols = design["canonical_cols"].astype(np.int64)
    signs = design["signs"].astype(np.float64)
    train_pids = np.asarray([p for p, v in pmeta.items() if v["split"] == "train"])
    active = np.unique(cols[np.isin(groups["parent_id"], train_pids)])
    mp = np.full(int(cols.max()) + 1, -1, dtype=np.int32)
    mp[active] = np.arange(len(active), dtype=np.int32)
    ci = mp[cols]
    ex = design["extras"].astype(np.float64)
    train_rows = np.isin(groups["parent_id"], train_pids)
    mu = ex[train_rows].mean(0)
    sd = ex[train_rows].std(0)
    sd[sd < 1e-8] = 1
    ex = (ex - mu) / sd
    phase = phase_matrix(groups["pieces"])
    side = groups["stm"].astype(np.float64)[:, None]

    rng = np.random.default_rng(B1_SEED)
    emb = rng.normal(0, .02, size=(len(active), 8))
    W1 = rng.normal(0, .02, size=(133, 64))
    b1 = np.zeros(64)
    W2 = rng.normal(0, .02, size=64)
    b2 = 0.0
    params = [emb, W1, b1, W2]
    ms = [np.zeros_like(x) for x in params]
    vs = [np.zeros_like(x) for x in params]
    mb = 0.0
    vb = 0.0
    step = 0

    for _ep in range(6):
        order = rng.permutation(len(good))
        for st in range(0, len(order), 4096):
            ix = order[st:st + 4096]
            rg = good[ix]
            rb = bad[ix]

            def fwd(rr):
                e = (emb[ci[rr]] * signs[rr, :, None]).sum(1)
                inp = np.concatenate([e, ex[rr], phase[rr], side[rr]], axis=1)
                pre = inp.dot(W1) + b1
                h = np.maximum(pre, 0)
                sc = h.dot(W2) + b2
                return inp, pre, h, sc

            ig, pg, hg, sg = fwd(rg)
            ib, pb, hb, sb = fwd(rb)
            z = sg - sb
            q = -expit(-z) / len(z)
            gW2 = hg.T.dot(q) + hb.T.dot(-q)
            gb2 = float(q.sum() + (-q).sum())
            ghg = q[:, None] * W2
            ghb = -q[:, None] * W2
            gpg = ghg * (pg > 0)
            gpb = ghb * (pb > 0)
            gW1 = ig.T.dot(gpg) + ib.T.dot(gpb)
            gb1 = gpg.sum(0) + gpb.sum(0)
            gig = gpg.dot(W1.T)[:, :8]
            gib = gpb.dot(W1.T)[:, :8]
            gemb = np.zeros_like(emb)
            for k in range(8):
                np.add.at(gemb, ci[rg, k], gig * signs[rg, k, None])
                np.add.at(gemb, ci[rb, k], gib * signs[rb, k, None])
            grads = [gemb, gW1, gb1, gW2]
            step += 1
            for n, (p, g) in enumerate(zip(params, grads)):
                ms[n] = .9 * ms[n] + .1 * g
                vs[n] = .999 * vs[n] + .001 * g * g
                mh = ms[n] / (1 - .9 ** step)
                vh = vs[n] / (1 - .999 ** step)
                p -= 1e-3 * mh / (np.sqrt(vh) + 1e-8)
            mb = .9 * mb + .1 * gb2
            vb = .999 * vb + .001 * gb2 * gb2
            b2 -= 1e-3 * (mb / (1 - .9 ** step)) / (math.sqrt(vb / (1 - .999 ** step)) + 1e-8)

    e = (emb[ci] * signs[:, :, None]).sum(1)
    inp = np.concatenate([e, ex, phase, side], axis=1)
    score = np.maximum(inp.dot(W1) + b1, 0).dot(W2) + b2
    receipt = {
        "seed": B1_SEED,
        "active_patterns": int(len(active)),
        "embedding_dim": 8,
        "dense_extras": 120,
        "phase_one_hot": 4,
        "side": 1,
        "hidden": 64,
        "activation": "relu",
        "optimizer": "adam",
        "lr": 1e-3,
        "batch": 4096,
        "epochs": 6,
        "pair_family": "top_plus_adjacent",
        "parameter_count": int(emb.size + W1.size + b1.size + W2.size + 1),
        "train_only_normalization": True,
        "forbidden_inputs": ["D1", "q1000_as_input", "q50", "q200", "WDL", "search_scores"],
    }
    arrays = {
        "active_patterns": active.astype(np.int32),
        "embedding": emb,
        "W1": W1,
        "b1": b1,
        "W2": W2,
        "b2": np.asarray([b2], dtype=np.float64),
        "extras_mean": mu,
        "extras_std": sd,
    }
    return score, receipt, arrays


def score_b1_bundle(bundle: dict, design: dict, groups: dict) -> np.ndarray:
    a = bundle["arrays"]
    cols = design["canonical_cols"].astype(np.int64)
    signs = design["signs"].astype(np.float64)
    active = a["active_patterns"].astype(np.int64)
    mp = np.full(int(cols.max()) + 1, -1, dtype=np.int32)
    if np.any(active > cols.max()):
        raise SystemExit("B1 active-pattern map outside design domain")
    mp[active] = np.arange(len(active), dtype=np.int32)
    ci = mp[cols]
    ex = (design["extras"].astype(np.float64) - a["extras_mean"]) / a["extras_std"]
    phase = phase_matrix(groups["pieces"])
    side = groups["stm"].astype(np.float64)[:, None]
    e = (a["embedding"][ci] * signs[:, :, None]).sum(1)
    inp = np.concatenate([e, ex, phase, side], axis=1)
    return np.maximum(inp.dot(a["W1"]) + a["b1"], 0).dot(a["W2"]) + float(a["b2"][0])


def score_c0_bundle(bundle: dict, t0: np.ndarray, d1: np.ndarray, groups: dict) -> np.ndarray:
    a = bundle["arrays"]
    x = np.column_stack([t0, d1, phase_matrix(groups["pieces"]), groups["stm"]])
    return x.dot(a["weights"]) + float(a["intercept"][0])


def metric_global(screen: dict, groups: dict, pmeta: dict, score: np.ndarray) -> dict:
    return screen["strata"](groups, pmeta, score)[0]["global"]


def assert_metric(name: str, got: dict):
    ep, et = EXPECTED[name]
    if abs(float(got["pairwise"]) - ep) > REPLAY_METRIC_TOL:
        raise SystemExit(f"{name} pairwise replay mismatch: {got['pairwise']} vs {ep}")
    if abs(float(got["top_hit"]) - et) > REPLAY_METRIC_TOL:
        raise SystemExit(f"{name} top_hit replay mismatch: {got['top_hit']} vs {et}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--screen-source", required=True)
    ap.add_argument("--design", required=True)
    ap.add_argument("--constraints", required=True)
    ap.add_argument("--groups", required=True)
    ap.add_argument("--children", required=True)
    ap.add_argument("--curriculum", required=True)
    ap.add_argument("--d1-policy", required=True)
    ap.add_argument("--a6-g0", required=True)
    ap.add_argument("--score-binary", required=True)
    ap.add_argument("--outdir", required=True)
    args = ap.parse_args()

    paths = {k: Path(v) for k, v in vars(args).items() if k not in {"outdir"}}
    for key, p in paths.items():
        if key == "score_binary":
            continue
        low = str(p).lower()
        if any(token in low for token in ("1610", "1612", "q200", "fresh")):
            raise SystemExit(f"forbidden F0 input surface: {p}")
        if not p.exists():
            raise SystemExit(f"missing input: {p}")
    out = Path(args.outdir)
    out.mkdir(parents=True, exist_ok=True)

    if sha256(paths["curriculum"]) != CURRICULUM_SHA:
        raise SystemExit("T0/CURRICULUM raw SHA drift")
    if sha256(paths["d1_policy"]) != D1_SHA:
        raise SystemExit("sealed D1 SHA drift")
    if sha256(paths["a6_g0"]) != A6_G0_SHA:
        raise SystemExit("A6-G0 raw SHA drift")

    screen = load_screen(paths["screen_source"])
    dnp = np.load(paths["design"], allow_pickle=False)
    design = {k: dnp[k] for k in dnp.files}
    cnp = np.load(paths["constraints"], allow_pickle=False)
    cons = {k: cnp[k] for k in cnp.files}
    groups = screen["read_groups"](paths["groups"])
    if len(groups["parent_id"]) != screen["M3_EXPECTED_ROWS"] or len(cons["good"]) != screen["M3_EXPECTED_CONSTRAINTS"]:
        raise SystemExit("M3 support drift")
    pmeta = screen["parent_meta"](groups)
    train = {p for p, v in pmeta.items() if v["split"] == "train"}
    if len(train) + sum(v["split"] == "dev" for v in pmeta.values()) != screen["M3_EXPECTED_PARENTS"]:
        raise SystemExit("M3 parent split drift")

    header, _w0 = screen["m4"].load_pjtw(paths["curriculum"])
    top = screen["filter_constraints"](cons, train)
    dense = screen["make_dense_constraints"](groups, pmeta, "train")

    # Baseline frozen scores.
    t0 = groups["t0"].copy()
    dx = screen["d_features"](design, groups)
    dw, db = screen["load_d1"](paths["d1_policy"])
    d1 = np.asarray([dx[i].dot(dw if groups["stm"][i] == 0 else db) for i in range(len(dx))])
    t0_metric = metric_global(screen, groups, pmeta, t0)
    d1_metric = metric_global(screen, groups, pmeta, d1)
    assert_metric("T0", t0_metric)
    assert_metric("D1", d1_metric)

    # Exact persisted A6-G0: no fit, score only.
    a6_dir = out / "a6-replay"
    a6_dir.mkdir(exist_ok=True)
    a6_score = screen["score_binary"](
        paths["score_binary"], paths["children"], paths["curriculum"], paths["a6_g0"], a6_dir, "dev"
    )
    a6_metric = metric_global(screen, groups, pmeta, a6_score)
    assert_metric("A6_G0", a6_metric)

    # Exact B1 reconstruction and deterministic serialized replay.
    b1_score, b1_receipt, b1_arrays = train_b1_exact(
        screen, design, groups, pmeta, dense["good"].astype(np.int64), dense["bad"].astype(np.int64)
    )
    if b1_receipt["parameter_count"] != 875601:
        raise SystemExit(f"B1 parameter count drift: {b1_receipt['parameter_count']}")
    b1_metric = metric_global(screen, groups, pmeta, b1_score)
    assert_metric("B1", b1_metric)
    b1_path = out / "B1-frozen.json"
    b1_sha = write_bundle(
        b1_path,
        "jass.joint_td_fresh.b1_frozen.v1",
        b1_arrays,
        {
            "prereg_sha": PREREG_SHA,
            "source_code_sha": SCREEN_CODE_SHA,
            "split_seed": SPLIT_SEED,
            "receipt": b1_receipt,
            "dev_expected": {"pairwise": EXPECTED["B1"][0], "top_hit": EXPECTED["B1"][1]},
            "replay_metric_tolerance": REPLAY_METRIC_TOL,
        },
    )
    b1_replay = score_b1_bundle(read_bundle(b1_path), design, groups)
    if float(np.max(np.abs(b1_replay - b1_score))) > REPLAY_SCORE_TOL:
        raise SystemExit("B1 serialized scoring replay mismatch")
    b1_replay_metric = metric_global(screen, groups, pmeta, b1_replay)
    assert_metric("B1", b1_replay_metric)

    # Exact C0 reconstruction selected by 1614; no fresh input and no retune.
    good = top["good"].astype(np.int64)
    bad = top["bad"].astype(np.int64)
    c0x = np.column_stack([t0, d1, phase_matrix(groups["pieces"]), groups["stm"]])
    c0w, c0_receipt = screen["fit_dense_pair"](c0x, good, bad, l2=1e-6)
    c0_score = c0x.dot(c0w)
    c0_metric = metric_global(screen, groups, pmeta, c0_score)
    assert_metric("C0", c0_metric)
    c0_path = out / "C0-frozen.json"
    c0_sha = write_bundle(
        c0_path,
        "jass.joint_td_fresh.c0_frozen.v1",
        {"weights": c0w, "intercept": np.asarray([0.0], dtype=np.float64)},
        {
            "prereg_sha": PREREG_SHA,
            "source_code_sha": SCREEN_CODE_SHA,
            "split_seed": SPLIT_SEED,
            "inputs": ["T0_scalar", "D1_scalar", "phase_onehot_P0_P1_P2_P3", "parent_colour"],
            "objective": "pairwise_logistic",
            "l2": 1e-6,
            "fit_receipt": c0_receipt,
            "dev_expected": {"pairwise": EXPECTED["C0"][0], "top_hit": EXPECTED["C0"][1]},
            "replay_metric_tolerance": REPLAY_METRIC_TOL,
        },
    )
    c0_replay = score_c0_bundle(read_bundle(c0_path), t0, d1, groups)
    if float(np.max(np.abs(c0_replay - c0_score))) > REPLAY_SCORE_TOL:
        raise SystemExit("C0 serialized scoring replay mismatch")
    c0_replay_metric = metric_global(screen, groups, pmeta, c0_replay)
    assert_metric("C0", c0_replay_metric)

    receipt = {
        "schema": "jass.joint_td_fresh.f0_candidate_freeze.v1",
        "verdict": "JOINT_TD_F0_CANDIDATE_FREEZE_READY",
        "passed": True,
        "prereg_sha": PREREG_SHA,
        "screen_source_job": "cpx62-1614-l3-transfer-capacity-joint-screen-v2",
        "screen_source_attempt": "20260828T092856Z-d8241edc",
        "screen_code_sha": SCREEN_CODE_SHA,
        "split_seed": SPLIT_SEED,
        "replay_metric_tolerance": REPLAY_METRIC_TOL,
        "replay_score_tolerance": REPLAY_SCORE_TOL,
        "candidates": {
            "T0": {"sha256": CURRICULUM_SHA, "metric": t0_metric, "refit": False},
            "D1": {"sha256": D1_SHA, "metric": d1_metric, "refit": False},
            "A6_G0": {"sha256": A6_G0_SHA, "metric": a6_metric, "refit": False},
            "B1": {"sha256": b1_sha, "metric": b1_replay_metric, "receipt": b1_receipt, "replay": True},
            "C0": {"sha256": c0_sha, "metric": c0_replay_metric, "receipt": c0_receipt, "replay": True},
        },
        "guards": {
            "fresh_parent_reads": 0,
            "fresh_label_reads": 0,
            "q50_reads": 0,
            "q200_reads": 0,
            "q1000_fresh_reads": 0,
            "m5_1612_reads": 0,
            "d1_refits": 0,
            "a6_refits": 0,
            "selfplay": 0,
            "strength_games": 0,
            "promotion_authorized": False,
            "automatic_promotion": False,
        },
        "f1_authorized": True,
    }
    (out / "candidate-freeze-receipt.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8"
    )
    print(json.dumps({"verdict": receipt["verdict"], "B1_sha256": b1_sha, "C0_sha256": c0_sha}, sort_keys=True))


if __name__ == "__main__":
    main()
