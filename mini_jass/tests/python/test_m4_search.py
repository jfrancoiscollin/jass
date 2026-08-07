from __future__ import annotations

import numpy as np
import torch
from torch import nn

from mini_jass_lab.game_graph import GameGraph
from mini_jass_lab.search import SearchConfig, bounded_negamax, resolve_node_budget


class FixedModel(nn.Module):
    def __init__(self, preferred_action: int = 0) -> None:
        super().__init__()
        self.preferred_action = preferred_action

    def forward(self, features: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        values = torch.zeros(features.shape[0])
        logits = torch.zeros((features.shape[0], 72))
        logits[:, self.preferred_action] = 2.0
        return values, logits


def tiny_graph() -> GameGraph:
    features = np.zeros((3, 54), dtype=np.float32)
    legal = np.zeros((3, 72), dtype=np.bool_)
    children = np.full((3, 72), -1, dtype=np.int32)
    legal[0, [0, 1]] = True
    children[0, 0] = 1
    children[0, 1] = 2
    return GameGraph(features, legal, children, np.asarray([0, 1, 2], dtype=np.uint8))


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


def test_all_budget_policies_are_supported() -> None:
    budgets = [1, 2, 4, 8, 16, 32, 64, 128, 256]
    for policy in ("fixed", "uniform", "log_uniform", "curriculum", "complexity", "mixed"):
        value = resolve_node_budget(policy, budgets, 3, 2, np.random.default_rng(91))
        assert value in budgets
    assert resolve_node_budget("curriculum", budgets, 3, 1, np.random.default_rng(1)) == 4
