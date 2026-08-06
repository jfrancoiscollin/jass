"""Immutable canonical-class train/development/frozen-test splits."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np

from .oracle import OracleArrays, ensure_artefact_path

SPLIT_NAMES = ("train", "development", "frozen_test")
SPLIT_SCHEMA = "mini_jass.split_manifest.v1"
SPLIT_ALGORITHM = "sha256_ordered_exact_70_15_15_within_value_material_v1"


@dataclass(frozen=True)
class SplitDefinition:
    canonical_assignments: np.ndarray
    raw_assignments: np.ndarray
    manifest: dict[str, Any]

    def indices(self, name: str) -> np.ndarray:
        if name not in SPLIT_NAMES:
            raise ValueError(f"unknown split {name}")
        return np.flatnonzero(self.raw_assignments == SPLIT_NAMES.index(name))


def _stable_order(seed: int, solver_hash: int, canonical_id: int) -> bytes:
    message = f"mini_jass.split.v1|{seed}|{solver_hash}|{canonical_id}".encode()
    return hashlib.sha256(message).digest()


def _canonical_material(oracle: OracleArrays, raw_index: int) -> tuple[int, int, int, int]:
    wm, bm, wk, bk = (int(value) for value in oracle.bitboards[raw_index])
    counts = (wm.bit_count(), bm.bit_count(), wk.bit_count(), bk.bit_count())
    if oracle.canonical_transforms[raw_index]:
        return counts[1], counts[0], counts[3], counts[2]
    return counts


def build_split(oracle: OracleArrays, seed: int = 20260806) -> SplitDefinition:
    canonical_count = int(oracle.manifest["canonical_state_count"])
    representatives = np.full(canonical_count, -1, dtype=np.int32)
    for raw_index, canonical_id in enumerate(oracle.canonical_ids):
        if representatives[canonical_id] == -1:
            representatives[canonical_id] = raw_index
    if np.any(representatives < 0):
        raise ValueError("every canonical class must have a raw representative")

    strata: dict[tuple[int, int, int, int, int], list[int]] = {}
    for canonical_id, raw_index in enumerate(representatives):
        key = (int(oracle.values[raw_index]), *_canonical_material(oracle, int(raw_index)))
        strata.setdefault(key, []).append(canonical_id)

    solver_hash = int(oracle.manifest["solver_hash"])
    assignments = np.empty(canonical_count, dtype=np.uint8)
    stratum_manifest: list[dict[str, Any]] = []
    for stratum, canonical_ids in sorted(strata.items()):
        ordered = sorted(
            canonical_ids,
            key=lambda canonical_id: _stable_order(seed, solver_hash, canonical_id),
        )
        count = len(ordered)
        train_end = int(count * 0.70)
        development_end = train_end + int(count * 0.15)
        assignments[ordered[:train_end]] = 0
        assignments[ordered[train_end:development_end]] = 1
        assignments[ordered[development_end:]] = 2
        stratum_manifest.append(
            {
                "value": stratum[0],
                "material": list(stratum[1:]),
                "canonical_counts": {
                    "train": train_end,
                    "development": development_end - train_end,
                    "frozen_test": count - development_end,
                },
            }
        )

    raw_assignments = assignments[oracle.canonical_ids]
    assignment_hasher = hashlib.sha256()
    for canonical_id, split_code in enumerate(assignments):
        assignment_hasher.update(f"{canonical_id}:{int(split_code)}\n".encode())

    canonical_counts = np.bincount(assignments, minlength=3)
    raw_counts = np.bincount(raw_assignments, minlength=3)
    manifest: dict[str, Any] = {
        "schema": SPLIT_SCHEMA,
        "algorithm": SPLIT_ALGORITHM,
        "seed": seed,
        "solver_hash": solver_hash,
        "solver_manifest_hash": int(oracle.manifest["manifest_hash"]),
        "canonical_state_count": canonical_count,
        "raw_state_count": oracle.state_count,
        "canonical_counts": {
            name: int(canonical_counts[index]) for index, name in enumerate(SPLIT_NAMES)
        },
        "raw_counts": {
            name: int(raw_counts[index]) for index, name in enumerate(SPLIT_NAMES)
        },
        "strata": stratum_manifest,
        "assignment_hash": assignment_hasher.hexdigest(),
    }
    payload = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
    manifest["manifest_hash"] = hashlib.sha256(payload).hexdigest()
    return SplitDefinition(assignments, raw_assignments, manifest)


def write_split_manifest(split: SplitDefinition, path: Path) -> None:
    path = ensure_artefact_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(split.manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
