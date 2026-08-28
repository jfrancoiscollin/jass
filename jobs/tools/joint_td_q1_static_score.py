#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Inference-only scorer for preregistered Joint T+D Q1.

Consumes already-labelled Q1 sibling states only after S0..S4 have been frozen.
It reconstructs the exact production PatternEval row representation needed by
frozen B1, scores sealed D1 with zero refit, then evaluates frozen C0.  There is
no training, calibration, model selection, search, game play, or label-dependent
branch in this program.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import sys

import numpy as np

TOOLS = Path(__file__).resolve().parents[2] / "pattern_jass" / "tools"
sys.path.insert(0, str(TOOLS))
import master_loader  # type: ignore  # noqa: E402
import train  # type: ignore  # noqa: E402
import train_stream  # type: ignore  # noqa: E402

PREREG_SHA = "b280fc1f4878133a41168f4bbc6a537eec526cdc"
T0_SHA = "319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1"
D1_SHA = "e91a55500713154f50be74db5d699b64d7684e1c078725d09e1d15e713549b49"
A6_SHA = "271733adb8441630e1bae77b85951c05caa452107d3e8af4782f577347be06ed"
B1_MANIFEST_SHA = "052090887dd45f40f14cdb2a336c34b3c5d27c61dd483f82349c3086cd9577c7"
C0_ARTIFACT_SHA = "2b51e8d36f3d0241ca5254de68a686808b6dbf619211c5bbdcc02879921493ba"
EXPECTED_EXTRAS = 120


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def phase_index(pieces: int) -> int:
    if 30 <= pieces <= 40: return 0
    if 20 <= pieces <= 29: return 1
    if 12 <= pieces <= 19: return 2
    if 9 <= pieces <= 11: return 3
    raise ValueError(f"pieces outside frozen Q1 support: {pieces}")


def read_groups(path: Path) -> dict[str, np.ndarray]:
    fields = (
        "row_index", "parent_id", "parent_stm", "parent_pieces", "from", "to",
        "num_captures", "promotes", "moving_king", "captured_kings", "t_baseline_parent",
    )
    cols: dict[str, list[str]] = {k: [] for k in fields}
    with path.open(newline="", encoding="utf-8") as f:
        rd = csv.DictReader(f, delimiter="\t")
        if rd.fieldnames is None or not set(fields).issubset(rd.fieldnames):
            raise ValueError(f"Q1 teacher group fields drift: {rd.fieldnames!r}")
        for r in rd:
            for k in fields: cols[k].append(r[k])
    n = len(cols["row_index"])
    if [int(x) for x in cols["row_index"]] != list(range(n)):
        raise ValueError("Q1 sibling row_index is not contiguous")
    return {
        "parent_id": np.asarray(cols["parent_id"], dtype=np.int32),
        "stm": np.asarray(cols["parent_stm"], dtype=np.int8),
        "pieces": np.asarray(cols["parent_pieces"], dtype=np.int16),
        "from": np.asarray(cols["from"], dtype=np.float64),
        "to": np.asarray(cols["to"], dtype=np.float64),
        "num_captures": np.asarray(cols["num_captures"], dtype=np.float64),
        "promotes": np.asarray(cols["promotes"], dtype=np.float64),
        "moving_king": np.asarray(cols["moving_king"], dtype=np.float64),
        "captured_kings": np.asarray(cols["captured_kings"], dtype=np.float64),
        "t0": np.asarray(cols["t_baseline_parent"], dtype=np.float64),
    }


def load_d1(path: Path) -> tuple[np.ndarray, np.ndarray]:
    if sha256(path) != D1_SHA:
        raise ValueError("sealed D1 SHA mismatch")
    j = json.loads(path.read_text(encoding="utf-8"))
    if j.get("schema") != "jass.deep_sibling_policy.v1" or not j.get("usable"):
        raise ValueError("sealed D1 policy unusable")
    w = np.asarray(j["weights"]["white_parent"], dtype=np.float64)
    b = np.asarray(j["weights"]["black_parent"], dtype=np.float64)
    if w.shape != (126,) or b.shape != (126,):
        raise ValueError("sealed D1 feature width drift")
    return w, b


def verify_freeze(path: Path) -> dict:
    j = json.loads(path.read_text(encoding="utf-8"))
    if j.get("schema") != "jass.joint_td_candidate_freeze.v1" or j.get("verdict") != "JOINT_TD_CANDIDATE_FREEZE_READY":
        raise ValueError("candidate freeze is not PASS")
    if j.get("prereg_sha") != PREREG_SHA or j.get("frozen_before_fresh_selection") is not True:
        raise ValueError("candidate freeze prereg/timing drift")
    c = j["candidates"]
    if c["S0_T0"].get("sha256") != T0_SHA or c["S1_D1"].get("sha256") != D1_SHA:
        raise ValueError("S0/S1 identity drift")
    if c["S2_A6_G0"].get("sha256") != A6_SHA:
        raise ValueError("S2 identity drift")
    if c["S3_B1"].get("manifest_sha256") != B1_MANIFEST_SHA:
        raise ValueError("S3 identity drift")
    if c["S4_C0"].get("artifact_sha256") != C0_ARTIFACT_SHA:
        raise ValueError("S4 identity drift")
    return j


