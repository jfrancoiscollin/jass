from __future__ import annotations

import numpy as np

from mini_jass_lab.replay import ReplayBuffer, ReplaySample


def sample(state_id: int, generation: int) -> ReplaySample:
    policy = np.zeros(72, dtype=np.float32)
    policy[state_id % 72] = 1.0
    return ReplaySample(state_id, 0.0, policy, generation, state_id, 0)


def test_replay_is_fifo_bounded_and_sampling_is_seeded() -> None:
    replay = ReplayBuffer(4)
    replay.extend([sample(index, 1) for index in range(6)])
    assert [item.state_id for item in replay.samples] == [2, 3, 4, 5]
    first = replay.sample(8, "generation_mix", np.random.default_rng(5), 1)
    second = replay.sample(8, "generation_mix", np.random.default_rng(5), 1)
    assert [item.state_id for item in first] == [item.state_id for item in second]
    assert replay.metrics()["size"] == 4


def test_recency_sampling_accepts_multiple_generations() -> None:
    replay = ReplayBuffer(10)
    replay.extend([sample(1, 1), sample(2, 2), sample(3, 3)])
    selected = replay.sample(20, "recency", np.random.default_rng(7), 3)
    assert len(selected) == 20
    assert {item.state_id for item in selected}.issubset({1, 2, 3})


def test_disabled_policy_selects_only_the_current_tail() -> None:
    replay = ReplayBuffer(10)
    replay.extend([sample(1, 1), sample(2, 1), sample(3, 2)])
    selected = replay.sample(1, "disabled", np.random.default_rng(2), 2)
    assert [item.state_id for item in selected] == [3]
