#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Sample complete paired games and measure CTX2 activation coverage.

The sampler selects complete opening groups, never isolated records.  The
analyser reports both the 30 phase-weighted CTX2 channels and the 15 underlying
base signals reconstructed as ``tempo_mid + tempo_end``.  This distinction is
important: a raw bank may be zero because its phase weight is zero even though
the board signal itself is present.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import heapq
import json
import math
import os
from pathlib import Path
import struct
import time
from typing import Any, Iterable

import numpy as np

try:  # Script execution (jobs/tools is sys.path[0]).
    from l3_conditional_targets import (
        CTX2_BASE_COMPONENTS,
        CTX2_CONTEXT_COMPONENTS,
        JNNW_DTYPE,
        _open_counted,
        _open_feat,
        _open_meta,
        tempo_phase_from_records,
    )
except ModuleNotFoundError:  # Package import from repository tests.
    from jobs.tools.l3_conditional_targets import (
        CTX2_BASE_COMPONENTS,
        CTX2_CONTEXT_COMPONENTS,
        JNNW_DTYPE,
        _open_counted,
        _open_feat,
        _open_meta,
        tempo_phase_from_records,
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _splitmix64(value: int) -> int:
    mask = (1 << 64) - 1
    z = (value + 0x9E3779B97F4A7C15) & mask
    z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & mask
    z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & mask
    return (z ^ (z >> 31)) & mask


def _json_no_clobber(path: Path, payload: Any) -> None:
    if path.exists():
        raise ValueError(f"{path}: output exists (no-clobber)")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}-{time.time_ns()}")
    try:
        temporary.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        os.link(temporary, path)
    except FileExistsError as exc:
        raise ValueError(f"{path}: output exists (no-clobber)") from exc
    finally:
        temporary.unlink(missing_ok=True)


def _iter_game_segments(
    metadata: np.ndarray, *, chunk_size: int = 1_000_000
) -> Iterable[tuple[int, int, int, int]]:
    """Yield contiguous ``(game_id, opening_id, start, stop)`` segments."""
    count = len(metadata)
    if count == 0:
        return
    segment_start = 0
    current_game = int(metadata["game_id"][0])
    current_opening = int(metadata["opening_id"][0])
    previous_game = current_game
    previous_opening = current_opening
    for chunk_start in range(0, count, chunk_size):
        chunk_stop = min(chunk_start + chunk_size, count)
        games = np.asarray(metadata["game_id"][chunk_start:chunk_stop])
        openings = np.asarray(metadata["opening_id"][chunk_start:chunk_stop])
        if chunk_start:
            if int(games[0]) == previous_game and int(openings[0]) != previous_opening:
                raise ValueError("opening_id changed inside a game at chunk boundary")
            boundaries = [] if int(games[0]) == previous_game else [chunk_start]
        else:
            boundaries = []
        if len(games) > 1:
            same_game = games[1:] == games[:-1]
            if np.any(same_game & (openings[1:] != openings[:-1])):
                raise ValueError("opening_id changed inside a game")
            boundaries.extend(
                int(chunk_start + value)
                for value in (np.flatnonzero(~same_game) + 1)
            )
        for boundary in boundaries:
            yield current_game, current_opening, segment_start, boundary
            segment_start = boundary
            current_game = int(metadata["game_id"][boundary])
            current_opening = int(metadata["opening_id"][boundary])
        previous_game = int(games[-1])
        previous_opening = int(openings[-1])
    yield current_game, current_opening, segment_start, count


