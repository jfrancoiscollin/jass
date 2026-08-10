"""Contracts for the architecture-correct M21-P strength experiment."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np

from mini_jass_lab.replay import ReplaySample

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools" / "run_pattern_learning_signal_composition.py"
SPEC = importlib.util.spec_from_file_location("run_pattern_m21p", TOOL)
assert SPEC and SPEC.loader
M21P = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M21P)


def _sample(generation: int, game: int, state: int) -> ReplaySample:
    policy = np.zeros(72, dtype=np.float32)
    policy[0] = 1.0
    return ReplaySample(state, float((state % 3) - 1), policy, generation, game, 0)


class _GraphFixture:
    def __init__(self) -> None:
        self.features = np.zeros((256, 10), dtype=np.float32)
        self.legal_mask = np.zeros((256, 72), dtype=np.bool_)
        self.legal_mask[:, 0] = True


def _primary(mean: float, lower: float, upper: float) -> dict[str, object]:
    return {
        "generation_composition": {
            "arena_score": {"mean": mean, "lower": lower, "upper": upper}
        }
    }


GATE = {"minimum_practical_arena_gain": 0.05}


def test_m21p_config_uses_fresh_pattern_seeds_and_common_search_arena() -> None:
    config, loop = M21P._resolve(
        ROOT / "configs" / "l1_pattern_learning_signal_composition.yaml"
    )
    assert config["paired_seeds"] == list(range(266001, 266021))
    assert loop["model"]["architecture"] == "folded_pattern_value"
    assert loop["training"]["policy_weight"] == 0.0
    assert loop["generations"] == 8
    assert config["strength_arena"]["pairs"] == 128
    assert config["strength_arena"]["start_state_source"] == "development"
    assert config["boundaries"]["cohorts_sealed"] == ["frozen_test"]


def test_m21p_primary_pool_equalizes_unique_rows() -> None:
    per_generation = {
        generation: [
            _sample(generation, game, generation * 10 + game)
            for game in range(3)
        ]
        for generation in range(1, 9)
    }
    wide = [_sample(1, game, 100 + game) for game in range(24)]
    pools, census = M21P.build_pools(per_generation, wide, _GraphFixture(), 266001)
    assert len(pools["MIX_OUTCOME"]) == 24
    assert len(pools["G1_WIDE_OUTCOME"]) == 24
    assert len(pools["G1_ONLY_OUTCOME"]) == 3
    assert len(pools["G1_PLUS_NOVEL_LATE_OUTCOME"]) == 3
    assert census["identity_hash_by_arm"]["MIX_OUTCOME"] != census[
        "identity_hash_by_arm"
    ]["G1_WIDE_OUTCOME"]


def test_m21p_same_size_arms_can_share_exact_batch_schedules() -> None:
    first = M21P._random_schedule(32, 16, 8, 91)
    second = M21P._random_schedule(32, 16, 8, 91)
    assert np.array_equal(first, second)
    assert first.shape == (16, 8)


def test_m21p_strength_arena_decides_a_pass() -> None:
    result = M21P.build_recommendation(_primary(0.08, 0.02, 0.14), GATE, 5.0, 1.0)
    assert result["status"] == "PASS"
    assert result["generation_composition_strength_signal"] is True
    assert result["promotable"] is False


def test_m21p_excludes_a_practical_effect_only_when_upper_bound_is_small() -> None:
    failed = M21P.build_recommendation(
        _primary(0.00, -0.02, 0.02), GATE, 5.0, 1.0
    )
    uncertain = M21P.build_recommendation(
        _primary(0.04, -0.02, 0.10), GATE, 5.0, 1.0
    )
    assert failed["status"] == "FAIL"
    assert failed["generation_composition_strength_signal"] is False
    assert uncertain["status"] == "INCONCLUSIVE"
    assert uncertain["generation_composition_strength_signal"] is None


def test_m21p_is_inconclusive_if_the_causal_pack_does_not_advance() -> None:
    result = M21P.build_recommendation(_primary(0.10, 0.06, 0.14), GATE, 0.0, 1.0)
    assert result["status"] == "INCONCLUSIVE"
    assert result["generation_composition_strength_signal"] is None


def test_m21p_result_write_read_round_trip_preserves_verdict(tmp_path: Path) -> None:
    result = {
        "schema": M21P.SCHEMA,
        "milestone": "M21-P",
        "status": "PASS",
        "result_hash": "fixture-hash",
        "recommendation": {"finding": "fixture-finding"},
    }
    run_dir = tmp_path / "run"
    compact = tmp_path / "result.full.json"
    M21P._write_outputs(result, run_dir, compact)
    assert (run_dir / "result.json").read_bytes() == compact.read_bytes()


def test_m21p_progress_reports_seed_rate(tmp_path: Path) -> None:
    output = tmp_path / "PROGRESS.json"
    M21P._write_progress(output, 2, 20, 266002, M21P.time.monotonic() - 120.0)
    payload = M21P.json.loads(output.read_text(encoding="utf-8"))
    assert payload["completed_seeds"] == 2
    assert payload["total_seeds"] == 20
    assert payload["eta_remaining_seconds"] > 0.0
