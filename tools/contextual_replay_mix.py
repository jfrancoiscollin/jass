#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Build a deterministic old-replay + all-new training mix for continual fits.

The intended primary experiment is:

    CURRENT = 100% NEW train rows + previous champion prior
    REPLAY  = 75% NEW effective loss mass + 25% OLD replay mass
              + the exact same previous champion prior

This tool prepares only the REPLAY training dataset.  It deliberately does not
fit a model and never reads holdout rows as training input.

Key properties
--------------
* NEW: every row in the declared NEW train prefix is retained.
* OLD: whole opening groups are replayed; an opening is never partially kept.
* OLD replay is stratified without using targets/WDL: mean piece-count band,
  king exposure and seeded/standard provenance.
* The opening-group selection is deterministic for a fixed seed.
* Float32 sample weights make OLD/NEW contribute the requested effective loss
  masses exactly up to float32 rounding, regardless of the realised replay row
  count.  ``train_stream.py`` already normalises these weights on train rows.
* Optional external target sidecars are copied 1:1 with selected records.
* OLD and NEW game/opening IDs are source-namespaced in the output metadata.
* If metadata schemas differ, downgrade to JSM1 is explicit and fail-closed.

The caller remains responsible for authenticating that OLD and NEW target
sidecars implement the same scientific target recipe.  Their hashes are
recorded in the manifest so a job template can enforce that contract.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import struct
import sys
from dataclasses import dataclass, replace
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import selfplay_frontier as sf  # noqa: E402


@dataclass
class OpeningStats:
    opening_id: int
    rows: int = 0
    piece_sum: int = 0
    king_rows: int = 0
    seeded_rows: int = 0

    def stratum(self) -> str:
        mean_pieces = self.piece_sum / max(1, self.rows)
        if mean_pieces <= 10.0:
            phase = "deep_endgame"
        elif mean_pieces <= 16.0:
            phase = "endgame"
        elif mean_pieces <= 24.0:
            phase = "late_midgame"
        else:
            phase = "opening_midgame"
        king_fraction = self.king_rows / max(1, self.rows)
        if king_fraction == 0.0:
            kings = "no_kings"
        elif king_fraction < 0.5:
            kings = "mixed_kings"
        else:
            kings = "king_heavy"
        provenance = "seeded" if self.seeded_rows else "standard"
        return f"{phase}|{kings}|{provenance}"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _record_shape(record: bytes) -> tuple[int, bool]:
    wm, wk, bm, bk = struct.unpack_from("<QQQQ", record, 0)
    pieces = wm.bit_count() + wk.bit_count() + bm.bit_count() + bk.bit_count()
    return pieces, bool(wk or bk)


def _opening_rank(seed: int, stratum: str, opening_id: int) -> bytes:
    payload = struct.pack("<QQ", seed & ((1 << 64) - 1), opening_id)
    payload += stratum.encode("utf-8")
    return hashlib.blake2b(payload, digest_size=16).digest()


def _nearest_prefix(groups: list[OpeningStats], quota: int, seed: int, stratum: str) -> list[OpeningStats]:
    if quota <= 0 or not groups:
        return []
    ordered = sorted(groups, key=lambda row: (_opening_rank(seed, stratum, row.opening_id), row.opening_id))
    cumulative = 0
    best_count = 1
    best_distance = math.inf
    for index, row in enumerate(ordered, start=1):
        cumulative += row.rows
        distance = abs(cumulative - quota)
        if distance < best_distance:
            best_distance = distance
            best_count = index
        # Once we are past quota and getting farther away, every later prefix
        # can only add rows, so the nearest prefix is already known.
        if cumulative >= quota and distance > best_distance:
            break
    return ordered[:best_count]