def _selected_opening_groups(
    metadata: np.ndarray,
    *,
    opening_count: int,
    seed: int,
    games_per_opening: int,
) -> tuple[list[tuple[int, tuple[tuple[int, int, int], ...]]], dict[str, int]]:
    """Keep the lowest deterministic hashes using O(opening_count) memory."""
    heap: list[tuple[int, int, int, tuple[tuple[int, int, int], ...]]] = []
    seen_games: set[int] = set()
    seen_openings: set[int] = set()
    source_games = 0
    source_openings = 0
    eligible_openings = 0
    incomplete_openings = 0
    source_records = 0
    active_opening: int | None = None
    active_games: list[tuple[int, int, int]] = []

    def finish_group(opening_id: int, games: list[tuple[int, int, int]]) -> None:
        nonlocal source_openings, eligible_openings, incomplete_openings
        if opening_id in seen_openings:
            raise ValueError(f"opening {opening_id} is not contiguous")
        seen_openings.add(opening_id)
        source_openings += 1
        if len(games) != games_per_opening:
            # A fixed-record self-play producer can hit its target after the
            # first colour of its final pair.  Such an edge group is valid in
            # the source but ineligible for this paired census.
            incomplete_openings += 1
            return
        if len({row[0] for row in games}) != games_per_opening:
            raise ValueError(f"opening {opening_id} repeats a game id")
        eligible_openings += 1
        group = tuple(games)
        rank_hash = _splitmix64(opening_id ^ seed)
        item = (-rank_hash, -opening_id, source_openings, group)
        if len(heap) < opening_count:
            heapq.heappush(heap, item)
        else:
            worst_hash, worst_opening = -heap[0][0], -heap[0][1]
            if (rank_hash, opening_id) < (worst_hash, worst_opening):
                heapq.heapreplace(heap, item)

    for game_id, opening_id, start, stop in _iter_game_segments(metadata):
        if game_id in seen_games:
            raise ValueError(f"game {game_id} is not contiguous")
        seen_games.add(game_id)
        source_games += 1
        source_records += stop - start
        if active_opening is None:
            active_opening = opening_id
        elif opening_id != active_opening:
            finish_group(active_opening, active_games)
            active_opening = opening_id
            active_games = []
        active_games.append((game_id, start, stop))
    if active_opening is not None:
        finish_group(active_opening, active_games)
    if eligible_openings < opening_count:
        raise ValueError(
            f"source has {eligible_openings} complete opening groups, need {opening_count}"
        )
    selected = [(-item[1], item[3]) for item in heap]
    selected.sort(key=lambda row: row[1][0][1])
    return selected, {
        "records": source_records,
        "games": source_games,
        "openings": source_openings,
        "eligible_complete_openings": eligible_openings,
        "excluded_incomplete_openings": incomplete_openings,
    }


def _coalesce_intervals(
    groups: list[tuple[int, tuple[tuple[int, int, int], ...]]]
) -> list[tuple[int, int]]:
    intervals = sorted((start, stop) for _, games in groups for _, start, stop in games)
    merged: list[tuple[int, int]] = []
    for start, stop in intervals:
        if merged and merged[-1][1] == start:
            merged[-1] = (merged[-1][0], stop)
        else:
            merged.append((start, stop))
    return merged


def _copy_counted_intervals(
    source: Path,
    destination: Path,
    *,
    magic: bytes,
    record_size: int,
    intervals: list[tuple[int, int]],
    total_rows: int,
) -> None:
    if destination.exists():
        raise ValueError(f"{destination}: output exists (no-clobber)")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(
        f".{destination.name}.tmp-{os.getpid()}-{time.time_ns()}"
    )
    with source.open("rb") as src, temporary.open("xb") as dst:
        dst.write(magic + struct.pack("<I", total_rows))
        for start, stop in intervals:
            src.seek(8 + start * record_size)
            remaining = (stop - start) * record_size
            while remaining:
                block = src.read(min(remaining, 8 << 20))
                if not block:
                    raise ValueError(f"{source}: truncated while copying interval")
                dst.write(block)
                remaining -= len(block)
        dst.flush()
        os.fsync(dst.fileno())
    try:
        os.link(temporary, destination)
    except FileExistsError as exc:
        raise ValueError(f"{destination}: output exists (no-clobber)") from exc
    finally:
        temporary.unlink(missing_ok=True)


