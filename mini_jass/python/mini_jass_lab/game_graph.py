"""Rule-only graph view used by self-play and bounded search.

The exact oracle also carries value, DTW, and optimal-action labels.  M4 must not
use those labels to generate experience, so this module exposes only features,
legal transitions, and terminal outcomes that follow directly from the rules.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .oracle import ACTION_COUNT, OracleArrays, encode_features


@dataclass(frozen=True)
class GameGraph:
    features: np.ndarray
    legal_mask: np.ndarray
    action_children: np.ndarray
    terminal_status: np.ndarray

    @classmethod
    def from_oracle(cls, oracle: OracleArrays) -> "GameGraph":
        """Drop every solved label while retaining the compiled game graph."""
        return cls(
            features=encode_features(oracle),
            legal_mask=oracle.legal_mask,
            action_children=oracle.action_children,
            terminal_status=oracle.terminal_status,
        )

    @property
    def state_count(self) -> int:
        return int(self.features.shape[0])

    def validate(self) -> None:
        if self.features.shape != (self.state_count, 54):
            raise ValueError("Mini-Jass features must have shape [states, 54]")
        if self.legal_mask.shape != (self.state_count, ACTION_COUNT):
            raise ValueError("Mini-Jass legal mask must have 72 actions")
        if self.action_children.shape != self.legal_mask.shape:
            raise ValueError("child table must align with legal actions")
        if self.terminal_status.shape != (self.state_count,):
            raise ValueError("terminal-status vector must align with states")
        if not np.all(np.isin(self.terminal_status, (0, 1, 2))):
            raise ValueError("terminal status is outside the rule vocabulary")
        if not np.array_equal(self.terminal_status == 0, self.legal_mask.any(axis=1)):
            raise ValueError("terminal status and legal-action set disagree")
        if np.any(self.action_children[self.legal_mask] < 0):
            raise ValueError("every legal action must have a child")
        if np.any(self.action_children[~self.legal_mask] != -1):
            raise ValueError("illegal actions must not have children")

    def legal_actions(self, state_id: int) -> np.ndarray:
        return np.flatnonzero(self.legal_mask[state_id]).astype(np.int16, copy=False)

    def child(self, state_id: int, action: int) -> int:
        child_id = int(self.action_children[state_id, action])
        if child_id < 0:
            raise ValueError(f"action {action} is illegal in state {state_id}")
        return child_id

    def terminal_value(self, state_id: int) -> float | None:
        """Return the rule outcome from the side-to-move perspective."""
        status = int(self.terminal_status[state_id])
        if status == 0:
            return None
        if status == 2:
            return 0.0
        return -1.0
