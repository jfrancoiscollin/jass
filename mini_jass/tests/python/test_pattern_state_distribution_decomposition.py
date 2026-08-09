"""Causal contracts for the architecture-correct M18-P decomposition."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pytest

from mini_jass_lab.replay import ReplaySample

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools" / "run_pattern_state_distribution_decomposition.py"
SPEC = importlib.util.spec_from_file_location("run_pattern_m18p", TOOL)
assert SPEC and SPEC.loader
M18P = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M18P)


def _sample(generation: int, game: int, state: int) -> ReplaySample:
    policy = np.zeros(72, dtype=np.float32)
    policy[0] = 1.0
    return ReplaySample(state, float((state % 3) - 1), policy, generation, game, 0)


def _interval(mean: float, lower: float) -> dict[str, float]:
    return {"mean": mean, "lower": lower, "upper": mean + (mean - lower)}


def _contrasts(
    *, exact: tuple[float, float] = (0.0, -0.01),
    honest: tuple[float, float] = (0.0, -0.01),
    labels: tuple[float, float] = (0.0, -0.01),
    path: tuple[float, float] = (0.0, -0.01),
) -> dict[str, dict[str, object]]:
    rows = {
        name: {
            "zero_regret_gain": _interval(0.0, -0.01),
            "value_sign_gain": _interval(0.0, -0.01),
        }
        for name in M18P.CONTRASTS
    }
    rows["state_distribution_exact"]["zero_regret_gain"] = _interval(*exact)
    rows["deployable_composition"]["zero_regret_gain"] = _interval(*honest)
    rows["label_noise_under_mix"]["zero_regret_gain"] = _interval(*labels)
    rows["optimizer_path"]["zero_regret_gain"] = _interval(*path)
    return rows


GATE = {
    "require_ci_above_zero": True,
    "minimum_practical_gain": 0.01,
}


def test_m18p_config_is_fresh_pattern_only_and_reuses_the_repaired_arena() -> None:
    config, loop = M18P._resolve(
        ROOT / "configs" / "l1_pattern_state_distribution_decomposition.yaml"
    )
    assert config["paired_seeds"] == list(range(265001, 265021))
    assert loop["model"]["architecture"] == "folded_pattern_value"
    assert loop["training"]["policy_weight"] == 0.0
    assert loop["generations"] == 8
    assert loop["arena"]["pairs"] == 128
    assert loop["arena"]["confidence_unit"] == "pairs"
    assert loop["arena"]["start_state_source"] == "provided"
    assert config["boundaries"]["cohorts_sealed"] == ["frozen_test"]


def test_m18p_primary_pools_equalize_rows_not_generation_identity() -> None:
    per_generation = {
        generation: [
            _sample(generation, 0, generation * 10),
            _sample(generation, 1, generation * 10 + 1),
        ]
        for generation in range(1, 9)
    }
    wide = [_sample(1, game, 100 + game) for game in range(16)]
    pools, selected, census = M18P.build_pools(per_generation, wide, 265001)
    assert len(selected) == 8
    assert len(pools["MIX_OUTCOME"]) == 16
    assert len(pools["G1_WIDE_OUTCOME"]) == 16
    assert len(pools["G1_ONLY_OUTCOME"]) == 2
    assert census["unit_rows_per_generation"] == 2
    assert census["mix_identity_hash"] != census["g1_wide_identity_hash"]


def test_m18p_path_schedules_share_exact_draw_multiset() -> None:
    one_shot, sequential, audit = M18P.build_mix_schedules(5, 16, 3, 91)
    grouped = np.concatenate(
        [schedule + generation * 5 for generation, schedule in enumerate(sequential)]
    )
    assert one_shot.shape == (16, 3)
    assert len(sequential) == 8
    assert np.array_equal(np.sort(one_shot.ravel()), np.sort(grouped.ravel()))
    assert audit["same_draw_multiset"] is True


def test_m18p_distribution_requires_exact_and_honest_contrasts() -> None:
    result = M18P.build_recommendation(
        _contrasts(exact=(0.02, 0.015), honest=(0.018, 0.012)), GATE
    )
    assert result["identified_mechanism"] == "state_distribution"
    assert result["decision"] == "replicate_state_distribution_factor_on_fresh_seeds"
    assert result["promotable"] is False


def test_m18p_can_identify_optimizer_path_without_distribution() -> None:
    result = M18P.build_recommendation(
        _contrasts(path=(0.02, 0.011), labels=(0.03, 0.02)), GATE
    )
    assert result["identified_mechanism"] == "optimizer_path"
    assert result["label_noise_pass"] is True


def test_m18p_does_not_call_honest_only_shift_a_state_mechanism() -> None:
    result = M18P.build_recommendation(
        _contrasts(honest=(0.02, 0.011)), GATE
    )
    assert result["identified_mechanism"] is None
    assert result["finding"] == "native_target_shift_or_interaction_not_state_distribution"


def test_m18p_is_inconclusive_when_the_generated_ladder_does_not_advance() -> None:
    result = M18P.build_recommendation(
        _contrasts(exact=(0.02, 0.015), honest=(0.018, 0.012)),
        GATE,
        mean_advancing_generations=0.0,
        minimum_advancing_generations=1.0,
    )
    assert result["status"] == "INCONCLUSIVE"
    assert result["identified_mechanism"] is None


def test_m18p_rejects_an_incomplete_generation_pack() -> None:
    with pytest.raises(ValueError, match="all eight generation pools"):
        M18P.build_pools({1: [_sample(1, 0, 1), _sample(1, 1, 2)]}, [], 1)


def test_m18p_result_write_read_round_trip_preserves_verdict(tmp_path: Path) -> None:
    result = {
        "schema": M18P.SCHEMA,
        "milestone": "M18-P",
        "status": "PASS",
        "result_hash": "fixture-hash",
        "recommendation": {"finding": "fixture-finding"},
    }
    run_dir = tmp_path / "run"
    compact = tmp_path / "result.full.json"
    M18P._write_outputs(result, run_dir, compact)
    assert (run_dir / "result.json").read_bytes() == compact.read_bytes()


def test_m18p_progress_round_trip_reports_seed_rate(tmp_path: Path) -> None:
    output = tmp_path / "PROGRESS.json"
    M18P._write_progress(output, 2, 20, 265002, M18P.time.monotonic() - 120.0)
    payload = M18P.json.loads(output.read_text(encoding="utf-8"))
    assert payload["completed_seeds"] == 2
    assert payload["total_seeds"] == 20
    assert payload["eta_remaining_seconds"] > 0.0
