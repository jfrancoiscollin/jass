"""Deterministic node-bounded negamax alpha-beta search."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
import math
from typing import Any

import numpy as np
import torch
from torch import nn

from .game_graph import GameGraph


@dataclass(frozen=True)
class SearchConfig:
    max_depth: int = 4
    node_budget: int = 16
    root_allocation: str = "sequential"

    def __post_init__(self) -> None:
        if self.max_depth < 1:
            raise ValueError("max_depth must be positive")
        if self.node_budget < 1:
            raise ValueError("node_budget must be positive")
        if self.root_allocation not in ("sequential", "balanced"):
            raise ValueError("root allocation must be sequential or balanced")


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
    root_legal_actions: int = 0
    root_searched_actions: int = 0
    root_minimum_nodes: int = 0
    root_maximum_nodes: int = 0
    root_minimum_budget: int = 0
    root_maximum_budget: int = 0

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["mean_branching_factor"] = (
            self.generated_children / self.expanded_nodes if self.expanded_nodes else 0.0
        )
        result["root_action_coverage"] = (
            self.root_searched_actions / self.root_legal_actions
            if self.root_legal_actions
            else 0.0
        )
        result["root_node_imbalance"] = (
            self.root_maximum_nodes - self.root_minimum_nodes
            if self.root_searched_actions
            else 0
        )
        result["root_budget_imbalance"] = (
            self.root_maximum_budget - self.root_minimum_budget
            if self.root_searched_actions
            else 0
        )
        return result


@dataclass(frozen=True)
class SearchResult:
    selected_action: int
    root_score: float
    action_scores: dict[int, float]
    visit_counts: dict[int, int]
    stats: SearchStats
    action_count: int
    contextual_tiebreak: dict[str, Any] | None = None

    def visit_policy(self) -> np.ndarray:
        policy = np.zeros(self.action_count, dtype=np.float32)
        total = sum(self.visit_counts.values())
        if total:
            for action, visits in self.visit_counts.items():
                policy[action] = visits / total
        else:
            policy[self.selected_action] = 1.0
        return policy

    def best_action_policy(self) -> np.ndarray:
        policy = np.zeros(self.action_count, dtype=np.float32)
        policy[self.selected_action] = 1.0
        return policy

    def score_policy(self, temperature: float = 1.0) -> np.ndarray:
        if temperature <= 0:
            raise ValueError("score-policy temperature must be positive")
        if not self.action_scores:
            return self.best_action_policy()
        actions = np.asarray(sorted(self.action_scores), dtype=np.int64)
        scores = np.asarray(
            [self.action_scores[int(action)] for action in actions], dtype=np.float64
        )
        scores = (scores - scores.max()) / temperature
        probabilities = np.exp(scores)
        probabilities /= probabilities.sum()
        policy = np.zeros(self.action_count, dtype=np.float32)
        policy[actions] = probabilities.astype(np.float32)
        return policy


class InferenceCache:
    """Per-model cache; it never contains solved labels."""

    def __init__(self) -> None:
        self._predictions: dict[int, tuple[float, np.ndarray]] = {}

    @torch.no_grad()
    def predict(
        self, model: nn.Module, graph: GameGraph, state_id: int
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
    model: nn.Module,
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
    stats.root_legal_actions = int(legal.size)
    action_scores: dict[int, float] = {}
    visit_counts: dict[int, int] = {}

    def negamax(
        node: int,
        depth: int,
        alpha: float,
        beta: float,
        ply: int,
        node_limit: int,
    ) -> float:
        stats.consumed_nodes += 1
        stats.reached_depth = max(stats.reached_depth, ply)
        outcome = graph.terminal_value(node)
        if outcome is not None:
            stats.terminal_hits += 1
            return outcome
        if depth == 0 or stats.consumed_nodes >= node_limit:
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
            if stats.consumed_nodes >= node_limit:
                break
            searched_child = True
            score = -negamax(
                graph.child(node, action), depth - 1, -beta, -alpha, ply + 1, node_limit
            )
            best = max(best, score)
            alpha = max(alpha, score)
            if alpha >= beta:
                stats.alpha_beta_cutoffs += 1
                break
        return best if searched_child else value

    stats.expanded_nodes += 1
    stats.generated_children += int(legal.size)
    if config.root_allocation == "balanced":
        child_budget = config.node_budget - stats.consumed_nodes
        quotient, remainder = divmod(child_budget, len(ordered))
        quotas = [quotient + (index < remainder) for index in range(len(ordered))]
    else:
        quotas = [config.node_budget] * len(ordered)
    for action, quota in zip(ordered, quotas, strict=True):
        if stats.consumed_nodes >= config.node_budget or quota < 1:
            break
        before = stats.consumed_nodes
        node_limit = (
            min(config.node_budget, before + int(quota))
            if config.root_allocation == "balanced"
            else config.node_budget
        )
        score = -negamax(
            graph.child(state_id, action),
            config.max_depth - 1,
            -math.inf,
            math.inf,
            1,
            node_limit,
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
    root_nodes = list(visit_counts.values())
    allocated_budgets = [int(quota) for quota in quotas if quota > 0]
    stats.root_searched_actions = len(action_scores)
    stats.root_minimum_nodes = min(root_nodes) if root_nodes else 0
    stats.root_maximum_nodes = max(root_nodes) if root_nodes else 0
    stats.root_minimum_budget = min(allocated_budgets) if allocated_budgets else 0
    stats.root_maximum_budget = max(allocated_budgets) if allocated_budgets else 0
    return SearchResult(
        selected, float(root_score), action_scores, visit_counts, stats, graph.action_count
    )


def apply_contextual_tiebreak(
    graph: GameGraph,
    context_model: nn.Module,
    state_id: int,
    temporal_result: SearchResult,
    delta: float,
    cache: InferenceCache | None = None,
) -> SearchResult:
    """Use a second value channel only inside a temporal uncertainty band.

    The temporal search is left byte-for-byte untouched: its scores, visits and
    node accounting are reused.  The context model can only choose between root
    actions whose temporal score is within ``delta`` of the temporal winner.
    This is intentionally a decision rule, not a scalar blend of two targets.
    """

    if not math.isfinite(delta) or delta < 0.0:
        raise ValueError("contextual tie-break delta must be finite and non-negative")
    if not temporal_result.action_scores:
        return replace(
            temporal_result,
            contextual_tiebreak={
                "activated": False,
                "changed_action": False,
                "delta": float(delta),
                "eligible_actions": [int(temporal_result.selected_action)],
                "context_scores": {},
                "reason": "no_searched_root_scores",
            },
        )

    best_temporal = max(float(value) for value in temporal_result.action_scores.values())
    eligible = sorted(
        int(action)
        for action, value in temporal_result.action_scores.items()
        if best_temporal - float(value) <= delta
    )
    if len(eligible) < 2:
        return replace(
            temporal_result,
            contextual_tiebreak={
                "activated": False,
                "changed_action": False,
                "delta": float(delta),
                "best_temporal_score": best_temporal,
                "eligible_actions": eligible,
                "context_scores": {},
                "reason": "single_temporal_candidate",
            },
        )

    inference = cache if cache is not None else InferenceCache()
    context_scores: dict[int, float] = {}
    for action in eligible:
        child = graph.child(state_id, action)
        terminal = graph.terminal_value(child)
        if terminal is None:
            child_value, _, _ = inference.predict(context_model, graph, child)
        else:
            child_value = float(terminal)
        context_scores[action] = -float(child_value)
    selected = min(
        eligible,
        key=lambda action: (-context_scores[action], action),
    )
    changed = selected != int(temporal_result.selected_action)
    ordered_context = sorted(context_scores.values(), reverse=True)
    context_margin = (
        float(ordered_context[0] - ordered_context[1])
        if len(ordered_context) > 1
        else 0.0
    )
    return replace(
        temporal_result,
        selected_action=selected,
        root_score=float(temporal_result.action_scores[selected]),
        contextual_tiebreak={
            "activated": True,
            "changed_action": changed,
            "delta": float(delta),
            "best_temporal_score": best_temporal,
            "selected_temporal_score": float(temporal_result.action_scores[selected]),
            "temporal_sacrifice": best_temporal
            - float(temporal_result.action_scores[selected]),
            "eligible_actions": eligible,
            "context_scores": {
                str(action): float(context_scores[action]) for action in eligible
            },
            "context_margin": context_margin,
            "reason": "contextual_tiebreak",
        },
    )


def bounded_negamax_with_context(
    graph: GameGraph,
    temporal_model: nn.Module,
    context_model: nn.Module,
    state_id: int,
    config: SearchConfig,
    delta: float,
    temporal_cache: InferenceCache | None = None,
    context_cache: InferenceCache | None = None,
) -> SearchResult:
    """Run the ordinary temporal search, then apply the separate context channel."""

    temporal = bounded_negamax(
        graph, temporal_model, state_id, config, temporal_cache
    )
    return apply_contextual_tiebreak(
        graph, context_model, state_id, temporal, delta, context_cache
    )


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
