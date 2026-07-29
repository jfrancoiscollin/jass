#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Build an authenticated MATCHED_RANDOM control for HARD reverse seeds.

The historical holdout is never eligible.  The treatment catalogue is the
zero-target HARD seed output of ``selfplay_frontier.py mine-hard``.  Control
roots are selected without looking at WDL, from the same authenticated train
source, and matched on the preregistered coarse state strata.
"""

from __future__ import annotations

import argparse
import hashlib
import heapq
import json
import re
import struct
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import selfplay_frontier as frontier


@dataclass(frozen=True)
class RankedCandidate:
    game_priority: int
    priority: int
    source_index: int
    record: bytes
    meta: frontier.Meta


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json(path: Path) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{path}: unreadable JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: expected a JSON object")
    return payload


def _read_seed_records(path: Path) -> list[bytes]:
    count, body = frontier._read_counted(
        path, frontier.JNNW_MAGIC, frontier.JNNW_REC
    )
    return [
        body[index * frontier.JNNW_REC:(index + 1) * frontier.JNNW_REC]
        for index in range(count)
    ]


def _stratum(record: bytes, source_temporal_id: str) -> tuple[str, str, str, str]:
    _, margin, pieces = frontier._material(record)
    return (
        source_temporal_id,
        frontier._phase_band(pieces),
        frontier._piece_band(pieces),
        frontier._material_stratum(margin),
    )


def _stratum_name(value: tuple[str, str, str, str]) -> str:
    source, phase, pieces, material = value
    return (
        f"source={source}|phase={phase}|piece_band={pieces}|"
        f"material={material}"
    )


def _candidate_priority(
    record: bytes,
    row: frontier.Meta,
    matching_seed: int,
    source_temporal_id: str,
) -> int:
    payload = (
        record[:33]
        + struct.pack("<QQQ", row.game_id, row.opening_id, matching_seed)
        + source_temporal_id.encode("utf-8")
    )
    return int.from_bytes(
        hashlib.blake2b(payload, digest_size=16).digest(), "big"
    )


def _game_priority(
    game_id: int,
    stratum: tuple[str, str, str, str],
    matching_seed: int,
) -> int:
    payload = (
        struct.pack("<QQ", game_id, matching_seed)
        + b"\0".join(part.encode("utf-8") for part in stratum)
    )
    return int.from_bytes(
        hashlib.blake2b(payload, digest_size=16).digest(), "big"
    )


def _verify_hard_manifest(
    manifest: dict,
    *,
    manifest_path: Path,
    history_data: Path,
    history_meta: Path,
    history_split: Path,
    hard_replay: Path,
    hard_meta: Path,
    hard_seeds: Path,
    expected_hard_code_sha: str,
    records: int,
) -> None:
    outputs = manifest.get("outputs", {})
    expected = {
        "hard_replay": (hard_replay, records),
        "hard_replay_meta": (hard_meta, records),
        "hard_seeds": (hard_seeds, records),
    }
    if (
        manifest.get("schema") != 1
        or manifest.get("operation") != "mine-hard"
        or manifest.get("signal") != "failed_conversion"
        or manifest.get("selection_scope") != "train_only"
        or manifest.get("holdout_records_examined_for_signal") != 0
        or manifest.get("external_teacher_inputs") != 0
        or manifest.get("one_per_game") is not True
        or manifest.get("colour_mirror") is not True
        or manifest.get("code_sha") != expected_hard_code_sha
        or manifest.get("selection", {}).get("output_records") != records
        or manifest.get("input", {}).get("data_sha256") != _sha256(history_data)
        or manifest.get("input", {}).get("meta_sha256") != _sha256(history_meta)
        or manifest.get("input", {}).get("split_manifest_sha256")
        != _sha256(history_split)
    ):
        raise ValueError(f"{manifest_path}: hard-mining certificate mismatch")
    for name, (path, expected_records) in expected.items():
        output = outputs.get(name, {})
        if (
            output.get("sha256") != _sha256(path)
            or output.get("records") != expected_records
        ):
            raise ValueError(
                f"{manifest_path}: hard-mining output mismatch for {name}"
            )


def _validate_treatment(
    replay: list[bytes],
    rows: list[frontier.Meta],
    seeds: list[bytes],
    source_temporal_id: str,
) -> tuple[
    list[tuple[str, str, str, str]],
    set[int],
    set[bytes],
]:
    if len(replay) != len(rows) or len(replay) != len(seeds):
        raise ValueError("hard replay/meta/seed counts differ")
    if not replay or len(replay) % 2:
        raise ValueError("hard treatment must contain non-empty colour pairs")

    base_strata: list[tuple[str, str, str, str]] = []
    games: set[int] = set()
    canonical_positions: set[bytes] = set()
    for index in range(0, len(replay), 2):
        original = replay[index]
        mirrored = replay[index + 1]
        original_seed = seeds[index]
        mirrored_seed = seeds[index + 1]
        if mirrored != frontier._mirror_record_preserve_targets(original):
            raise ValueError(f"hard replay pair {index // 2} is not a colour mirror")
        if rows[index + 1] != rows[index]:
            raise ValueError(f"hard meta pair {index // 2} is not aligned")
        if original_seed != frontier._zero_targets(original):
            raise ValueError(f"hard seed {index} differs from zero-target replay")
        if mirrored_seed != frontier.mirror_record(original_seed):
            raise ValueError(f"hard seed pair {index // 2} is not a colour mirror")
        if original_seed[33:] != b"\0" * 5 or mirrored_seed[33:] != b"\0" * 5:
            raise ValueError("hard treatment seed targets must be zero")
        base_strata.append(_stratum(original_seed, source_temporal_id))
        games.add(rows[index].game_id)
        canonical_positions.add(frontier._canonical_position(original_seed))
    if len(games) != len(base_strata):
        raise ValueError("hard treatment is not one-per-game")
    if len(canonical_positions) != len(base_strata):
        raise ValueError("hard treatment is not canonically deduplicated")
    return base_strata, games, canonical_positions


def _push_candidate(
    heap: list[tuple[int, int]],
    by_game: dict[int, RankedCandidate],
    candidate: RankedCandidate,
    capacity: int,
) -> None:
    game_id = candidate.meta.game_id
    previous = by_game.get(game_id)
    if previous is not None:
        if (candidate.priority, candidate.source_index) < (
            previous.priority,
            previous.source_index,
        ):
            by_game[game_id] = candidate
        return

    item = (-candidate.game_priority, -game_id)
    if len(heap) < capacity:
        heapq.heappush(heap, item)
        by_game[game_id] = candidate
        return
    largest_priority = -heap[0][0]
    largest_game_id = -heap[0][1]
    if (candidate.game_priority, game_id) < (
        largest_priority,
        largest_game_id,
    ):
        heapq.heapreplace(heap, item)
        del by_game[largest_game_id]
        by_game[game_id] = candidate


def build_matched_catalogues(args: argparse.Namespace) -> dict:
    if not re.fullmatch(r"[0-9a-f]{40}", args.code_sha):
        raise ValueError("--code-sha must be a full lowercase 40-hex SHA")
    if not re.fullmatch(r"[0-9a-f]{40}", args.expected_hard_code_sha):
        raise ValueError(
            "--expected-hard-code-sha must be a full lowercase 40-hex SHA"
        )
    if not re.fullmatch(r"[A-Za-z0-9._:/-]+", args.source_temporal_id):
        raise ValueError("--source-temporal-id contains unsupported characters")
    if args.matching_seed < 0:
        raise ValueError("--matching-seed must be non-negative")

    paths = {
        "history_data": Path(args.history_data),
        "history_meta": Path(args.history_meta),
        "history_split": Path(args.history_split_manifest),
        "hard_replay": Path(args.hard_replay),
        "hard_meta": Path(args.hard_meta),
        "hard_seeds": Path(args.hard_seeds),
        "hard_manifest": Path(args.hard_manifest),
        "control": Path(args.out_control_seeds),
        "treatment": Path(args.out_treatment_seeds),
        "manifest": Path(args.manifest),
    }
    resolved = [path.resolve() for path in paths.values()]
    if len(set(resolved)) != len(resolved):
        raise ValueError("all input and output paths must be distinct")
    for name in ("control", "treatment", "manifest"):
        if paths[name].exists():
            raise ValueError(f"refusing to overwrite existing output: {paths[name]}")

    history_count = frontier._counted_file_count(
        paths["history_data"], frontier.JNNW_MAGIC, frontier.JNNW_REC
    )
    if (
        frontier._counted_file_count(
            paths["history_meta"], frontier.META_MAGIC, frontier.META_REC
        )
        != history_count
    ):
        raise ValueError("history data/meta count mismatch")
    split, train_count = frontier._load_split_manifest(
        paths["history_split"], history_count
    )
    train_openings, holdout_openings = frontier._split_opening_sets(
        paths["history_split"], paths["history_meta"], history_count, train_count
    )
    if (
        split.get("train_openings") != len(train_openings)
        or split.get("holdout_openings") != len(holdout_openings)
    ):
        raise ValueError("history split opening counts do not match inputs")
    if train_count <= 0 or train_count >= history_count:
        raise ValueError("history train and holdout must both be non-empty")

    hard_replay, hard_rows = frontier.read_pair(
        paths["hard_replay"], paths["hard_meta"]
    )
    hard_seeds = _read_seed_records(paths["hard_seeds"])
    hard_manifest = _read_json(paths["hard_manifest"])
    _verify_hard_manifest(
        hard_manifest,
        manifest_path=paths["hard_manifest"],
        history_data=paths["history_data"],
        history_meta=paths["history_meta"],
        history_split=paths["history_split"],
        hard_replay=paths["hard_replay"],
        hard_meta=paths["hard_meta"],
        hard_seeds=paths["hard_seeds"],
        expected_hard_code_sha=args.expected_hard_code_sha,
        records=len(hard_seeds),
    )
    treatment_strata, treatment_games, treatment_positions = _validate_treatment(
        hard_replay, hard_rows, hard_seeds, args.source_temporal_id
    )
    quotas = Counter(treatment_strata)
    capacities = {
        stratum: quota + max(16, (quota + 3) // 4)
        for stratum, quota in quotas.items()
    }
    heaps: dict[tuple[str, str, str, str], list[tuple[int, int]]] = defaultdict(
        list
    )
    candidates_by_game: dict[
        tuple[str, str, str, str], dict[int, RankedCandidate]
    ] = defaultdict(dict)
    eligible_records_by_stratum: Counter = Counter()
    source_seeded_records = 0

    for index, record, row in frontier.iter_pair(
        paths["history_data"], paths["history_meta"]
    ):
        if index >= train_count:
            break
        if row.seeded not in (0, 1):
            raise ValueError(f"history meta record {index}: invalid seeded flag")
        if row.seeded:
            source_seeded_records += 1
            continue
        stratum = _stratum(record, args.source_temporal_id)
        if stratum not in quotas:
            continue
        canonical = frontier._canonical_position(record)
        if row.game_id in treatment_games or canonical in treatment_positions:
            continue
        eligible_records_by_stratum[stratum] += 1
        candidate = RankedCandidate(
            _game_priority(row.game_id, stratum, args.matching_seed),
            _candidate_priority(
                record, row, args.matching_seed, args.source_temporal_id
            ),
            index,
            record,
            row,
        )
        _push_candidate(
            heaps[stratum],
            candidates_by_game[stratum],
            candidate,
            capacities[stratum],
        )

    if source_seeded_records:
        raise ValueError(
            "authenticated source is not pure unseeded self-play: "
            f"{source_seeded_records} seeded train records"
        )

    selected_by_stratum: dict[
        tuple[str, str, str, str], list[RankedCandidate]
    ] = {}
    used_games: set[int] = set()
    used_positions: set[bytes] = set()
    for stratum in sorted(quotas):
        ranked = sorted(
            candidates_by_game.get(stratum, {}).values(),
            key=lambda row: (
                row.game_priority,
                row.priority,
                row.source_index,
            ),
        )
        selected: list[RankedCandidate] = []
        for candidate in ranked:
            canonical = frontier._canonical_position(candidate.record)
            if (
                candidate.meta.game_id in used_games
                or canonical in used_positions
            ):
                continue
            selected.append(candidate)
            used_games.add(candidate.meta.game_id)
            used_positions.add(canonical)
            if len(selected) == quotas[stratum]:
                break
        if len(selected) != quotas[stratum]:
            raise ValueError(
                "matched-random capacity insufficient for "
                f"{_stratum_name(stratum)}: selected={len(selected)} "
                f"required={quotas[stratum]}"
            )
        selected_by_stratum[stratum] = selected

    offsets: Counter = Counter()
    control_records: list[bytes] = []
    for stratum in treatment_strata:
        candidate = selected_by_stratum[stratum][offsets[stratum]]
        offsets[stratum] += 1
        original = frontier._zero_targets(candidate.record)
        control_records.extend((original, frontier.mirror_record(original)))

    if len(control_records) != len(hard_seeds):
        raise ValueError("internal error: control/treatment cardinality mismatch")
    for index in range(0, len(control_records), 2):
        if frontier.mirror_record(control_records[index]) != control_records[index + 1]:
            raise ValueError("internal error: control mirror alignment failed")
        if (
            _stratum(control_records[index], args.source_temporal_id)
            != treatment_strata[index // 2]
        ):
            raise ValueError("internal error: matched stratum order drift")

    control_payload = (
        frontier.JNNW_MAGIC
        + struct.pack("<I", len(control_records))
        + b"".join(control_records)
    )
    treatment_payload = (
        frontier.JNNW_MAGIC
        + struct.pack("<I", len(hard_seeds))
        + b"".join(hard_seeds)
    )
    frontier._atomic_write_bytes(paths["control"], control_payload)
    frontier._atomic_write_bytes(paths["treatment"], treatment_payload)
    checked_control = _read_seed_records(paths["control"])
    checked_treatment = _read_seed_records(paths["treatment"])
    if checked_control != control_records or checked_treatment != hard_seeds:
        raise ValueError("matched catalogue read-back verification failed")

    treatment_counts = Counter(_stratum_name(value) for value in treatment_strata)
    control_counts = Counter(
        _stratum_name(
            _stratum(checked_control[index], args.source_temporal_id)
        )
        for index in range(0, len(checked_control), 2)
    )
    if control_counts != treatment_counts:
        raise ValueError("control/treatment stratum distributions differ")

    payload = {
        "schema": 1,
        "operation": "l3-reverse-seed-matching",
        "code_sha": args.code_sha,
        "upstream_hard_code_sha": args.expected_hard_code_sha,
        "primary_contrast": "HARD_SEED_SELFPLAY minus MATCHED_RANDOM_SEED_SELFPLAY",
        "single_factor": "seed_root_selection_policy",
        "matching_seed": args.matching_seed,
        "source_temporal_id": args.source_temporal_id,
        "matching_dimensions": [
            "source_temporal_id",
            "phase_band",
            "piece_band",
            "material_stratum",
        ],
        "stratum_definitions": {
            "phase_band": {
                "opening": "pieces>=30",
                "midgame": "22<=pieces<=29",
                "late_midgame": "15<=pieces<=21",
                "endgame": "8<=pieces<=14",
                "deep_endgame": "pieces<=7",
            },
            "piece_band": {
                "late_midgame": "pieces>=17",
                "endgame": "11<=pieces<=16",
                "deep_endgame": "pieces<=10",
            },
            "material_stratum": {
                "p4_equal": "margin=0",
                "p3_thin": "margin=1",
                "p2_medium": "2<=margin<=3",
                "p1_clear": "margin>=4",
            },
        },
        "source": {
            "data_sha256": _sha256(paths["history_data"]),
            "meta_sha256": _sha256(paths["history_meta"]),
            "split_manifest_sha256": _sha256(paths["history_split"]),
            "records": history_count,
            "train_records": train_count,
            "holdout_records": history_count - train_count,
            "train_openings": len(train_openings),
            "holdout_openings": len(holdout_openings),
            "holdout_examined_for_selection": False,
            "seeded_train_records": source_seeded_records,
        },
        "upstream_hard": {
            "manifest_sha256": _sha256(paths["hard_manifest"]),
            "replay_sha256": _sha256(paths["hard_replay"]),
            "meta_sha256": _sha256(paths["hard_meta"]),
            "seeds_sha256": _sha256(paths["hard_seeds"]),
            "records": len(hard_seeds),
            "base_positions": len(treatment_strata),
        },
        "selection": {
            "control_policy": (
                "deterministic_blake2b_priority_sample_from_authenticated_train"
            ),
            "treatment_policy": "failed_conversion_train_only_v1",
            "treatment_games_excluded_from_control": True,
            "treatment_positions_excluded_from_control": True,
            "control_one_per_game": True,
            "control_canonical_dedup": True,
            "control_unique_games": len(used_games),
            "control_unique_canonical_positions": len(used_positions),
            "candidate_buffer_policy": (
                "unique_game_quota_plus_max_16_or_25pct"
            ),
            "eligible_records_by_stratum": {
                _stratum_name(key): value
                for key, value in sorted(eligible_records_by_stratum.items())
            },
            "retained_unique_games_by_stratum": {
                _stratum_name(key): len(value)
                for key, value in sorted(candidates_by_game.items())
            },
            "buffer_capacity_by_stratum": {
                _stratum_name(key): value
                for key, value in sorted(capacities.items())
            },
        },
        "matched_base_positions_by_stratum": dict(sorted(treatment_counts.items())),
        "causal_certificate": {
            "same_authenticated_source": True,
            "same_source_temporal_id": True,
            "same_cardinality": True,
            "same_index_ordered_strata": True,
            "colour_pairs_verified": True,
            "zero_targets_verified": True,
            "historical_holdout_excluded": True,
            "control_selection_uses_wdl": False,
        },
        "outputs": {
            "control_seeds": {
                "path": str(paths["control"]),
                "sha256": _sha256(paths["control"]),
                "records": len(checked_control),
            },
            "treatment_seeds": {
                "path": str(paths["treatment"]),
                "sha256": _sha256(paths["treatment"]),
                "records": len(checked_treatment),
            },
        },
        "probe_authorized": True,
        "training_authorized": False,
        "promotion_authorized": False,
        "automatic_next_job": None,
        "external_teacher_inputs": 0,
    }
    frontier._atomic_write_text(
        paths["manifest"],
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
    )
    print(json.dumps(payload, sort_keys=True, ensure_ascii=False))
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--history-data", required=True)
    parser.add_argument("--history-meta", required=True)
    parser.add_argument("--history-split-manifest", required=True)
    parser.add_argument("--hard-replay", required=True)
    parser.add_argument("--hard-meta", required=True)
    parser.add_argument("--hard-seeds", required=True)
    parser.add_argument("--hard-manifest", required=True)
    parser.add_argument("--expected-hard-code-sha", required=True)
    parser.add_argument("--source-temporal-id", required=True)
    parser.add_argument("--matching-seed", type=int, required=True)
    parser.add_argument("--code-sha", required=True)
    parser.add_argument("--out-control-seeds", required=True)
    parser.add_argument("--out-treatment-seeds", required=True)
    parser.add_argument("--manifest", required=True)
    return parser


def main() -> int:
    build_matched_catalogues(build_parser().parse_args())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