def _validate_targets(path: Path, total_records: int, label: str) -> np.ndarray:
    try:
        values = np.load(path, allow_pickle=False, mmap_mode="r")
    except (OSError, ValueError) as exc:
        raise ValueError(f"{label}: cannot load target sidecar {path}: {exc}") from exc
    if not isinstance(values, np.ndarray) or values.dtype != np.dtype(np.float32):
        raise ValueError(f"{label}: target sidecar must be float32 NumPy array")
    if values.shape != (total_records,):
        raise ValueError(
            f"{label}: target sidecar shape {values.shape} != ({total_records},)"
        )
    if not bool(np.all(np.isfinite(values))):
        raise ValueError(f"{label}: target sidecar contains NaN/inf")
    if float(np.min(values)) < 0.0 or float(np.max(values)) > 1.0:
        raise ValueError(f"{label}: target sidecar must stay in [0,1]")
    return values


def _resolve_output_schema(old_schema, new_schema, downgrade_meta: str | None):
    if old_schema is new_schema:
        return old_schema
    if downgrade_meta == "jsm1":
        return sf.JSM1_SCHEMA
    raise ValueError(
        "OLD/NEW metadata schemas differ; pass --downgrade-meta jsm1 explicitly "
        "only after all JSM2-only contextual filtering has already happened"
    )


def _namespaced_meta(row, *, source_index: int, game_map: dict[int, int], opening_map: dict[int, int], out_schema):
    game_local = game_map.setdefault(row.game_id, len(game_map))
    opening_local = opening_map.setdefault(row.opening_id, len(opening_map))
    if game_local >= (1 << 56) or opening_local >= (1 << 56):
        raise ValueError("too many games/openings for 8-bit source namespace")
    rewritten = replace(
        row,
        game_id=(source_index << 56) | game_local,
        opening_id=(source_index << 56) | opening_local,
    )
    return sf._downgrade_meta(rewritten, out_schema)


def _prepare_old_selection(old_data: Path, old_meta: Path, train_count: int, old_budget: int, seed: int):
    by_opening: dict[int, OpeningStats] = {}
    scanned = 0
    for index, record, row in sf.iter_pair(old_data, old_meta):
        if index >= train_count:
            break
        pieces, has_king = _record_shape(record)
        stats = by_opening.setdefault(row.opening_id, OpeningStats(row.opening_id))
        stats.rows += 1
        stats.piece_sum += pieces
        stats.king_rows += int(has_king)
        stats.seeded_rows += int(row.seeded)
        scanned += 1
    if scanned != train_count:
        raise ValueError(f"OLD: scanned {scanned} train rows, expected {train_count}")
    if not by_opening:
        raise ValueError("OLD: empty train opening catalogue")

    strata: dict[str, list[OpeningStats]] = {}
    for stats in by_opening.values():
        strata.setdefault(stats.stratum(), []).append(stats)
    names = sorted(strata)
    record_weights = [sum(row.rows for row in strata[name]) for name in names]
    quotas = sf._weighted_quotas(old_budget, record_weights)

    selected: list[OpeningStats] = []
    manifest = {}
    for name, quota in zip(names, quotas):
        chosen = _nearest_prefix(strata[name], quota, seed, name)
        selected.extend(chosen)
        manifest[name] = {
            "input_openings": len(strata[name]),
            "input_records": sum(row.rows for row in strata[name]),
            "target_records": quota,
            "selected_openings": len(chosen),
            "selected_records": sum(row.rows for row in chosen),
        }
    selected_ids = {row.opening_id for row in selected}
    selected_rows = sum(row.rows for row in selected)
    if old_budget > 0 and not selected_ids:
        raise ValueError("OLD replay selection unexpectedly empty")
    return selected_ids, selected_rows, len(by_opening), manifest


