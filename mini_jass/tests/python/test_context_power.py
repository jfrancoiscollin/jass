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
FROZEN_M21P_HASH = "2a376c7215212777e466fe41c7bf30a1af1d700f706ee7ca882c0fe2b3ac2745"
FROZEN_POWER_HASH = "db870aec453cf8876191b1624edd13045be50cf589aca33184d6175f67bae86c"


def _config() -> dict:
    return yaml.safe_load(
        (ROOT / "configs" / "contextual_outcome_supervision.yaml").read_text(
            encoding="utf-8"
        )
    )


def _fixture_config() -> dict:
    config = deepcopy(_config())
    prereq = config["data_contract"]["prerequisites"]["M21_P_strength_source"]
    prereq["result_hash"] = PENDING
    prereq.pop("result_uri", None)
    prereq.pop("protocol_hash", None)
    prereq.pop("verdict", None)
    config["replay_source_decision_v1"]["selected_source"] = PENDING
    return config


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


def test_context_config_freezes_m21p_without_authorizing_c0() -> None:
    config = _config()
    prereq = config["data_contract"]["prerequisites"]["M21_P_strength_source"]
    report = config["power_sizing_v1"]["frozen_report_v1"]
    assert config["schema"] == "mini_jass.contextual_outcome_supervision.v3"
    assert config["status"] == "C0_implementation_ready_for_verification"
    assert prereq["result_hash"] == FROZEN_M21P_HASH
    assert prereq["verdict"] == "FAIL"
    assert config["replay_source_decision_v1"]["selected_source"] == "G1_WIDE_OUTCOME"
    assert config["power_sizing_v1"]["selected_pairs_per_seed"] == 64
    assert report["report_hash"] == FROZEN_POWER_HASH
    assert report["c0_or_training_authorized"] is False
    assert config["program_order"]["C0_or_C1_launch_while_M21P_running_forbidden"]


def test_m21p_pass_selects_mix_and_fail_selects_equal_volume_g1() -> None:
    passed = validate_m21p_evidence(_fixture_config(), _result("PASS"), _status())
    failed = validate_m21p_evidence(_fixture_config(), _result("FAIL"), _status())
    assert passed["selected_replay_source"] == "MIX_OUTCOME"
    assert failed["selected_replay_source"] == "G1_WIDE_OUTCOME"


def test_m21p_inconclusive_and_running_status_abort() -> None:
    with pytest.raises(ValueError, match="ABORT_AND_RESOLVE_M21P"):
        validate_m21p_evidence(_fixture_config(), _result("INCONCLUSIVE"), _status())
    status = _status()
    status["state"] = "running"
    with pytest.raises(ValueError, match="runner evidence"):
        validate_m21p_evidence(_fixture_config(), _result("PASS"), status)


def test_m21p_payload_hash_is_recomputed() -> None:
    result = _result()
    result["seed_results"][0]["arms"]["MIX_OUTCOME"]["arena_score"] = 0.99
    with pytest.raises(ValueError, match="result hash"):
        validate_m21p_evidence(_fixture_config(), result, _status())


def test_frozen_runner_protocol_and_verdict_metadata_fail_closed() -> None:
    config = _fixture_config()
    prereq = config["data_contract"]["prerequisites"]["M21_P_strength_source"]
    prereq["result_uri"] = "r2:different"
    with pytest.raises(ValueError, match="runner evidence"):
        validate_m21p_evidence(config, _result(), _status())

    config = _fixture_config()
    prereq = config["data_contract"]["prerequisites"]["M21_P_strength_source"]
    prereq["protocol_hash"] = "different-protocol"
    with pytest.raises(ValueError, match="protocol differs"):
        validate_m21p_evidence(config, _result(), _status())

    config = _fixture_config()
    prereq = config["data_contract"]["prerequisites"]["M21_P_strength_source"]
    prereq["verdict"] = "FAIL"
    with pytest.raises(ValueError, match="verdict differs"):
        validate_m21p_evidence(config, _result("PASS"), _status())


def test_power_report_is_deterministic_and_does_not_authorize_training() -> None:
    first = build_power_freeze_report(_fixture_config(), _result(), _status())
    second = build_power_freeze_report(_fixture_config(), _result(), _status())
    assert first == second
    assert first["selected_pairs_per_seed"] in {64, 128, 256}
    assert first["c0_or_training_authorized"] is False
    assert first["report_hash"] == digest(
        {key: value for key, value in first.items() if key != "report_hash"}
    )


def test_a_frozen_different_result_hash_fails_closed() -> None:
    config = _fixture_config()
    config["data_contract"]["prerequisites"]["M21_P_strength_source"][
        "result_hash"
    ] = "different-frozen-result"
    with pytest.raises(ValueError, match="frozen contextual pin"):
        validate_m21p_evidence(config, _result(), _status())


def test_a_frozen_replay_source_must_match_the_upstream_verdict() -> None:
    config = _fixture_config()
    config["replay_source_decision_v1"]["selected_source"] = "G1_WIDE_OUTCOME"
    with pytest.raises(ValueError, match="frozen replay source"):
        validate_m21p_evidence(config, _result("PASS"), _status())
