"""Frozen M18 protocol, constants, and small statistical helpers."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import yaml

from mini_jass_lab.learning_gate import resolve_learning_gate_config

SCHEMA = "mini_jass.wdl_policy_iteration_microscope.v1"
EXPECTED_SEEDS = [180001, 180002, 180003, 180004, 180005]
EXPECTED_ARMS = {
    "evolving_arena_gate": {
        "generator_source": "evolving_parent",
        "search_depth": "frozen_m17",
        "promotion_rule": "arena_only",
    },
    "frozen_generator": {
        "generator_source": "initial_model",
        "search_depth": "frozen_m17",
        "promotion_rule": "arena_only",
    },
    "shallow_search": {
        "generator_source": "evolving_parent",
        "search_depth": 1,
        "promotion_rule": "arena_only",
    },
    "forced_advance": {
        "generator_source": "evolving_parent",
        "search_depth": "frozen_m17",
        "promotion_rule": "always",
    },
}
ARM_ORDER = tuple(EXPECTED_ARMS)
WDL_NAME = {-1: "L", 0: "D", 1: "W"}


def _digest(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _mean(values: list[float]) -> float:
    return float(np.mean(np.asarray(values, dtype=np.float64)))


def _confidence_95(values: list[float], critical: float) -> list[float]:
    samples = np.asarray(values, dtype=np.float64)
    if samples.size == 0:
        return [0.0, 0.0]
    if samples.size == 1:
        value = float(samples[0])
        return [value, value]
    center = float(samples.mean())
    half = critical * float(samples.std(ddof=1)) / math.sqrt(samples.size)
    return [center - half, center + half]


def _paired_summary(values: list[float], critical: float) -> dict[str, Any]:
    return {
        "count": len(values),
        "mean": _mean(values),
        "confidence_95": _confidence_95(values, critical),
        "values": [float(value) for value in values],
    }


def _resolve_config(path: Path) -> dict[str, Any]:
    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    if config.get("schema") != SCHEMA or config.get("milestone") != "M18":
        raise ValueError("unexpected M18 WDL policy-iteration schema")
    if config.get("expected_execution_host") != "cpx62":
        raise ValueError("M18 must remain cpx62-routed")
    if config.get("paired_seeds") != EXPECTED_SEEDS:
        raise ValueError("M18 paired seeds changed after preregistration")
    if config.get("arms") != EXPECTED_ARMS:
        raise ValueError("M18 arm definitions changed after preregistration")
    if config.get("ladder_max") != 8 or config.get("report_rungs") != [0, 1, 2, 4, 8]:
        raise ValueError("M18 ladder changed after preregistration")

    observer = config.get("observer_contract", {})
    if set(observer.get("oracle_reads_forbidden_for", [])) != {
        "training_targets",
        "selfplay_generation",
        "promotion_decision",
    }:
        raise ValueError("M18 oracle causal boundary changed")
    boundaries = config.get("boundaries", {})
    if (
        boundaries.get("promotable") is not False
        or boundaries.get("production_jass_changes_authorized") is not False
        or boundaries.get("direct_10x10_transfer_authorized") is not False
    ):
        raise ValueError("M18 crossed a forbidden boundary")

    root = path.resolve().parent.parent
    ladder_path = root / str(config["base_ladder_config"])
    ladder = yaml.safe_load(ladder_path.read_text(encoding="utf-8"))
    if (
        ladder.get("schema") != "mini_jass.generation_ladder.v1"
        or int(ladder.get("ladder_max", 0)) != 8
        or ladder.get("report_rungs") != [1, 2, 4, 8]
        or ladder.get("boundaries", {}).get("promotable") is not False
    ):
        raise ValueError("M18 requires the exact M17 eight-generation ladder")

    gate_path = root / str(ladder["base_gate_config"])
    gate = resolve_learning_gate_config(gate_path)
    if gate.milestone != "M8":
        raise ValueError("M18 requires the frozen passing M8 L1 recipe")
    base_loop = deepcopy(gate.resolved["base_loop"])
    if int(base_loop["generations"]) != 1:
        raise ValueError("M18 expects the historical M8 recipe at one generation")
    base_loop["generations"] = 8

    resolved = deepcopy(config)
    resolved["base_ladder_config"] = str(ladder_path.resolve())
    resolved["base_gate_config"] = str(gate_path.resolve())
    resolved["base_loop"] = base_loop
    return resolved
