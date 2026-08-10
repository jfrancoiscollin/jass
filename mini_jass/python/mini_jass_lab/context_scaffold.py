"""Shared contextual scaffold with exact scalar PatternEval export."""

from __future__ import annotations

import hashlib
import math

import numpy as np
import torch
from torch import nn

from .context import COMPONENTS
from .pattern_eval import PatternEval
from .patterns import PLAYABLE, PatternSet, STATES_PER_SQUARE

INITIALIZATION_SCHEMA = "sha256_counter_normal_v1"


def _counter_normal(
    shape: tuple[int, ...],
    *,
    seed: int,
    namespace: str,
    standard_deviation: float,
) -> np.ndarray:
    count = int(np.prod(shape, dtype=np.int64))
    values: list[float] = []
    counter = 0
    while len(values) < count:
        payload = (f"{INITIALIZATION_SCHEMA}|{int(seed)}|{namespace}|{counter}").encode(
            "utf-8"
        )
        block = hashlib.sha256(payload).digest()
        first = (int.from_bytes(block[:8], "big") + 0.5) / 2**64
        second = (int.from_bytes(block[8:16], "big") + 0.5) / 2**64
        radius = math.sqrt(-2.0 * math.log(first))
        angle = 2.0 * math.pi * second
        values.extend((radius * math.cos(angle), radius * math.sin(angle)))
        counter += 1
    return np.asarray(values[:count], dtype=np.float64).reshape(shape) * float(
        standard_deviation
    )


