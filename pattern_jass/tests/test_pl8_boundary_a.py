from __future__ import annotations

from pathlib import Path

import numpy as np

from jobs.tools import pl8_fit
from jobs.tools import pl8_fresh_select
from jobs.tools import pl8_deep_readout

ROOT = Path(__file__).resolve().parents[2]


def test_frozen_pl8_geometry_and_seeds():
    assert pl8_fit.INPUT_WIDTH == 138
    assert pl8_fit.LATENT == 8
    assert pl8_fit.PARAMS == 1121
    assert pl8_fit.TEMPERATURE == 100.0
    assert pl8_fit.FIT_SEED == 2026103101
    assert pl8_fit.L2 == 1.0e-5
    assert pl8_fresh_select.SEED == 2026103120
    assert pl8_fresh_select.PER_PHASE == 2000
    assert pl8_fresh_select.TOTAL == 8000
    assert pl8_deep_readout.BOOTSTRAP_SEED == 2026103121
    assert pl8_deep_readout.BOOTSTRAP_SAMPLES == 200000
    assert pl8_deep_readout.MIN_ACCEPTED == 6000
    assert pl8_deep_readout.MIN_ACCEPTED_PHASE == 1200
    assert pl8_deep_readout.MIN_ACCEPTED_COLOUR == 2400


def test_xavier_initialization_is_deterministic():
    a = pl8_fit.init_params()
    b = pl8_fit.init_params()
    assert a.shape == (1121,)
    assert np.array_equal(a, b)
    n1 = 8 * 138
    assert np.all(a[n1:n1 + 8] == 0.0)
    assert a[-1] == 0.0


def test_listwise_analytic_gradient_matches_central_difference():
    rng = np.random.default_rng(42)
    # Four parents, two siblings each; one parent in each phase with colors
    # chosen so all eight strata cannot be represented in this tiny unit. The
    # objective itself receives already-frozen parent weights, which is the part
    # being differentiated here.
    x = rng.normal(size=(8, 138))
    mu = x.mean(axis=0)
    sigma = x.std(axis=0)
    sigma[sigma < 1e-6] = 1.0
    starts = np.asarray([0, 2, 4, 6], dtype=np.int64)
    counts = np.asarray([2, 2, 2, 2], dtype=np.int64)
    teacher = np.asarray([30, -20, 10, 50, -5, 25, 80, 0], dtype=np.float64)
    q = pl8_fit.softmax_segments(teacher / pl8_fit.TEMPERATURE, starts, counts)
    tr = {
        "starts": starts,
        "counts": counts,
        "q": q,
        "row_weight": np.repeat(np.full(4, 0.25), 2),
        "t0": rng.normal(size=8),
    }
    theta = pl8_fit.init_params()
    loss, grad = pl8_fit.objective(theta, x, mu, sigma, tr, max_batch_rows=4)
    assert np.isfinite(loss)
    assert np.all(np.isfinite(grad))
    eps = 1e-6
    for idx in (0, 137, 500, 1103, 1112, 1120):
        up = theta.copy(); dn = theta.copy()
        up[idx] += eps; dn[idx] -= eps
        fp = pl8_fit.objective(up, x, mu, sigma, tr, max_batch_rows=4)[0]
        fm = pl8_fit.objective(dn, x, mu, sigma, tr, max_batch_rows=4)[0]
        numeric = (fp - fm) / (2.0 * eps)
        assert np.isclose(grad[idx], numeric, rtol=3e-4, atol=3e-6), (idx, grad[idx], numeric)


def test_phase_mapping_and_stable_pair_rule_are_frozen():
    pieces = np.asarray([40, 30, 29, 20, 19, 12, 11, 9])
    assert pl8_fit.phase_id(pieces).tolist() == [0, 0, 1, 1, 2, 2, 3, 3]
    a = pl8_deep_readout.Sib(0, 0, 0, 2, 0, 0, 40, 80)
    b = pl8_deep_readout.Sib(1, 0, 0, 2, 0, 0, 20, 40)
    assert pl8_deep_readout.stable(a, b) == 1
    weak = pl8_deep_readout.Sib(1, 0, 0, 2, 0, 0, 35, 55)
    assert pl8_deep_readout.stable(a, weak) == 0


def test_runtime_sources_have_no_forbidden_inference_dependencies():
    text = "\n".join((ROOT / p).read_text(encoding="utf-8") for p in ("src/pl8.hpp", "src/pl8.cpp"))
    forbidden = (
        "residual_features.hpp",
        "rich_d",
        "micro_search",
        "JASS_T3_F6_MODEL",
        "D1",
    )
    for token in forbidden:
        assert token not in text
    # The runtime implementation may implement INetwork, but must not invoke
    # search or move generation itself.
    assert "generate_legal_moves" not in text
    assert "jass::search(" not in text


def test_prereg_constants_are_present_in_tool_sources():
    fit = (ROOT / "jobs/tools/pl8_fit.py").read_text(encoding="utf-8")
    assert '"L-BFGS-B"' in fit
    for literal in ("maxiter\":300", "maxcor\":10", "gtol\":1e-6", "ftol\":1e-12"):
        assert literal in fit.replace(" ", "")
    assert "2026103101" in fit
    assert "TEMPERATURE = 100.0" in fit
