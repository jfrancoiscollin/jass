from __future__ import annotations

import numpy as np
import torch
from torch import nn

from mini_jass_lab.arena import ArenaConfig, run_arena
from mini_jass_lab.game_graph import GameGraph
from mini_jass_lab.search import (
    SearchConfig,
    apply_contextual_tiebreak,
    bounded_negamax,
    resolve_node_budget,
)


class FixedModel(nn.Module):
    def __init__(self, preferred_action: int = 0) -> None:
        super().__init__()
        self.preferred_action = preferred_action

    def forward(self, features: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        values = torch.zeros(features.shape[0])
        logits = torch.zeros((features.shape[0], 72))
        logits[:, self.preferred_action] = 2.0
        return values, logits


class StateValueModel(nn.Module):
    def __init__(self, values: dict[int, float]) -> None:
        super().__init__()
        self.values = values

    def forward(self, features: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        state_ids = features[:, 0].to(torch.int64).tolist()
        values = torch.tensor([self.values.get(state, 0.0) for state in state_ids])
        return values, torch.zeros((features.shape[0], 72))


def tiny_graph() -> GameGraph:
    features = np.zeros((3, 54), dtype=np.float32)
    legal = np.zeros((3, 72), dtype=np.bool_)
    children = np.full((3, 72), -1, dtype=np.int32)
    legal[0, [0, 1]] = True
    children[0, 0] = 1
    children[0, 1] = 2
    return GameGraph(features, legal, children, np.asarray([0, 1, 2], dtype=np.uint8))


def tiebreak_graph() -> GameGraph:
    features = np.zeros((5, 54), dtype=np.float32)
    features[:, 0] = np.arange(5)
    legal = np.zeros((5, 72), dtype=np.bool_)
    children = np.full((5, 72), -1, dtype=np.int32)
    legal[0, [0, 1]] = True
    children[0, 0] = 1
    children[0, 1] = 2
    legal[1, 0] = True
    legal[2, 0] = True
    children[1, 0] = 3
    children[2, 0] = 4
    graph = GameGraph(
        features, legal, children, np.asarray([0, 0, 0, 1, 1], dtype=np.uint8)
    )
    graph.validate()
    return graph


def test_search_prefers_forced_win_and_respects_node_budget() -> None:
    result = bounded_negamax(tiny_graph(), FixedModel(1), 0, SearchConfig(2, 3))
    assert result.selected_action == 0
    assert result.root_score == 1.0
    assert result.stats.consumed_nodes == 3
    assert result.stats.requested_nodes == 3
    assert result.stats.terminal_hits == 2
    assert np.isclose(result.visit_policy().sum(), 1.0)


def test_one_node_budget_has_deterministic_policy_fallback() -> None:
    result = bounded_negamax(tiny_graph(), FixedModel(1), 0, SearchConfig(4, 1))
    assert result.selected_action == 1
    assert result.stats.consumed_nodes == 1
    assert result.visit_counts == {1: 1}


def test_balanced_root_allocation_searches_every_action_fairly() -> None:
    result = bounded_negamax(
        tiny_graph(), FixedModel(1), 0, SearchConfig(4, 3, "balanced")
    )
    assert result.action_scores.keys() == {0, 1}
    assert result.visit_counts == {1: 1, 0: 1}
    assert result.stats.root_searched_actions == result.stats.root_legal_actions == 2
    assert result.stats.root_maximum_nodes - result.stats.root_minimum_nodes == 0


def test_policy_target_encodings_are_normalized() -> None:
    result = bounded_negamax(
        tiny_graph(), FixedModel(1), 0, SearchConfig(4, 3, "balanced")
    )
    assert np.isclose(result.best_action_policy().sum(), 1.0)
    assert result.best_action_policy()[0] == 1.0
    score_policy = result.score_policy(0.25)
    assert np.isclose(score_policy.sum(), 1.0)
    assert score_policy[0] > score_policy[1]


def test_context_channel_only_changes_actions_inside_temporal_band() -> None:
    graph = tiebreak_graph()
    temporal = bounded_negamax(
        graph,
        StateValueModel({1: -0.40, 2: -0.38}),
        0,
        SearchConfig(1, 3, "balanced"),
    )
    assert temporal.selected_action == 0
    aligned = apply_contextual_tiebreak(
        graph,
        StateValueModel({1: 0.50, 2: -0.50}),
        0,
        temporal,
        0.03,
    )
    assert aligned.selected_action == 1
    assert aligned.action_scores == temporal.action_scores
    assert aligned.visit_counts == temporal.visit_counts
    decision = aligned.contextual_tiebreak
    assert decision is not None
    assert decision["activated"] is True
    assert decision["changed_action"] is True
    assert decision["eligible_actions"] == [0, 1]
    assert decision["context_scores"] == {"0": -0.5, "1": 0.5}
    assert np.isclose(decision["temporal_sacrifice"], 0.02)

    outside = apply_contextual_tiebreak(
        graph,
        StateValueModel({1: 0.50, 2: -0.50}),
        0,
        temporal,
        0.01,
    )
    assert outside.selected_action == temporal.selected_action
    assert outside.contextual_tiebreak["activated"] is False


def test_arena_reports_context_activation_without_mixing_search_scores() -> None:
    graph = tiebreak_graph()
    temporal = StateValueModel({1: -0.40, 2: -0.38})
    aligned = StateValueModel({1: 0.50, 2: -0.50})
    shuffled = StateValueModel({1: -0.50, 2: 0.50})
    result = run_arena(
        graph,
        temporal,
        temporal,
        ArenaConfig(
            pairs=1,
            max_plies=4,
            search_depth=1,
            node_budget=3,
            confidence_unit="pairs",
        ),
        seed=77,
        candidate_context_model=aligned,
        parent_context_model=shuffled,
        contextual_delta=0.03,
    )
    assert result["games"] == 2
    assert result["contextual_decision_stats"]["candidate"]["decisions"] > 0
    assert result["contextual_decision_stats"]["parent"]["decisions"] > 0
    assert (
        result["contextual_decision_stats"]["candidate"]["activations"]
        + result["contextual_decision_stats"]["parent"]["activations"]
        > 0
    )
    historical = run_arena(
        graph,
        temporal,
        temporal,
        ArenaConfig(
            pairs=1,
            max_plies=4,
            search_depth=1,
            node_budget=3,
            confidence_unit="pairs",
        ),
        seed=77,
    )
    assert "contextual_decision_stats" not in historical


def test_all_budget_policies_are_supported() -> None:
    budgets = [1, 2, 4, 8, 16, 32, 64, 128, 256]
    for policy in ("fixed", "uniform", "log_uniform", "curriculum", "complexity", "mixed"):
        value = resolve_node_budget(policy, budgets, 3, 2, np.random.default_rng(91))
        assert value in budgets
    assert resolve_node_budget("curriculum", budgets, 3, 1, np.random.default_rng(1)) == 4
