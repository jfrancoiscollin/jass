from __future__ import annotations

import importlib
import json
from pathlib import Path
import sys
import tempfile

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "jobs" / "tools"
sys.path.insert(0, str(TOOLS))


def load():
    return importlib.import_module("joint_td_candidate_freeze_f0")


def test_exact_f0_provenance_and_candidate_contract():
    m = load()
    assert m.PREREG_SHA == "ffa7d7c802bc2f50731a6d3bb32e80a4c02567d8"
    assert m.SCREEN_JOB == "cpx62-1614-l3-transfer-capacity-joint-screen-v2"
    assert m.SCREEN_ATTEMPT == "20260828T092856Z-d8241edc"
    assert m.READOUT_JOB == "cpx62-1615-l3-transfer-capacity-joint-readout-publish-v1"
    assert m.READOUT_ATTEMPT == "20260828T100556Z-d8241edc"
    assert m.T0_SHA == "319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1"
    assert m.D1_SHA == "e91a55500713154f50be74db5d699b64d7684e1c078725d09e1d15e713549b49"
    assert m.A6_G0_SHA == "271733adb8441630e1bae77b85951c05caa452107d3e8af4782f577347be06ed"
    assert m.B1_SEED == 2026090402
    assert m.B1_PARAMETER_COUNT == 875601
    assert m.C0_L2 == 1e-6
    assert m.REPLAY_TOL == 1e-12
    m.verify_frozen_contract()


def test_no_forbidden_fresh_or_m5_1612_input_surface():
    m = load()
    base = Path(m.freeze.__file__).read_text(encoding="utf-8")
    wrapper = Path(m.__file__).read_text(encoding="utf-8")
    # Exact F0 CLI is old frozen-data only. No future cohort can be supplied.
    for forbidden_arg in ("--fresh", "--q50", "--q200", "--q1000", "--m5", "--1612"):
        assert forbidden_arg not in base
        assert forbidden_arg not in wrapper
    for required_arg in ("--design", "--constraints", "--groups", "--curriculum", "--d1-policy", "--a6-g0", "--outdir"):
        assert required_arg in base
    assert '"fresh_q200": 0' in base
    assert '"fresh_selection": 0' in base
    assert '"selfplay": 0' in base
    assert '"strength_games": 0' in base
    assert '"promotion_authorized": False' in base


def test_b1_numpy_serialization_roundtrip_is_exact():
    m = load()
    arr = np.asarray([[1.25, -2.5], [3.75, 4.0]], dtype=np.float64)
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "x.npy"
        digest = m.freeze._npy(p, arr)
        got = np.load(p, allow_pickle=False)
        assert np.array_equal(got, arr)
        assert digest == m.freeze.sha256(p)


def test_c0_json_serialization_roundtrip_preserves_float64_values():
    m = load()
    coeffs = [float(x) for x in np.asarray([0.1, -0.2, 0.3, 0.4, -0.5, 0.6, 0.7], dtype=np.float64)]
    payload = {
        "schema": "jass.c0_joint_td_frozen_scorer.v1",
        "coefficients_float64": coeffs,
        "l2": m.C0_L2,
        "split_seed": 2026090401,
        "T0_sha256": m.T0_SHA,
        "D1_policy_sha256": m.D1_SHA,
    }
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "c0-freeze.json"
        p.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        got = json.loads(p.read_text(encoding="utf-8"))
        assert got == payload
        assert len(got["coefficients_float64"]) == 7
        assert got["l2"] == 1e-6