def load_b1(manifest_path: Path, b1_dir: Path) -> tuple[dict, dict[str, np.ndarray]]:
    if sha256(manifest_path) != B1_MANIFEST_SHA:
        raise ValueError("B1 manifest SHA mismatch")
    m = json.loads(manifest_path.read_text(encoding="utf-8"))
    if m.get("schema") != "jass.b1_frozen_scorer.v1":
        raise ValueError("B1 manifest schema drift")
    expected = m.get("arrays_sha256", {})
    names = (
        "active_patterns.npy", "pattern_index_map.npy", "embeddings.npy",
        "extras_mean.npy", "extras_std.npy", "W1.npy", "b1.npy", "W2.npy", "b2.npy",
    )
    arrays: dict[str, np.ndarray] = {}
    for name in names:
        p = b1_dir / name
        if expected.get(name) != sha256(p):
            raise ValueError(f"B1 frozen array SHA mismatch: {name}")
        arrays[name] = np.load(p, allow_pickle=False)
    r = m.get("receipt", {})
    exact = {
        "seed": 2026090402, "embedding_dim": 8, "dense_extras": 120,
        "phase_one_hot": 4, "side": 1, "hidden": 64, "activation": "relu",
        "optimizer": "adam", "lr": 1e-3, "batch": 4096, "epochs": 6,
        "pair_family": "top_plus_adjacent", "parameter_count": 875601,
        "train_only_normalization": True,
    }
    for k, v in exact.items():
        if r.get(k) != v:
            raise ValueError(f"B1 frozen receipt drift for {k}: {r.get(k)!r}")
    return m, arrays


