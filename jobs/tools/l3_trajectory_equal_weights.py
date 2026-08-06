#!/usr/bin/env python3
"""Build fail-closed per-record weights that give every represented game equal mass.

The input pair must be an aligned JNNW/JSM2 corpus after its opening-grouped
train/holdout split.  For every TRAIN game ``g`` with ``m_g`` retained records,
the raw weight of each retained record is ``1 / m_g``.  ``train_stream.py`` then
normalises the TRAIN weights to mean one, preserving the historical total loss
scale and therefore the relative L2/prior scale.

Holdout rows receive the neutral raw weight 1.0.  The trainer never applies
sample weights to holdout rows; keeping them neutral makes that contract visible
and keeps validation bounds simple.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import selfplay_frontier as frontier  # noqa: E402


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _summary(values: list[int]) -> dict[str, object]:
    if not values:
        raise ValueError("cannot summarise an empty collection")
    data = np.asarray(values, dtype=np.float64)
    probabilities = (0.0, 0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99, 1.0)
    quantiles = np.quantile(data, probabilities, method="linear")
    return {
        "count": len(values),
        "sum": int(sum(values)),
        "mean": float(data.mean()),
        "min": int(min(values)),
        "max": int(max(values)),
        "quantiles": {
            f"p{int(probability * 100):02d}": float(value)
            for probability, value in zip(probabilities, quantiles)
        },
    }


def _shares(counts: Counter[int]) -> dict[str, dict[str, float | int]]:
    names = {-1: "white_loss", 0: "draw", 1: "white_win"}
    total = sum(counts.values())
    return {
        names[value]: {
            "count": int(counts[value]),
            "share": counts[value] / total if total else 0.0,
        }
        for value in (-1, 0, 1)
    }


def _publish_outputs(
    row_weights_path: Path,
    row_weights: np.ndarray,
    game_weights_path: Path,
    game_weights: np.ndarray,
    report_path: Path,
    report: dict[str, object],
) -> None:
    targets = (row_weights_path, game_weights_path, report_path)
    if len({target.resolve(strict=False) for target in targets}) != len(targets):
        raise ValueError("row weights, game weights and report outputs must be distinct")
    for target in targets:
        if target.exists():
            raise ValueError(f"refusing to overwrite existing output: {target}")
        target.parent.mkdir(parents=True, exist_ok=True)

    stamp = f"{os.getpid()}-{time.time_ns()}"
    row_tmp = row_weights_path.with_name(f".{row_weights_path.name}.tmp-{stamp}")
    game_tmp = game_weights_path.with_name(f".{game_weights_path.name}.tmp-{stamp}")
    report_tmp = report_path.with_name(f".{report_path.name}.tmp-{stamp}")
    published: list[Path] = []
    try:
        for temporary, values in ((row_tmp, row_weights), (game_tmp, game_weights)):
            with temporary.open("xb") as handle:
                np.save(handle, values, allow_pickle=False)
                handle.flush()
                os.fsync(handle.fileno())
        report["output"] = {
            "row_weights": {
                "path": str(row_weights_path),
                "sha256": _sha256(row_tmp),
                "dtype": str(row_weights.dtype),
                "shape": [int(value) for value in row_weights.shape],
                "raw_value": 1.0,
            },
            "game_weights": {
                "path": str(game_weights_path),
                "sha256": _sha256(game_tmp),
                "dtype": str(game_weights.dtype),
                "shape": [int(value) for value in game_weights.shape],
            },
        }
        serialized = json.dumps(report, indent=2, sort_keys=True) + "\n"
        with report_tmp.open("x", encoding="utf-8") as handle:
            handle.write(serialized)
            handle.flush()
            os.fsync(handle.fileno())

        # Hard-link publication is atomic and no-clobber. Roll back all prior
        # links if a later one fails, so no partial output set remains.
        for temporary, target in (
            (row_tmp, row_weights_path),
            (game_tmp, game_weights_path),
            (report_tmp, report_path),
        ):
            os.link(temporary, target)
            published.append(target)
    except FileExistsError as exc:
        for target in reversed(published):
            target.unlink(missing_ok=True)
        raise ValueError("an output appeared while publishing; nothing was replaced") from exc
    except OSError as exc:
        for target in reversed(published):
            target.unlink(missing_ok=True)
        raise ValueError(f"cannot atomically publish outputs: {exc}") from exc
    finally:
        row_tmp.unlink(missing_ok=True)
        game_tmp.unlink(missing_ok=True)
        report_tmp.unlink(missing_ok=True)


def build_weights(
    data_path: Path,
    meta_path: Path,
    holdout_count: int,
) -> tuple[np.ndarray, dict[str, object]]:
    records = frontier._counted_file_count(
        data_path, frontier.JNNW_MAGIC, frontier.JNNW_REC
    )
    schema, meta_records = frontier._meta_file_info(meta_path)
    if schema is not frontier.JSM2_SCHEMA:
        raise ValueError("TRAJ-EQUAL requires JSM2; JSM1 has no trajectory context")
    if records != meta_records:
        raise ValueError(f"data/meta count mismatch: {records} != {meta_records}")
    if holdout_count < 0 or holdout_count >= records:
        raise ValueError(
            f"holdout_count must be in [0,{records}), got {holdout_count}"
        )
    train_count = records - holdout_count
    initial_stats = {
        data_path: data_path.stat(),
        meta_path: meta_path.stat(),
    }

    game_counts: Counter[int] = Counter()
    game_context: dict[int, tuple[int, int, int, int, int]] = {}
    game_results: dict[int, int] = {}
    game_lengths: dict[int, int] = {}
    opening_games: defaultdict[int, set[int]] = defaultdict(set)
    train_game_ids: set[int] = set()
    holdout_game_ids: set[int] = set()
    train_openings: set[int] = set()
    holdout_openings: set[int] = set()
    row_game_ids = np.empty(records, dtype=np.uint64)

    sign_checked = 0
    with meta_path.open("rb") as meta_handle, data_path.open("rb") as data_handle:
        meta_header = meta_handle.read(8)
        data_header = data_handle.read(8)
        if meta_header[:4] != frontier.JSM2_MAGIC:
            raise ValueError("metadata magic changed after schema validation")
        if data_header[:4] != frontier.JNNW_MAGIC:
            raise ValueError("data magic changed after count validation")
        for index in range(records):
            raw = meta_handle.read(schema.record.size)
            record = data_handle.read(frontier.JNNW_REC)
            if len(raw) != schema.record.size:
                raise ValueError(f"metadata truncated at record {index}")
            if len(record) != frontier.JNNW_REC:
                raise ValueError(f"data truncated at record {index}")
            row = frontier._decode_meta(
                raw, schema, context=f"{meta_path}: record {index}"
            )
            assert row.game_plies is not None and row.last_eps_ply is not None
            assert row.game_result is not None and row.flags is not None
            context = (
                row.opening_id,
                row.seeded,
                row.game_plies,
                row.last_eps_ply,
                row.flags & ~0x04,  # tb_relabelled is a per-record flag.
            )
            previous = game_context.setdefault(row.game_id, context)
            if previous != context:
                raise ValueError(f"inconsistent JSM2 context within game {row.game_id}")
            previous_result = game_results.setdefault(row.game_id, row.game_result)
            if previous_result != row.game_result:
                raise ValueError(f"inconsistent result within game {row.game_id}")
            stm = record[32]
            wdl = int.from_bytes(record[37:38], "little", signed=True)
            if stm not in (0, 1) or wdl not in (-1, 0, 1):
                raise ValueError(
                    f"record {index}: invalid JNNW stm/wdl pair {stm}/{wdl}"
                )
            if not row.flags & 0x04:
                expected_wdl = row.game_result * (1 if stm == 0 else -1)
                if wdl != expected_wdl:
                    raise ValueError(
                        f"record {index}: JNNW/JSM2 POV mismatch, "
                        f"wdl={wdl}, white_result={row.game_result}, stm={stm}"
                    )
                sign_checked += 1
            game_lengths[row.game_id] = row.game_plies
            opening_games[row.opening_id].add(row.game_id)
            row_game_ids[index] = row.game_id
            if index < train_count:
                game_counts[row.game_id] += 1
                train_game_ids.add(row.game_id)
                train_openings.add(row.opening_id)
            else:
                holdout_game_ids.add(row.game_id)
                holdout_openings.add(row.opening_id)
        if meta_handle.read(1) or data_handle.read(1):
            raise ValueError("aligned input contains trailing bytes")

    for path, before in initial_stats.items():
        after = path.stat()
        if before.st_size != after.st_size or before.st_mtime_ns != after.st_mtime_ns:
            raise ValueError(f"input changed while weights were built: {path}")

    crossed_games = train_game_ids & holdout_game_ids
    if crossed_games:
        raise ValueError(
            f"{len(crossed_games)} game_id values cross the train/holdout boundary"
        )
    crossed_openings = train_openings & holdout_openings
    if crossed_openings:
        raise ValueError(
            f"{len(crossed_openings)} opening_id values cross the train/holdout boundary"
        )
    if not game_counts:
        raise ValueError("no represented TRAIN games")

    weights = np.ones(records, dtype=np.float32)
    for index in range(train_count):
        weights[index] = np.float32(1.0 / game_counts[int(row_game_ids[index])])

    raw_train = weights[:train_count].astype(np.float64)
    raw_mean = float(raw_train.mean())
    factor = 1.0 / raw_mean
    normalized = raw_train * factor
    expected_game_mass = train_count / len(game_counts)
    mass_by_game: defaultdict[int, float] = defaultdict(float)
    for index, value in enumerate(normalized):
        mass_by_game[int(row_game_ids[index])] += float(value)
    max_mass_error = max(
        abs(value - expected_game_mass) for value in mass_by_game.values()
    )
    if max_mass_error > max(1e-5, expected_game_mass * 2e-7):
        raise ValueError(
            "float32 weights do not give games equal mass within tolerance: "
            f"max_error={max_mass_error} expected_mass={expected_game_mass}"
        )

    train_records_by_result: Counter[int] = Counter()
    train_games_by_result: Counter[int] = Counter()
    lengths_by_result: defaultdict[int, list[int]] = defaultdict(list)
    for game_id, count in game_counts.items():
        result = game_results[game_id]
        train_records_by_result[result] += count
        train_games_by_result[result] += 1
        lengths_by_result[result].append(game_lengths[game_id])

    counts_sorted = sorted(game_counts.values(), reverse=True)
    longest_ten_percent = max(1, (len(counts_sorted) + 9) // 10)
    opening_hist = Counter(
        len(games & train_game_ids) for games in opening_games.values()
        if games & train_game_ids
    )
    report: dict[str, object] = {
        "schema": 1,
        "operation": "l3_trajectory_equal_weights",
        "definition": {
            "unit": "represented_train_game_id",
            "raw_train_weight": "1 / retained_train_records_in_game",
            "holdout_raw_weight": 1.0,
            "trainer_normalization": "mean-train-1",
            "claim_scope": (
                "equal mass across games represented in the retained corpus; "
                "discarded source records are not reconstructed"
            ),
        },
        "inputs": {
            "data_path": str(data_path),
            "data_sha256": _sha256(data_path),
            "meta_path": str(meta_path),
            "meta_sha256": _sha256(meta_path),
            "sidecar_schema": schema.name,
        },
        "split": {
            "records": records,
            "train_records": train_count,
            "holdout_records": holdout_count,
            "train_games": len(game_counts),
            "holdout_games": len(holdout_game_ids),
            "train_openings": len(train_openings),
            "holdout_openings": len(holdout_openings),
            "games_crossing_boundary": 0,
            "openings_crossing_boundary": 0,
        },
        "alignment": {
            "data_meta_counts_equal": True,
            "records_pov_checked_without_tb_relabel": sign_checked,
            "record_order_shared_by_both_arms": True,
        },
        "row_equal_control": {
            "retained_train_records_per_game": _summary(list(game_counts.values())),
            "longest_10_percent_games_record_share": (
                sum(counts_sorted[:longest_ten_percent]) / train_count
            ),
            "game_result_distribution": _shares(train_games_by_result),
            "record_mass_result_distribution": _shares(train_records_by_result),
            "game_plies_by_result": {
                {-1: "white_loss", 0: "draw", 1: "white_win"}[result]: _summary(values)
                for result, values in sorted(lengths_by_result.items())
            },
            "train_games_per_opening_histogram": {
                str(games): count for games, count in sorted(opening_hist.items())
            },
        },
        "trajectory_equal_treatment": {
            "raw_train_weight_min": float(raw_train.min()),
            "raw_train_weight_max": float(raw_train.max()),
            "raw_train_weight_mean": raw_mean,
            "normalization_factor": factor,
            "normalized_train_weight_min": float(normalized.min()),
            "normalized_train_weight_max": float(normalized.max()),
            "normalized_train_weight_mean": float(normalized.mean()),
            "equal_total_mass_per_game": expected_game_mass,
            "max_abs_game_mass_error": max_mass_error,
        },
    }
    return weights, report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", required=True, type=Path)
    parser.add_argument("--meta", required=True, type=Path)
    parser.add_argument("--holdout-count", required=True, type=int)
    parser.add_argument("--out-row-weights", required=True, type=Path)
    parser.add_argument("--out-game-weights", required=True, type=Path)
    parser.add_argument("--out-report", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        game_weights, report = build_weights(args.data, args.meta, args.holdout_count)
        row_weights = np.ones_like(game_weights, dtype=np.float32)
        _publish_outputs(
            args.out_row_weights,
            row_weights,
            args.out_game_weights,
            game_weights,
            args.out_report,
            report,
        )
    except (OSError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc
    print(
        "TRAJ_EQUAL_WEIGHTS_READY "
        f"records={len(game_weights)} train_games={report['split']['train_games']} "
        f"raw_range=[{game_weights.min():.9g},{game_weights.max():.9g}]"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
