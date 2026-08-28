#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Mechanical launcher/serialized-replay verifier for Joint T+D F0.

The immutable 1614 screen source contains one documented bracket typo and the
first F0 helper was authored against a later duplicate preregistration. This
launcher repairs only those two mechanical references in-memory, then verifies
that the serialized B1/C0 bytes themselves replay the preregistered 1614 DEV
metrics before F1 can be authorized. No fresh cohort surface is exposed.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import types

import numpy as np

TOOLS = Path(__file__).resolve().parent
SCREEN = TOOLS / "transfer_capacity_joint_screen.py"
FREEZE = TOOLS / "joint_td_candidate_freeze.py"

PINNED_PREREG_SHA = "ffa7d7c802bc2f50731a6d3bb32e80a4c02567d8"
DUPLICATE_PREREG_SHA = "b280fc1f4878133a41168f4bbc6a537eec526cdc"
SCREEN_CODE_SHA = "d8241edc680eb50f324b2440fbde2bdadad29178"
B1_EXPECTED = (0.6532855603952976, 0.26667692149925654)
C0_EXPECTED = (0.6726851201348883, 0.3072860585550941)
REPLAY_TOL = 1e-12


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def arg_value(name: str) -> Path:
    try:
        i = sys.argv.index(name)
    except ValueError as e:
        raise SystemExit(f"missing launcher argument {name}") from e
    if i + 1 >= len(sys.argv):
        raise SystemExit(f"missing value for {name}")
    return Path(sys.argv[i + 1])


def load_exact_screen() -> types.ModuleType:
    src = SCREEN.read_text(encoding="utf-8")
    old = 'mask=np.asarray([int(p) in ids for p in allm["pid"])'
    new = 'mask=np.asarray([int(p) in ids for p in allm["pid"]])'
    if src.count(old) != 1:
        raise SystemExit(f"expected one documented 1614 screen typo, found {src.count(old)}")
    m = types.ModuleType("transfer_capacity_joint_screen")
    m.__file__ = str(SCREEN)
    m.__package__ = None
    exec(compile(src.replace(old, new), str(SCREEN), "exec"), m.__dict__, m.__dict__)
    if m.SPLIT_SEED != 2026090401 or m.B1_SEED != 2026090402:
        raise SystemExit("1614 frozen seed drift")
    sys.modules["transfer_capacity_joint_screen"] = m
    return m


def run_freeze_with_pinned_prereg() -> None:
    src = FREEZE.read_text(encoding="utf-8")
    old = f'PREREG_SHA = "{DUPLICATE_PREREG_SHA}"'
    new = f'PREREG_SHA = "{PINNED_PREREG_SHA}"'
    if src.count(old) != 1:
        raise SystemExit(f"expected one duplicate-prereg F0 reference, found {src.count(old)}")
    ns = {"__name__": "__main__", "__file__": str(FREEZE), "__package__": None}
    exec(compile(src.replace(old, new), str(FREEZE), "exec"), ns, ns)


def phase_matrix(pieces: np.ndarray) -> np.ndarray:
    phase = np.zeros((len(pieces), 4), dtype=np.float64)
    for i, p in enumerate(pieces):
        phase[i, 0 if p >= 30 else 1 if p >= 20 else 2 if p >= 12 else 3] = 1.0
    return phase


