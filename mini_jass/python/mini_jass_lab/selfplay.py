"""Outcome-only and search-improved Mini-Jass self-play generation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from .game_graph import GameGraph
from .model import MiniJassMLP
from .replay import ReplaySample
from .search import (
    InferenceCache,
    SearchConfig,
    bounded_negamax,
    resolve_node_budget,
)


@dataclass(frozen=True)
class ExplorationConfig:
    strategy: str = "epsilon_greedy"
    epsilon: float = 0.10
    top_k: int = 3
    temperature: float = 1.0
    warmup_games: int = 0
    warmup_epsilon: float = 0.25

    def __post_init__(self) -> None:
        if not 0.0 <= self.epsilon <= 1.0:
            raise ValueError("epsilon must be in [0, 1]")
        if self.top_k < 1 or self.temperature <= 0:
            raise ValueError("top_k and temperature must be positive")
        if self.warmup_games < 0 or not 0.0 <= self.warmup_epsilon <= 1.0:
            raise ValueError("warm-up games and epsilon are invalid")


@dataclass(frozen=True)
class SelfPlayConfig:
    mode: str = "search_improved"
    games: int = 8
    max_plies: int = 128
    search_depth: int = 4
    budget_policy: str = "fixed"
    node_budgets: tuple[int, ...] = (16,)
    search_enabled: bool | None = None
    game_schedule: tuple[int, ...] | None = None
    start_state_source: str = "initial"
    exploration: ExplorationConfig = field(default_factory=ExplorationConfig)

    def __post_init__(self) -> None:
        if self.mode not in ("outcome_only", "search_improved"):
            raise ValueError("self-play mode must be outcome_only or search_improved")
        if self.games < 1 or self.max_plies < 1:
            raise ValueError("games and max_plies must be positive")
        if self.mode == "search_improved" and self.search_enabled is False:
            raise ValueError("search-improved targets require search")
        if self.start_state_source not in ("initial", "train_split"):
            raise ValueError("start-state source must be initial or train_split")
        if self.game_schedule is not None and (
            not self.game_schedule or any(games < 1 for games in self.game_schedule)
        ):
            raise ValueError("game schedule must contain positive game counts")

    @property
    def uses_search(self) -> bool:
        if self.search_enabled is not None:
            return self.search_enabled
        return self.mode == "search_improved"

    def games_for_generation(self, generation: int) -> int:
        if self.game_schedule is None:
            return self.games
        if generation < 1 or generation > len(self.game_schedule):
            raise ValueError("generation is outside the configured game schedule")
        return self.game_schedule[generation - 1]


@dataclass(frozen=True)
class GenerationResult:
    samples: list[ReplaySample]
    metrics: dict[str, Any]
    coverage: dict[str, Any]


def select_action(
    legal_actions: np.ndarray,
    preferences: np.ndarray,
    config: ExplorationConfig,
    rng: np.random.Generator,
) -> int:
    actions = np.asarray(legal_actions, dtype=np.int64)
    if actions.size == 0:
        raise ValueError("cannot select from an empty action set")
    ranked = sorted((int(action) for action in actions), key=lambda action: (-float(preferences[action]), action))
    if config.strategy == "greedy":
        return ranked[0]
    if config.strategy == "epsilon_greedy":
        return int(rng.choice(actions)) if rng.random() < config.epsilon else ranked[0]
    top = np.asarray(ranked[: min(config.top_k, len(ranked))], dtype=np.int64)
    if config.strategy == "top_k_uniform":
        return int(rng.choice(top))
    if config.strategy == "top_k_softmax":
        values = preferences[top].astype(np.float64) / config.temperature
        values -= values.max()
        probabilities = np.exp(values)
        probabilities /= probabilities.sum()
        return int(rng.choice(top, p=probabilities))
    raise ValueError(f"unknown exploration strategy: {config.strategy}")


def _search_preferences(policy: np.ndarray) -> np.ndarray:
    preferences = np.full(72, -1.0e9, dtype=np.float32)
    selected = policy > 0
    preferences[selected] = policy[selected]
    return preferences


def generate_self_play(
    graph: GameGraph,
    model: MiniJassMLP,
    config: SelfPlayConfig,
    generation: int,
    seed: int,
    start_state_ids: np.ndarray | None = None,
) -> GenerationResult:
    """Generate replay targets without reading solved oracle labels."""
    if config.start_state_source == "train_split":
        if start_state_ids is None or not len(start_state_ids):
            raise ValueError("train-split starts require non-terminal state ids")
        available_starts = np.asarray(start_state_ids, dtype=np.int64)
    else:
        available_starts = None
    inference = InferenceCache()
    samples: list[ReplaySample] = []
    visited_states: set[int] = set()
    visited_actions: set[int] = set()
    outcomes = {"win": 0, "draw": 0, "loss": 0}
    lengths: list[int] = []
    search_totals = {
        "decisions": 0,
        "requested_nodes": 0,
        "consumed_nodes": 0,
        "expanded_nodes": 0,
        "generated_children": 0,
        "terminal_hits": 0,
        "leaf_model_evaluations": 0,
        "alpha_beta_cutoffs": 0,
        "maximum_reached_depth": 0,
    }
    search_trace: list[dict[str, Any]] = []
    safety_draws = 0
    game_count = config.games_for_generation(generation)
    selected_starts: list[int] = []

    for game_id in range(game_count):
        rng = np.random.default_rng(seed + game_id)
        state_id = (
            int(rng.choice(available_starts))
            if available_starts is not None
            else 0
        )
        selected_starts.append(state_id)
        trajectory: list[tuple[int, np.ndarray, int]] = []
        terminal_value: float | None = None
        for ply in range(config.max_plies):
            terminal_value = graph.terminal_value(state_id)
            if terminal_value is not None:
                break
            legal = graph.legal_actions(state_id)
            if config.uses_search:
                budget = resolve_node_budget(
                    config.budget_policy,
                    list(config.node_budgets),
                    generation,
                    int(legal.size),
                    rng,
                )
                result = bounded_negamax(
                    graph,
                    model,
                    state_id,
                    SearchConfig(config.search_depth, budget),
                    inference,
                )
                search_policy = result.visit_policy()
                preferences = _search_preferences(search_policy)
                target_policy = (
                    search_policy
                    if config.mode == "search_improved"
                    else np.zeros(72, dtype=np.float32)
                )
                for key in (
                    "requested_nodes",
                    "consumed_nodes",
                    "expanded_nodes",
                    "generated_children",
                    "terminal_hits",
                    "leaf_model_evaluations",
                    "alpha_beta_cutoffs",
                ):
                    search_totals[key] += int(getattr(result.stats, key))
                search_totals["decisions"] += 1
                search_totals["maximum_reached_depth"] = max(
                    search_totals["maximum_reached_depth"], result.stats.reached_depth
                )
                stats = result.stats.to_dict()
                search_trace.append(
                    {
                        "game_id": game_id,
                        "ply": ply,
                        "state_id": state_id,
                        "selected_action": result.selected_action,
                        "root_score": result.root_score,
                        "root_action_scores": result.action_scores,
                        "root_visit_counts": result.visit_counts,
                        **stats,
                    }
                )
            else:
                _, logits, _ = inference.predict(model, graph, state_id)
                preferences = logits
                target_policy = np.zeros(72, dtype=np.float32)

            exploration = config.exploration
            if game_id < exploration.warmup_games:
                exploration = ExplorationConfig(
                    strategy="epsilon_greedy",
                    epsilon=exploration.warmup_epsilon,
                    top_k=exploration.top_k,
                    temperature=exploration.temperature,
                )
            action = select_action(legal, preferences, exploration, rng)
            if config.mode == "outcome_only":
                target_policy[action] = 1.0
            trajectory.append((state_id, target_policy, ply))
            visited_states.add(state_id)
            visited_actions.add(action)
            state_id = graph.child(state_id, action)
        else:
            terminal_value = 0.0
            safety_draws += 1

        if terminal_value is None:
            raise RuntimeError("self-play game ended without a rule outcome")
        initial_outcome = terminal_value if len(trajectory) % 2 == 0 else -terminal_value
        outcomes["win" if initial_outcome > 0 else "loss" if initial_outcome < 0 else "draw"] += 1
        lengths.append(len(trajectory))
        for index, (sample_state, policy, ply) in enumerate(trajectory):
            remaining = len(trajectory) - index
            value_target = terminal_value if remaining % 2 == 0 else -terminal_value
            samples.append(
                ReplaySample(
                    state_id=sample_state,
                    value_target=float(value_target),
                    policy_target=policy,
                    generation=generation,
                    game_id=game_id,
                    ply=ply,
                )
            )

    metrics: dict[str, Any] = {
        "generation": generation,
        "mode": config.mode,
        "games": game_count,
        "positions": len(samples),
        "mean_game_length": float(np.mean(lengths)),
        "max_game_length": max(lengths),
        "outcomes_from_initial_side": outcomes,
        "safety_draws": safety_draws,
        "start_states": {
            "source": config.start_state_source,
            "unique": len(set(selected_starts)),
        },
        "search": search_totals,
        "search_trace": search_trace,
    }
    coverage = {
        "generation": generation,
        "unique_states": len(visited_states),
        "state_coverage": len(visited_states) / graph.state_count,
        "unique_actions": len(visited_actions),
        "action_coverage": len(visited_actions) / 72,
        "duplicate_position_rate": 1.0 - len(visited_states) / len(samples) if samples else 0.0,
    }
    return GenerationResult(samples=samples, metrics=metrics, coverage=coverage)
