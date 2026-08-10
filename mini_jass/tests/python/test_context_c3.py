"""Train-only and non-promotable contracts for contextual C3."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest

from mini_jass_lab.context import COMPONENTS
from mini_jass_lab.context_c3 import canonical_fold_ids, fit_tanh_linear

ROOT = Path(__file__).resolve().parents[2]


def _tool(name: str):
    path = ROOT / "tools" / name
    spec = importlib.util.spec_from_file_location(name.removesuffix(".py"), path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


C3 = _tool("run_contextual_c3.py")


def test_canonical_folds_keep_raw_views_together_and_are_stable() -> None:
    canonical = np.repeat(np.arange(30, dtype=np.int64), 2)
    first = canonical_fold_ids(
        canonical, fold_count=5, namespace="contextual_c3_train_only_folds_v1"
    )
    second = canonical_fold_ids(
        canonical[::-1], fold_count=5, namespace="contextual_c3_train_only_folds_v1"
    )[::-1]
    assert np.array_equal(first, second)
    for canonical_id in np.unique(canonical):
        assert np.unique(first[canonical == canonical_id]).size == 1


def test_tanh_linear_fit_is_deterministic_and_reduces_loss() -> None:
    rng = np.random.default_rng(20260810)
    contexts = rng.normal(0.0, 0.4, size=(600, len(COMPONENTS)))
    truth = np.linspace(-0.7, 0.8, len(COMPONENTS))
    targets = np.tanh(contexts @ truth)
    initial = np.zeros(len(COMPONENTS), dtype=np.float64)
    kwargs = {
        "initial_theta": initial,
        "ridge": 0.0001,
        "max_iterations": 64,
        "tolerance": 1e-10,
        "line_search_steps": 24,
    }
    first, first_report = fit_tanh_linear(contexts, targets, **kwargs)
    second, second_report = fit_tanh_linear(contexts, targets, **kwargs)
    assert np.array_equal(first, second)
    assert first_report == second_report
    assert first_report["final_loss"] < first_report["initial_loss"] * 0.01


def test_c3_resolver_requires_the_frozen_sealed_result(tmp_path: Path) -> None:
    sealed = {
        "schema": "mini_jass.contextual_sealed_read.v1",
        "status": "SEALED_TEST_DESCRIPTIVE_READ_COMPLETE",
        "result_hash": C3.EXPECTED_SEALED_RESULT_HASH,
        "sealed_test_read_count": 1,
        "final_chained_decision_unchanged": C3.EXPECTED_FINAL_DECISION,
        "descriptive_only": True,
        "promotable": False,
    }
    path = tmp_path / "sealed.json"
    path.write_text(json.dumps(sealed), encoding="utf-8")
    config = C3._resolve(
        ROOT / "configs" / "contextual_outcome_supervision.yaml", path
    )
    protocol = config["c3_diagnostic_v1"]["protocol"]
    assert protocol["cohort"] == "train"
    assert all(protocol["forbidden"].values())

    sealed["sealed_test_read_count"] = 2
    path.write_text(json.dumps(sealed), encoding="utf-8")
    with pytest.raises(ValueError, match="sealed-result prerequisite"):
        C3._resolve(ROOT / "configs" / "contextual_outcome_supervision.yaml", path)


def test_c3_runner_and_cpx_entrypoint_are_fail_closed() -> None:
    module = (ROOT / "python" / "mini_jass_lab" / "context_c3.py").read_text(
        encoding="utf-8"
    )
    runner = (ROOT / "tools" / "run_contextual_c3.py").read_text(
        encoding="utf-8"
    )
    job = (ROOT / "jobs" / "run_contextual_c3_cpx.sh").read_text(
        encoding="utf-8"
    )
    assert 'getattr(split, "indices")("train")' in module
    assert 'getattr(split, "indices")("development")' not in module
    assert 'getattr(split, "indices")("frozen_test")' not in module
    assert "sealed_test_read_count_added" in module
    assert "CONTEXTUAL_C3_IMPLEMENTATION_SHA" in job
    assert "CONTEXTUAL_SEALED_RESULT_PATH" in job
    assert "https://download.pytorch.org/whl/cpu" in job
    assert "torch==2.13.0" in job
    assert "scientific-summary.json exceeds 64 KiB" in job
    assert "run_c3_diagnostic" in runner
    assert "EXPECTED_PROTOCOL_HASH" in runner
