from __future__ import annotations

import numpy as np
import torch

from mini_jass_lab.model import MiniJassMLP, model_hash
from mini_jass_lab.train import seed_everything, train_epoch


def _run_once() -> tuple[str, dict[str, float]]:
    seed_everything(123, threads=1)
    model = MiniJassMLP()
    optimizer = torch.optim.AdamW(model.parameters(), lr=0.01)
    generator = torch.Generator().manual_seed(999)
    features = torch.randn((32, 54), generator=generator)
    values = torch.tensor(([-1.0, 0.0, 1.0, 0.0] * 8))
    legal = torch.zeros((32, 72), dtype=torch.bool)
    optimal = torch.zeros((32, 72))
    for index in range(32):
        legal[index, index % 8] = True
        legal[index, (index + 1) % 8] = True
        optimal[index, index % 8] = 1.0
    metrics = train_epoch(
        model,
        optimizer,
        {"features": features, "values": values, "legal": legal, "optimal": optimal},
        np.arange(32),
        batch_size=8,
        seed=77,
    )
    return model_hash(model), metrics


def test_one_epoch_is_byte_reproducible() -> None:
    first_hash, first_metrics = _run_once()
    second_hash, second_metrics = _run_once()
    assert first_hash == second_hash
    assert first_metrics == second_metrics
