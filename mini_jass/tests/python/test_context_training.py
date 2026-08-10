"""Replay, pairing and optimization contracts for contextual C1."""

from __future__ import annotations

from copy import deepcopy
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
import torch
import yaml

from mini_jass_lab.context import ContextState, WHITE, terminal_status
from mini_jass_lab.context_replay import (
    allocate_disjoint_state_manifests,
    assert_replay_pool_disjointness,
    assigned_states,
    freeze_replay_manifest,
)
from mini_jass_lab.context_scaffold import ContextualPatternScaffold
from mini_jass_lab.context_training import (
    batch_schedule,
    contextual_replay_targets,
    tensor_state_hash,
    train_contextual_from_replay,
)
from mini_jass_lab.game_graph import GameGraph
from mini_jass_lab.patterns import PLAYABLE, PatternSet
from mini_jass_lab.replay import ReplaySample

ROOT = Path(__file__).resolve().parents[2]


def _tool(name: str):
    path = ROOT / "tools" / name
    spec = importlib.util.spec_from_file_location(name.removesuffix(".py"), path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


C1 = _tool("run_contextual_c1.py")
C2 = _tool("run_contextual_c2.py")
SEALED = _tool("run_contextual_sealed_read.py")


def _fixture() -> tuple[SimpleNamespace, GameGraph, list[ReplaySample]]:
    states = (
        ContextState(1 << 8, 1 << 2, 0, 0, WHITE, 0),
        ContextState(1 << 3, 0, 0, 0, 1, 0),
    )
    children = np.full((2, 72), -1, dtype=np.int32)
    children[0, 0] = 1
    statuses = np.asarray((0, terminal_status(states[1])), dtype=np.uint8)
    oracle = SimpleNamespace(
        bitboards=np.asarray(
            [
                (
                    state.white_men,
                    state.black_men,
                    state.white_kings,
                    state.black_kings,
                )
                for state in states
            ],
            dtype=np.uint32,
        ),
        sides=np.asarray([state.side_to_move for state in states], dtype=np.uint8),
        reversible_plies=np.asarray(
            [state.reversible_plies for state in states], dtype=np.uint8
        ),
        terminal_status=statuses,
        action_children=children,
    )
    features = np.zeros((2, 4 * PLAYABLE + 2), dtype=np.float32)
    for row, state in enumerate(states):
        for plane, board in enumerate(
            (
                state.white_men,
                state.black_men,
                state.white_kings,
                state.black_kings,
            )
        ):
            for square in range(PLAYABLE):
                if board & (1 << square):
                    features[row, plane * PLAYABLE + square] = 1.0
        features[row, 4 * PLAYABLE] = float(state.side_to_move)
        features[row, 4 * PLAYABLE + 1] = state.reversible_plies / 20.0
    legal = children >= 0
    graph = GameGraph(features, legal, children, statuses)
    policy = np.zeros(72, dtype=np.float32)
    policy[0] = 1.0
    samples = [
        ReplaySample(0, 1.0, policy.copy(), 1, game_id, 0, 0) for game_id in range(4)
    ]
    return oracle, graph, samples


def _config() -> dict:
    arms = {
        "WDL_ONLY": (0.0, 0.0, 0.0),
        "WDL_PLUS_CONTEXT": (0.25, 0.0, 0.0),
        "WDL_PLUS_DELTA_CONTEXT": (0.0, 0.25, 0.0),
        "WDL_PLUS_RESIDUAL": (0.0, 0.0, 0.25),
        "WDL_PLUS_FULL_CONTEXT": (1.0 / 12.0,) * 3,
    }
    return {
        "c1_arms": {
            arm: {
                "value_target": "terminal_wdl",
                "beta_context": weights[0],
                "gamma_delta_context": weights[1],
                "eta_residual": weights[2],
                "oracle_training_signal": False,
            }
            for arm, weights in arms.items()
        }
    }


def test_start_manifests_are_deterministic_and_disjoint_across_c1_c2() -> None:
    pools = {"C1": (270501, 270502), "C2": (270601, 270602)}
    first = allocate_disjoint_state_manifests(
        range(100), pools, states_per_seed=5, namespace="fixture"
    )
    second = allocate_disjoint_state_manifests(
        reversed(range(100)), pools, states_per_seed=5, namespace="fixture"
    )
    assert first == second
    rows = [
        assigned_states(first, pool, seed).tolist()
        for pool, seeds in pools.items()
        for seed in seeds
    ]
    flattened = [state for row in rows for state in row]
    assert len(flattened) == len(set(flattened)) == 20


def test_replay_manifest_and_targets_require_the_recorded_legal_action() -> None:
    oracle, graph, samples = _fixture()
    manifest = freeze_replay_manifest(
        samples, pool="C1", seed=270501, source="G1_WIDE_OUTCOME", start_state_ids=(0,)
    )
    assert manifest["selected_action_complete"] is True
    targets = contextual_replay_targets(
        oracle,
        graph,
        samples,
        allowed_state_mask=np.asarray((True, False)),
        baseline_weights={
            "material_man_delta": 1.0,
            "material_king_delta": 1.5,
            "legal_move_delta": 0.2,
            "capture_option_delta": 0.15,
            "promotion_pressure_delta": 0.2,
            "blocked_man_delta": -0.15,
            "advanced_man_delta": 0.1,
            "center_presence_delta": 0.05,
            "terminal_flag": 0.0,
        },
        tau=1.5,
        residual_clip=1.5,
    )
    assert np.array_equal(targets["child_ids"], np.ones(4, dtype=np.int64))

    missing = deepcopy(samples)
    missing[0] = ReplaySample(0, 1.0, samples[0].policy_target, 1, 0, 0)
    with pytest.raises(ValueError, match="missing its selected"):
        contextual_replay_targets(
            oracle,
            graph,
            missing,
            allowed_state_mask=np.asarray((True, False)),
            baseline_weights={
                name: 0.0
                for name in (
                    "material_man_delta",
                    "material_king_delta",
                    "legal_move_delta",
                    "capture_option_delta",
                    "promotion_pressure_delta",
                    "blocked_man_delta",
                    "advanced_man_delta",
                    "center_presence_delta",
                    "terminal_flag",
                )
            },
            tau=1.5,
            residual_clip=1.5,
        )


def test_replay_disjointness_verifies_hashes_and_rejects_reuse() -> None:
    _, _, samples = _fixture()
    c1 = freeze_replay_manifest(
        samples,
        pool="C1",
        seed=270501,
        source="G1_WIDE_OUTCOME",
        start_state_ids=(1,),
    )
    c2_samples = [
        ReplaySample(
            sample.state_id,
            sample.value_target,
            sample.policy_target,
            sample.generation,
            sample.game_id + 10,
            sample.ply,
            sample.selected_action,
        )
        for sample in samples
    ]
    c2 = freeze_replay_manifest(
        c2_samples,
        pool="C2",
        seed=270601,
        source="G1_WIDE_OUTCOME",
        start_state_ids=(2,),
    )
    report = assert_replay_pool_disjointness((c1, c2))
    assert report["seed_disjoint"] is True
    assert report["replay_fingerprint_disjoint"] is True
    corrupted = deepcopy(c2)
    corrupted["replay_fingerprint"] = c1["replay_fingerprint"]
    corrupted["manifest_hash"] = c1["manifest_hash"]
    with pytest.raises(ValueError, match="hash mismatch|reuse"):
        assert_replay_pool_disjointness((c1, corrupted))


def test_contextual_arms_share_batches_and_auxiliary_loss_changes_export() -> None:
    oracle, graph, samples = _fixture()
    targets = contextual_replay_targets(
        oracle,
        graph,
        samples,
        allowed_state_mask=np.asarray((True, False)),
        baseline_weights={
            "material_man_delta": 1.0,
            "material_king_delta": 1.5,
            "legal_move_delta": 0.2,
            "capture_option_delta": 0.15,
            "promotion_pressure_delta": 0.2,
            "blocked_man_delta": -0.15,
            "advanced_man_delta": 0.1,
            "center_presence_delta": 0.05,
            "terminal_flag": 0.0,
        },
        tau=1.5,
        residual_clip=1.5,
    )
    schedule = batch_schedule(len(samples), 4, 2, 99)
    control = ContextualPatternScaffold(PatternSet.from_window(2), seed=270501)
    full = ContextualPatternScaffold(PatternSet.from_window(2), seed=270501)
    control_metrics = train_contextual_from_replay(
        control,
        graph,
        targets,
        arm="WDL_ONLY",
        config=_config(),
        indices=schedule,
        learning_rate=0.01,
        weight_decay=0.0,
    )
    full_metrics = train_contextual_from_replay(
        full,
        graph,
        targets,
        arm="WDL_PLUS_FULL_CONTEXT",
        config=_config(),
        indices=schedule,
        learning_rate=0.01,
        weight_decay=0.0,
    )
    assert control_metrics["initial_export_hash"] == full_metrics["initial_export_hash"]
    assert control_metrics["batch_schedule_hash"] == full_metrics["batch_schedule_hash"]
    assert control_metrics["final_export_hash"] != full_metrics["final_export_hash"]
    assert full_metrics["changed_exported_bucket_count"] > 0
    assert not torch.equal(
        control.export_pattern_eval().bucket_weight,
        full.export_pattern_eval().bucket_weight,
    )


def test_c1_runner_and_cpx_entrypoint_are_fail_closed() -> None:
    config, loop = C1._resolve(ROOT / "configs" / "contextual_outcome_supervision.yaml")
    assert loop["model"]["architecture"] == "folded_pattern_value"
    assert config["c1_execution_v1"]["replay"]["source"] == "G1_WIDE_OUTCOME"
    runner = (ROOT / "tools" / "run_contextual_c1.py").read_text(encoding="utf-8")
    assert 'split.indices("frozen_test")' not in runner
    assert "prove_scalar_export(scaffold, oracle)" in runner
    job = (ROOT / "jobs" / "run_contextual_c1_cpx.sh").read_text(encoding="utf-8")
    assert "CONTEXTUAL_C1_IMPLEMENTATION_SHA" in job
    assert 'actual_sha=$(git -C "$repo" rev-parse HEAD)' in job
    assert "scientific-summary.json exceeds 64 KiB" in job


def test_c2_runner_and_cpx_entrypoint_are_fail_closed() -> None:
    config, loop = C2._resolve(ROOT / "configs" / "contextual_outcome_supervision.yaml")
    assert loop["model"]["architecture"] == "folded_pattern_value"
    assert config["c1_decision"]["frozen_report_v1"]["c2_authorized"] is True
    runner = (ROOT / "tools" / "run_contextual_c2.py").read_text(encoding="utf-8")
    assert 'split.indices("frozen_test")' not in runner
    assert "assert_replay_pool_disjointness" in runner
    assert "sequential_flat_prior_paired_score" in runner
    job = (ROOT / "jobs" / "run_contextual_c2_cpx.sh").read_text(encoding="utf-8")
    assert "CONTEXTUAL_C2_IMPLEMENTATION_SHA" in job
    assert "CONTEXTUAL_C1_RESULT_PATH" in job
    assert "CONTEXTUAL_C1_FREEZE_REPORT_PATH" in job
    assert "scientific-summary.json exceeds 64 KiB" in job


def test_sealed_runner_checkpoint_roundtrip_and_entrypoint_are_fail_closed(
    tmp_path: Path,
) -> None:
    config_path = ROOT / "configs" / "contextual_outcome_supervision.yaml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    with pytest.raises(ValueError, match="independently frozen C2"):
        SEALED._resolve(config_path)
    assert config["c2_disjoint_replication"]["frozen_report_v1"][
        "sealed_test_read_authorized"
    ] is True
    assert config["sealed_test_read"]["frozen_report_v1"][
        "sealed_test_read_count"
    ] == 1
    model = ContextualPatternScaffold(
        PatternSet.from_window(3), seed=270601
    ).export_pattern_eval()
    checkpoint = tmp_path / "checkpoint.npz"
    np.savez_compressed(
        checkpoint,
        bucket_weight=model.bucket_weight.detach().cpu().numpy(),
        extra_weight=model.extra_weight.detach().cpu().numpy(),
        bias=model.bias.detach().cpu().numpy(),
        bucket_class=model.bucket_class.detach().cpu().numpy(),
    )
    loaded = SEALED._load_checkpoint(checkpoint, config)
    assert tensor_state_hash(loaded) == tensor_state_hash(model)
    runner = (ROOT / "tools" / "run_contextual_sealed_read.py").read_text(
        encoding="utf-8"
    )
    assert 'split.indices("frozen_test")' in runner
    assert "protocol_hash_frozen_before_metric_read" in runner
    assert "SEALED_READ_STARTED.json" in runner
    assert "train_contextual_from_replay" not in runner
    job = (ROOT / "jobs" / "run_contextual_sealed_read_cpx.sh").read_text(
        encoding="utf-8"
    )
    assert "CONTEXTUAL_SEALED_IMPLEMENTATION_SHA" in job
    assert "retry_without_protocol_review_forbidden_if_read_started" in job
    assert "scientific-summary.json exceeds 64 KiB" in job
