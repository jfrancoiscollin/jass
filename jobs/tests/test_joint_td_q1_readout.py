from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
P = ROOT / "jobs" / "tools" / "joint_td_q1_readout.py"
spec = importlib.util.spec_from_file_location("q1", P)
q1 = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(q1)


def sib(i, pid, exact, q50, q200, q1000=0.0):
    return q1.Sibling(i, pid, 0, exact, 0.0, q1000, q50, q200)


def test_frozen_constants_and_bootstrap():
    assert q1.PREREG_SHA == "b280fc1f4878133a41168f4bbc6a537eec526cdc"
    assert q1.BOOTSTRAP_SAMPLES == 100_000
    assert q1.BOOTSTRAP_SEED == 2026090421
    assert q1.T0_SHA == "319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1"
    assert q1.D1_SHA == "e91a55500713154f50be74db5d699b64d7684e1c078725d09e1d15e713549b49"
    assert q1.A6_SHA == "271733adb8441630e1bae77b85951c05caa452107d3e8af4782f577347be06ed"


def test_stable_nonterminal_exact_threshold_contract():
    # sign agrees, exactly prereg thresholds => accepted.
    a = sib(0, 7, q1.EXACT_SENTINEL, 10, 30)
    b = sib(1, 7, q1.EXACT_SENTINEL, 0, 0)
    assert q1.stable_relation(a, b) == 1
    # q50 margin below 10 => rejected.
    assert q1.stable_relation(sib(0, 7, 2, 9, 100), b) == 0
    # q200 margin below 30 => rejected.
    assert q1.stable_relation(sib(0, 7, 2, 100, 29), b) == 0
    # sign disagreement => rejected.
    assert q1.stable_relation(sib(0, 7, 2, 100, -100), b) == 0
    # q1000 never enters acceptance.
    assert q1.stable_relation(sib(0, 7, 2, 10, 30, q1000=-9999), sib(1, 7, 2, 0, 0, q1000=9999)) == 1


def test_exact_terminal_tb_precedence():
    # Exact W>D>L wins despite contradictory q50/q200.
    win = sib(0, 3, 1, -1000, -1000)
    draw = sib(1, 3, 0, 1000, 1000)
    loss = sib(2, 3, -1, 2000, 2000)
    assert q1.stable_relation(win, draw) == 1
    assert q1.stable_relation(draw, loss) == 1
    assert q1.stable_relation(loss, win) == -1


def test_ratio_guard():
    assert q1.ratio(1.0, 2.0)["value"] == 0.5
    assert q1.ratio(1.0, 0.0)["defined"] is False
    assert q1.ratio(1.0, -1.0)["defined"] is False
