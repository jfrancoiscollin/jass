from __future__ import annotations

from copy import deepcopy

import numpy as np
import pytest

from mini_jass_lab.model import model_hash
from mini_jass_lab.pattern_eval import PatternEval
from mini_jass_lab.patterns import PatternSet
from mini_jass_lab.replay import ReplaySample
from mini_jass_lab.selfplay_train import train_from_replay

from test_m4_search import tiny_graph


def _sample(policy: np.ndarray) -> ReplaySample:
    return ReplaySample(0, 1.0, policy, 1, 0, 0)


def _train(model: PatternEval, policy: np.ndarray):
    return train_from_replay(
        model,
        tiny_graph(),
        [_sample(policy)],
        steps=3,
        batch_size=1,
        learning_rate=0.01,
        weight_decay=0.0,
        value_weight=1.0,
        policy_weight=0.0,
        seed=91,
    )


def test_value_only_replay_updates_value_and_ignores_policy_targets() -> None:
    initial = PatternEval(PatternSet.from_window(2))
    left = deepcopy(initial)
    right = deepcopy(initial)
    policy_left = np.zeros(72, dtype=np.float32)
    policy_right = np.zeros(72, dtype=np.float32)
    policy_left[0] = 1.0
    policy_right[1] = 1.0
    left_metrics = _train(left, policy_left)
    right_metrics = _train(right, policy_right)
    assert model_hash(left) == model_hash(right)
    assert model_hash(left) != model_hash(initial)
    assert left_metrics["policy_loss"] is None
    assert left_metrics["policy_trained"] is False
    assert left_metrics["action_source"] == "search"


def test_value_only_replay_refuses_a_silent_policy_loss() -> None:
    model = PatternEval(PatternSet.from_window(2))
    policy = np.zeros(72, dtype=np.float32)
    policy[0] = 1.0
    with pytest.raises(ValueError, match="policy_weight=0"):
        train_from_replay(
            model,
            tiny_graph(),
            [_sample(policy)],
            steps=1,
            batch_size=1,
            learning_rate=0.01,
            weight_decay=0.0,
            value_weight=1.0,
            policy_weight=1.0,
            seed=91,
        )


def test_explicit_batch_schedule_controls_draws_independently_of_seed() -> None:
    policy = np.zeros(72, dtype=np.float32)
    policy[0] = 1.0
    initial = PatternEval(PatternSet.from_window(2))
    left = deepcopy(initial)
    right = deepcopy(initial)
    schedule = np.zeros((3, 1), dtype=np.int64)
    left_metrics = train_from_replay(
        left,
        tiny_graph(),
        [_sample(policy)],
        steps=3,
        batch_size=1,
        learning_rate=0.01,
        weight_decay=0.0,
        value_weight=1.0,
        policy_weight=0.0,
        seed=1,
        batch_indices=schedule,
    )
    train_from_replay(
        right,
        tiny_graph(),
        [_sample(policy)],
        steps=3,
        batch_size=1,
        learning_rate=0.01,
        weight_decay=0.0,
        value_weight=1.0,
        policy_weight=0.0,
        seed=999,
        batch_indices=schedule,
    )
    assert model_hash(left) == model_hash(right)
    assert left_metrics["explicit_batch_schedule"] is True


@pytest.mark.parametrize(
    "schedule,match",
    [
        (np.zeros((2, 1), dtype=np.int64), "must have shape"),
        (np.ones((3, 1), dtype=np.int64), "invalid index"),
    ],
)
def test_explicit_batch_schedule_fails_closed(
    schedule: np.ndarray, match: str
) -> None:
    policy = np.zeros(72, dtype=np.float32)
    policy[0] = 1.0
    with pytest.raises(ValueError, match=match):
        train_from_replay(
            PatternEval(PatternSet.from_window(2)),
            tiny_graph(),
            [_sample(policy)],
            steps=3,
            batch_size=1,
            learning_rate=0.01,
            weight_decay=0.0,
            value_weight=1.0,
            policy_weight=0.0,
            seed=91,
            batch_indices=schedule,
        )
