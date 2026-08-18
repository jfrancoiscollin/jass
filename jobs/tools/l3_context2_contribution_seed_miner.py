#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Mine deterministic CTX2 weak-contribution seed pools from corpus 1409.

The certified mapper is replayed without refit.  Five pools target the weakest
base-component contributions found by the 1412 autopsy; a sixth neutral pool
has the exact same phase/WDL/material histogram.  Outputs contain positions
only: score and WDL are zeroed before they can be used as fresh self-play
seeds.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import heapq
import itertools
import json
import math
from pathlib import Path
import struct
from typing import Any

import numpy as np

try:
    from l3_conditional_targets import (
        CTX2_BASE_COMPONENTS,
        CTX2_CONTEXT_COMPONENTS,
        JNNW_DTYPE,
        _open_counted,
        _open_feat,
        _open_meta,
        _sha256,
        _splitmix64,
        game_folds,
        tempo_phase_from_records,
    )
except ModuleNotFoundError:
    from jobs.tools.l3_conditional_targets import (
        CTX2_BASE_COMPONENTS,
        CTX2_CONTEXT_COMPONENTS,
        JNNW_DTYPE,
        _open_counted,
        _open_feat,
        _open_meta,
        _sha256,
        _splitmix64,
        game_folds,
        tempo_phase_from_records,
    )


HEADER = struct.Struct("<4sI")
RECORD_SIZE = JNNW_DTYPE.itemsize
TARGET_COMPONENTS = (
    "king_safe_mobility_delta",
    "legal_capture_option_delta",
    "center_presence_delta",
    "king_centrality_delta",
    "blocked_man_delta",
)
DOMINANT_COMPONENT = "men_delta"
PIECE_EDGES = np.asarray([0, 8, 15, 22, 30, 41], dtype=np.int16)
POOL_NAMES = {component: component.removesuffix("_delta") for component in TARGET_COMPONENTS}
MAX_ALLOCATION_ATTEMPTS = math.factorial(len(TARGET_COMPONENTS))


class AllocationShortfall(ValueError):
    """A greedy allocation path exhausted a bucket under the exact guards."""


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _rot50(value: int) -> int:
    result = 0
    while value:
        lsb = value & -value
        square = lsb.bit_length() - 1
        result |= 1 << (49 - square)
        value ^= lsb
    return result


def _mirror_position(record: bytes) -> bytes:
    wm, wk, bm, bk = struct.unpack_from("<QQQQ", record, 0)
    stm = record[32]
    return struct.pack(
        "<QQQQB", _rot50(bm), _rot50(bk), _rot50(wm), _rot50(wk), 1 - stm
    )


def canonical_position(record: bytes) -> bytes:
    return min(record[:33], _mirror_position(record))


def zero_targets(record: bytes) -> bytes:
    if len(record) != RECORD_SIZE:
        raise ValueError("JNNW record size drift")
    return record[:33] + struct.pack("<ib", 0, 0)


def allocate_capped_proportional(
    capacities: np.ndarray, weights: np.ndarray, total: int
) -> np.ndarray:
    """Allocate an exact integer total proportionally, without exceeding caps."""
    caps = np.asarray(capacities, dtype=np.int64)
    mass = np.asarray(weights, dtype=np.float64)
    if caps.ndim != 1 or mass.shape != caps.shape or np.any(caps < 0) or np.any(mass < 0):
        raise ValueError("invalid allocation inputs")
    if total < 0 or int(caps.sum()) < total:
        raise ValueError("insufficient capped capacity")
    allocation = np.zeros(len(caps), dtype=np.int64)
    remaining = int(total)
    while remaining:
        active = allocation < caps
        if not np.any(active):
            raise ValueError("allocation exhausted before target")
        active_mass = np.where(active, mass, 0.0)
        if float(active_mass.sum()) <= 0:
            active_mass = active.astype(np.float64)
        ideal = remaining * active_mass / active_mass.sum()
        room = caps - allocation
        step = np.minimum(np.floor(ideal).astype(np.int64), room)
        gained = int(step.sum())
        if gained:
            allocation += step
            remaining -= gained
            continue
        fractions = ideal - np.floor(ideal)
        order = np.lexsort((np.arange(len(caps)), -fractions, -active_mass))
        for index in order:
            if active[index]:
                allocation[index] += 1
                remaining -= 1
                break
    return allocation