def sample_complete_games(args: argparse.Namespace) -> dict[str, Any]:
    data_path = Path(args.data)
    meta_path = Path(args.meta)
    out_data = Path(args.out_data)
    out_meta = Path(args.out_meta)
    manifest_path = Path(args.manifest)
    paths = [data_path, meta_path, out_data, out_meta, manifest_path]
    if len({path.resolve(strict=False) for path in paths}) != len(paths):
        raise ValueError("all sample inputs and outputs must be distinct")
    if args.games <= 0 or args.games % args.games_per_opening:
        raise ValueError("--games must be positive and divisible by --games-per-opening")
    records = _open_counted(data_path, b"JNNW", JNNW_DTYPE)
    metadata, meta_schema = _open_meta(meta_path, len(records))
    opening_count = args.games // args.games_per_opening
    groups, source = _selected_opening_groups(
        metadata,
        opening_count=opening_count,
        seed=args.seed,
        games_per_opening=args.games_per_opening,
    )
    intervals = _coalesce_intervals(groups)
    selected_rows = sum(stop - start for start, stop in intervals)
    selected_games = sum(len(games) for _, games in groups)
    if selected_games != args.games or len(groups) != opening_count:
        raise RuntimeError("sampler cardinality drift")
    meta_magic = meta_schema.encode("ascii")
    meta_record_size = int(metadata.dtype.itemsize)
    _copy_counted_intervals(
        data_path,
        out_data,
        magic=b"JNNW",
        record_size=JNNW_DTYPE.itemsize,
        intervals=intervals,
        total_rows=selected_rows,
    )
    _copy_counted_intervals(
        meta_path,
        out_meta,
        magic=meta_magic,
        record_size=meta_record_size,
        intervals=intervals,
        total_rows=selected_rows,
    )
    check_records = _open_counted(out_data, b"JNNW", JNNW_DTYPE)
    check_meta, check_schema = _open_meta(out_meta, len(check_records))
    check_games = sum(1 for _ in _iter_game_segments(check_meta))
    check_openings = len(set(int(value) for value in np.unique(check_meta["opening_id"])))
    if (
        check_schema != meta_schema
        or check_games != args.games
        or check_openings != opening_count
    ):
        raise RuntimeError("sample round-trip identity/cardinality check failed")
    payload = {
        "schema": "jass.l3_context2_complete_game_sample.v1",
        "selection": "lowest_splitmix64_opening_hash_complete_groups",
        "selection_seed": args.seed,
        "games_per_opening": args.games_per_opening,
        "source": {
            "data": str(data_path),
            "meta": str(meta_path),
            "meta_schema": meta_schema,
            **source,
        },
        "sample": {
            "records": selected_rows,
            "games": selected_games,
            "openings": len(groups),
            "intervals": len(intervals),
            "complete_games": True,
            "complete_opening_groups": True,
            "data_sha256": _sha256(out_data),
            "meta_sha256": _sha256(out_meta),
        },
    }
    _json_no_clobber(manifest_path, payload)
    return payload


def _metric(
    values: np.ndarray,
    game_starts: np.ndarray,
    *,
    material_threshold: float,
) -> dict[str, Any]:
    finite = np.isfinite(values)
    if not bool(np.all(finite)):
        raise ValueError("CTX2 contains non-finite values")
    absolute = np.abs(values)
    exact = absolute > 0.0
    material = absolute > material_threshold
    active_values = absolute[exact]
    material_values = absolute[material]
    game_exact = np.logical_or.reduceat(exact, game_starts)
    game_material = np.logical_or.reduceat(material, game_starts)

    def quantiles(array: np.ndarray) -> dict[str, float | None]:
        if not len(array):
            return {"p50": None, "p90": None, "p99": None}
        values_q = np.quantile(array, [0.5, 0.9, 0.99])
        return {"p50": float(values_q[0]), "p90": float(values_q[1]), "p99": float(values_q[2])}

    count = len(values)
    games = len(game_starts)
    return {
        "position_count": count,
        "active_positions_exact": int(exact.sum()),
        "active_position_rate_exact": float(exact.mean()),
        "active_positions_material": int(material.sum()),
        "active_position_rate_material": float(material.mean()),
        "positive_position_rate": float(np.mean(values > material_threshold)),
        "negative_position_rate": float(np.mean(values < -material_threshold)),
        "active_games_exact": int(game_exact.sum()),
        "active_game_rate_exact": float(game_exact.sum() / games),
        "active_games_material": int(game_material.sum()),
        "active_game_rate_material": float(game_material.sum() / games),
        "mean": float(np.mean(values)),
        "mean_absolute": float(np.mean(absolute)),
        "rms": float(math.sqrt(float(np.mean(values * values)))),
        "minimum": float(np.min(values)),
        "maximum": float(np.max(values)),
        "active_absolute_quantiles_exact": quantiles(active_values),
        "active_absolute_quantiles_material": quantiles(material_values),
    }


