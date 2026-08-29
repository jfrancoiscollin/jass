import numpy as np

from jobs.tools import residual_feature_probe as rf
from jobs.tools import t3_rf1_joint_ab as t3


def test_fixed_widths_and_seeds():
    assert rf.ALL_NEW_WIDTH == 66
    assert t3.F6_WIDTH == t3.A_WIDTH == 66
    assert t3.B_WIDTH == 67
    assert t3.HIDDEN == (256, 128, 64)
    assert (t3.INIT_SEED, t3.ORDER_SEED, t3.PAIR_CAP_SEED, t3.D1_INIT_SEED) == (
        2026090801, 2026090802, 2026090803, 2026090804
    )
    assert t3.EPOCHS == 80 and t3.BATCH_SIZE == 4096
    assert t3.PAIR_CAP_PER_CELL == 150000


def test_nested_initialization_is_shared_except_d1_row():
    a1, b1, r1 = t3.init_paired_models()
    a2, b2, r2 = t3.init_paired_models()
    for k in a1:
        assert np.array_equal(a1[k], a2[k])
    for k in b1:
        assert np.array_equal(b1[k], b2[k])
    assert np.array_equal(a1["W0"], b1["W0"][:66])
    assert b1["W0"].shape == (67, 256)
    for k in ("W1", "W2", "W3", "b0", "b1", "b2", "b3"):
        assert np.array_equal(a1[k], b1[k])
    assert r1 == r2


def test_parent_score_orientation_zero_residual():
    a, _, _ = t3.init_paired_models()
    for k in a:
        a[k][...] = 0.0
    x = np.zeros((3, 66), dtype=np.float64)
    base = np.asarray([12.0, -7.5, 0.0])
    mean = np.zeros(66); std = np.ones(66)
    got = t3.parent_scores(a, x, base, mean, std)
    assert np.array_equal(got, base)


def test_equal_total_cell_weighting():
    meta = [
        t3.StaticMeta(0, 0, "P0", 0.0, 0.0),
        t3.StaticMeta(0, 0, "P0", 0.0, 0.0),
        t3.StaticMeta(1, 1, "P3", 0.0, 0.0),
        t3.StaticMeta(1, 1, "P3", 0.0, 0.0),
        t3.StaticMeta(1, 1, "P3", 0.0, 0.0),
    ]
    pairs = [
        t3.Pair(0, 0, "P0", 0, 1),
        t3.Pair(1, 1, "P3", 2, 3),
        t3.Pair(1, 1, "P3", 2, 4),
    ]
    selected, w, counts = t3.cap_and_weight_pairs(pairs)
    assert len(selected) == 3
    assert counts == {"P0_white": 1, "P3_black": 2}
    assert np.isclose(w[0], 0.5)
    assert np.isclose(w[1] + w[2], 0.5)
    assert np.isclose(w.sum(), 1.0)


def test_forbidden_input_contract_and_positional_f6_names():
    assert len(t3.F6_POSITIONAL_NAMES) == 66
    assert len(set(t3.F6_POSITIONAL_NAMES)) == 66
    for token in ("q200", "q1000", "t2", "wdl", "source", "holdout", "q1"):
        assert token in t3.FORBIDDEN_INPUT_NAMES
    assert "sealed_d1_parent_score" not in t3.FORBIDDEN_INPUT_NAMES