class ContextualPatternScaffold(nn.Module):
    """Rank-10 training family whose value path exports to PatternEval."""

    def __init__(
        self,
        pattern_set: PatternSet,
        *,
        seed: int,
        rank: int = 10,
        include_reversible_plies: bool = True,
        bucket_standard_deviation: float = 0.01,
        reversible_standard_deviation: float = 0.01,
        auxiliary_standard_deviation: float | None = None,
    ) -> None:
        super().__init__()
        if rank != 1 + len(COMPONENTS):
            raise ValueError("context scaffold rank must reserve value plus nine axes")
        template = PatternEval(pattern_set, include_reversible_plies)
        self.pattern_set = pattern_set
        self.rank = int(rank)
        self.class_count = int(template.class_count)
        self.include_reversible_plies = bool(include_reversible_plies)
        self.seed = int(seed)
        self.register_buffer("bucket_class", template.bucket_class.detach().clone())
        self.register_buffer(
            "pattern_squares", template.pattern_squares.detach().clone()
        )
        self.register_buffer("pattern_mask", template.pattern_mask.detach().clone())
        self.register_buffer("pattern_offset", template.pattern_offset.detach().clone())
        self.bucket_count = int(template.bucket_count)

        self.bucket_embedding = nn.Parameter(torch.empty(self.class_count, self.rank))
        self.reversible_embedding = nn.Parameter(torch.empty(self.rank))
        self.shared_bias = nn.Parameter(torch.zeros(self.rank))
        self.value_head = nn.Parameter(torch.zeros(self.rank))
        self.value_bias = nn.Parameter(torch.zeros(1))
        self.context_head = nn.Parameter(torch.empty(len(COMPONENTS), self.rank))
        self.context_bias = nn.Parameter(torch.zeros(len(COMPONENTS)))
        self.delta_context_head = nn.Parameter(torch.empty(len(COMPONENTS), self.rank))
        self.delta_context_bias = nn.Parameter(torch.zeros(len(COMPONENTS)))
        self.residual_head = nn.Parameter(torch.empty(self.rank))
        self.residual_bias = nn.Parameter(torch.zeros(1))
        auxiliary_sd = (
            1.0 / math.sqrt(self.rank)
            if auxiliary_standard_deviation is None
            else float(auxiliary_standard_deviation)
        )
        self._initialize(
            bucket_standard_deviation=float(bucket_standard_deviation),
            reversible_standard_deviation=float(reversible_standard_deviation),
            auxiliary_standard_deviation=auxiliary_sd,
        )
        self.value_only = True

    def _copy_normal(
        self,
        parameter: nn.Parameter,
        namespace: str,
        standard_deviation: float,
    ) -> None:
        values = _counter_normal(
            tuple(parameter.shape),
            seed=self.seed,
            namespace=namespace,
            standard_deviation=standard_deviation,
        )
        parameter.copy_(torch.as_tensor(values, dtype=parameter.dtype))

    def _initialize(
        self,
        *,
        bucket_standard_deviation: float,
        reversible_standard_deviation: float,
        auxiliary_standard_deviation: float,
    ) -> None:
        with torch.no_grad():
            self._copy_normal(
                self.bucket_embedding,
                "bucket_embedding",
                bucket_standard_deviation,
            )
            self._copy_normal(
                self.reversible_embedding,
                "reversible_embedding",
                reversible_standard_deviation,
            )
            self.shared_bias.zero_()
            self.value_head.zero_()
            self.value_head[0] = 1.0
            self.value_bias.zero_()
            self._copy_normal(
                self.context_head,
                "context_head",
                auxiliary_standard_deviation,
            )
            self.context_bias.zero_()
            self._copy_normal(
                self.delta_context_head,
                "delta_context_head",
                auxiliary_standard_deviation,
            )
            self.delta_context_bias.zero_()
            self._copy_normal(
                self.residual_head,
                "residual_head",
                auxiliary_standard_deviation,
            )
            self.residual_bias.zero_()

    def _classes(self, features: torch.Tensor) -> torch.Tensor:
        count = features.shape[0]
        planes = features[:, : 4 * PLAYABLE].reshape(count, 4, PLAYABLE)
        weights = torch.arange(
            1, 5, device=features.device, dtype=features.dtype
        ).reshape(1, 4, 1)
        states = (planes * weights).sum(dim=1).long()
        picked = states[:, self.pattern_squares]
        picked = torch.where(self.pattern_mask, picked, torch.zeros_like(picked))
        indices = torch.zeros(
            count,
            self.pattern_squares.shape[0],
            dtype=torch.long,
            device=features.device,
        )
        for position in range(self.pattern_squares.shape[1]):
            live = self.pattern_mask[:, position]
            indices = torch.where(
                live.unsqueeze(0),
                indices * STATES_PER_SQUARE + picked[:, :, position],
                indices,
            )
        buckets = indices + self.pattern_offset.unsqueeze(0)
        side = features[:, 4 * PLAYABLE]
        if torch.any((side != 0) & (side != 1)):
            raise ValueError("side-to-move feature must be exactly zero or one")
        augmented = buckets + side.long().unsqueeze(1) * self.bucket_count
        return self.bucket_class[augmented]

    def hidden(self, features: torch.Tensor) -> torch.Tensor:
        classes = self._classes(features)
        hidden = self.bucket_embedding[classes].sum(dim=1) + self.shared_bias
        if self.include_reversible_plies:
            reversible = features[:, 4 * PLAYABLE + 1].unsqueeze(1)
            hidden = hidden + reversible * self.reversible_embedding
        return hidden

    def forward(self, features: torch.Tensor) -> dict[str, torch.Tensor]:
        classes = self._classes(features)
        hidden = self.bucket_embedding[classes].sum(dim=1) + self.shared_bias
        if self.include_reversible_plies:
            reversible = features[:, 4 * PLAYABLE + 1].unsqueeze(1)
            hidden = hidden + reversible * self.reversible_embedding

        # Realise the scalar branch in the exact same floating-point order as
        # PatternEval.  ``hidden @ value_head`` is algebraically equivalent to
        # projecting every bucket before summation, but the two expressions are
        # not bitwise equivalent in float32.  A trained checkpoint can contain a
        # near-tied pair of child values for which that rounding difference
        # changes the deterministic action even though value error is < 1e-6.
        # The exported evaluator sums projected bucket weights first, then adds
        # the reversible term and bias; keep the live scaffold identical.
        bucket_weight = self.bucket_embedding @ self.value_head
        pre_value = bucket_weight[classes].sum(dim=1)
        if self.include_reversible_plies:
            reversible = features[:, 4 * PLAYABLE + 1 : 4 * PLAYABLE + 2]
            extra_weight = (self.reversible_embedding @ self.value_head).reshape(1)
            pre_value = pre_value + reversible @ extra_weight
        bias = self.shared_bias @ self.value_head + self.value_bias
        pre_value = pre_value + bias
        return {
            "value": torch.tanh(pre_value),
            "context": hidden @ self.context_head.T + self.context_bias,
            "delta_context": hidden @ self.delta_context_head.T
            + self.delta_context_bias,
            "residual": hidden @ self.residual_head + self.residual_bias,
        }

    def export_pattern_eval(self) -> PatternEval:
        exported = PatternEval(self.pattern_set, self.include_reversible_plies).to(
            device=self.bucket_embedding.device,
            dtype=self.bucket_embedding.dtype,
        )
        with torch.no_grad():
            exported.bucket_weight.copy_(self.bucket_embedding @ self.value_head)
            if self.include_reversible_plies:
                exported.extra_weight[0].copy_(
                    self.reversible_embedding @ self.value_head
                )
            exported.bias.copy_(self.shared_bias @ self.value_head + self.value_bias)
        return exported

    def trainable_parameter_total(self) -> int:
        return sum(parameter.numel() for parameter in self.parameters())


