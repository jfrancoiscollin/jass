"""Rule, leakage and metric contracts for contextual supervision C0."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
import yaml

from mini_jass_lab.context import (
    BLACK,
    COMPONENTS,
    DRAW,
    MAX_CAPTURE_MOVES,
    MAX_LEGAL_MOVES,
    SIDE_TO_MOVE_LOSS,
    WHITE,
    ContextState,
    board_moves,
    context_vector,
    feature_definition_hash,
    rotate180_and_swap_colours,
    terminal_status,
)
from mini_jass_lab.context_gate import (
    attach_export_proof,
    evaluate_c0,
    exact_pairwise_ordering,
    spearman_with_ties,
)
from mini_jass_lab.context_targets import (
    baseline_values,
    build_context_targets,
    transition_context_delta,
)

ROOT = Path(__file__).resolve().parents[2]


def _oracle(
    states: list[ContextState], values: tuple[int, ...] | None = None
) -> SimpleNamespace:
    count = len(states)
    children = np.full((count, 72), -1, dtype=np.int32)
    return SimpleNamespace(
        bitboards=np.asarray(
            [
                (
                    state.white_men,
                    state.black_men,
                    state.white_kings,
                    state.black_kings,
                )
                for state in states
            ],
            dtype=np.uint32,
        ),
        sides=np.asarray([state.side_to_move for state in states], dtype=np.uint8),
        reversible_plies=np.asarray(
            [state.reversible_plies for state in states], dtype=np.uint8
        ),
        terminal_status=np.asarray(
            [terminal_status(state) for state in states], dtype=np.uint8
        ),
        action_children=children,
        values=np.asarray((0,) * count if values is None else values, dtype=np.int8),
    )


def test_python_rules_reproduce_forced_multicapture_and_terminal_precedence() -> None:
    capture = ContextState(
        white_men=(1 << 3) | (1 << 9),
        black_men=1 << 0,
        white_kings=0,
        black_kings=0,
        side_to_move=BLACK,
        reversible_plies=0,
    )
    assert board_moves(capture) == ((0, (6, 12)),)

    blocked = ContextState(
        white_men=1 << 3,
        black_men=0,
        white_kings=0,
        black_kings=(1 << 0) | (1 << 1),
        side_to_move=WHITE,
        reversible_plies=20,
    )
    assert terminal_status(blocked) == SIDE_TO_MOVE_LOSS

    drawn = ContextState(
        white_men=0,
        black_men=0,
        white_kings=1 << 6,
        black_kings=1 << 0,
        side_to_move=WHITE,
        reversible_plies=20,
    )
    assert terminal_status(drawn) == DRAW
    assert MAX_LEGAL_MOVES == 8
    assert MAX_CAPTURE_MOVES == 4


@pytest.mark.parametrize(
    "state",
    (
        ContextState(1 << 8, 1 << 2, 1 << 6, 0, WHITE, 0),
        ContextState(0, 1 << 7, 1 << 4, 1 << 11, BLACK, 9),
        ContextState(1 << 3, 0, 0, (1 << 0) | (1 << 1), WHITE, 20),
    ),
)
def test_context_is_exactly_pov_antisymmetric_and_rot180_invariant(
    state: ContextState,
) -> None:
    white = context_vector(state, WHITE)
    black = context_vector(state, BLACK)
    assert np.array_equal(white, -black)
    image = rotate180_and_swap_colours(state)
    assert np.array_equal(context_vector(state), context_vector(image))


def test_feature_definition_hash_is_stable() -> None:
    assert (
        feature_definition_hash()
        == "c036cdc3677d094fd9bfaf46e0042ee6c43b60ba2816219deecfb52d1b395e03"
    )


def test_transition_delta_keeps_mover_pov_and_residual_has_no_oracle_input() -> None:
    parent = ContextState(1 << 8, 1 << 0, 0, 0, WHITE, 0)
    child = ContextState(1 << 5, 1 << 0, 0, 0, BLACK, 0)
    oracle = _oracle([parent, child])
    oracle.action_children[0, 7] = 1
    delta = transition_context_delta(oracle, 0, 1)
    expected = context_vector(child, WHITE) - context_vector(parent, WHITE)
    wrong_pov = context_vector(child, BLACK) - context_vector(parent, WHITE)
    assert np.array_equal(delta, expected)
    assert not np.array_equal(delta, wrong_pov)

    weights = {
        "material_man_delta": 1.0,
        "material_king_delta": 1.5,
        "legal_move_delta": 0.2,
        "capture_option_delta": 0.15,
        "promotion_pressure_delta": 0.2,
        "blocked_man_delta": -0.15,
        "advanced_man_delta": 0.1,
        "center_presence_delta": 0.05,
        "terminal_flag": 0.0,
    }
    targets = build_context_targets(
        oracle,
        (0,),
        (1,),
        (1.0,),
        baseline_weights=weights,
        tau=1.5,
        residual_clip=1.5,
    )
    expected_baseline = baseline_values(targets["context"], weights, 1.5)
    assert np.array_equal(targets["baseline"], expected_baseline)
    assert targets["residual"][0] == pytest.approx(1.0 - expected_baseline[0])


def test_terminal_pre_move_records_are_rejected_for_residual_training() -> None:
    terminal = ContextState(0, 1 << 0, 0, 0, WHITE, 0)
    oracle = _oracle([terminal])
    with pytest.raises(ValueError, match="non-terminal pre-move"):
        build_context_targets(
            oracle,
            (0,),
            (0,),
            (-1.0,),
            baseline_weights={name: 0.0 for name in COMPONENTS},
            tau=1.0,
            residual_clip=1.5,
        )


def test_exact_c0_rank_metrics_handle_ties_without_quadratic_materialization() -> None:
    exact = np.asarray((-1, -1, 0, 0, 1, 1), dtype=np.int8)
    baseline = np.asarray((-0.8, -0.2, -0.2, 0.3, 0.3, 0.9))
    ordering = exact_pairwise_ordering(baseline, exact)
    assert ordering["eligible_pair_count"] == 12
    assert ordering["baseline_tie_count"] == 2
    assert ordering["ordering_rate"] == pytest.approx(11.0 / 12.0)
    assert spearman_with_ties(baseline, exact) > 0.8


def test_c0_report_is_train_only_hashed_and_fail_closed() -> None:
    states = [
        ContextState(0, 0, 1 << 6, (1 << 0) | (1 << 12), WHITE, 0),
        ContextState(0, 0, 1 << 7, (1 << 1) | (1 << 11), WHITE, 1),
        ContextState(0, 0, 1 << 6, 1 << 0, WHITE, 0),
        ContextState(0, 0, 1 << 7, 1 << 1, WHITE, 1),
        ContextState(0, 0, (1 << 6) | (1 << 8), 1 << 0, WHITE, 0),
        ContextState(0, 0, (1 << 5) | (1 << 7), 1 << 2, WHITE, 1),
    ]
    oracle = _oracle(states, (-1, -1, 0, 0, 1, 1))

    class _Split:
        manifest = {"manifest_hash": "fixture-split"}

        @staticmethod
        def indices(name: str) -> np.ndarray:
            assert name == "train"
            return np.arange(len(states), dtype=np.int64)

    config = yaml.safe_load(
        (ROOT / "configs" / "contextual_outcome_supervision.yaml").read_text(
            encoding="utf-8"
        )
    )
    config = deepcopy(config)
    config["data_contract"]["split_manifest_hash"] = "fixture-split"
    config["c0_gate"]["required"]["minimum_baseline_spearman_vs_exact_value"] = -1.0
    config["c0_gate"]["required"]["minimum_baseline_pairwise_ordering_rate"] = 0.0
    report = evaluate_c0(oracle, _Split(), config)
    assert report["status"] == "PASS"
    assert report["cohort"] == "train"
    assert report["sealed_test_read"] is False
    assert report["c1_training_authorized"] is True
    assert len(report["report_hash"]) == 64
    passed = attach_export_proof(
        report,
        {
            "maximum_absolute_value_error": 0.0,
            "common_search_action_match_rate": 1.0,
            "value_error_pass": True,
            "action_match_pass": True,
        },
        config,
    )
    assert passed["status"] == "PASS"
    failed = attach_export_proof(
        report,
        {
            "maximum_absolute_value_error": 1.0e-3,
            "common_search_action_match_rate": 0.99,
            "value_error_pass": False,
            "action_match_pass": False,
        },
        config,
    )
    assert failed["status"] == "ABORT_C1_AND_REVISE_PREREGISTRATION"
    assert failed["c1_training_authorized"] is False
