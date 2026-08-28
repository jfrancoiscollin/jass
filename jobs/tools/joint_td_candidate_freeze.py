#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Freeze/replay S0..S4 for the preregistered joint T+D deep-fresh confirmation.

This tool consumes only frozen M3, CURRICULUM, sealed D1 and the selected A6-G0
bytes. It performs deterministic B1/C0 replay on the frozen M3 TRAIN split,
authenticates the frozen 1614 DEV metrics, serializes reusable scorer state and
writes candidate-freeze.json. It has no fresh-cohort selection or deep-label
surface.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.special import expit

import transfer_capacity_joint_screen as s

PREREG_SHA = "b280fc1f4878133a41168f4bbc6a537eec526cdc"
T0_SHA = "319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1"
D1_SHA = "e91a55500713154f50be74db5d699b64d7684e1c078725d09e1d15e713549b49"
A6_G0_SHA = "271733adb8441630e1bae77b85951c05caa452107d3e8af4782f577347be06ed"
B1_PAIRWISE = 0.6532855603952976
B1_TOP_HIT = 0.26667692149925654
C0_PAIRWISE = 0.6726851201348883
C0_TOP_HIT = 0.3072860585550941
TOL = 1e-12


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def _npy(path: Path, a: np.ndarray) -> str:
    np.save(path, np.asarray(a), allow_pickle=False)
    return sha256(path)