def _pieces(records: np.ndarray, chunk_size: int = 200_000) -> np.ndarray:
    lookup = np.asarray([int(value).bit_count() for value in range(256)], dtype=np.uint8)
    result = np.empty(len(records), dtype=np.int16)
    for start in range(0, len(records), chunk_size):
        stop = min(start + chunk_size, len(records))
        total = np.zeros(stop - start, dtype=np.int16)
        for field in ("wm", "wk", "bm", "bk"):
            values = np.ascontiguousarray(records[field][start:stop], dtype="<u8")
            total += lookup[values.view(np.uint8).reshape(-1, 8)].sum(
                axis=1, dtype=np.int16
            )
        result[start:stop] = total
    return result


def _strata(records: np.ndarray) -> tuple[np.ndarray, dict[str, Any]]:
    phase = np.asarray(tempo_phase_from_records(records), dtype=np.float64)
    phase_bins = np.minimum(np.floor(phase * 4).astype(np.int16), 3)
    piece_counts = _pieces(records)
    piece_bins = np.clip(np.digitize(piece_counts, PIECE_EDGES, right=False) - 1, 0, 4)
    wdl = np.asarray(records["wdl"], dtype=np.int16)
    if not np.all(np.isin(wdl, (-1, 0, 1))):
        raise ValueError("JNNW WDL outside {-1,0,1}")
    wdl_codes = wdl + 1
    strata = phase_bins * 15 + wdl_codes * 5 + piece_bins
    return strata.astype(np.int16), {
        "phase_bins": 4,
        "wdl_codes": {"loss": 0, "draw": 1, "win": 2},
        "piece_edges_inclusive_lower": PIECE_EDGES.tolist(),
        "stratum_formula": "phase_bin*15 + (wdl_stm+1)*5 + piece_bin",
        "strata": 60,
    }


def mapper_contribution_scores(
    *,
    metadata: np.ndarray,
    features: np.ndarray,
    report: dict[str, Any],
    chunk_size: int = 100_000,
) -> tuple[np.ndarray, np.ndarray, int]:
    if report.get("schema") != "jass.l3_conditional_targets.v2":
        raise ValueError("conditional mapper schema drift")
    if report.get("context_schema") != "ctx2-phase-tactical-30":
        raise ValueError("conditional context schema drift")
    mapping = report.get("mapping") or {}
    if tuple(mapping.get("components") or ()) != CTX2_CONTEXT_COMPONENTS:
        raise ValueError("conditional component order drift")
    if (
        mapping.get("fold_group") != "opening_id"
        or mapping.get("row_weighting") != "game_equal"
        or not mapping.get("fold_local_rms")
        or not mapping.get("all_groups_fold_disjoint")
    ):
        raise ValueError("conditional mapper contract drift")
    train_count = int(report.get("train_records", -1))
    if report.get("records") != len(metadata) or not 0 < train_count < len(metadata):
        raise ValueError("conditional mapper sizing drift")
    fold_count = int(mapping.get("fold_count", 0))
    fold_seed = int(mapping.get("fold_seed", -1))
    fold_rows = sorted(mapping.get("folds") or [], key=lambda row: int(row["fold"]))
    if fold_count != 5 or [int(row["fold"]) for row in fold_rows] != list(range(5)):
        raise ValueError("conditional mapper fold drift")
    fits = [row["fit"] for row in fold_rows] + [mapping["final_train_fit"]["fit"]]
    if not all(bool(row.get("converged")) for row in fits):
        raise ValueError("all six mapper fits must have converged")
    theta = np.asarray(
        [row["theta_raw"] for row in fold_rows]
        + [mapping["final_train_fit"]["theta_raw"]],
        dtype=np.float64,
    )
    if theta.shape != (6, len(CTX2_CONTEXT_COMPONENTS)):
        raise ValueError("mapper coefficient shape drift")
    folds = game_folds(
        np.asarray(metadata["opening_id"], dtype=np.uint64), fold_count, fold_seed
    )
    folds[train_count:] = fold_count
    selected_components = TARGET_COMPONENTS + (DOMINANT_COMPONENT,)
    selected_indices = np.asarray(
        [CTX2_BASE_COMPONENTS.index(name) for name in selected_components], dtype=np.int64
    )
    scores = np.empty((len(metadata), len(selected_components)), dtype=np.float32)
    signs = np.empty((len(metadata), len(TARGET_COMPONENTS)), dtype=np.int8)
    for start in range(0, len(metadata), chunk_size):
        stop = min(start + chunk_size, len(metadata))
        x = np.asarray(features[start:stop], dtype=np.float64)
        linear = x * theta[np.asarray(folds[start:stop], dtype=np.int64)]
        base_linear = linear[:, :15] + linear[:, 15:]
        denominator = np.abs(base_linear).sum(axis=1)
        valid = denominator > 1e-15
        normalized = np.zeros_like(base_linear)
        normalized[valid] = np.abs(base_linear[valid]) / denominator[valid, None]
        scores[start:stop] = normalized[:, selected_indices]
        signs[start:stop] = np.sign(base_linear[:, selected_indices[:-1]]).astype(np.int8)
    return scores, signs, train_count