class _ScaffoldValueAdapter(nn.Module):
    def __init__(self, scaffold: ContextualPatternScaffold) -> None:
        super().__init__()
        self.scaffold = scaffold
        self.value_only = True

    def forward(self, features: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        value = self.scaffold(features)["value"]
        logits = torch.zeros(
            features.shape[0], 72, device=features.device, dtype=value.dtype
        )
        return value, logits


def prove_scalar_export(
    scaffold: ContextualPatternScaffold,
    oracle: object,
    *,
    batch_size: int = 8192,
) -> dict[str, float | int | bool]:
    """Prove value and one-ply common-search parity on every oracle state."""
    from .game_graph import GameGraph
    from .oracle import encode_features
    from .pattern_eval import greedy_answer

    raw = encode_features(oracle)
    features = torch.from_numpy(raw).to(
        device=scaffold.bucket_embedding.device,
        dtype=scaffold.bucket_embedding.dtype,
    )
    exported = scaffold.export_pattern_eval()
    direct_values: list[torch.Tensor] = []
    exported_values: list[torch.Tensor] = []
    with torch.no_grad():
        for start in range(0, features.shape[0], int(batch_size)):
            batch = features[start : start + int(batch_size)]
            direct_values.append(scaffold(batch)["value"].detach().cpu())
            exported_values.append(exported(batch)[0].detach().cpu())
    direct = torch.cat(direct_values)
    scalar = torch.cat(exported_values)
    maximum_error = float(torch.max(torch.abs(direct - scalar)).item())

    graph = GameGraph.from_oracle(oracle)
    graph.validate()
    tensors = {"features": features}
    state_ids = np.arange(graph.state_count, dtype=np.int64)
    direct_actions = greedy_answer(
        _ScaffoldValueAdapter(scaffold),
        graph,
        tensors,
        state_ids,
        batch_size=int(batch_size),
    )
    exported_actions = greedy_answer(
        exported,
        graph,
        tensors,
        state_ids,
        batch_size=int(batch_size),
    )
    playable = graph.legal_mask.any(axis=1)
    action_match_rate = float(
        np.mean(direct_actions[playable] == exported_actions[playable])
    )
    return {
        "state_count": int(graph.state_count),
        "playable_state_count": int(np.count_nonzero(playable)),
        "maximum_absolute_value_error": maximum_error,
        "common_search_action_match_rate": action_match_rate,
        "value_error_pass": maximum_error <= 1.0e-6,
        "action_match_pass": action_match_rate == 1.0,
    }