def _matrix_diagnostics(matrix: np.ndarray) -> dict[str, Any]:
    if matrix.shape[0] < 2:
        raise ValueError("diagnostic matrix needs at least two rows")
    covariance = np.cov(matrix, rowvar=False)
    covariance = np.atleast_2d(covariance)
    eigenvalues = np.maximum(np.linalg.eigvalsh(covariance), 0.0)
    largest = float(eigenvalues[-1]) if len(eigenvalues) else 0.0
    threshold = max(largest * 1e-10, 1e-14)
    positive = eigenvalues[eigenvalues > threshold]
    correlation = np.corrcoef(matrix, rowvar=False)
    correlation = np.nan_to_num(correlation, nan=0.0, posinf=0.0, neginf=0.0)
    return {
        "rows": int(matrix.shape[0]),
        "dimension": int(matrix.shape[1]),
        "effective_rank": int(len(positive)),
        "covariance_condition_number": (
            float(positive[-1] / positive[0]) if len(positive) else None
        ),
        "correlation": correlation.tolist(),
    }


def _game_boundaries(metadata: np.ndarray) -> tuple[np.ndarray, np.ndarray, int]:
    starts: list[int] = []
    stops: list[int] = []
    openings: set[int] = set()
    for _, opening_id, start, stop in _iter_game_segments(metadata):
        starts.append(start)
        stops.append(stop)
        openings.add(opening_id)
    starts_array = np.asarray(starts, dtype=np.int64)
    stops_array = np.asarray(stops, dtype=np.int64)
    if (
        not len(starts_array)
        or starts_array[0] != 0
        or stops_array[-1] != len(metadata)
        or np.any(stops_array[:-1] != starts_array[1:])
    ):
        raise ValueError("game segmentation does not cover the sample exactly")
    return starts_array, stops_array, len(openings)