def _thresholds(
    scores: np.ndarray, strata: np.ndarray
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    width = len(TARGET_COMPONENTS)
    count = 60
    p90 = np.full((width, count), np.inf, dtype=np.float64)
    men_median = np.full(count, -np.inf, dtype=np.float64)
    stratum_counts = np.zeros(count, dtype=np.int64)
    men = scores[:, -1]
    for stratum in range(count):
        rows = np.flatnonzero(strata == stratum)
        stratum_counts[stratum] = len(rows)
        if not len(rows):
            continue
        men_median[stratum] = float(np.quantile(men[rows], 0.50))
        for component in range(width):
            p90[component, stratum] = float(np.quantile(scores[rows, component], 0.90))
    return p90, men_median, stratum_counts


def _eligible(
    scores: np.ndarray,
    signs: np.ndarray,
    strata: np.ndarray,
    p90: np.ndarray,
    men_median: np.ndarray,
    component: int,
    sign: int,
    stratum: int,
) -> np.ndarray:
    threshold = p90[component, stratum]
    return np.flatnonzero(
        (strata == stratum)
        & (scores[:, component] > 0.0)
        & (scores[:, component] >= threshold)
        & (scores[:, -1] < men_median[stratum])
        & (signs[:, component] == sign)
    )


def _rank_indices(
    indices: np.ndarray,
    metadata: np.ndarray,
    *,
    seed: int,
    salt: int,
) -> np.ndarray:
    if not len(indices):
        return indices
    values = (
        np.asarray(indices, dtype=np.uint64)
        ^ np.asarray(metadata["opening_id"][indices], dtype=np.uint64)
        ^ np.asarray(metadata["game_id"][indices], dtype=np.uint64)
        ^ np.uint64(seed)
        ^ np.uint64(salt)
    )
    keys = _splitmix64(values)
    return indices[np.lexsort((indices, keys))]


def _opening_pool_masks(
    eligible_by_bucket: dict[tuple[int, int, int], np.ndarray],
    metadata: np.ndarray,
) -> dict[int, int]:
    """Map each eligible opening to every target pool that can use it.

    The previous allocator only discovered cross-pool contention after an
    earlier pool had claimed an opening.  Recording the contention graph up
    front lets every pool consume its exclusive openings before touching the
    shared openings needed by a scarcer pool.
    """
    masks: dict[int, int] = defaultdict(int)
    for (component, _sign_index, _stratum), indices in eligible_by_bucket.items():
        if not len(indices):
            continue
        bit = 1 << component
        for raw_opening in np.unique(metadata["opening_id"][indices]):
            masks[int(raw_opening)] |= bit
    return dict(masks)


def _global_request_order(
    *,
    eligible_by_bucket: dict[tuple[int, int, int], np.ndarray],
    common_sign_quotas: np.ndarray,
    metadata: np.ndarray,
    opening_masks: dict[int, int],
    seed: int,
) -> list[tuple[int, int, int, int]]:
    """Order exact target buckets by global scarcity, not by whole pool.

    A request with few openings exclusive to its pool must claim shared
    openings before requests that can be satisfied from abundant exclusive
    supply.  Integer cross-products keep ordering deterministic and avoid
    floating-point drift.
    """
    requests: list[tuple[int, int, int, int]] = []
    sort_keys: dict[tuple[int, int, int, int], tuple[int, ...]] = {}
    for component in range(len(TARGET_COMPONENTS)):
        bit = 1 << component
        for sign_index in range(2):
            for stratum in range(60):
                required = int(common_sign_quotas[sign_index, stratum])
                if not required:
                    continue
                candidates = eligible_by_bucket[(component, sign_index, stratum)]
                openings = np.unique(metadata["opening_id"][candidates])
                exclusive = sum(
                    opening_masks.get(int(raw_opening), 0) == bit
                    for raw_opening in openings
                )
                request = (component, sign_index, stratum, required)
                requests.append(request)
                # First: lowest exclusive supply per requested row.  Second:
                # lowest total candidate supply.  The hash is only a stable
                # tie-breaker and never overrides either scarcity measure.
                tie = int.from_bytes(
                    hashlib.sha256(
                        struct.pack("<QBBBB", int(seed), component, sign_index, stratum, 0)
                    ).digest()[:8],
                    "little",
                )
                sort_keys[request] = (
                    exclusive * 1_000_000 // required,
                    len(candidates) * 1_000_000 // required,
                    tie,
                    component,
                    sign_index,
                    stratum,
                )
    return sorted(requests, key=sort_keys.__getitem__)


def _rank_global_candidates(
    indices: np.ndarray,
    metadata: np.ndarray,
    *,
    pool: str,
    opening_owner: dict[int, str],
    opening_masks: dict[int, int],
    seed: int,
    salt: int,
) -> np.ndarray:
    """Prefer reusable/exclusive openings, then the deterministic hash rank."""
    if not len(indices):
        return indices
    openings = np.asarray(metadata["opening_id"][indices], dtype=np.uint64)
    owner_rank = np.fromiter(
        (
            0 if opening_owner.get(int(raw_opening)) == pool
            else 1 if int(raw_opening) not in opening_owner
            else 2
            for raw_opening in openings
        ),
        dtype=np.uint8,
        count=len(indices),
    )
    competition = np.fromiter(
        (opening_masks.get(int(raw_opening), 0).bit_count() for raw_opening in openings),
        dtype=np.uint8,
        count=len(indices),
    )
    values = (
        np.asarray(indices, dtype=np.uint64)
        ^ openings
        ^ np.asarray(metadata["game_id"][indices], dtype=np.uint64)
        ^ np.uint64(seed)
        ^ np.uint64(salt)
    )
    hashes = _splitmix64(values)
    return indices[np.lexsort((indices, hashes, competition, owner_rank))]


def _opening_request_capacities(
    requests: list[tuple[int, int, int, int]],
    eligible_by_bucket: dict[tuple[int, int, int], np.ndarray],
    metadata: np.ndarray,
) -> tuple[dict[int, list[tuple[int, int]]], np.ndarray]:
    """Index request capacity by opening, respecting the two-row game cap."""
    by_opening: dict[int, list[tuple[int, int]]] = defaultdict(list)
    totals = np.zeros(len(requests), dtype=np.int64)
    for request_index, (component, sign_index, stratum, _required) in enumerate(requests):
        indices = eligible_by_bucket[(component, sign_index, stratum)]
        pairs = np.empty((len(indices), 2), dtype=np.uint64)
        pairs[:, 0] = metadata["opening_id"][indices]
        pairs[:, 1] = metadata["game_id"][indices]
        unique_pairs, counts = np.unique(pairs, axis=0, return_counts=True)
        opening_capacity: Counter[int] = Counter()
        for pair, count in zip(unique_pairs, counts, strict=True):
            opening_capacity[int(pair[0])] += min(int(count), 2)
        for opening, capacity in opening_capacity.items():
            by_opening[opening].append((request_index, capacity))
            totals[request_index] += capacity
    return dict(by_opening), totals


def _current_request_capacity(
    *,
    candidates: np.ndarray,
    pool: str,
    metadata: np.ndarray,
    opening_owner: dict[int, str],
    game_counts: Counter[int],
) -> int:
    """Return exact remaining row capacity under opening and game guards."""
    by_game: Counter[int] = Counter()
    for raw_index in candidates:
        index = int(raw_index)
        opening = int(metadata["opening_id"][index])
        owner = opening_owner.get(opening)
        if owner is not None and owner != pool:
            continue
        game = int(metadata["game_id"][index])
        if game_counts[game] < 2:
            by_game[game] += 1
    return sum(min(count, 2 - game_counts[game]) for game, count in by_game.items())


def _record_bytes(records: np.ndarray, index: int) -> bytes:
    value = records[index].tobytes()
    if len(value) != RECORD_SIZE:
        raise ValueError("JNNW memmap row size drift")
    return value


def _select_bucket(
    *,
    candidates: np.ndarray,
    required: int,
    pool: str,
    records: np.ndarray,
    metadata: np.ndarray,
    opening_owner: dict[int, str],
    game_counts: Counter[int],
    canonical_used: set[bytes],
    claimed_openings: set[int] | None = None,
) -> list[int]:
    selected: list[int] = []
    for raw_index in candidates:
        index = int(raw_index)
        opening = int(metadata["opening_id"][index])
        owner = opening_owner.get(opening)
        if owner is not None and owner != pool:
            continue
        game = int(metadata["game_id"][index])
        if game_counts[game] >= 2:
            continue
        record = _record_bytes(records, index)
        canonical = canonical_position(record)
        if canonical in canonical_used:
            continue
        if owner is None and claimed_openings is not None:
            claimed_openings.add(opening)
        opening_owner[opening] = pool
        game_counts[game] += 1
        canonical_used.add(canonical)
        selected.append(index)
        if len(selected) == required:
            break
    if len(selected) != required:
        raise AllocationShortfall(
            f"pool {pool}: selected {len(selected)} of {required} after disjointness guards"
        )
    return selected


def _allocation_orders(
    base_order: list[int], seed: int
) -> list[tuple[int, ...]]:
    """Return every component order once, deterministically, base order first."""
    base = tuple(base_order)
    remaining = [
        order
        for order in itertools.permutations(range(len(base)))
        if order != base
    ]
    remaining.sort(
        key=lambda order: hashlib.sha256(
            struct.pack("<Q", int(seed)) + bytes(order)
        ).digest()
    )
    return [base, *remaining]


def _write_pool(path: Path, records: np.ndarray, indices: list[int]) -> str:
    if path.exists():
        raise ValueError(f"refusing to overwrite {path}")
    temporary = path.with_name(f".{path.name}.tmp")
    if temporary.exists():
        temporary.unlink()
    with temporary.open("xb") as stream:
        stream.write(HEADER.pack(b"JNNW", len(indices)))
        for index in indices:
            stream.write(zero_targets(_record_bytes(records, index)))
        stream.flush()
    temporary.replace(path)
    raw = path.read_bytes()
    if len(raw) != HEADER.size + len(indices) * RECORD_SIZE:
        raise ValueError(f"{path}: output size drift")
    magic, count = HEADER.unpack_from(raw)
    if magic != b"JNNW" or count != len(indices):
        raise ValueError(f"{path}: output header drift")
    rows = [raw[8 + i * RECORD_SIZE : 8 + (i + 1) * RECORD_SIZE] for i in range(count)]
    if any(row[33:] != b"\0\0\0\0\0" for row in rows):
        raise ValueError(f"{path}: seed target leakage")
    if len({canonical_position(row) for row in rows}) != count:
        raise ValueError(f"{path}: canonical duplicate")
    return _sha256(path)


def mine(args: argparse.Namespace) -> dict[str, Any]:
    data_path = Path(args.data)
    meta_path = Path(args.meta)
    feat_path = Path(args.features)
    conditional_path = Path(args.conditional_report)
    autopsy_path = Path(args.autopsy)
    out_dir = Path(args.out_dir)
    manifest_path = Path(args.manifest)
    if out_dir.exists() or manifest_path.exists():
        raise ValueError("outputs are no-clobber")
    if args.per_pool <= 0 or args.per_pool % 2:
        raise ValueError("--per-pool must be a positive even integer")

    conditional = _load(conditional_path)
    autopsy = _load(autopsy_path)
    if autopsy.get("verdict") != "JASS_CONTEXT2_INTERVENTION_CONTRIBUTION_AUTOPSY_READY":
        raise ValueError("autopsy verdict drift")
    if autopsy.get("dominant_component", {}).get("component") != DOMINANT_COMPONENT:
        raise ValueError("dominant component drift")
    weak = tuple(row["component"] for row in autopsy.get("five_weakest_components", []))
    if weak != TARGET_COMPONENTS:
        raise ValueError(f"weak component order drift: {weak}")
    if autopsy.get("fixed_mapper_quota_lattice", {}).get("quota_only_rescue_predicted"):
        raise ValueError("quota-only rescue unexpectedly open")

    records = _open_counted(data_path, b"JNNW", JNNW_DTYPE)
    metadata, meta_schema = _open_meta(meta_path, len(records))
    features, width = _open_feat(feat_path, len(records))
    if meta_schema != "JSM2" or width != len(CTX2_CONTEXT_COMPONENTS):
        raise ValueError("source schema drift")
    source = conditional.get("source") or {}
    if source.get("data_sha256") != _sha256(data_path):
        raise ValueError("conditional source data hash drift")
    if source.get("meta_sha256") != _sha256(meta_path):
        raise ValueError("conditional source meta hash drift")
    if source.get("feat_sha256") != _sha256(feat_path):
        raise ValueError("conditional source feature hash drift")

    scores, signs, train_count = mapper_contribution_scores(
        metadata=metadata, features=features, report=conditional
    )
    strata, stratum_definition = _strata(records)
    p90, men_median, stratum_counts = _thresholds(scores, strata)

    capacities = np.zeros((2, 60), dtype=np.int64)
    target_capacity = np.zeros((len(TARGET_COMPONENTS), 2, 60), dtype=np.int64)
    eligible_by_bucket: dict[tuple[int, int, int], np.ndarray] = {}
    for component in range(len(TARGET_COMPONENTS)):
        for sign_index, sign in enumerate((-1, 1)):
            for stratum in range(60):
                candidates = _eligible(
                    scores, signs, strata, p90, men_median,
                    component, sign, stratum,
                )
                eligible_by_bucket[(component, sign_index, stratum)] = candidates
                target_capacity[component, sign_index, stratum] = len(candidates)
    capacities[:] = target_capacity.min(axis=0)
    half = args.per_pool // 2
    common_sign_quotas = np.stack(
        [
            allocate_capped_proportional(capacities[index], stratum_counts, half)
            for index in range(2)
        ]
    )
    common_total_quotas = common_sign_quotas.sum(axis=0)

    opening_masks = _opening_pool_masks(eligible_by_bucket, metadata)
    request_order = _global_request_order(
        eligible_by_bucket=eligible_by_bucket,
        common_sign_quotas=common_sign_quotas,
        metadata=metadata,
        opening_masks=opening_masks,
        seed=args.seed,
    )
    opening_request_capacities, initial_request_capacities = _opening_request_capacities(
        request_order, eligible_by_bucket, metadata
    )
    neutral_by_stratum = {
        stratum: np.flatnonzero(strata == stratum) for stratum in range(60)
    }
    allocation_errors: list[str] = []
    selected_by_pool: dict[str, list[int]] | None = None
    opening_owner: dict[int, str] = {}
    game_counts: Counter[int] = Counter()
    canonical_used: set[bytes] = set()
    allocation_attempt = -1
    selected_request_order: list[int] = []

    for allocation_attempt in range(MAX_ALLOCATION_ATTEMPTS):
        opening_owner = {}
        game_counts = Counter()
        canonical_used = set()
        attempt_selection: dict[str, list[int]] = {
            POOL_NAMES[component]: [] for component in TARGET_COMPONENTS
        }
        attempt_salt = allocation_attempt * 1_000_000
        feasible_capacity = initial_request_capacities.copy()
        versions = np.zeros(len(request_order), dtype=np.int64)
        pending = set(range(len(request_order)))
        queue: list[tuple[int, int, int]] = []

        def push_request(request_index: int) -> None:
            required = request_order[request_index][3]
            ratio = int(feasible_capacity[request_index]) * 1_000_000 // required
            heapq.heappush(
                queue, (ratio, request_index, int(versions[request_index]))
            )

        for request_index in pending:
            push_request(request_index)
        attempt_request_order: list[int] = []
        try:
            while pending:
                while True:
                    _ratio, request_index, version = heapq.heappop(queue)
                    if (
                        request_index in pending
                        and version == int(versions[request_index])
                    ):
                        break
                component, sign_index, stratum, required = request_order[request_index]
                name = POOL_NAMES[TARGET_COMPONENTS[component]]
                raw_candidates = eligible_by_bucket[(component, sign_index, stratum)]
                exact_capacity = _current_request_capacity(
                    candidates=raw_candidates,
                    pool=name,
                    metadata=metadata,
                    opening_owner=opening_owner,
                    game_counts=game_counts,
                )
                if exact_capacity != int(feasible_capacity[request_index]):
                    feasible_capacity[request_index] = exact_capacity
                    versions[request_index] += 1
                    push_request(request_index)
                    continue
                if exact_capacity < required:
                    raise AllocationShortfall(
                        f"pool {name} sign_index={sign_index} stratum={stratum}: "
                        f"remaining capacity {exact_capacity} below required {required}"
                    )
                candidates = _rank_global_candidates(
                    raw_candidates,
                    metadata,
                    pool=name,
                    opening_owner=opening_owner,
                    opening_masks=opening_masks,
                    seed=args.seed,
                    salt=(
                        attempt_salt
                        + component * 1000
                        + sign_index * 100
                        + stratum
                    ),
                )
                claimed_openings: set[int] = set()
                try:
                    chosen = _select_bucket(
                        candidates=candidates,
                        required=required,
                        pool=name,
                        records=records,
                        metadata=metadata,
                        opening_owner=opening_owner,
                        game_counts=game_counts,
                        canonical_used=canonical_used,
                        claimed_openings=claimed_openings,
                    )
                except AllocationShortfall as error:
                    raise AllocationShortfall(
                        f"{error}; sign_index={sign_index} stratum={stratum} "
                        f"tracked_capacity={exact_capacity}"
                    ) from error
                attempt_selection[name].extend(chosen)
                pending.remove(request_index)
                attempt_request_order.append(request_index)
                for opening in claimed_openings:
                    for other_index, capacity in opening_request_capacities.get(opening, []):
                        if other_index not in pending:
                            continue
                        other_component = request_order[other_index][0]
                        if other_component == component:
                            continue
                        feasible_capacity[other_index] -= capacity
                        versions[other_index] += 1
                        push_request(other_index)
            for name in POOL_NAMES.values():
                if len(attempt_selection[name]) != args.per_pool:
                    raise ValueError(f"pool {name}: exact quota drift")

            neutral: list[int] = []
            for stratum in range(60):
                required = int(common_total_quotas[stratum])
                if not required:
                    continue
                candidates = _rank_global_candidates(
                    neutral_by_stratum[stratum],
                    metadata,
                    pool="neutral",
                    opening_owner=opening_owner,
                    opening_masks=opening_masks,
                    seed=args.seed,
                    salt=attempt_salt + 900_000 + stratum,
                )
                neutral.extend(
                    _select_bucket(
                        candidates=candidates,
                        required=required,
                        pool="neutral",
                        records=records,
                        metadata=metadata,
                        opening_owner=opening_owner,
                        game_counts=game_counts,
                        canonical_used=canonical_used,
                    )
                )
            if len(neutral) != args.per_pool:
                raise ValueError("neutral exact quota drift")
            attempt_selection["neutral"] = neutral
        except AllocationShortfall as error:
            allocation_errors.append(str(error))
            continue
        selected_by_pool = attempt_selection
        selected_request_order = attempt_request_order
        break

    if selected_by_pool is None:
        last_error = allocation_errors[-1] if allocation_errors else "unknown shortfall"
        raise ValueError(
            f"exact allocation infeasible after {MAX_ALLOCATION_ATTEMPTS} deterministic attempts; "
            f"last={last_error}"
        )

    out_dir.mkdir(parents=True)
    pool_reports: dict[str, Any] = {}
    for name in sorted(selected_by_pool):
        indices = selected_by_pool[name]
        output = out_dir / f"{name}.jnnw"
        digest = _write_pool(output, records, indices)
        source_wdl = Counter(int(records["wdl"][index]) for index in indices)
        selected_strata = Counter(int(strata[index]) for index in indices)
        target_component = next(
            (component for component, pool in POOL_NAMES.items() if pool == name), None
        )
        row: dict[str, Any] = {
            "file": output.name,
            "sha256": digest,
            "records": len(indices),
            "unique_openings": len({int(metadata["opening_id"][i]) for i in indices}),
            "unique_games": len({int(metadata["game_id"][i]) for i in indices}),
            "source_wdl_stm": {str(key): value for key, value in sorted(source_wdl.items())},
            "stratum_counts": {str(key): value for key, value in sorted(selected_strata.items())},
            "source_index_sha256": hashlib.sha256(
                np.asarray(indices, dtype="<u8").tobytes()
            ).hexdigest(),
        }
        if target_component is not None:
            component_index = TARGET_COMPONENTS.index(target_component)
            values = scores[indices, component_index]
            men_values = scores[indices, -1]
            row.update({
                "target_component": target_component,
                "target_sign_counts": {
                    "negative": int(np.sum(signs[indices, component_index] < 0)),
                    "positive": int(np.sum(signs[indices, component_index] > 0)),
                },
                "mean_normalized_target_contribution": float(np.mean(values)),
                "mean_normalized_men_delta_contribution": float(np.mean(men_values)),
            })
        pool_reports[name] = row

    expected_histogram = {str(i): int(value) for i, value in enumerate(common_total_quotas) if value}
    if any(row["stratum_counts"] != expected_histogram for row in pool_reports.values()):
        raise ValueError("pool stratum matching drift")
    openings = [
        {int(metadata["opening_id"][index]) for index in indices}
        for indices in selected_by_pool.values()
    ]
    if any(openings[i] & openings[j] for i in range(len(openings)) for j in range(i)):
        raise ValueError("opening overlap across pools")
    if max(game_counts.values(), default=0) > 2:
        raise ValueError("source-game cap drift")

    payload = {
        "schema": "jass.l3_context2_contribution_seed_miner.v1",
        "verdict": "JASS_CONTEXT2_CONTRIBUTION_SEEDS_READY",
        "seed": int(args.seed),
        "source": {
            "data_sha256": _sha256(data_path),
            "meta_sha256": _sha256(meta_path),
            "features_sha256": _sha256(feat_path),
            "conditional_report_sha256": _sha256(conditional_path),
            "autopsy_sha256": _sha256(autopsy_path),
            "records": len(records),
            "train_records": train_count,
            "selection_scope": "train_and_holdout_with_certified_oof_or_train-only_mapper",
        },
        "target_components": list(TARGET_COMPONENTS),
        "dominant_component_suppressed": DOMINANT_COMPONENT,
        "selection": {
            "target_quantile_within_stratum": 0.90,
            "dominant_component_max_quantile_within_stratum": 0.50,
            "target_sign_quota": {"negative": half, "positive": half},
            "per_pool": int(args.per_pool),
            "opening_ids_disjoint_across_pools": True,
            "maximum_positions_per_source_game": 2,
            "canonical_position_dedup_across_pools": True,
            "score_and_wdl_zeroed": True,
            "allocation_request_count": len(request_order),
            "allocation_request_order_sha256": hashlib.sha256(
                json.dumps(request_order, separators=(",", ":")).encode("ascii")
            ).hexdigest(),
            "allocation_dynamic_order_sha256": hashlib.sha256(
                np.asarray(selected_request_order, dtype="<u2").tobytes()
            ).hexdigest(),
            "allocation_algorithm": "deterministic_dynamic_global_scarcity_multistart_v3",
            "allocation_attempt_zero_based": allocation_attempt,
            "allocation_failed_attempts": len(allocation_errors),
            "allocation_max_attempts": MAX_ALLOCATION_ATTEMPTS,
            "common_sign_stratum_quotas": {
                label: {str(i): int(value) for i, value in enumerate(common_sign_quotas[row]) if value}
                for row, label in enumerate(("negative", "positive"))
            },
        },
        "stratum_definition": stratum_definition,
        "pools": pool_reports,
        "guards": {
            "pool_count": len(pool_reports),
            "exact_records_total": sum(row["records"] for row in pool_reports.values()),
            "all_pool_counts_exact": all(row["records"] == args.per_pool for row in pool_reports.values()),
            "all_stratum_histograms_identical": True,
            "all_target_signs_balanced_50_50": all(
                row.get("target_sign_counts") == {"negative": half, "positive": half}
                for row in pool_reports.values() if "target_component" in row
            ),
            "opening_overlap_count": 0,
            "canonical_duplicate_count": 0,
            "maximum_realized_positions_per_source_game": max(game_counts.values(), default=0),
        },
        "protocol": {
            "mapper_refit": False,
            "patterneval_fit": False,
            "selfplay_generated": False,
            "force_games_played": 0,
            "frozen_read": False,
            "promotion_authorized": False,
            "automatic_next_job": None,
        },
    }
    # Release memmaps explicitly: the production host is Linux, while local
    # Windows contract tests cannot remove an open temporary file.
    del features, metadata, records
    manifest_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", required=True)
    parser.add_argument("--meta", required=True)
    parser.add_argument("--features", required=True)
    parser.add_argument("--conditional-report", required=True)
    parser.add_argument("--autopsy", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--seed", type=int, default=2026081806)
    parser.add_argument("--per-pool", type=int, default=4096)
    args = parser.parse_args(argv)
    payload = mine(args)
    print(json.dumps({
        "verdict": payload["verdict"],
        "pools": sorted(payload["pools"]),
        "records": payload["guards"]["exact_records_total"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
