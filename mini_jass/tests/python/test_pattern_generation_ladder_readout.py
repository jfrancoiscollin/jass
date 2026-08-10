from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[2]
TOOL_PATH = ROOT / "tools" / "read_pattern_generation_ladder.py"
SPEC = importlib.util.spec_from_file_location("pattern_ladder_readout", TOOL_PATH)
assert SPEC and SPEC.loader
READOUT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(READOUT)


def _config() -> dict:
    return yaml.safe_load(
        (ROOT / "configs" / "l1_pattern_generation_ladder_readout.yaml").read_text(
            encoding="utf-8"
        )
    )


def _result() -> dict:
    config = _config()
    rows = []
    for index in range(20):
        first = 0.06 + index * 0.0001
        values = {1: first, 2: first + 0.008, 4: first + 0.016, 8: first + 0.024}
        diagnostics = []
        for generation in range(1, 9):
            diagnostics.append(
                {
                    "generation": generation,
                    "arena": {
                        "pairs": 128,
                        "score": 0.48 + (generation % 5) * 0.01,
                        "confidence_unit": "pairs",
                        "effective_observations": 128,
                        "start_state_source": "provided",
                        "unique_start_state_count": 128,
                        "start_state_ids": list(range(128)),
                        "pair_score_histogram": {
                            "0.00": 0,
                            "0.25": 10,
                            "0.50": 108,
                            "0.75": 10,
                            "1.00": 0,
                        },
                    },
                }
            )
        rows.append(
            {
                "seed": 263001 + index,
                "by_rung": {
                    str(rung): {
                        "zero_regret_delta": values[rung],
                        "value_sign_delta": values[rung] * 3.0,
                    }
                    for rung in (1, 2, 4, 8)
                },
                "advancing_generations": 6 + index % 2,
                "promotion_diagnostics": diagnostics,
            }
        )
    return {
        "schema": config["source_result"]["schema"],
        "milestone": config["source_result"]["milestone"],
        "result_hash": config["source_result"]["result_hash"],
        "protocol_hash": config["source_result"]["protocol_hash"],
        "seed_results": rows,
    }


def test_readout_requires_paired_ci_and_a_noncollapsed_arena() -> None:
    readout = READOUT.analyze(_result(), _config())
    assert readout["status"] == "PASS"
    assert readout["primary"]["lower"] > 0.0
    assert readout["primary"]["seeds_positive"] == 20
    assert len(readout["primary"]["by_seed"]) == 20
    assert readout["arena_audit"]["pass"] is True
    assert readout["arena_audit"]["distinct_score_count"] == 5
    assert readout["recommendation"]["decision"] == (
        "replicate_ladder_on_sized_fresh_seed_cohort"
    )


def test_readout_fails_closed_when_start_states_are_duplicated() -> None:
    result = _result()
    arena = result["seed_results"][0]["promotion_diagnostics"][0]["arena"]
    arena["start_state_ids"][-1] = arena["start_state_ids"][0]
    readout = READOUT.analyze(result, _config())
    assert readout["status"] == "FAIL"
    assert readout["arena_audit"]["start_contract_pass"] is False
    assert readout["recommendation"]["promotable"] is False


def test_readout_rejects_a_different_source_hash() -> None:
    result = _result()
    result["result_hash"] = "wrong"
    with pytest.raises(ValueError, match="source result hash mismatch"):
        READOUT.analyze(result, _config())


def test_power_sizing_uses_the_minimum_practical_effect() -> None:
    n_small_effect = READOUT.normal_approximation_sample_size(0.03, 0.01, 0.80)
    n_large_effect = READOUT.normal_approximation_sample_size(0.03, 0.02, 0.80)
    assert n_small_effect > n_large_effect
    assert n_small_effect == 71