def replay_b1(design: dict, groups: dict, pmeta: dict, train_pairs: tuple[np.ndarray, np.ndarray], out: Path):
    # Exact 1614 b1_probe training semantics; only serialization is added.
    cols = design["canonical_cols"].astype(np.int64)
    signs = design["signs"].astype(np.float64)
    train_ids = np.asarray([p for p, v in pmeta.items() if v["split"] == "train"])
    active = np.unique(cols[np.isin(groups["parent_id"], train_ids)])
    mp = np.full(int(cols.max()) + 1, -1, dtype=np.int32)
    mp[active] = np.arange(len(active), dtype=np.int32)
    ci = mp[cols]
    ex = design["extras"].astype(np.float64)
    train_rows = np.isin(groups["parent_id"], train_ids)
    mu = ex[train_rows].mean(0)
    sd = ex[train_rows].std(0)
    sd[sd < 1e-8] = 1
    ex = (ex - mu) / sd
    phase = np.zeros((len(ex), 4))
    side = groups["stm"].astype(np.float64)[:, None]
    for i, p in enumerate(groups["pieces"]):
        phase[i, (0 if p >= 30 else 1 if p >= 20 else 2 if p >= 12 else 3)] = 1

    rng = np.random.default_rng(s.B1_SEED)
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
    good, bad = train_pairs

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
            b2 -= 1e-3 * (mb / (1 - .9 ** step)) / (np.sqrt(vb / (1 - .999 ** step)) + 1e-8)

    e = (emb[ci] * signs[:, :, None]).sum(1)
    inp = np.concatenate([e, ex, phase, side], axis=1)
    score = np.maximum(inp.dot(W1) + b1, 0).dot(W2) + b2
    receipt = {
        "seed": s.B1_SEED,
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
        "feature_order": ["signed_pattern_embedding_sum_8", "normalized_extras_120", "phase_P0_P1_P2_P3", "parent_side"],
        "forbidden_inputs": ["D1", "q1000_as_input", "q50", "q200", "WDL", "search_scores"],
    }
    if receipt["parameter_count"] != 875601:
        raise SystemExit(f"B1 parameter count drift: {receipt['parameter_count']}")

    bdir = out / "b1"
    bdir.mkdir(parents=True, exist_ok=True)
    arrays = {
        "active_patterns.npy": active.astype(np.int64),
        "pattern_index_map.npy": mp.astype(np.int32),
        "embeddings.npy": emb.astype(np.float64),
        "extras_mean.npy": mu.astype(np.float64),
        "extras_std.npy": sd.astype(np.float64),
        "W1.npy": W1.astype(np.float64),
        "b1.npy": b1.astype(np.float64),
        "W2.npy": W2.astype(np.float64),
        "b2.npy": np.asarray([b2], dtype=np.float64),
    }
    shas = {name: _npy(bdir / name, arr) for name, arr in arrays.items()}
    manifest = {"schema": "jass.b1_frozen_scorer.v1", "receipt": receipt, "arrays_sha256": shas}
    manifest_path = out / "b1-freeze.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return score, receipt, manifest_path


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--design", required=True)
    ap.add_argument("--constraints", required=True)
    ap.add_argument("--groups", required=True)
    ap.add_argument("--curriculum", required=True)
    ap.add_argument("--d1-policy", required=True)
    ap.add_argument("--a6-g0", required=True)
    ap.add_argument("--outdir", required=True)
    args = ap.parse_args()

    out = Path(args.outdir)
    out.mkdir(parents=True, exist_ok=True)
    design_path = Path(args.design)
    constraints_path = Path(args.constraints)
    groups_path = Path(args.groups)
    curriculum = Path(args.curriculum)
    d1_policy = Path(args.d1_policy)
    a6 = Path(args.a6_g0)

    checks = {
        "T0": (sha256(curriculum), T0_SHA),
        "D1": (sha256(d1_policy), D1_SHA),
        "A6_G0": (sha256(a6), A6_G0_SHA),
    }
    bad = {k: v for k, v in checks.items() if v[0] != v[1]}
    if bad:
        raise SystemExit(f"candidate source SHA drift: {bad}")

    dnp = np.load(design_path, allow_pickle=False)
    design = {k: dnp[k] for k in dnp.files}
    cnp = np.load(constraints_path, allow_pickle=False)
    cons = {k: cnp[k] for k in cnp.files}
    groups = s.read_groups(groups_path)
    if len(groups["parent_id"]) != s.M3_EXPECTED_ROWS or len(cons["good"]) != s.M3_EXPECTED_CONSTRAINTS:
        raise SystemExit("M3 support drift")
    pmeta = s.parent_meta(groups)
    train_ids = {p for p, v in pmeta.items() if v["split"] == "train"}
    top = s.filter_constraints(cons, train_ids)
    dense = s.make_dense_constraints(groups, pmeta, "train")

    b1_score, b1_receipt, b1_manifest = replay_b1(
        design, groups, pmeta,
        (dense["good"].astype(np.int64), dense["bad"].astype(np.int64)), out,
    )
    b1_stats, _ = s.strata(groups, pmeta, b1_score)
    b1g = b1_stats["global"]
    if abs(b1g["pairwise"] - B1_PAIRWISE) > TOL or abs(b1g["top_hit"] - B1_TOP_HIT) > TOL:
        raise SystemExit(f"B1 replay mismatch: {b1g}")

    dx = s.d_features(design, groups)
    dw, db = s.load_d1(d1_policy)
    d1 = np.asarray([dx[i].dot(dw if groups["stm"][i] == 0 else db) for i in range(len(dx))])
    t0 = groups["t0"].copy()
    phase = np.zeros((len(dx), 4))
    for i, p in enumerate(groups["pieces"]):
        phase[i, (0 if p >= 30 else 1 if p >= 20 else 2 if p >= 12 else 3)] = 1
    c0x = np.column_stack([t0, d1, phase, groups["stm"]])
    good = top["good"].astype(np.int64)
    bad_rows = top["bad"].astype(np.int64)
    c0w, c0_receipt = s.fit_dense_pair(c0x, good, bad_rows, l2=1e-6)
    if len(c0w) != 7:
        raise SystemExit(f"C0 coefficient width drift: {len(c0w)}")
    c0_score = c0x.dot(c0w)
    c0_stats, _ = s.strata(groups, pmeta, c0_score)
    c0g = c0_stats["global"]
    if abs(c0g["pairwise"] - C0_PAIRWISE) > TOL or abs(c0g["top_hit"] - C0_TOP_HIT) > TOL:
        raise SystemExit(f"C0 replay mismatch: {c0g}")

    c0_artifact = out / "c0-freeze.json"
    c0_payload = {
        "schema": "jass.c0_joint_td_frozen_scorer.v1",
        "feature_order": ["T0", "D1", "phase_P0", "phase_P1", "phase_P2", "phase_P3", "parent_side"],
        "coefficients_float64": [float(x) for x in c0w],
        "fit_receipt": c0_receipt,
        "l2": 1e-6,
        "split_seed": s.SPLIT_SEED,
        "T0_sha256": T0_SHA,
        "D1_policy_sha256": D1_SHA,
    }
    c0_artifact.write_text(json.dumps(c0_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    freeze = {
        "schema": "jass.joint_td_candidate_freeze.v1",
        "verdict": "JOINT_TD_CANDIDATE_FREEZE_READY",
        "prereg_sha": PREREG_SHA,
        "frozen_before_fresh_selection": True,
        "m3_replay_split_seed": s.SPLIT_SEED,
        "candidates": {
            "S0_T0": {"type": "PatternEval", "sha256": T0_SHA},
            "S1_D1": {"type": "sealed_dssd_static", "sha256": D1_SHA, "refit": False},
            "S2_A6_G0": {"type": "PatternEval", "sha256": A6_G0_SHA, "refit": False},
            "S3_B1": {
                "type": "nonlinear_same_observables",
                "manifest": b1_manifest.name,
                "manifest_sha256": sha256(b1_manifest),
                "receipt": b1_receipt,
                "dev_replay": b1g,
                "expected_dev": {"pairwise": B1_PAIRWISE, "top_hit": B1_TOP_HIT, "tolerance": TOL},
            },
            "S4_C0": {
                "type": "minimal_joint_T_plus_D",
                "artifact": c0_artifact.name,
                "artifact_sha256": sha256(c0_artifact),
                "coefficients": 7,
                "dev_replay": c0g,
                "expected_dev": {"pairwise": C0_PAIRWISE, "top_hit": C0_TOP_HIT, "tolerance": TOL},
            },
        },
        "source_hashes": {
            "design_sha256": sha256(design_path),
            "constraints_sha256": sha256(constraints_path),
            "groups_sha256": sha256(groups_path),
        },
        "guards": {
            "fresh_selection": 0,
            "fresh_q50": 0,
            "fresh_q200": 0,
            "fresh_q1000": 0,
            "fresh_model_selection": 0,
            "d1_refits": 0,
            "a6_refits": 0,
            "selfplay": 0,
            "strength_games": 0,
            "promotion_authorized": False,
        },
    }
    freeze_path = out / "candidate-freeze.json"
    freeze_path.write_text(json.dumps(freeze, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "verdict": freeze["verdict"],
        "candidate_freeze_sha256": sha256(freeze_path),
        "B1": b1g,
        "C0": c0g,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