def build_replay_mix(args: argparse.Namespace) -> dict:
    old_data, old_meta = Path(args.old_data), Path(args.old_meta)
    new_data, new_meta = Path(args.new_data), Path(args.new_meta)
    out_data, out_meta = Path(args.out_data), Path(args.out_meta)
    out_weights, manifest_path = Path(args.out_weights), Path(args.manifest)

    old_share = float(args.old_share)
    new_share = float(args.new_share)
    if not (0.0 < old_share < 1.0 and 0.0 < new_share < 1.0):
        raise ValueError("--old-share and --new-share must both lie strictly in (0,1)")
    if not math.isclose(old_share + new_share, 1.0, rel_tol=0.0, abs_tol=1e-12):
        raise ValueError("--old-share + --new-share must equal 1")

    old_total = sf._counted_file_count(old_data, sf.JNNW_MAGIC, sf.JNNW_REC)
    new_total = sf._counted_file_count(new_data, sf.JNNW_MAGIC, sf.JNNW_REC)
    old_schema, old_meta_count = sf._meta_file_info(old_meta)
    new_schema, new_meta_count = sf._meta_file_info(new_meta)
    if old_meta_count != old_total or new_meta_count != new_total:
        raise ValueError("data/meta count mismatch")
    old_train, new_train = int(args.old_train_count), int(args.new_train_count)
    if not (0 < old_train <= old_total and 0 < new_train <= new_total):
        raise ValueError("train counts must be positive prefixes within their sources")
    out_schema = _resolve_output_schema(old_schema, new_schema, args.downgrade_meta)

    targets_enabled = any((args.old_targets, args.new_targets, args.out_targets))
    if targets_enabled and not all((args.old_targets, args.new_targets, args.out_targets)):
        raise ValueError("--old-targets, --new-targets and --out-targets are all-or-none")
    old_targets = new_targets = None
    out_targets_path = Path(args.out_targets) if args.out_targets else None
    if targets_enabled:
        old_targets = _validate_targets(Path(args.old_targets), old_total, "OLD")
        new_targets = _validate_targets(Path(args.new_targets), new_total, "NEW")

    outputs = [out_data, out_meta, out_weights, manifest_path]
    if out_targets_path is not None:
        outputs.append(out_targets_path)
    resolved_outputs = [path.resolve(strict=False) for path in outputs]
    if len(resolved_outputs) != len(set(resolved_outputs)):
        raise ValueError("all output paths must be distinct")
    input_paths = [old_data, old_meta, new_data, new_meta]
    if targets_enabled:
        input_paths += [Path(args.old_targets), Path(args.new_targets)]
    input_resolved = {path.resolve(strict=False) for path in input_paths}
    if any(path in input_resolved for path in resolved_outputs):
        raise ValueError("outputs must not overwrite inputs")
    for path in outputs:
        if path.exists():
            raise ValueError(f"refusing to overwrite existing output: {path}")
        path.parent.mkdir(parents=True, exist_ok=True)

    desired_old_rows = int(round(new_train * old_share / new_share))
    desired_old_rows = max(1, min(old_train, desired_old_rows))
    selected_openings, selected_old_rows, old_openings, strata = _prepare_old_selection(
        old_data, old_meta, old_train, desired_old_rows, int(args.seed)
    )
    mixed_rows = selected_old_rows + new_train
    if mixed_rows <= 1:
        raise ValueError("mixed training dataset unexpectedly tiny")

    weights_tmp = out_weights.with_name(out_weights.name + ".tmp")
    weights = np.lib.format.open_memmap(
        weights_tmp, mode="w+", dtype=np.float32, shape=(mixed_rows,)
    )
    old_weight = np.float32(old_share * mixed_rows / selected_old_rows)
    new_weight = np.float32(new_share * mixed_rows / new_train)
    weights[:selected_old_rows] = old_weight
    weights[selected_old_rows:] = new_weight
    weights.flush()
    del weights

    targets_tmp = None
    out_targets = None
    if out_targets_path is not None:
        targets_tmp = out_targets_path.with_name(out_targets_path.name + ".tmp")
        out_targets = np.lib.format.open_memmap(
            targets_tmp, mode="w+", dtype=np.float32, shape=(mixed_rows,)
        )

    data_tmp = out_data.with_name(out_data.name + ".tmp")
    meta_tmp = out_meta.with_name(out_meta.name + ".tmp")
    data_hash = hashlib.sha256(sf.JNNW_MAGIC + struct.pack("<I", mixed_rows))
    meta_hash = hashlib.sha256(out_schema.magic + struct.pack("<I", mixed_rows))
    old_games: dict[int, int] = {}
    old_openings_map: dict[int, int] = {}
    new_games: dict[int, int] = {}
    new_openings_map: dict[int, int] = {}
    cursor = 0
    try:
        with data_tmp.open("wb") as data_out, meta_tmp.open("wb") as meta_out:
            data_out.write(sf.JNNW_MAGIC + struct.pack("<I", mixed_rows))
            meta_out.write(out_schema.magic + struct.pack("<I", mixed_rows))

            selected_counts: dict[int, int] = {}
            for index, record, row in sf.iter_pair(old_data, old_meta):
                if index >= old_train:
                    break
                if row.opening_id not in selected_openings:
                    continue
                selected_counts[row.opening_id] = selected_counts.get(row.opening_id, 0) + 1
                encoded = sf._encode_meta(
                    _namespaced_meta(
                        row, source_index=1, game_map=old_games,
                        opening_map=old_openings_map, out_schema=out_schema,
                    ),
                    out_schema,
                    context="contextual replay OLD output",
                )
                data_out.write(record); meta_out.write(encoded)
                data_hash.update(record); meta_hash.update(encoded)
                if out_targets is not None:
                    out_targets[cursor] = old_targets[index]
                cursor += 1
            if set(selected_counts) != selected_openings:
                raise ValueError("OLD replay write pass lost a selected opening")
            if cursor != selected_old_rows:
                raise ValueError(f"OLD replay wrote {cursor} rows, expected {selected_old_rows}")

            for index, record, row in sf.iter_pair(new_data, new_meta):
                if index >= new_train:
                    break
                encoded = sf._encode_meta(
                    _namespaced_meta(
                        row, source_index=2, game_map=new_games,
                        opening_map=new_openings_map, out_schema=out_schema,
                    ),
                    out_schema,
                    context="contextual replay NEW output",
                )
                data_out.write(record); meta_out.write(encoded)
                data_hash.update(record); meta_hash.update(encoded)
                if out_targets is not None:
                    out_targets[cursor] = new_targets[index]
                cursor += 1
        if cursor != mixed_rows:
            raise ValueError(f"mixed write produced {cursor} rows, expected {mixed_rows}")
        if out_targets is not None:
            out_targets.flush()
            del out_targets
        data_tmp.replace(out_data)
        meta_tmp.replace(out_meta)
        weights_tmp.replace(out_weights)
        if targets_tmp is not None:
            targets_tmp.replace(out_targets_path)
    finally:
        for tmp in (data_tmp, meta_tmp, weights_tmp, targets_tmp):
            if tmp is not None and Path(tmp).exists():
                Path(tmp).unlink()

    final_weights = np.load(out_weights, allow_pickle=False, mmap_mode="r")
    old_mass = float(np.sum(final_weights[:selected_old_rows], dtype=np.float64))
    new_mass = float(np.sum(final_weights[selected_old_rows:], dtype=np.float64))
    total_mass = old_mass + new_mass
    realised_old_share = old_mass / total_mass
    realised_new_share = new_mass / total_mass
    if abs(realised_old_share - old_share) > 2e-7 or abs(realised_new_share - new_share) > 2e-7:
        raise ValueError(
            f"float32 effective mass drift old/new={realised_old_share}/{realised_new_share}"
        )

    payload = {
        "schema": "jass.contextual_replay_mix.v1",
        "operation": "opening_group_stratified_replay_plus_all_new",
        "seed": int(args.seed),
        "selection_scope": "train_prefix_only",
        "holdout_rows_read_into_training": 0,
        "requested_effective_loss_mass": {"OLD": old_share, "NEW": new_share},
        "realised_effective_loss_mass": {
            "OLD": realised_old_share,
            "NEW": realised_new_share,
        },
        "row_budget": {
            "desired_old_replay_records": desired_old_rows,
            "selected_old_replay_records": selected_old_rows,
            "all_new_train_records": new_train,
            "mixed_train_records": mixed_rows,
            "old_budget_clipped_to_available_train": desired_old_rows == old_train and old_train < round(new_train * old_share / new_share),
        },
        "selection": {
            "unit": "opening_id",
            "whole_opening_groups_only": True,
            "target_independent": True,
            "strata": "mean_piece_band_x_king_exposure_x_seeded_provenance",
            "quota_basis": "OLD_train_record_mass",
            "within_stratum_order": "blake2b(seed,stratum,opening_id)",
            "within_stratum_choice": "nearest_deterministic_opening_prefix_to_record_quota",
            "input_old_openings": old_openings,
            "selected_old_openings": len(selected_openings),
            "by_stratum": strata,
        },
        "sources": {
            "OLD": {
                "data": str(old_data), "data_sha256": _sha256(old_data),
                "meta": str(old_meta), "meta_sha256": _sha256(old_meta),
                "records": old_total, "train_records": old_train,
                "holdout_records_excluded": old_total - old_train,
                "metadata_schema": old_schema.name,
                "targets_sha256": _sha256(Path(args.old_targets)) if targets_enabled else None,
            },
            "NEW": {
                "data": str(new_data), "data_sha256": _sha256(new_data),
                "meta": str(new_meta), "meta_sha256": _sha256(new_meta),
                "records": new_total, "train_records": new_train,
                "holdout_records_excluded": new_total - new_train,
                "metadata_schema": new_schema.name,
                "targets_sha256": _sha256(Path(args.new_targets)) if targets_enabled else None,
            },
        },
        "metadata": {
            "output_schema": out_schema.name,
            "downgraded_to_jsm1": bool(args.downgrade_meta == "jsm1" and old_schema is not new_schema),
            "source_namespaced": True,
            "old_output_games": len(old_games),
            "old_output_openings": len(old_openings_map),
            "new_output_games": len(new_games),
            "new_output_openings": len(new_openings_map),
        },
        "sample_weights": {
            "dtype": "float32",
            "OLD_raw_weight": float(old_weight),
            "NEW_raw_weight": float(new_weight),
            "min": float(min(old_weight, new_weight)),
            "max": float(max(old_weight, new_weight)),
            "normalization_expected_in_trainer": "mean-train-1",
            "path": str(out_weights),
            "sha256": _sha256(out_weights),
        },
        "targets": {
            "external_targets_copied": targets_enabled,
            "caller_must_authenticate_same_target_recipe_across_sources": True,
            "path": str(out_targets_path) if out_targets_path else None,
            "sha256": _sha256(out_targets_path) if out_targets_path else None,
        },
        "outputs": {
            "data": str(out_data), "data_sha256": data_hash.hexdigest(),
            "meta": str(out_meta), "meta_sha256": meta_hash.hexdigest(),
            "weights": str(out_weights), "weights_sha256": _sha256(out_weights),
            "targets": str(out_targets_path) if out_targets_path else None,
        },
        "fit_contract": {
            "primary_control": "NEW_only_plus_same_parent_prior",
            "primary_treatment": "OLD_replay_plus_all_NEW_weighted_plus_same_parent_prior",
            "same_parent_prior_required": True,
            "same_optimizer_recipe_required": True,
            "same_target_recipe_required": True,
            "old_and_new_holdouts_must_remain_separate_for_readout": True,
        },
    }
    manifest_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, sort_keys=True))
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--old-data", required=True)
    parser.add_argument("--old-meta", required=True)
    parser.add_argument("--old-train-count", required=True, type=int)
    parser.add_argument("--new-data", required=True)
    parser.add_argument("--new-meta", required=True)
    parser.add_argument("--new-train-count", required=True, type=int)
    parser.add_argument("--old-share", required=True, type=float)
    parser.add_argument("--new-share", required=True, type=float)
    parser.add_argument("--seed", required=True, type=int)
    parser.add_argument("--old-targets")
    parser.add_argument("--new-targets")
    parser.add_argument("--out-targets")
    parser.add_argument("--out-data", required=True)
    parser.add_argument("--out-meta", required=True)
    parser.add_argument("--out-weights", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument(
        "--downgrade-meta", choices=("jsm1",),
        help="explicitly downgrade mixed JSM2/JSM1 inputs to JSM1 after contextual filtering",
    )
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    build_replay_mix(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