def load_c0(path: Path) -> dict:
    if sha256(path) != C0_ARTIFACT_SHA:
        raise ValueError("C0 artifact SHA mismatch")
    j = json.loads(path.read_text(encoding="utf-8"))
    if j.get("schema") != "jass.c0_joint_td_frozen_scorer.v1":
        raise ValueError("C0 schema drift")
    if j.get("T0_sha256") != T0_SHA or j.get("D1_policy_sha256") != D1_SHA:
        raise ValueError("C0 upstream identity drift")
    if j.get("feature_order") != ["T0", "D1", "phase_P0", "phase_P1", "phase_P2", "phase_P3", "parent_side"]:
        raise ValueError("C0 feature order drift")
    w = np.asarray(j.get("coefficients_float64"), dtype=np.float64)
    if w.shape != (7,) or not np.all(np.isfinite(w)):
        raise ValueError("C0 coefficients drift")
    return j


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--children", type=Path, required=True)
    ap.add_argument("--groups", type=Path, required=True)
    ap.add_argument("--feat", type=Path, required=True)
    ap.add_argument("--candidate-freeze", type=Path, required=True)
    ap.add_argument("--d1-policy", type=Path, required=True)
    ap.add_argument("--b1-manifest", type=Path, required=True)
    ap.add_argument("--b1-dir", type=Path, required=True)
    ap.add_argument("--c0-artifact", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--report", type=Path, required=True)
    args = ap.parse_args()

    freeze = verify_freeze(args.candidate_freeze)
    d1w, d1b = load_d1(args.d1_policy)
    _b1m, ba = load_b1(args.b1_manifest, args.b1_dir)
    c0j = load_c0(args.c0_artifact)

    ds = master_loader.load(str(args.children))
    groups = read_groups(args.groups)
    n = ds.n_records
    if any(len(v) != n for v in groups.values()):
        raise ValueError("Q1 children/groups alignment drift")
    if n == 0 or np.any(ds.score != 0) or np.any(ds.wdl != 0):
        raise ValueError("Q1 child target bytes must remain zero and nonempty")
    if not np.all((groups["stm"] == 0) | (groups["stm"] == 1)):
        raise ValueError("invalid Q1 parent colour")

    extras = train.load_feature_file(str(args.feat), n, standardise=False).astype(np.float64, copy=False)
    if extras.shape != (n, EXPECTED_EXTRAS):
        raise ValueError(f"Q1 production extras drift: {extras.shape}")

    # Exact production fold, identical to the 1614/M3 representation B1 saw.
    folder = train_stream.Folder("exact")
    canonical_cols, signs = folder.cols_signs(ds.black_men, ds.white_men)
    if signs is None or canonical_cols.shape != signs.shape:
        raise ValueError("exact PatternEval fold/sign drift")
    canonical_cols = canonical_cols.astype(np.int64, copy=False)
    signs = signs.astype(np.float64, copy=False)

    # Sealed D1: 120 production extras + six preregistered move-local observables.
    dx = np.column_stack([
        extras,
        groups["num_captures"], groups["captured_kings"], groups["promotes"], groups["moving_king"],
        groups["from"] / 50.0, groups["to"] / 50.0,
    ])
    if dx.shape != (n, 126):
        raise ValueError("Q1 D1 design width drift")
    d1 = np.empty(n, dtype=np.float64)
    white = groups["stm"] == 0
    d1[white] = dx[white].dot(d1w)
    d1[~white] = dx[~white].dot(d1b)

    # Frozen B1 inference.  The -1 entries in the serialized index map retain
    # the exact 1614 numpy semantics (index the final embedding) for patterns
    # absent from M3 TRAIN; this is an immutable part of the selected candidate.
    mp = ba["pattern_index_map.npy"].astype(np.int64, copy=False)
    if canonical_cols.size and int(canonical_cols.max()) >= len(mp):
        raise ValueError("Q1 pattern bucket outside frozen B1 map")
    ci = mp[canonical_cols]
    emb = ba["embeddings.npy"].astype(np.float64, copy=False)
    if np.any(ci < -1) or np.any(ci >= len(emb)):
        raise ValueError("frozen B1 pattern mapping index drift")
    signed_emb = (emb[ci] * signs[:, :, None]).sum(axis=1)
    mu = ba["extras_mean.npy"].astype(np.float64, copy=False)
    sd = ba["extras_std.npy"].astype(np.float64, copy=False)
    if mu.shape != (120,) or sd.shape != (120,) or np.any(sd <= 0):
        raise ValueError("frozen B1 normalization drift")
    normalized = (extras - mu) / sd
    phase = np.zeros((n, 4), dtype=np.float64)
    for i, pc in enumerate(groups["pieces"]): phase[i, phase_index(int(pc))] = 1.0
    side = groups["stm"].astype(np.float64)[:, None]
    inp = np.concatenate([signed_emb, normalized, phase, side], axis=1)
    W1 = ba["W1.npy"].astype(np.float64, copy=False)
    b1v = ba["b1.npy"].astype(np.float64, copy=False)
    W2 = ba["W2.npy"].astype(np.float64, copy=False)
    b2 = float(np.ravel(ba["b2.npy"])[0])
    if inp.shape[1] != 133 or W1.shape != (133, 64) or b1v.shape != (64,) or W2.shape != (64,):
        raise ValueError("frozen B1 dense shape drift")
    b1 = np.maximum(inp.dot(W1) + b1v, 0.0).dot(W2) + b2

    # Frozen C0: [T0, D1, phase4, parent side] and exactly seven coefficients.
    c0w = np.asarray(c0j["coefficients_float64"], dtype=np.float64)
    c0x = np.column_stack([groups["t0"], d1, phase, groups["stm"].astype(np.float64)])
    c0 = c0x.dot(c0w)
    if not all(np.all(np.isfinite(v)) for v in (d1, b1, c0)):
        raise ValueError("non-finite frozen Q1 score")

    with args.output.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter="\t", lineterminator="\n")
        w.writerow(["row_index", "d1_parent", "b1_parent", "c0_parent"])
        for i in range(n):
            w.writerow([i, format(float(d1[i]), ".17g"), format(float(b1[i]), ".17g"), format(float(c0[i]), ".17g")])

    report = {
        "schema": "jass.joint_td_q1_static_score.v1",
        "prereg_sha": PREREG_SHA,
        "rows": int(n),
        "score_convention": "higher_is_better_for_parent",
        "candidate_freeze_sha256": sha256(args.candidate_freeze),
        "candidate_identities": {
            "S0_T0": T0_SHA, "S1_D1": D1_SHA, "S2_A6_G0": A6_SHA,
            "S3_B1_manifest": B1_MANIFEST_SHA, "S4_C0_artifact": C0_ARTIFACT_SHA,
        },
        "freeze_verdict": freeze["verdict"],
        "exact_pattern_fold": True,
        "production_extras": EXPECTED_EXTRAS,
        "d1_refits": 0,
        "b1_refits": 0,
        "c0_refits": 0,
        "post_freeze_fits": 0,
        "q1000_used_for_inference": False,
        "q50_used_for_inference": False,
        "q200_used_for_inference": False,
        "selfplay": 0,
        "strength_games": 0,
        "promotion_authorized": False,
    }
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"rows": n, "verdict": "JOINT_TD_Q1_STATIC_SCORES_READY"}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
