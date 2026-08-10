"""Immutable replay and disjoint start-state manifests for contextual pools."""

from __future__ import annotations

import hashlib
from typing import Iterable, Mapping, Sequence

import numpy as np

from .pattern_reconstruction import digest, replay_fingerprint
from .replay import ReplaySample

START_MANIFEST_SCHEMA = "mini_jass.contextual_start_manifest.v1"
REPLAY_MANIFEST_SCHEMA = "mini_jass.contextual_replay_manifest.v1"


def _rank_state(namespace: str, state_id: int) -> bytes:
    return hashlib.sha256(f"{namespace}|{int(state_id)}".encode("ascii")).digest()


def allocate_disjoint_state_manifests(
    eligible_state_ids: Iterable[int],
    pool_seeds: Mapping[str, Sequence[int]],
    *,
    states_per_seed: int,
    namespace: str,
) -> dict[str, object]:
    """Allocate one deterministic, globally disjoint start list per pool/seed."""
    count = int(states_per_seed)
    if count < 1:
        raise ValueError("start manifest states_per_seed must be positive")
    pools = {
        str(pool): tuple(int(seed) for seed in seeds)
        for pool, seeds in pool_seeds.items()
    }
    if not pools or any(not seeds for seeds in pools.values()):
        raise ValueError("start manifest requires non-empty evidence pools")
    all_seeds = [seed for seeds in pools.values() for seed in seeds]
    if len(all_seeds) != len(set(all_seeds)):
        raise ValueError("start manifest evidence seeds must be globally unique")
    eligible = sorted({int(state) for state in eligible_state_ids})
    required = count * len(all_seeds)
    if len(eligible) < required:
        raise ValueError(
            f"start manifest needs {required} unique states, only {len(eligible)} exist"
        )
    ordered = sorted(eligible, key=lambda state: (_rank_state(namespace, state), state))
    cursor = 0
    assignments: dict[str, dict[str, list[int]]] = {}
    for pool, seeds in pools.items():
        assignments[pool] = {}
        for seed in seeds:
            selected = ordered[cursor : cursor + count]
            cursor += count
            assignments[pool][str(seed)] = selected
    flattened = [
        state
        for by_seed in assignments.values()
        for selected in by_seed.values()
        for state in selected
    ]
    if len(flattened) != len(set(flattened)):
        raise RuntimeError("start manifest allocation is not disjoint")
    report: dict[str, object] = {
        "schema": START_MANIFEST_SCHEMA,
        "namespace": str(namespace),
        "states_per_seed": count,
        "eligible_state_count": len(eligible),
        "assignments": assignments,
        "globally_disjoint": True,
    }
    report["manifest_hash"] = digest(report)
    return report


def assigned_states(manifest: Mapping[str, object], pool: str, seed: int) -> np.ndarray:
    if manifest.get("schema") != START_MANIFEST_SCHEMA:
        raise ValueError("unexpected contextual start manifest schema")
    assignments = manifest["assignments"]
    if not isinstance(assignments, Mapping):
        raise ValueError("contextual start manifest assignments are invalid")
    pool_rows = assignments.get(str(pool))
    if not isinstance(pool_rows, Mapping) or str(int(seed)) not in pool_rows:
        raise ValueError("contextual start manifest has no requested pool/seed")
    states = np.asarray(pool_rows[str(int(seed))], dtype=np.int64)
    expected = int(manifest["states_per_seed"])
    if states.shape != (expected,) or len(set(states.tolist())) != expected:
        raise ValueError("contextual start manifest row is not uniquely sized")
    return states


def freeze_replay_manifest(
    samples: Sequence[ReplaySample],
    *,
    pool: str,
    seed: int,
    source: str,
    start_state_ids: Iterable[int],
) -> dict[str, object]:
    if not samples:
        raise ValueError("cannot freeze an empty contextual replay")
    if any(sample.selected_action is None for sample in samples):
        raise ValueError("contextual replay cannot omit selected actions")
    identities = [
        {
            "seed": int(seed),
            "generation": int(sample.generation),
            "game_id": int(sample.game_id),
            "ply": int(sample.ply),
            "state_id": int(sample.state_id),
            "selected_action": int(sample.selected_action),
        }
        for sample in samples
    ]
    starts = [int(state) for state in start_state_ids]
    report: dict[str, object] = {
        "schema": REPLAY_MANIFEST_SCHEMA,
        "pool": str(pool),
        "seed": int(seed),
        "source": str(source),
        "sample_count": len(samples),
        "unique_state_count": len({int(sample.state_id) for sample in samples}),
        "sample_identity_hash": digest(identities),
        "replay_fingerprint": replay_fingerprint(samples),
        "selected_action_complete": True,
        "reserved_start_state_count": len(starts),
        "unique_reserved_start_state_count": len(set(starts)),
        "reserved_start_state_hash": digest(starts),
    }
    report["manifest_hash"] = digest(report)
    return report


def assert_replay_pool_disjointness(
    manifests: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    if not manifests:
        raise ValueError("replay disjointness requires manifests")
    for manifest in manifests:
        if manifest.get("schema") != REPLAY_MANIFEST_SCHEMA:
            raise ValueError("unexpected contextual replay manifest schema")
        expected_hash = digest(
            {key: value for key, value in manifest.items() if key != "manifest_hash"}
        )
        if manifest.get("manifest_hash") != expected_hash:
            raise ValueError("contextual replay manifest hash mismatch")
        if manifest.get("selected_action_complete") is not True:
            raise ValueError("contextual replay manifest omits selected actions")
        if int(manifest["reserved_start_state_count"]) != int(
            manifest["unique_reserved_start_state_count"]
        ):
            raise ValueError("contextual replay reserved starts are not unique")
    keys = [(str(manifest["pool"]), int(manifest["seed"])) for manifest in manifests]
    if len(keys) != len(set(keys)):
        raise ValueError("duplicate contextual replay pool/seed manifest")
    c1 = {int(manifest["seed"]) for manifest in manifests if manifest["pool"] == "C1"}
    c2 = {int(manifest["seed"]) for manifest in manifests if manifest["pool"] == "C2"}
    disjoint = c1.isdisjoint(c2)
    if not disjoint:
        raise ValueError("C1 and C2 replay seeds overlap")
    if not c1 or not c2:
        raise ValueError("replay disjointness proof requires both C1 and C2")
    unique_fields = (
        "manifest_hash",
        "sample_identity_hash",
        "replay_fingerprint",
        "reserved_start_state_hash",
    )
    for field in unique_fields:
        values = [str(manifest[field]) for manifest in manifests]
        if len(values) != len(set(values)):
            raise ValueError(f"C1/C2 replay manifests reuse {field}")
    report: dict[str, object] = {
        "schema": "mini_jass.contextual_replay_disjointness.v1",
        "manifest_count": len(manifests),
        "c1_seed_count": len(c1),
        "c2_seed_count": len(c2),
        "seed_disjoint": True,
        "sample_identity_hash_disjoint": True,
        "replay_fingerprint_disjoint": True,
        "reserved_start_state_hash_disjoint": True,
        "selected_action_complete": True,
        "manifest_hashes": sorted(
            str(manifest["manifest_hash"]) for manifest in manifests
        ),
    }
    report["report_hash"] = digest(report)
    return report
