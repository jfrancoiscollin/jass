"""Deterministic replay-buffer policies for Mini-Jass self-play."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class ReplaySample:
    state_id: int
    value_target: float
    policy_target: np.ndarray
    generation: int
    game_id: int
    ply: int
    # The behavior action is part of the training record.  Historical callers
    # did not need it because value/policy targets were sufficient; contextual
    # transition supervision must reconstruct the exact observed s -> s'.
    selected_action: int | None = None


class ReplayBuffer:
    def __init__(self, capacity: int) -> None:
        if capacity < 1:
            raise ValueError("replay capacity must be positive")
        self.capacity = capacity
        self._samples: list[ReplaySample] = []

    def __len__(self) -> int:
        return len(self._samples)

    @property
    def samples(self) -> tuple[ReplaySample, ...]:
        return tuple(self._samples)

    def extend(self, samples: list[ReplaySample]) -> None:
        self._samples.extend(samples)
        overflow = len(self._samples) - self.capacity
        if overflow > 0:
            del self._samples[:overflow]

    def sample(
        self,
        count: int,
        strategy: str,
        rng: np.random.Generator,
        current_generation: int,
    ) -> list[ReplaySample]:
        if not self._samples:
            raise ValueError("cannot sample an empty replay buffer")
        count = max(1, int(count))
        indices = np.arange(len(self._samples), dtype=np.int64)
        probabilities: np.ndarray | None = None
        if strategy in ("disabled", "fifo"):
            indices = indices[-min(count, indices.size) :]
            return [self._samples[int(index)] for index in indices]
        if strategy == "uniform":
            pass
        elif strategy == "recency":
            ages = np.asarray(
                [current_generation - sample.generation for sample in self._samples],
                dtype=np.float64,
            )
            probabilities = np.exp(-0.7 * ages)
            probabilities /= probabilities.sum()
        elif strategy == "generation_mix":
            current = np.asarray(
                [sample.generation == current_generation for sample in self._samples],
                dtype=np.float64,
            )
            if current.sum() == len(self._samples) or current.sum() == 0:
                probabilities = None
            else:
                probabilities = np.where(
                    current > 0,
                    0.7 / current.sum(),
                    0.3 / (len(self._samples) - current.sum()),
                )
        else:
            raise ValueError(f"unknown replay strategy: {strategy}")
        selected = rng.choice(indices, size=count, replace=True, p=probabilities)
        return [self._samples[int(index)] for index in selected]

    def metrics(self) -> dict[str, float | int]:
        state_ids = [sample.state_id for sample in self._samples]
        unique = len(set(state_ids))
        return {
            "size": len(self._samples),
            "capacity": self.capacity,
            "unique_states": unique,
            "duplicate_rate": 1.0 - unique / len(state_ids) if state_ids else 0.0,
        }
