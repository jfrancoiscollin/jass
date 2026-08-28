#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import tempfile
import json

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "jobs" / "tools"
sys.path.insert(0, str(TOOLS))


def load_module():
    p = TOOLS / "transfer_capacity_joint_screen.py"
    src = p.read_text(encoding="utf-8")
    old = 'mask=np.asarray([int(p) in ids for p in allm["pid"])'
    new = 'mask=np.asarray([int(p) in ids for p in allm["pid"]])'
    assert src.count(old) == 1
    code = compile(src.replace(old, new), str(p), "exec")
    ns = {"__name__": "transfer_capacity_joint_screen_test", "__file__": str(p), "__package__": None}
    exec(code, ns, ns)
    return ns


def test_frozen_science_constants_and_guards():
    m = load_module()
    assert m["SPLIT_SEED"] == 2026090401
    assert m["B1_SEED"] == 2026090402
    assert m["BOOTSTRAP_SEED"] == 2026090403
    assert m["GUARDS"] == {"G0": (12.0, 35.0), "G1": (20.0, 60.0), "G2": (35.0, 100.0)}
    assert set(m["ARMS"]) == {
        "A0_M4_REPLICATION", "A1_L2_0", "A2_L2_1E7", "A3_L2_1E6", "A4_L2_1E4",
        "A5_MARGIN_L2_1E6", "A6_MARGIN_L2_1E5", "A7_DENSE_L2_1E6", "A8_DENSE_MARGIN_L2_1E6",
    }


def test_margin_weight_exact_contract():
    m = load_module()
    got = m["margin_weight"](np.asarray([0.0, 25.0, 100.0, 400.0, 900.0]))
    assert np.allclose(got, [0.25, 0.25, 1.0, 4.0, 4.0])


def test_split_is_deterministic_parent_cluster():
    m = load_module()
    a = m["split_bucket"]("canonical-parent-A")
    b = m["split_bucket"]("canonical-parent-A")
    c = m["split_bucket"]("canonical-parent-B")
    assert a == b and 0 <= a < 100 and 0 <= c < 100


def test_dense_pairs_include_top_rest_and_adjacent_without_wrong_order():
    m = load_module()
    g = {
        "parent_id": np.asarray([0,0,0,0], dtype=np.int32),
        "teacher": np.asarray([10.0, 40.0, 30.0, 20.0]),
        "from": np.asarray([1,2,3,4]), "to": np.asarray([5,6,7,8]),
        "num_captures": np.asarray([0,0,0,0]), "captured_kings": np.asarray([0,0,0,0]),
        "promotes": np.asarray([0,0,0,0]), "moving_king": np.asarray([0,0,0,0]),
    }
    pm = {0:{"split":"train"}}
    c = m["make_dense_constraints"](g, pm, "train")
    pairs = list(zip(c["good"].tolist(), c["bad"].tolist()))
    assert (1,2) in pairs and (1,3) in pairs and (1,0) in pairs
    assert (2,3) in pairs and (3,0) in pairs
    assert all(g["teacher"][a] > g["teacher"][b] for a,b in pairs)


def test_anchor_regimes_are_nested_and_a0_semantics_frozen():
    m = load_module()
    assert m["GUARDS"]["G0"][0] < m["GUARDS"]["G1"][0] < m["GUARDS"]["G2"][0]
    assert m["GUARDS"]["G0"][1] < m["GUARDS"]["G1"][1] < m["GUARDS"]["G2"][1]
    assert m["ARMS"]["A0_M4_REPLICATION"] == (1e-5, "top", False)


def test_sealed_d1_zero_refit_input_contract():
    m = load_module()
    policy = {"schema":"jass.deep_sibling_policy.v1","usable":True,
              "weights":{"white_parent":[0.0]*126,"black_parent":[1.0]*126}}
    with tempfile.TemporaryDirectory() as td:
        p=Path(td)/"d1.json"; p.write_text(json.dumps(policy))
        w,b=m["load_d1"](p)
        assert w.shape == (126,) and b.shape == (126,)
        assert np.all(w == 0) and np.all(b == 1)


def test_no_fresh_or_strength_execution_surface():
    text = (TOOLS / "transfer_capacity_joint_screen.py").read_text(encoding="utf-8")
    assert "--q200" not in text
    assert "gen-opening-pool" not in text
    assert "strength_games\":0" in text.replace(" ", "")
    assert "fresh_q200_generated\":0" in text.replace(" ", "")
    assert "promotion_authorized\":False" in text.replace(" ", "")