def analyze(args: argparse.Namespace) -> dict[str, Any]:
    data_path = Path(args.data)
    meta_path = Path(args.meta)
    feat_path = Path(args.feat)
    report_path = Path(args.report)
    csv_path = Path(args.csv)
    markdown_path = Path(args.markdown)
    records = _open_counted(data_path, b"JNNW", JNNW_DTYPE)
    metadata, meta_schema = _open_meta(meta_path, len(records))
    features, width = _open_feat(feat_path, len(records))
    if width != len(CTX2_CONTEXT_COMPONENTS):
        raise ValueError(f"CTX2 width {width} != {len(CTX2_CONTEXT_COMPONENTS)}")
    game_starts, _, opening_count = _game_boundaries(metadata)
    game_count = len(game_starts)
    if args.expected_games is not None and game_count != args.expected_games:
        raise ValueError(f"sample has {game_count} games, expected {args.expected_games}")
    if args.expected_openings is not None and opening_count != args.expected_openings:
        raise ValueError(
            f"sample has {opening_count} openings, expected {args.expected_openings}"
        )

    wmg = np.asarray(tempo_phase_from_records(records), dtype=np.float64)
    weg = 1.0 - wmg
    raw_metrics: dict[str, dict[str, Any]] = {}
    base_metrics: dict[str, dict[str, Any]] = {}
    phase_recomposition_max_error = 0.0
    for index, name in enumerate(CTX2_CONTEXT_COMPONENTS):
        raw_metrics[name] = _metric(
            np.asarray(features[:, index], dtype=np.float64),
            game_starts,
            material_threshold=args.material_threshold,
        )
    for index, name in enumerate(CTX2_BASE_COMPONENTS):
        mid = np.asarray(features[:, index], dtype=np.float64)
        end = np.asarray(features[:, index + len(CTX2_BASE_COMPONENTS)], dtype=np.float64)
        base = mid + end
        base_metrics[name] = _metric(
            base,
            game_starts,
            material_threshold=args.material_threshold,
        )
        phase_recomposition_max_error = max(
            phase_recomposition_max_error,
            float(np.max(np.abs(mid - wmg * base))),
            float(np.max(np.abs(end - weg * base))),
        )

    sample_rows = np.linspace(
        0, len(records) - 1, min(args.rank_rows, len(records)), dtype=np.int64
    )
    raw_sample = np.asarray(features[sample_rows], dtype=np.float64)
    base_sample = raw_sample[:, : len(CTX2_BASE_COMPONENTS)] + raw_sample[:, len(CTX2_BASE_COMPONENTS) :]
    phase_edges = np.asarray([0.0, 0.2, 0.4, 0.6, 0.8, 1.0000001])
    phase_bins = np.clip(np.digitize(wmg, phase_edges, right=False) - 1, 0, 4)
    strata: list[dict[str, Any]] = []
    for phase_bin in range(5):
        mask = phase_bins == phase_bin
        strata.append(
            {
                "label": f"wmg_[{phase_edges[phase_bin]:.1f},{min(1.0, phase_edges[phase_bin + 1]):.1f}]",
                "positions": int(mask.sum()),
                "position_rate": float(mask.mean()),
                "base_active_position_rates_material": {
                    name: float(
                        np.mean(
                            np.abs(
                                np.asarray(features[mask, index], dtype=np.float64)
                                + np.asarray(
                                    features[mask, index + len(CTX2_BASE_COMPONENTS)],
                                    dtype=np.float64,
                                )
                            )
                            > args.material_threshold
                        )
                    )
                    if np.any(mask)
                    else None
                    for index, name in enumerate(CTX2_BASE_COMPONENTS)
                },
            }
        )

    all_raw_active = all(
        row["active_positions_material"] > 0 for row in raw_metrics.values()
    )
    all_base_active = all(
        row["active_positions_material"] > 0 for row in base_metrics.values()
    )
    rare_raw = [
        name
        for name, row in raw_metrics.items()
        if row["active_position_rate_material"] < args.rare_threshold
    ]
    rare_base = [
        name
        for name, row in base_metrics.items()
        if row["active_position_rate_material"] < args.rare_threshold
    ]
    wdl_counts = {
        str(value): int(np.sum(records["wdl"] == value)) for value in (-1, 0, 1)
    }
    if sum(wdl_counts.values()) != len(records):
        raise ValueError("JNNW WDL outside {-1,0,1}")
    payload = {
        "schema": "jass.l3_context2_activation_census.v1",
        "inputs": {
            "data": str(data_path),
            "meta": str(meta_path),
            "feat": str(feat_path),
            "meta_schema": meta_schema,
        },
        "population": {
            "positions": len(records),
            "games": game_count,
            "openings": opening_count,
            "complete_game_sampling": True,
            "wdl_stm_counts": wdl_counts,
            "wdl_stm_rates": {
                key: value / len(records) for key, value in wdl_counts.items()
            },
        },
        "thresholds": {
            "exact": 0.0,
            "material": args.material_threshold,
            "rare_position_rate": args.rare_threshold,
        },
        "phase": {
            "tempo_mid_weight_mean": float(np.mean(wmg)),
            "tempo_mid_weight_nonzero_rate": float(np.mean(wmg > args.material_threshold)),
            "tempo_end_weight_mean": float(np.mean(weg)),
            "tempo_end_weight_nonzero_rate": float(np.mean(weg > args.material_threshold)),
            "recomposition_max_absolute_error": phase_recomposition_max_error,
            "strata": strata,
        },
        "raw_30_channels": raw_metrics,
        "base_15_signals": base_metrics,
        "diagnostics": {
            "all_30_channels_materially_active": all_raw_active,
            "all_15_base_signals_materially_active": all_base_active,
            "rare_raw_channels": rare_raw,
            "rare_base_signals": rare_base,
            "raw_matrix": _matrix_diagnostics(raw_sample),
            "base_matrix": _matrix_diagnostics(base_sample),
        },
        "verdict": (
            "JASS_CONTEXT2_ALL_CHANNELS_OBSERVED"
            if all_raw_active and all_base_active
            else "JASS_CONTEXT2_COVERAGE_GAPS_OBSERVED"
        ),
    }
    _json_no_clobber(report_path, payload)
    if csv_path.exists() or markdown_path.exists():
        raise ValueError("CSV/Markdown outputs are no-clobber")
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "kind",
        "component",
        "active_position_rate_exact",
        "active_position_rate_material",
        "active_game_rate_exact",
        "active_game_rate_material",
        "positive_position_rate",
        "negative_position_rate",
        "mean_absolute",
        "rms",
    ]
    with csv_path.open("x", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for kind, rows in (("raw_channel", raw_metrics), ("base_signal", base_metrics)):
            for component, row in rows.items():
                writer.writerow({key: row.get(key) for key in fieldnames} | {"kind": kind, "component": component})
    ordered = sorted(
        ((name, row) for name, row in base_metrics.items()),
        key=lambda item: item[1]["active_position_rate_material"],
    )
    lines = [
        "# CTX2 activation census",
        "",
        f"Verdict: `{payload['verdict']}`",
        "",
        f"Population: {len(records):,} positions, {game_count:,} complete games, {opening_count:,} paired openings.",
        "",
        "| Base signal | Active positions | Active games | RMS |",
        "|---|---:|---:|---:|",
    ]
    for name, row in ordered:
        lines.append(
            f"| {name} | {100*row['active_position_rate_material']:.3f}% | "
            f"{100*row['active_game_rate_material']:.3f}% | {row['rms']:.6g} |"
        )
    lines.extend(
        [
            "",
            f"Rare base signals (< {100*args.rare_threshold:.3f}% positions): "
            + (", ".join(rare_base) if rare_base else "none"),
            "",
        ]
    )
    markdown_path.write_text("\n".join(lines), encoding="utf-8")
    return payload


def compare(args: argparse.Namespace) -> dict[str, Any]:
    reports: dict[str, dict[str, Any]] = {}
    for item in args.cell:
        if "=" not in item:
            raise ValueError("--cell must use NAME=report.json")
        name, path = item.split("=", 1)
        if not name or name in reports:
            raise ValueError(f"invalid or duplicate cell {name!r}")
        reports[name] = json.loads(Path(path).read_text(encoding="utf-8"))
    if args.baseline not in reports or args.replicate not in reports:
        raise ValueError("baseline and replicate cells are required")
    base = reports[args.baseline]["base_15_signals"]
    replicate = reports[args.replicate]["base_15_signals"]
    rows: list[dict[str, Any]] = []
    for cell, report in reports.items():
        if cell in (args.baseline, args.replicate):
            continue
        for component in CTX2_BASE_COMPONENTS:
            base_rate = base[component]["active_position_rate_material"]
            candidate = report["base_15_signals"][component]
            rate = candidate["active_position_rate_material"]
            seed_noise = abs(
                replicate[component]["active_position_rate_material"] - base_rate
            )
            delta = rate - base_rate
            rows.append(
                {
                    "cell": cell,
                    "component": component,
                    "activation_delta_percentage_points": 100.0 * delta,
                    "baseline_replicate_noise_percentage_points": 100.0 * seed_noise,
                    "mean_absolute_delta": (
                        candidate["mean_absolute"] - base[component]["mean_absolute"]
                    ),
                    "rms_delta": candidate["rms"] - base[component]["rms"],
                    "absolute_effect_over_seed_noise": (
                        abs(delta) / seed_noise if seed_noise > 0 else None
                    ),
                    "direction": "increase" if delta > 0 else ("decrease" if delta < 0 else "none"),
                }
            )
    payload = {
        "schema": "jass.l3_context2_knob_attribution.v1",
        "baseline": args.baseline,
        "baseline_replicate": args.replicate,
        "effects": rows,
        "interpretation": "diagnostic paired-seed pilot; force and target quality are not inferred",
    }
    _json_no_clobber(Path(args.report), payload)
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    sample = subparsers.add_parser("sample", help="sample complete opening groups")
    sample.add_argument("--data", required=True)
    sample.add_argument("--meta", required=True)
    sample.add_argument("--out-data", required=True)
    sample.add_argument("--out-meta", required=True)
    sample.add_argument("--manifest", required=True)
    sample.add_argument("--games", type=int, required=True)
    sample.add_argument("--games-per-opening", type=int, default=2)
    sample.add_argument("--seed", type=int, required=True)
    analyse = subparsers.add_parser("analyze", help="measure CTX2 activation")
    analyse.add_argument("--data", required=True)
    analyse.add_argument("--meta", required=True)
    analyse.add_argument("--feat", required=True)
    analyse.add_argument("--report", required=True)
    analyse.add_argument("--csv", required=True)
    analyse.add_argument("--markdown", required=True)
    analyse.add_argument("--expected-games", type=int)
    analyse.add_argument("--expected-openings", type=int)
    analyse.add_argument("--material-threshold", type=float, default=1e-6)
    analyse.add_argument("--rare-threshold", type=float, default=1e-3)
    analyse.add_argument("--rank-rows", type=int, default=250_000)
    compare_parser = subparsers.add_parser("compare", help="compare matched knob cells")
    compare_parser.add_argument("--cell", action="append", required=True)
    compare_parser.add_argument("--baseline", default="BASE")
    compare_parser.add_argument("--replicate", default="BASEBIS")
    compare_parser.add_argument("--report", required=True)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.command == "sample":
        payload = sample_complete_games(args)
    elif args.command == "analyze":
        payload = analyze(args)
    else:
        payload = compare(args)
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
