"""Stable C++ oracle export and compact NumPy loading."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import subprocess
from typing import Any

import numpy as np

ACTION_COUNT = 72
PLAYABLE_SQUARES = 13
REVERSIBLE_PLY_LIMIT = 20
EXPECTED_SOLVER_HASH = 10671205679107391448
EXPECTED_MANIFEST_HASH = 16484585856267539683
L2_EXPECTED_SOLVER_HASH = 4061279344067907157
L2_EXPECTED_MANIFEST_HASH = 3750885099149748467


@dataclass(frozen=True)
class OracleArrays:
    manifest: dict[str, Any]
    state_keys: np.ndarray
    bitboards: np.ndarray
    sides: np.ndarray
    reversible_plies: np.ndarray
    terminal_status: np.ndarray
    canonical_ids: np.ndarray
    canonical_transforms: np.ndarray
    canonical_parent_counts: np.ndarray
    values: np.ndarray
    dtw: np.ndarray
    legal_mask: np.ndarray
    optimal_mask: np.ndarray
    action_children: np.ndarray

    @property
    def state_count(self) -> int:
        return int(self.state_keys.shape[0])

    @property
    def action_count(self) -> int:
        return int(self.manifest.get("action_count", ACTION_COUNT))

    @property
    def playable_squares(self) -> int:
        return int(self.manifest.get("playable_squares", PLAYABLE_SQUARES))

    @property
    def feature_count(self) -> int:
        return int(self.manifest.get("feature_count", 4 * self.playable_squares + 2))

    @property
    def reversible_ply_limit(self) -> int:
        return int(self.manifest.get("reversible_ply_limit", REVERSIBLE_PLY_LIMIT))

    @property
    def root_state_ids(self) -> tuple[int, ...]:
        return tuple(int(value) for value in self.manifest.get("root_state_ids", [0]))


def mini_jass_root() -> Path:
    return Path(__file__).resolve().parents[2]


def ensure_artefact_path(path: Path) -> Path:
    resolved = path.resolve()
    artefacts = (mini_jass_root() / "artefacts").resolve()
    if not resolved.is_relative_to(artefacts):
        raise ValueError(f"output must remain under {artefacts}")
    return resolved


def export_oracle(executable: Path, output: Path, level: str = "l1") -> str:
    """Run the C++ oracle exporter atomically and return its SHA-256."""
    executable = executable.resolve()
    output = ensure_artefact_path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    with temporary.open("wb") as stream:
        command = "export-oracle" if level == "l1" else "l2-export-oracle"
        if level not in ("l1", "l2"):
            raise ValueError("oracle level must be l1 or l2")
        subprocess.run(
            [str(executable), command],
            stdout=stream,
            check=True,
        )
    os.replace(temporary, output)
    return hashlib.sha256(output.read_bytes()).hexdigest()


def load_oracle(path: Path) -> OracleArrays:
    """Load and validate the deterministic JSONL oracle export."""
    with path.open("r", encoding="utf-8") as stream:
        first_line = stream.readline()
        if not first_line:
            raise ValueError("oracle export is empty")
        manifest = json.loads(first_line)
        schema = manifest.get("schema")
        if manifest.get("type") != "manifest" or schema not in (
            "mini_jass.oracle_dataset.v1",
            "mini_jass.oracle_dataset.l2.v1",
        ):
            raise ValueError("unexpected oracle dataset schema")
        expected_solver = (
            EXPECTED_SOLVER_HASH
            if schema == "mini_jass.oracle_dataset.v1"
            else L2_EXPECTED_SOLVER_HASH
        )
        expected_manifest = (
            EXPECTED_MANIFEST_HASH
            if schema == "mini_jass.oracle_dataset.v1"
            else L2_EXPECTED_MANIFEST_HASH
        )
        if manifest.get("solver_hash") != expected_solver:
            raise ValueError("oracle solver hash does not match the frozen Mini-Jass level")
        if manifest.get("manifest_hash") != expected_manifest:
            raise ValueError("oracle manifest hash does not match the frozen Mini-Jass level")

        count = int(manifest["state_count"])
        action_count = int(manifest.get("action_count", ACTION_COUNT))
        state_keys = np.empty(count, dtype=np.uint64)
        bitboards = np.empty((count, 4), dtype=np.uint32)
        sides = np.empty(count, dtype=np.uint8)
        reversible = np.empty(count, dtype=np.uint8)
        terminal_status = np.empty(count, dtype=np.uint8)
        canonical_ids = np.empty(count, dtype=np.uint32)
        canonical_transforms = np.empty(count, dtype=np.bool_)
        parent_counts = np.empty(count, dtype=np.uint16)
        values = np.empty(count, dtype=np.int8)
        dtw = np.full(count, -1, dtype=np.int16)
        legal_mask = np.zeros((count, action_count), dtype=np.bool_)
        optimal_mask = np.zeros((count, action_count), dtype=np.bool_)
        action_children = np.full((count, action_count), -1, dtype=np.int32)

        loaded = 0
        for loaded, line in enumerate(stream, start=1):
            record = json.loads(line)
            index = loaded - 1
            if index >= count or record.get("type") != "state":
                raise ValueError("oracle state count or record type is invalid")
            if record.get("raw_state_id") != index:
                raise ValueError("oracle raw state IDs are not contiguous")

            state_keys[index] = record["state_key"]
            bitboards[index] = (
                record["white_men"],
                record["black_men"],
                record["white_kings"],
                record["black_kings"],
            )
            sides[index] = record["side_to_move"]
            reversible[index] = record["reversible_plies"]
            terminal_status[index] = record["terminal_status"]
            canonical_ids[index] = record["canonical_state_id"]
            canonical_transforms[index] = record["canonical_transform"]
            parent_counts[index] = record["canonical_parent_count"]
            values[index] = record["value"]
            if record["dtw"] is not None:
                dtw[index] = record["dtw"]

            legal = record["legal_actions"]
            children = record["child_ids"]
            optimal = record["optimal_actions"]
            if len(legal) != len(children):
                raise ValueError("legal actions and child IDs are not aligned")
            if any(action < 0 or action >= action_count for action in legal + optimal):
                raise ValueError("oracle action is outside its frozen vocabulary")
            legal_mask[index, legal] = True
            optimal_mask[index, optimal] = True
            action_children[index, legal] = children
            if not set(optimal).issubset(legal):
                raise ValueError("optimal actions must be legal")
            if terminal_status[index] not in (0, 1, 2):
                raise ValueError("terminal status is outside the rule vocabulary")
            if (terminal_status[index] == 0) != bool(legal):
                raise ValueError("terminal status and legal-action set disagree")

    if loaded != count:
        raise ValueError(f"oracle expected {count} states but loaded {loaded}")
    if int(canonical_ids.max(initial=0)) >= int(manifest["canonical_state_count"]):
        raise ValueError("canonical state ID exceeds manifest count")
    if not np.all(np.isin(values, (-1, 0, 1))):
        raise ValueError("oracle values must be W/L/D")

    return OracleArrays(
        manifest=manifest,
        state_keys=state_keys,
        bitboards=bitboards,
        sides=sides,
        reversible_plies=reversible,
        terminal_status=terminal_status,
        canonical_ids=canonical_ids,
        canonical_transforms=canonical_transforms,
        canonical_parent_counts=parent_counts,
        values=values,
        dtw=dtw,
        legal_mask=legal_mask,
        optimal_mask=optimal_mask,
        action_children=action_children,
    )


def encode_features(oracle: OracleArrays) -> np.ndarray:
    """Encode the level-specific raw state in bitboard-major order."""
    shifts = np.arange(oracle.playable_squares, dtype=np.uint32)
    planes = ((oracle.bitboards[:, :, None] >> shifts) & 1).astype(np.float32)
    plane_count = 4 * oracle.playable_squares
    features = np.empty((oracle.state_count, oracle.feature_count), dtype=np.float32)
    features[:, :plane_count] = planes.reshape(oracle.state_count, plane_count)
    features[:, plane_count] = oracle.sides.astype(np.float32)
    features[:, plane_count + 1] = (
        oracle.reversible_plies.astype(np.float32) / oracle.reversible_ply_limit
    )
    return features


def uniform_optimal_targets(optimal_mask: np.ndarray) -> np.ndarray:
    targets = optimal_mask.astype(np.float32)
    counts = targets.sum(axis=1, keepdims=True)
    np.divide(targets, counts, out=targets, where=counts != 0)
    return targets
