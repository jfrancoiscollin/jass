"""Deterministic node-bounded negamax alpha-beta search."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from typing import Any

import numpy as np
import torch

from .game_graph import GameGraph
from .model import MiniJassMLP


@dataclass(frozen=True)
class SearchConfig:
    max_depth: int = 4
    node_budget: int = 16

    def __post_init__(self) -> None:
        if self.max_depth < 1:
            raise ValueError("max_depth must be positive")
        if self.node_budget < 1:
            raise ValueError("node_budget must be positive")


@dataclass
class SearchStats:
    requested_nodes: int
    consumed_nodes: int = 0
    reached_depth: int = 0
    expanded_nodes: int = 0
    generated_children: int = 0
    terminal_hits: int = 0
    leaf_model_evaluations: int = 0
    alpha_beta_cutoffs: int = 0

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["mean_branching_factor"] = (
            self.generated_children / self.expanded_nodes if self.expanded_nodes else 0.0
        )
        return result


@dataclass(frozen=True)
class SearchResult:
    selected_action: int
    root_score: float
    action_scores: dict[int, float]
    visit_counts: dict[int, int]
    stats: SearchStats

    def visit_policy(self) -> np.ndarray:
        policy = np.zeros(72, dtype=np.float32)
        total = sum(self.visit_counts.values())
        if total:
            for action, visits in self.visit_counts.items():
                policy[action] = visits / total
        else:
            policy[self.selected_action] = 1.0
        return policy


class InferenceCache:
    """Per-model cache; it never contains solved labels."""

    def __init__(self) -> None:
        self._predictions: dict[int, tuple[float, np.ndarray]] = {}

    @torch.no_grad()
    def predict(
        self, model: MiniJassMLP, graph: GameGraph, state_id: int
    ) -> tuple[float, np.ndarray, bool]:
        cached = self._predictions.get(state_id)
        if cached is not None:
            return cached[0], cached[1], True
        model.eval()
        features = torch.from_numpy(graph.features[state_id : state_id + 1])
        value, logits = model(features)
        prediction = (float(value.item()), logits[0].detach().cpu().numpy().copy())
        self._predictions[state_id] = prediction
        return prediction[0], prediction[1], False


def _ordered_actions(actions: np.ndarray, logits: np.ndarray) -> list[int]:
    return sorted((int(action) for action in actions), key=lambda action: (-float(logits[action]), action))


def bounded_negamax(
    graph: GameGraph,
    model: MiniJassMLP,
    state_id: int,
    config: SearchConfig,
    cache: InferenceCache | None = None,
) -> SearchResult:
    """Search without consulting exact values, DTW, or optimal actions."""
    inference = cache if cache is not None else InferenceCache()
    stats = SearchStats(requested_nodes=config.node_budget)
    terminal = graph.terminal_value(state_id)
    if terminal is not None:
        raise ValueError("cannot select an action in a terminal state")

    stats.consumed_nodes = 1
    root_value, root_logits, cached = inference.predict(model, graph, state_id)
    if not cached:
        stats.leaf_model_evaluations += 1
    legal = graph.legal_actions(state_id)
    ordered = _ordered_actions(legal, root_logits)
    action_scores: dict[int, float] = {}
    visit_counts: dict[int, int] = {}

    def negamax(node: int, depth: int, alpha: float, beta: float, ply: int) -> float:
        stats.consumed_nodes += 1
        stats.reached_depth = max(stats.reached_depth, ply)
        outcome = graph.terminal_value(node)
        if outcome is not None:
            stats.terminal_hits += 1
            return outcome
        if depth == 0 or stats.consumed_nodes >= config.node_budget:
            value, _, was_cached = inference.predict(model, graph, node)
            if not was_cached:
                stats.leaf_model_evaluations += 1
            return value

        value, logits, was_cached = inference.predict(model, graph, node)
        if not was_cached:
            stats.leaf_model_evaluations += 1
        actions = graph.legal_actions(node)
        stats.expanded_nodes += 1
        stats.generated_children += int(actions.size)
        best = -math.inf
        searched_child = False
        for action in _ordered_actions(actions, logits):
            if stats.consumed_nodes >= config.node_budget:
                break
            searched_child = True
            score = -negamax(graph.child(node, action), depth - 1, -beta, -alpha, ply + 1)
            best = max(best, score)
            alpha = max(alpha, score)
            if alpha >= beta:
                stats.alpha_beta_cutoffs += 1
                break
        return best if searched_child else value

    stats.expanded_nodes += 1
    stats.generated_children += int(legal.size)
    for action in ordered:
        if stats.consumed_nodes >= config.node_budget:
            break
        before = stats.consumed_nodes
        score = -negamax(
            graph.child(state_id, action), config.max_depth - 1, -math.inf, math.inf, 1
        )
        action_scores[action] = score
        visit_counts[action] = stats.consumed_nodes - before

    if action_scores:
        selected = min(action_scores, key=lambda action: (-action_scores[action], action))
        root_score = action_scores[selected]
    else:
        selected = ordered[0]
        root_score = root_value
        visit_counts[selected] = 1
    return SearchResult(selected, float(root_score), action_scores, visit_counts, stats)


def resolve_node_budget(
    policy: str,
    budgets: list[int],
    generation: int,
    legal_count: int,
    rng: np.random.Generator,
) -> int:
    """Resolve every budget policy named in the M4 experiment contract."""
    if not budgets or any(value < 1 for value in budgets):
        raise ValueError("budget list must contain positive values")
    ordered = sorted(set(int(value) for value in budgets))
    if policy == "fixed":
        return ordered[0]
    if policy == "uniform":
        return int(rng.choice(ordered))
    if policy == "log_uniform":
        logs = np.log(np.asarray(ordered, dtype=np.float64))
        sample = rng.uniform(logs[0], logs[-1])
        return min(ordered, key=lambda value: (abs(math.log(value) - sample), value))
    if policy == "curriculum":
        return ordered[min(max(generation - 1, 0), len(ordered) - 1)]
    if policy == "complexity":
        return min(ordered, key=lambda value: (abs(value - max(1, legal_count * 4)), value))
    if policy == "mixed":
        return (
            resolve_node_budget("curriculum", ordered, generation, legal_count, rng)
            if rng.random() < 0.5
            else resolve_node_budget("complexity", ordered, generation, legal_count, rng)
        )
    raise ValueError(f"unknown node-budget policy: {policy}")
