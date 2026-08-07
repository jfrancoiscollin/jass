"""Deterministic exact-supervised and all-state-fit training."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import platform
import random
import sys
from typing import Any

import numpy as np
import torch
import torch.nn.functional as functional
import yaml

from .model import MiniJassMLP, ModelConfig, masked_policy_logits, model_hash, parameter_count
from .oracle import OracleArrays, encode_features, ensure_artefact_path, load_oracle, uniform_optimal_targets
from .split import SPLIT_NAMES, SplitDefinition, build_split


def seed_everything(seed: int, threads: int = 1) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.set_num_threads(threads)
    torch.use_deterministic_algorithms(True)


def _tensor_data(oracle: OracleArrays) -> dict[str, torch.Tensor]:
    return {
        "features": torch.from_numpy(encode_features(oracle)),
        "values": torch.from_numpy(oracle.values.astype(np.float32)),
        "legal": torch.from_numpy(oracle.legal_mask),
        "optimal": torch.from_numpy(uniform_optimal_targets(oracle.optimal_mask)),
    }


def train_epoch(
    model: MiniJassMLP,
    optimizer: torch.optim.Optimizer,
    tensors: dict[str, torch.Tensor],
    indices: np.ndarray,
    batch_size: int,
    seed: int,
    value_weight: float = 1.0,
    policy_weight: float = 1.0,
) -> dict[str, float]:
    model.train()
    generator = torch.Generator().manual_seed(seed)
    order = torch.from_numpy(indices.astype(np.int64, copy=False))
    order = order[torch.randperm(order.numel(), generator=generator)]
    total_loss = 0.0
    total_value = 0.0
    total_policy = 0.0
    total_examples = 0

    for start in range(0, order.numel(), batch_size):
        batch = order[start : start + batch_size]
        features = tensors["features"][batch]
        targets = tensors["values"][batch]
        legal = tensors["legal"][batch]
        optimal = tensors["optimal"][batch]
        predicted_values, logits = model(features)
        value_loss = functional.mse_loss(predicted_values, targets)

        policy_rows = optimal.sum(dim=1) > 0
        if torch.any(policy_rows):
            masked = masked_policy_logits(logits[policy_rows], legal[policy_rows])
            log_probabilities = functional.log_softmax(masked, dim=1)
            policy_loss = -(optimal[policy_rows] * log_probabilities).sum(dim=1).mean()
        else:
            policy_loss = logits.sum() * 0.0
        loss = value_weight * value_loss + policy_weight * policy_loss

        optimizer.zero_grad(set_to_none=True)
        loss.backward()
        optimizer.step()

        examples = int(batch.numel())
        total_examples += examples
        total_loss += float(loss.detach()) * examples
        total_value += float(value_loss.detach()) * examples
        total_policy += float(policy_loss.detach()) * examples

    return {
        "loss": total_loss / total_examples,
        "value_loss": total_value / total_examples,
        "policy_loss": total_policy / total_examples,
    }


def _value_calibration(predictions: np.ndarray, targets: np.ndarray) -> list[dict[str, Any]]:
    edges = np.linspace(-1.0, 1.0, 11)
    bins = np.clip(np.digitize(predictions, edges[1:-1]), 0, 9)
    result: list[dict[str, Any]] = []
    for index in range(10):
        selected = bins == index
        count = int(selected.sum())
        result.append(
            {
                "lower": float(edges[index]),
                "upper": float(edges[index + 1]),
                "count": count,
                "mean_prediction": float(predictions[selected].mean()) if count else None,
                "mean_exact_value": float(targets[selected].mean()) if count else None,
            }
        )
    return result


@torch.no_grad()
def evaluate(
    model: MiniJassMLP,
    tensors: dict[str, torch.Tensor],
    oracle: OracleArrays,
    indices: np.ndarray,
    batch_size: int,
) -> dict[str, Any]:
    model.eval()
    predictions = np.empty(indices.size, dtype=np.float32)
    top_actions = np.full(indices.size, -1, dtype=np.int16)
    optimal_mass = np.zeros(indices.size, dtype=np.float32)
    cross_entropy = np.zeros(indices.size, dtype=np.float32)
    has_policy = np.zeros(indices.size, dtype=np.bool_)

    for start in range(0, indices.size, batch_size):
        raw_batch = indices[start : start + batch_size]
        batch = torch.from_numpy(raw_batch.astype(np.int64, copy=False))
        values, logits = model(tensors["features"][batch])
        predictions[start : start + batch.numel()] = values.numpy()
        legal = tensors["legal"][batch]
        optimal = tensors["optimal"][batch]
        policy_rows = optimal.sum(dim=1) > 0
        if torch.any(policy_rows):
            local_rows = torch.nonzero(policy_rows, as_tuple=False).squeeze(1)
            masked = masked_policy_logits(logits[policy_rows], legal[policy_rows])
            probabilities = functional.softmax(masked, dim=1)
            targets = optimal[policy_rows]
            positions = start + local_rows.numpy()
            top_actions[positions] = probabilities.argmax(dim=1).numpy()
            optimal_mass[positions] = (probabilities * (targets > 0)).sum(dim=1).numpy()
            cross_entropy[positions] = -(
                targets * functional.log_softmax(masked, dim=1)
            ).sum(dim=1).numpy()
            has_policy[positions] = True

    targets = oracle.values[indices].astype(np.float32)
    predicted_classes = np.where(predictions > 1.0 / 3.0, 1, np.where(predictions < -1.0 / 3.0, -1, 0))
    policy_positions = np.flatnonzero(has_policy)
    raw_policy_indices = indices[policy_positions]
    selected_actions = top_actions[policy_positions]
    top1_optimal = oracle.optimal_mask[raw_policy_indices, selected_actions]
    child_ids = oracle.action_children[raw_policy_indices, selected_actions]
    selected_scores = -oracle.values[child_ids]
    regret = oracle.values[raw_policy_indices].astype(np.int16) - selected_scores.astype(np.int16)

    return {
        "count": int(indices.size),
        "value_mae": float(np.abs(predictions - targets).mean()),
        "value_mse": float(np.square(predictions - targets).mean()),
        "value_sign_accuracy": float((predicted_classes == targets).mean()),
        "policy_count": int(policy_positions.size),
        "optimal_top1_accuracy": float(top1_optimal.mean()) if policy_positions.size else None,
        "optimal_probability_mass": float(optimal_mass[has_policy].mean()) if policy_positions.size else None,
        "policy_cross_entropy": float(cross_entropy[has_policy].mean()) if policy_positions.size else None,
        "mean_selected_regret": float(regret.mean()) if policy_positions.size else None,
        "zero_regret_rate": float((regret == 0).mean()) if policy_positions.size else None,
        "calibration": _value_calibration(predictions, targets),
    }


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _summary_markdown(result: dict[str, Any]) -> str:
    lines = [
        "# Mini-Jass M3 exact-supervised report",
        "",
        f"- Mode: `{result['mode']}`",
        f"- Gate: **{result['gate']['status']}**",
        f"- Parameters: {result['parameter_count']}",
        f"- Model hash: `{result['model_hash']}`",
        f"- Split hash: `{result['split_manifest_hash']}`",
        "",
        "| Cohort | Count | Value sign | Value MAE | Optimal top-1 | Optimal mass |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for cohort, metrics in result["final_metrics"].items():
        lines.append(
            f"| {cohort} | {metrics['count']} | {metrics['value_sign_accuracy']:.4f} | "
            f"{metrics['value_mae']:.4f} | {metrics['optimal_top1_accuracy']:.4f} | "
            f"{metrics['optimal_probability_mass']:.4f} |"
        )
    return "\n".join(lines) + "\n"


def run_training(
    config_path: Path,
    oracle_path: Path,
    run_dir: Path,
) -> dict[str, Any]:
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if config.get("schema") != "mini_jass.training.v1":
        raise ValueError("unexpected training config schema")
    mode = config["mode"]
    if mode not in ("exact_supervised", "all_state_fit"):
        raise ValueError("M3 mode must be exact_supervised or all_state_fit")

    run_dir = ensure_artefact_path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=False)
    oracle = load_oracle(oracle_path)
    split = build_split(oracle, int(config["split_seed"]))
    frozen_split_path = Path(config["frozen_split_manifest"])
    if not frozen_split_path.is_absolute():
        frozen_split_path = config_path.parent.parent / frozen_split_path
    frozen_split = json.loads(frozen_split_path.read_text(encoding="utf-8"))
    if split.manifest != frozen_split:
        raise ValueError("computed split differs from the frozen split manifest")

    threads = int(config["runtime"]["threads"])
    seed = int(config["seed"])
    seed_everything(seed, threads)
    model_config = ModelConfig(**config["model"])
    model = MiniJassMLP(model_config)
    tensors = _tensor_data(oracle)

    training = config["training"]
    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=float(training["learning_rate"]),
        weight_decay=float(training["weight_decay"]),
    )
    batch_size = int(training["batch_size"])
    if mode == "exact_supervised":
        training_indices = split.indices("train")
        development_indices = split.indices("development")
    else:
        training_indices = np.arange(oracle.state_count, dtype=np.int64)
        development_indices = training_indices

    metrics_path = run_dir / "metrics.jsonl"
    best_score = float("-inf")
    best_state: dict[str, torch.Tensor] | None = None
    history: list[dict[str, Any]] = []
    for epoch in range(1, int(training["epochs"]) + 1):
        train_losses = train_epoch(
            model,
            optimizer,
            tensors,
            training_indices,
            batch_size,
            seed + epoch,
            float(training["value_weight"]),
            float(training["policy_weight"]),
        )
        development = evaluate(model, tensors, oracle, development_indices, batch_size)
        score = development["value_sign_accuracy"] + development["optimal_probability_mass"]
        epoch_metrics = {
            "epoch": epoch,
            "train": train_losses,
            "development": development,
            "selection_score": score,
        }
        history.append(epoch_metrics)
        with metrics_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(epoch_metrics, sort_keys=True) + "\n")
        if score > best_score:
            best_score = score
            best_state = deepcopy(model.state_dict())

    if best_state is None:
        raise RuntimeError("training produced no checkpoint")
    final_state = deepcopy(model.state_dict())
    torch.save({"model": best_state, "config": asdict(model_config)}, run_dir / "checkpoint_best.pt")
    torch.save({"model": final_state, "config": asdict(model_config)}, run_dir / "checkpoint_final.pt")
    model.load_state_dict(best_state)

    if mode == "exact_supervised":
        cohorts = {
            "train": split.indices("train"),
            "development": split.indices("development"),
            "frozen_test": split.indices("frozen_test"),
        }
    else:
        cohorts = {"all_state_fit": np.arange(oracle.state_count, dtype=np.int64)}
    final_metrics = {
        name: evaluate(model, tensors, oracle, indices, batch_size)
        for name, indices in cohorts.items()
    }

    gate_config = config["gate"]
    gate_cohort = "development" if mode == "exact_supervised" else "all_state_fit"
    gate_metrics = final_metrics[gate_cohort]
    gate = {
        "cohort": gate_cohort,
        "minimum_value_sign_accuracy": float(gate_config["minimum_value_sign_accuracy"]),
        "minimum_optimal_probability_mass": float(gate_config["minimum_optimal_probability_mass"]),
    }
    gate["status"] = (
        "PASS"
        if gate_metrics["value_sign_accuracy"] >= gate["minimum_value_sign_accuracy"]
        and gate_metrics["optimal_probability_mass"] >= gate["minimum_optimal_probability_mass"]
        else "FAIL"
    )

    result: dict[str, Any] = {
        "schema": "mini_jass.training_result.v1",
        "mode": mode,
        "seed": seed,
        "parameter_count": parameter_count(model),
        "model_hash": model_hash(model),
        "solver_hash": int(oracle.manifest["solver_hash"]),
        "split_manifest_hash": split.manifest["manifest_hash"],
        "epochs": len(history),
        "best_epoch": max(history, key=lambda item: item["selection_score"])["epoch"],
        "gate": gate,
        "final_metrics": final_metrics,
    }
    result_payload = json.dumps(result, sort_keys=True, separators=(",", ":")).encode()
    result["result_hash"] = hashlib.sha256(result_payload).hexdigest()

    (run_dir / "config.resolved.yaml").write_text(
        yaml.safe_dump(config, sort_keys=True), encoding="utf-8"
    )
    _write_json(
        run_dir / "environment.json",
        {
            "python": sys.version,
            "platform": platform.platform(),
            "torch": torch.__version__,
            "numpy": np.__version__,
            "threads": threads,
            "cuda_available": torch.cuda.is_available(),
        },
    )
    _write_json(run_dir / "seeds.json", {"training": seed, "split": config["split_seed"]})
    solver_manifest = json.loads(
        (ensure_artefact_path(Path(__file__).resolve().parents[2] / "artefacts/solver_manifest.v1.json"))
        .read_text(encoding="utf-8")
    )
    _write_json(run_dir / "solver_manifest.json", solver_manifest)
    _write_json(
        run_dir / "rule_manifest.json",
        {
            "schema": solver_manifest["rules"]["schema"],
            "rules": solver_manifest["rules"],
            "action_schema": solver_manifest["action_schema"],
            "action_count": solver_manifest["action_count"],
            "action_vocabulary_hash": solver_manifest["action_vocabulary_hash"],
        },
    )
    _write_json(run_dir / "split_manifest.json", split.manifest)
    _write_json(run_dir / "result.json", result)
    (run_dir / "summary.md").write_text(_summary_markdown(result), encoding="utf-8")
    return result
