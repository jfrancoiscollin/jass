"""Contracts for the M21-P-gated contextual supervision preparation."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest
import yaml

from mini_jass_lab.context_power import (
    PENDING,
    build_power_freeze_report,
    digest,
    validate_m21p_evidence,
)


ROOT = Path(__file__).resolve().parents[2]


def _config() -> dict:
    return yaml.safe_load(
        (ROOT / "configs" / "contextual_outcome_supervision.yaml").read_text(
            encoding="utf-8"
        )
    )


def _result(verdict: str = "PASS") -> dict:
    rows = []
    for offset, seed in enumerate(range(266001, 266021)):
        rows.append(
            {
                "seed": seed,
                "arms": {
                    "MIX_OUTCOME": {"arena_score": 0.60 + offset / 1000.0},
                    "G1_WIDE_OUTCOME": {"arena_score": 0.50},
                },
            }
        )
    result = {
        "schema": "mini_jass.pattern_learning_signal_composition.v1",
        "milestone": "M21-P",
        "status": verdict,
        "protocol_hash": "protocol-fixture",
        "aggregate": {
            "all_arena_starts_paired": True,
            "mean_ladder_advance_count": 5.0,
        },
        "seed_results": rows,
        "recommendation": {"status": verdict},
        "promotable": False,
    }
    result["result_hash"] = digest(result)
    return result


def _status() -> dict:
    return {
        "job_id": "cpx62-1223-mini-jass-pattern-m21p-v1",
        "attempt_id": "20260810T055825Z-fe188c93",
        "code_sha": "fe188c93648100b6e6d31c8335e669dea28aa5bb",
        "state": "completed",
        "exit_code": 0,
        "result_uri": "r2:fixture",
    }


def test_context_config_is_blocked_until_m21p_hash_is_frozen() -> None:
    config = _config()
    prereq = config["data_contract"]["prerequisites"]["M21_P_strength_source"]
    assert config["schema"] == "mini_jass.contextual_outcome_supervision.v3"
    assert config["status"] == "implementation_blocked_on_frozen_M21P_result"
    assert prereq["result_hash"] == PENDING
    assert config["program_order"]["C0_or_C1_launch_while_M21P_running_forbidden"]


def test_m21p_pass_selects_mix_and_fail_selects_equal_volume_g1() -> None:
    passed = validate_m21p_evidence(_config(), _result("PASS"), _status())
    failed = validate_m21p_evidence(_config(), _result("FAIL"), _status())
    assert passed["selected_replay_source"] == "MIX_OUTCOME"
    assert failed["selected_replay_source"] == "G1_WIDE_OUTCOME"


def test_m21p_inconclusive_and_running_status_abort() -> None:
    with pytest.raises(ValueError, match="ABORT_AND_RESOLVE_M21P"):
        validate_m21p_evidence(_config(), _result("INCONCLUSIVE"), _status())
    status = _status()
    status["state"] = "running"
    with pytest.raises(ValueError, match="runner evidence"):
        validate_m21p_evidence(_config(), _result("PASS"), status)


def test_m21p_payload_hash_is_recomputed() -> None:
    result = _result()
    result["seed_results"][0]["arms"]["MIX_OUTCOME"]["arena_score"] = 0.99
    with pytest.raises(ValueError, match="result hash"):
        validate_m21p_evidence(_config(), result, _status())


def test_power_report_is_deterministic_and_does_not_authorize_training() -> None:
    first = build_power_freeze_report(_config(), _result(), _status())
    second = build_power_freeze_report(_config(), _result(), _status())
    assert first == second
    assert first["selected_pairs_per_seed"] in {64, 128, 256}
    assert first["c0_or_training_authorized"] is False
    assert first["report_hash"] == digest(
        {key: value for key, value in first.items() if key != "report_hash"}
    )


def test_a_frozen_different_result_hash_fails_closed() -> None:
    config = deepcopy(_config())
    config["data_contract"]["prerequisites"]["M21_P_strength_source"][
        "result_hash"
    ] = "different-frozen-result"
    with pytest.raises(ValueError, match="frozen contextual pin"):
        validate_m21p_evidence(config, _result(), _status())


def test_a_frozen_replay_source_must_match_the_upstream_verdict() -> None:
    config = deepcopy(_config())
    config["replay_source_decision_v1"]["selected_source"] = "G1_WIDE_OUTCOME"
    with pytest.raises(ValueError, match="frozen replay source"):
        validate_m21p_evidence(config, _result("PASS"), _status())