def verify_serialized_replay(s: types.ModuleType) -> None:
    out = arg_value("--outdir")
    design_path = arg_value("--design")
    groups_path = arg_value("--groups")
    d1_path = arg_value("--d1-policy")

    dnp = np.load(design_path, allow_pickle=False)
    design = {k: dnp[k] for k in dnp.files}
    groups = s.read_groups(groups_path)
    pmeta = s.parent_meta(groups)

    manifest_path = out / "b1-freeze.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema") != "jass.b1_frozen_scorer.v1":
        raise SystemExit("B1 frozen schema drift")
    bdir = out / "b1"
    for name, expected in manifest["arrays_sha256"].items():
        if sha256(bdir / name) != expected:
            raise SystemExit(f"B1 serialized array SHA drift: {name}")

    mp = np.load(bdir / "pattern_index_map.npy", allow_pickle=False)
    emb = np.load(bdir / "embeddings.npy", allow_pickle=False)
    mu = np.load(bdir / "extras_mean.npy", allow_pickle=False)
    sd = np.load(bdir / "extras_std.npy", allow_pickle=False)
    W1 = np.load(bdir / "W1.npy", allow_pickle=False)
    b1 = np.load(bdir / "b1.npy", allow_pickle=False)
    W2 = np.load(bdir / "W2.npy", allow_pickle=False)
    b2 = float(np.load(bdir / "b2.npy", allow_pickle=False)[0])
    cols = design["canonical_cols"].astype(np.int64)
    signs = design["signs"].astype(np.float64)
    if int(cols.max()) >= len(mp):
        raise SystemExit("B1 frozen pattern map too short")
    ci = mp[cols]
    ex = (design["extras"].astype(np.float64) - mu) / sd
    e = (emb[ci] * signs[:, :, None]).sum(1)
    inp = np.concatenate([
        e, ex, phase_matrix(groups["pieces"]), groups["stm"].astype(np.float64)[:, None]
    ], axis=1)
    b1_score = np.maximum(inp.dot(W1) + b1, 0).dot(W2) + b2
    b1g = s.strata(groups, pmeta, b1_score)[0]["global"]
    if abs(b1g["pairwise"] - B1_EXPECTED[0]) > REPLAY_TOL or abs(b1g["top_hit"] - B1_EXPECTED[1]) > REPLAY_TOL:
        raise SystemExit(f"serialized B1 replay mismatch: {b1g}")

    c0_path = out / "c0-freeze.json"
    c0j = json.loads(c0_path.read_text(encoding="utf-8"))
    if c0j.get("schema") != "jass.c0_joint_td_frozen_scorer.v1":
        raise SystemExit("C0 frozen schema drift")
    c0w = np.asarray(c0j["coefficients_float64"], dtype=np.float64)
    if c0w.shape != (7,) or float(c0j.get("l2")) != 1e-6:
        raise SystemExit("C0 frozen coefficient contract drift")
    dx = s.d_features(design, groups)
    dw, db = s.load_d1(d1_path)
    d1 = np.asarray([dx[i].dot(dw if groups["stm"][i] == 0 else db) for i in range(len(dx))])
    c0x = np.column_stack([
        groups["t0"].copy(), d1, phase_matrix(groups["pieces"]), groups["stm"]
    ])
    c0_score = c0x.dot(c0w)
    c0g = s.strata(groups, pmeta, c0_score)[0]["global"]
    if abs(c0g["pairwise"] - C0_EXPECTED[0]) > REPLAY_TOL or abs(c0g["top_hit"] - C0_EXPECTED[1]) > REPLAY_TOL:
        raise SystemExit(f"serialized C0 replay mismatch: {c0g}")

    freeze_path = out / "candidate-freeze.json"
    freeze = json.loads(freeze_path.read_text(encoding="utf-8"))
    if freeze.get("prereg_sha") != PINNED_PREREG_SHA:
        raise SystemExit("candidate freeze prereg SHA drift")
    freeze["screen_code_sha"] = SCREEN_CODE_SHA
    freeze["screen_source_job"] = "cpx62-1614-l3-transfer-capacity-joint-screen-v2"
    freeze["screen_source_attempt"] = "20260828T092856Z-d8241edc"
    freeze["serialized_replay"] = {
        "tolerance": REPLAY_TOL,
        "B1": {"passed": True, "pairwise": b1g["pairwise"], "top_hit": b1g["top_hit"]},
        "C0": {"passed": True, "pairwise": c0g["pairwise"], "top_hit": c0g["top_hit"]},
    }
    freeze["f1_authorized"] = True
    freeze_path.write_text(json.dumps(freeze, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    screen = load_exact_screen()
    run_freeze_with_pinned_prereg()
    verify_serialized_replay(screen)
