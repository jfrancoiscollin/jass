from __future__ import annotations

import json
from pathlib import Path
import struct

import numpy as np
import pytest

from jobs.tools import residual_feature_probe as rf


def test_widths_and_family_slices_are_frozen():
    assert rf.CTX2_WIDTH == 15
    assert (rf.F1_WIDTH, rf.F2_WIDTH, rf.F3_WIDTH, rf.F4_WIDTH, rf.F5_WIDTH) == (12,14,12,16,12)
    assert rf.ALL_NEW_WIDTH == 66
    assert rf.TOTAL_WIDTH == 81
    x = np.arange(2 * 81, dtype=np.float64).reshape(2,81)
    assert rf.family_matrix(x, "F1_CAPTURE_GEOMETRY").shape == (2,12)
    assert rf.family_matrix(x, "F6_ALL_NEW").shape == (2,66)
    assert np.array_equal(rf.family_matrix(x, "F6_ALL_NEW"), x[:,15:81])


def test_forbidden_input_guard():
    rf.validate_feature_names(["capture_count", "promotion_distance", "holes3"])
    for bad in ["q200_parent", "WDL", "d1_score", "t2_value", "source_id", "split_member", "target_label"]:
        with pytest.raises(ValueError):
            rf.validate_feature_names([bad])


def _synthetic():
    rng = np.random.default_rng(17)
    x = rng.normal(size=(40, 4))
    d1 = rng.normal(scale=0.15, size=40)
    good = np.arange(0, 20, dtype=np.int64)
    bad = np.arange(20, 40, dtype=np.int64)
    # Make feature 0 informative in the preregistered direction.
    x[good, 0] += 1.5
    x[bad, 0] -= 1.5
    return x, d1, good, bad


def test_fixed_d1_residual_optimizer_is_deterministic_and_improves_margin():
    x, d1, good, bad = _synthetic()
    a = rf.fit_probe("F_TEST", x, d1, good, bad, d1_sha256="abc")
    b = rf.fit_probe("F_TEST", x, d1, good, bad, d1_sha256="abc")
    assert np.array_equal(a.mean, b.mean)
    assert np.array_equal(a.std, b.std)
    assert np.array_equal(a.weights, b.weights)
    before = np.mean(d1[good] - d1[bad])
    pred = a.predict(x, d1)
    after = np.mean(pred[good] - pred[bad])
    assert after > before
    # Baseline coefficient stays exactly one: adding C to every D1 score adds C to every prediction.
    assert np.allclose(a.predict(x, d1 + 7.0) - pred, 7.0, atol=0.0, rtol=0.0)
    assert a.to_json_dict()["d1_coefficient"] == 1.0
    assert a.to_json_dict()["intercept"] == 0.0


def test_artifact_roundtrip(tmp_path: Path):
    x, d1, good, bad = _synthetic()
    a = rf.fit_probe("F_TEST", x, d1, good, bad, d1_sha256="deadbeef")
    path = tmp_path / "probe.json"
    rf.save_artifact(path, a)
    b = rf.load_artifact(path)
    assert b.family == a.family
    assert b.d1_sha256 == "deadbeef"
    assert np.array_equal(b.mean, a.mean)
    assert np.array_equal(b.std, a.std)
    assert np.array_equal(b.weights, a.weights)
    assert np.array_equal(b.predict(x, d1), a.predict(x, d1))
    obj = json.loads(path.read_text())
    obj["d1_coefficient"] = 0.9
    with pytest.raises(ValueError):
        rf.ProbeArtifact.from_json_dict(obj)


def test_parent_sign_sham_is_cluster_shared_and_deterministic():
    x = np.arange(24, dtype=np.float64).reshape(6,4) + 1
    fp = ["A", "A", "B", "B", "C", "C"]
    a = rf.apply_parent_sign_sham(x, fp, cohort="TRAIN_A", sham_index=7)
    b = rf.apply_parent_sign_sham(x, fp, cohort="TRAIN_A", sham_index=7)
    assert np.array_equal(a, b)
    for i in (0,2,4):
        assert np.array_equal(a[i] / x[i], a[i+1] / x[i+1])
    # Cohort is part of the sign hash, as required for independent TRAIN/B/C shams.
    signs_train = [rf.parent_sign(k, "TRAIN_A", 7) for k in ("A","B","C","D","E","F")]
    signs_dev = [rf.parent_sign(k, "DEV_B", 7) for k in ("A","B","C","D","E","F")]
    assert signs_train != signs_dev


def test_deterministic_pair_cap():
    g = np.arange(100, dtype=np.int64)
    b = g + 100
    fps = [f"p{i//2}" for i in range(100)]
    a = rf.deterministic_pair_cap(g,b,fps,cap=17)
    c = rf.deterministic_pair_cap(g,b,fps,cap=17)
    assert np.array_equal(a,c)
    assert len(a) == 17


def test_rffd_parser_and_width_guard(tmp_path: Path):
    x = np.arange(162, dtype=np.float32).reshape(2,81)
    path = tmp_path / "x.rffd"
    path.write_bytes(b"RFFD" + struct.pack("<II", 2, 81) + x.astype("<f4").tobytes())
    y = rf.read_rffd(path)
    assert np.array_equal(y, x.astype(np.float64))
    bad = tmp_path / "bad.rffd"
    bad.write_bytes(b"RFFD" + struct.pack("<II", 2, 80) + np.zeros(160,dtype="<f4").tobytes())
    with pytest.raises(ValueError):
        rf.read_rffd(bad)
