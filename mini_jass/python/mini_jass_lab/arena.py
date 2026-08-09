"""Paired, deterministic candidate-versus-parent arena."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Sequence

import numpy as np
from torch import nn

from .game_graph import GameGraph
from .search import InferenceCache, SearchConfig, bounded_negamax


@dataclass(frozen=True)
class ArenaConfig:
    pairs: int = 8
    max_plies: int = 128
    search_depth: int = 3
    node_budget: int = 8
    epsilon: float = 0.0
    confidence_z: float = 1.96
    confidence_unit: str = "games"
    start_state_source: str = "initial"


def _play_game(
    graph: GameGraph,
    candidate: nn.Module,
    parent: nn.Module,
    candidate_starts: bool,
    config: ArenaConfig,
    seed: int,
    start_state_id: int = 0,
) -> float:
    rng = np.random.default_rng(seed)
    candidate_cache = InferenceCache()
    parent_cache = InferenceCache()
    state_id = int(start_state_id)
    plies = 0
    terminal: float | None = None
    for plies in range(config.max_plies):
        terminal = graph.terminal_value(state_id)
        if terminal is not None:
            break
        candidate_turn = (plies % 2 == 0) == candidate_starts
        model = candidate if candidate_turn else parent
        cache = candidate_cache if candidate_turn else parent_cache
        legal = graph.legal_actions(state_id)
        if config.epsilon > 0 and rng.random() < config.epsilon:
            action = int(rng.choice(legal))
        else:
            result = bounded_negamax(
                graph,
                model,
                state_id,
                SearchConfig(config.search_depth, config.node_budget),
                cache,
            )
            action = result.selected_action
        state_id = graph.child(state_id, action)
    else:
        terminal = 0.0

    if terminal is None:
        raise RuntimeError("arena game ended without an outcome")
    starting_side_outcome = terminal if plies % 2 == 0 else -terminal
    return starting_side_outcome if candidate_starts else -starting_side_outcome


def run_arena(
    graph: GameGraph,
    candidate: nn.Module,
    parent: nn.Module,
    config: ArenaConfig,
    seed: int,
    start_state_ids: Sequence[int] | np.ndarray | None = None,
) -> dict[str, Any]:
    if config.pairs < 1:
        raise ValueError("arena requires at least one pair")
    if config.confidence_unit not in {"games", "pairs"}:
        raise ValueError("arena confidence_unit must be games or pairs")
    if config.start_state_source not in {"initial", "provided"}:
        raise ValueError("arena start_state_source must be initial or provided")
    if config.start_state_source == "initial":
        selected_start_states = [0] * config.pairs
    else:
        if start_state_ids is None:
            raise ValueError("arena requires provided start states")
        eligible_start_states = sorted(
            {
                int(state_id)
                for state_id in start_state_ids
                if graph.terminal_value(int(state_id)) is None
            }
        )
        if len(eligible_start_states) < config.pairs:
            raise ValueError(
                "arena requires at least one unique non-terminal start per pair"
            )
        rng = np.random.default_rng(seed)
        selected_start_states = [
            int(state_id)
            for state_id in rng.choice(
                eligible_start_states, size=config.pairs, replace=False
            )
        ]
    outcomes: list[float] = []
    paired_seeds: list[int] = []
    for pair in range(config.pairs):
        pair_seed = seed + pair
        paired_seeds.append(pair_seed)
        start_state_id = selected_start_states[pair]
        outcomes.append(
            _play_game(
                graph,
                candidate,
                parent,
                True,
                config,
                pair_seed,
                start_state_id,
            )
        )
        outcomes.append(
            _play_game(
                graph,
                candidate,
                parent,
                False,
                config,
                pair_seed,
                start_state_id,
            )
        )
    wins = sum(outcome > 0 for outcome in outcomes)
    draws = sum(outcome == 0 for outcome in outcomes)
    losses = sum(outcome < 0 for outcome in outcomes)
    pair_scores = [
        (outcomes[index] + outcomes[index + 1] + 2.0) / 4.0
        for index in range(0, len(outcomes), 2)
    ]
    pair_score_histogram = {
        f"{score_value / 4.0:.2f}": sum(
            math.isclose(pair_score, score_value / 4.0)
            for pair_score in pair_scores
        )
        for score_value in range(5)
    }
    games = len(outcomes)
    score = (wins + 0.5 * draws) / games
    effective_observations = (
        games if config.confidence_unit == "games" else config.pairs
    )
    standard_error = math.sqrt(
        max(score * (1.0 - score), 0.0) / effective_observations
    )
    lower_bound = max(0.0, score - config.confidence_z * standard_error)
    return {
        "games": games,
        "pairs": config.pairs,
        "wins": wins,
        "draws": draws,
        "losses": losses,
        "score": score,
        "score_lower_confidence_bound": lower_bound,
        "confidence_z": config.confidence_z,
        "confidence_unit": config.confidence_unit,
        "effective_observations": effective_observations,
        "start_state_source": config.start_state_source,
        "start_state_ids": selected_start_states,
        "unique_start_state_count": len(set(selected_start_states)),
        "pair_score_histogram": pair_score_histogram,
        "paired_seeds": paired_seeds,
    }
