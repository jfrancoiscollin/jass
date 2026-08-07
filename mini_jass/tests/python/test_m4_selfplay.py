from __future__ import annotations

from dataclasses import replace

import numpy as np

from mini_jass_lab.game_graph import GameGraph
from mini_jass_lab.selfplay import ExplorationConfig, SelfPlayConfig, generate_self_play

from test_m4_search import FixedModel, tiny_graph


def test_rule_graph_drops_every_exact_label(synthetic_oracle) -> None:
    poisoned = replace(synthetic_oracle, values=None, dtw=None, optimal_mask=None)
    graph = GameGraph.from_oracle(poisoned)
    assert graph.state_count == synthetic_oracle.state_count
    assert not hasattr(graph, "values")
    assert not hasattr(graph, "dtw")
    assert not hasattr(graph, "optimal_mask")


def test_outcome_only_propagates_final_wdl() -> None:
    config = SelfPlayConfig(
        mode="outcome_only",
        games=2,
        max_plies=4,
        exploration=ExplorationConfig(strategy="greedy"),
    )
    result = generate_self_play(tiny_graph(), FixedModel(0), config, 1, 100)
    assert len(result.samples) == 2
    assert all(sample.value_target == 1.0 for sample in result.samples)
    assert all(sample.policy_target[0] == 1.0 for sample in result.samples)
    assert result.metrics["outcomes_from_initial_side"]["win"] == 2


def test_search_improved_uses_visit_policy() -> None:
    config = SelfPlayConfig(
        mode="search_improved",
        games=1,
        max_plies=4,
        search_depth=2,
        node_budgets=(3,),
        exploration=ExplorationConfig(strategy="greedy"),
    )
    result = generate_self_play(tiny_graph(), FixedModel(1), config, 1, 200)
    policy = result.samples[0].policy_target
    assert np.isclose(policy.sum(), 1.0)
    assert policy[0] == policy[1] == 0.5
    assert result.samples[0].value_target == 1.0


def test_policy_target_is_decoupled_from_search_behavior() -> None:
    common = dict(
        mode="search_improved",
        games=1,
        max_plies=4,
        search_depth=2,
        node_budgets=(3,),
        root_allocation="balanced",
        behavior_policy="search_scores",
        exploration=ExplorationConfig(strategy="greedy"),
    )
    visits = generate_self_play(
        tiny_graph(),
        FixedModel(1),
        SelfPlayConfig(**common, policy_target="visit_distribution"),
        1,
        250,
    )
    best = generate_self_play(
        tiny_graph(),
        FixedModel(1),
        SelfPlayConfig(**common, policy_target="best_action"),
        1,
        250,
    )
    assert [sample.state_id for sample in visits.samples] == [
        sample.state_id for sample in best.samples
    ]
    assert visits.samples[0].policy_target[0] == 0.5
    assert best.samples[0].policy_target[0] == 1.0
    assert visits.metrics["search"]["root_coverage_failures"] == 0


def test_outcome_targets_can_use_search_for_move_selection() -> None:
    config = SelfPlayConfig(
        mode="outcome_only",
        games=1,
        max_plies=4,
        search_depth=2,
        node_budgets=(3,),
        search_enabled=True,
        exploration=ExplorationConfig(strategy="greedy"),
    )
    result = generate_self_play(tiny_graph(), FixedModel(1), config, 1, 300)
    assert result.samples[0].policy_target[0] == 1.0
    assert result.metrics["search"]["decisions"] == 1


def test_generation_game_schedule_is_explicit() -> None:
    config = SelfPlayConfig(games=9, game_schedule=(3, 2, 1))
    assert [config.games_for_generation(index) for index in (1, 2, 3)] == [3, 2, 1]


def test_train_split_start_states_are_explicit_and_deterministic() -> None:
    config = SelfPlayConfig(
        mode="outcome_only",
        games=2,
        max_plies=1,
        search_enabled=False,
        start_state_source="train_split",
        exploration=ExplorationConfig(strategy="greedy"),
    )
    starts = np.asarray([0], dtype=np.int64)
    first = generate_self_play(tiny_graph(), FixedModel(0), config, 1, 400, starts)
    second = generate_self_play(tiny_graph(), FixedModel(0), config, 1, 400, starts)
    assert first.metrics["start_states"] == {"source": "train_split", "unique": 1}
    assert [sample.state_id for sample in first.samples] == [
        sample.state_id for sample in second.samples
    ]
