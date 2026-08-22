#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Loss-to-region autopsy for a strictly local CURRICULUM repair fit.

The pipeline has three fail-closed stages:

``prepare``
    Read complete dumped games, retain every champion decision, and assign an
    opening-level discovery/confirmation split before any deep score is seen.

``worker``
    Re-search each historical decision with the byte-authenticated champion.
    If the deeper move differs, judge both children with the same deeper
    champion and publish the root-POV regret.  This is self-diagnosis, not an
    external teacher and not a game or fit.

``aggregate``
    Keep at most one decisive error per opening, match non-loss controls in
    the same phase/king/tactical stratum, discover enriched PatternEval buckets
    on one opening split and confirm them on the other.  It emits an exact-fold
    trainable-region manifest and neutral JNNW seeds for a later targeted
    self-play job.  It never trains or promotes a model.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
import math
import os
from pathlib import Path
import struct
import sys
import tempfile
from typing import Any, Iterable

import numpy as np

SCHEMA_SELECTION = "jass.l3_curriculum_error_selection.v1"
SCHEMA_SHARD = "jass.l3_curriculum_error_shard.v1"
SCHEMA_REPORT = "jass.l3_curriculum_error_autopsy.v1"
SCHEMA_REGION = "jass.l3_curriculum_error_region.v1"
JNNW_RECORD = struct.Struct("<QQQQBi b".replace(" ", ""))
JNNW_MAGIC = b"JNNW"


def _cv_module() -> Any:
    try:
        from jobs.tools import calibrate_vs_scan as cv
    except ModuleNotFoundError:
        import calibrate_vs_scan as cv  # type: ignore
    return cv


def _ctx_module() -> Any:
    try:
        from jobs.tools import l3_context3_decision_flip_autopsy as ctx
    except ModuleNotFoundError:
        import l3_context3_decision_flip_autopsy as ctx  # type: ignore
    return ctx


def _patterns_module() -> Any:
    tools = Path(__file__).resolve().parents[2] / "pattern_jass" / "tools"
    sys.path.insert(0, str(tools))
    import patterns  # type: ignore
    return patterns


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _phase(piece_count: int) -> str:
    if piece_count >= 30:
        return "opening"
    if piece_count >= 22:
        return "midgame"
    if piece_count >= 15:
        return "late_midgame"
    if piece_count >= 8:
        return "endgame"
    return "deep_endgame"


def _fen_bits(fen: str) -> tuple[int, int, int, int, int]:
    side, wm, wk, bm, bk = _cv_module().parse_jass_fen(fen)
    bitboard = lambda squares: sum(1 << (int(square) - 1) for square in squares)
    return (
        bitboard(wm),
        bitboard(wk),
        bitboard(bm),
        bitboard(bk),
        0 if side == "W" else 1,
    )


def _stratum(fen: str, move: str) -> str:
    wm, wk, bm, bk, _stm = _fen_bits(fen)
    pieces = (wm | wk | bm | bk).bit_count()
    kings = "kings" if (wk | bk) else "no_kings"
    tactical = "capture" if "x" in move else "quiet"
    return f"{_phase(pieces)}|{kings}|{tactical}"


def _opening_id(game: dict[str, Any]) -> str:
    supplied = game.get("opening_id")
    if supplied is not None:
        return str(supplied)
    opening = str(game.get("opening") or (game.get("fens") or [""])[0])
    if not opening:
        raise ValueError("game lacks opening/opening_id")
    return hashlib.sha256(opening.encode("utf-8")).hexdigest()[:16]


def _split(opening_id: str, seed: int) -> str:
    digest = hashlib.sha256(f"{seed}|{opening_id}".encode("utf-8")).digest()
    return "discovery" if int.from_bytes(digest[:8], "big") % 2 == 0 else "confirm"


def _exact_state_key(fen: str) -> str:
    """Canonical key under the exact rot180+colour-swap game symmetry."""
    wm, wk, bm, bk, stm = _fen_bits(fen)

    def rotate(bits: int) -> int:
        image = 0
        for square in range(1, 51):
            if bits & (1 << (square - 1)):
                image |= 1 << (50 - square)
        return image

    original = (stm, wm, wk, bm, bk)
    image = (1 - stm, rotate(bm), rotate(bk), rotate(wm), rotate(wk))
    representative = min(original, image)
    return hashlib.sha256(_canonical(representative)).hexdigest()


def prepare_games(game_dirs: Iterable[Path], *, split_seed: int) -> dict[str, Any]:
    paths = sorted(path for root in game_dirs for path in root.glob("game-*.json"))
    if not paths:
        raise ValueError("no game-*.json inputs")
    rows: list[dict[str, Any]] = []
    games_seen: set[str] = set()
    outcome_games: dict[str, int] = defaultdict(int)
    for path in paths:
        game = json.loads(path.read_text(encoding="utf-8"))
        fens = list(game.get("fens", []))
        moves = list(game.get("moves", []))
        if not moves or len(fens) != len(moves) + 1:
            raise ValueError(f"{path}: expected len(fens)=len(moves)+1")
        score = float(game.get("jass_score", -1.0))
        if score not in (0.0, 0.5, 1.0):
            raise ValueError(f"{path}: jass_score outside {{0,.5,1}}")
        outcome = {0.0: "loss", 0.5: "draw", 1.0: "win"}[score]
        opening_id = _opening_id(game)
        # Content identity deliberately excludes the source path: copying the
        # same game into a second input directory must not double its weight.
        uid = hashlib.sha256(
            _canonical(
                {
                    "opening_id": opening_id,
                    "jass_is_white": bool(game.get("jass_is_white")),
                    "jass_score": score,
                    "fens": fens,
                    "moves": moves,
                }
            )
        ).hexdigest()[:24]
        if uid in games_seen:
            raise ValueError(f"duplicate game identity {uid}")
        games_seen.add(uid)
        outcome_games[outcome] += 1
        champion_white = bool(game.get("jass_is_white"))
        for ply, move in enumerate(moves):
            side = str(fens[ply]).split(":", 1)[0]
            if (side == "W") != champion_white:
                continue
            rows.append(
                {
                    "ordinal": len(rows),
                    "game_uid": uid,
                    "source_file": str(path),
                    "source_game_id": game.get("game_id"),
                    "opening_id": opening_id,
                    "split": _split(opening_id, split_seed),
                    "outcome": outcome,
                    "ply": ply,
                    "fen": fens[ply],
                    "exact_state_key": _exact_state_key(fens[ply]),
                    "actual_move": str(move),
                    "stratum": _stratum(fens[ply], str(move)),
                }
            )
    splits = {row["opening_id"]: row["split"] for row in rows}
    if len(set(splits.values())) != 2:
        raise ValueError("opening split lacks discovery or confirmation rows")
    state_splits: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        state_splits[str(row["exact_state_key"])].add(str(row["split"]))
    leaked_states = [key for key, values in state_splits.items() if len(values) > 1]
    if leaked_states:
        raise ValueError(
            f"{len(leaked_states)} exact-symmetry state(s) cross discovery/confirm"
        )
    return {
        "schema": SCHEMA_SELECTION,
        "split": {
            "unit": "opening_id",
            "seed": split_seed,
            "method": "sha256_parity",
            "leakage": False,
            "exact_symmetry_state_overlap": 0,
        },
        "sources": [{"path": str(path), "sha256": sha256(path)} for path in paths],
        "games": len(games_seen),
        "games_by_outcome": dict(sorted(outcome_games.items())),
        "decisions": len(rows),
        "rows": rows,
        "external_teacher_inputs": 0,
        "fit_count": 0,
        "strength_games": 0,
        "promotion_authorized": False,
    }


def analyse_shard(args: argparse.Namespace) -> dict[str, Any]:
    selection_path = Path(args.selection)
    selection = json.loads(selection_path.read_text(encoding="utf-8"))
    if selection.get("schema") != SCHEMA_SELECTION:
        raise ValueError("selection schema drift")
    if not 0 <= args.shard < args.nshards:
        raise ValueError("invalid shard")
    if args.teacher_depth <= 0 or args.judge_depth <= args.teacher_depth:
        raise ValueError("judge_depth must be strictly deeper than teacher_depth")
    cv = _cv_module()
    ctx = _ctx_module()
    engine = cv.JassEngine(
        args.jass,
        label=f"curriculum-autopsy-s{args.shard}",
        pattern_path=args.champion,
        search_params=args.search_params,
    )
    referee = cv.Referee(args.jass)
    output: list[dict[str, Any]] = []
    try:
        for source in selection["rows"]:
            ordinal = int(source["ordinal"])
            if ordinal % args.nshards != args.shard:
                continue
            fen = str(source["fen"])
            actual = cv.parse_scan_move(str(source["actual_move"]))
            best, best_root = ctx._search(engine, fen, args.teacher_depth)
            actual_apply = actual.jass_apply_str()
            differs = actual_apply != best_root["apply"]
            row = {
                **source,
                "teacher_depth": args.teacher_depth,
                "judge_depth": args.judge_depth,
                "teacher": best_root,
                "actual_apply": actual_apply,
                "move_differs": differs,
                "regret_cp": 0,
            }
            if differs:
                actual_child = ctx._child_fen(referee, fen, actual)
                best_child = ctx._child_fen(referee, fen, best)
                _move, actual_judge = ctx._search(engine, actual_child, args.judge_depth)
                _move, best_judge = ctx._search(engine, best_child, args.judge_depth)
                actual_value = -int(actual_judge["score"])
                best_value = -int(best_judge["score"])
                row.update(
                    {
                        "actual_child": actual_child,
                        "teacher_child": best_child,
                        "root_pov_actual_cp": actual_value,
                        "root_pov_teacher_cp": best_value,
                        "regret_cp": best_value - actual_value,
                        "child_searches": {
                            "actual": actual_judge,
                            "teacher": best_judge,
                        },
                    }
                )
            if ordinal < args.symmetry_rows:
                image = ctx.exact_image_fen(fen)
                original = ctx._neteval(engine, fen)
                transformed = ctx._neteval(engine, image)
                row["exact_symmetry"] = {
                    "image_fen": image,
                    "original_static_score": original,
                    "image_static_score": transformed,
                    "score_delta": transformed - original,
                }
            output.append(row)
    finally:
        referee.close()
        engine.close()
    return {
        "schema": SCHEMA_SHARD,
        "selection_sha256": sha256(selection_path),
        "champion_sha256": sha256(Path(args.champion)),
        "jass_sha256": sha256(Path(args.jass)),
        "search_params_sha256": sha256(Path(args.search_params)),
        "shard": args.shard,
        "nshards": args.nshards,
        "teacher_depth": args.teacher_depth,
        "judge_depth": args.judge_depth,
        "rows": output,
    }


def _pattern_columns(fen: str) -> list[int]:
    patterns = _patterns_module()
    wm, _wk, bm, _bk, _stm = _fen_bits(fen)
    indices = patterns.extract_indices(
        np.asarray([bm], dtype=np.uint64), np.asarray([wm], dtype=np.uint64)
    )
    return [int(value) for value in patterns.flat_feature_columns(indices)[0]]


def _wilson(successes: int, total: int, z: float = 1.959963984540054) -> tuple[float, float]:
    if total <= 0:
        return 0.0, 1.0
    p = successes / total
    denom = 1.0 + z * z / total
    center = (p + z * z / (2.0 * total)) / denom
    radius = z * math.sqrt(p * (1.0 - p) / total + z * z / (4.0 * total * total)) / denom
    return max(0.0, center - radius), min(1.0, center + radius)


def _one_per_opening(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    best: dict[str, dict[str, Any]] = {}
    for row in rows:
        opening_id = str(row["opening_id"])
        previous = best.get(opening_id)
        if previous is None or (int(row["regret_cp"]), int(row["ply"])) > (
            int(previous["regret_cp"]),
            int(previous["ply"]),
        ):
            best[opening_id] = row
    return sorted(
        best.values(),
        key=lambda row: (str(row["opening_id"]), str(row["game_uid"])),
    )


def _matched_controls(
    errors: list[dict[str, Any]],
    rows: list[dict[str, Any]],
    *,
    seed: int,
    max_control_regret: int,
) -> list[dict[str, Any]]:
    pools: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    error_openings = {str(row["opening_id"]) for row in errors}
    # A control opening is clean only if its worst observed decision is clean.
    # Filtering rows before the opening-level maximum would let an opening with
    # one large error enter through a different, low-regret move.
    worst_by_opening = {
        str(row["opening_id"]): row for row in _one_per_opening(rows)
    }
    non_loss = _one_per_opening(row for row in rows if row["outcome"] != "loss")
    for row in non_loss:
        opening_id = str(row["opening_id"])
        if opening_id in error_openings:
            continue
        if int(worst_by_opening[opening_id]["regret_cp"]) > max_control_regret:
            continue
        pools[(str(row["split"]), str(row["stratum"]))].append(row)
    for key, values in pools.items():
        values.sort(
            key=lambda row: hashlib.sha256(
                f"{seed}|{key}|{row['game_uid']}|{row['ply']}".encode("utf-8")
            ).digest()
        )
    used: set[str] = set()
    matched: list[dict[str, Any]] = []
    for error in errors:
        key = (str(error["split"]), str(error["stratum"]))
        choice = next(
            (row for row in pools.get(key, []) if row["opening_id"] not in used),
            None,
        )
        if choice is not None:
            used.add(str(choice["opening_id"]))
            matched.append(choice)
    return matched


def _bucket_counts(rows: list[dict[str, Any]]) -> dict[int, int]:
    counts: dict[int, int] = defaultdict(int)
    for row in rows:
        for column in set(_pattern_columns(str(row["fen"]))):
            counts[column] += 1
    return counts


def _seed_record(fen: str) -> bytes:
    wm, wk, bm, bk, stm = _fen_bits(fen)
    return JNNW_RECORD.pack(wm, wk, bm, bk, stm, 0, 0)


def aggregate(
    selection: dict[str, Any],
    shards: list[dict[str, Any]],
    *,
    min_regret_cp: int,
    max_control_regret_cp: int,
    min_error_openings: int,
    min_discovery_hits: int,
    discovery_risk_ratio: float,
    confirm_risk_ratio: float,
    min_confirmed_buckets: int,
    max_region_buckets: int,
    match_seed: int,
) -> tuple[dict[str, Any], dict[str, Any], bytes]:
    expected = len(shards)
    if not shards:
        raise ValueError("at least one shard is required")
    if {int(shard.get("shard", -1)) for shard in shards} != set(range(expected)):
        raise ValueError("shard indices are incomplete")
    if any(shard.get("schema") != SCHEMA_SHARD for shard in shards):
        raise ValueError("shard schema drift")
    if any(int(shard.get("nshards", -1)) != expected for shard in shards):
        raise ValueError("shard count contract drift")
    selection_sha = hashlib.sha256(_canonical(selection)).hexdigest()
    if any(shard.get("selection_sha256") != selection_sha for shard in shards):
        raise ValueError("shard selection hash mismatch")
    rows = [row for shard in shards for row in shard.get("rows", [])]
    rows.sort(key=lambda row: int(row["ordinal"]))
    if [int(row["ordinal"]) for row in rows] != list(range(int(selection["decisions"]))):
        raise ValueError("shards do not exactly cover the selected decisions")
    symmetry = [int(row["exact_symmetry"]["score_delta"]) for row in rows if "exact_symmetry" in row]
    symmetry_ok = bool(symmetry) and max(map(abs, symmetry)) == 0

    errors = _one_per_opening(
        row
        for row in rows
        if row["outcome"] == "loss"
        and bool(row["move_differs"])
        and int(row["regret_cp"]) >= min_regret_cp
    )
    controls = _matched_controls(
        errors, rows, seed=match_seed, max_control_regret=max_control_regret_cp
    )
    matched_fraction = len(controls) / len(errors) if errors else 0.0
    by_split_error = {split: [row for row in errors if row["split"] == split] for split in ("discovery", "confirm")}
    by_split_control = {split: [row for row in controls if row["split"] == split] for split in ("discovery", "confirm")}
    discovery_error = _bucket_counts(by_split_error["discovery"])
    discovery_control = _bucket_counts(by_split_control["discovery"])
    n_de = len(by_split_error["discovery"])
    n_dc = len(by_split_control["discovery"])
    candidates = []
    for bucket, error_hits in discovery_error.items():
        control_hits = discovery_control.get(bucket, 0)
        error_rate = error_hits / max(n_de, 1)
        control_rate = control_hits / max(n_dc, 1)
        ratio = (error_rate + 0.5 / max(n_de, 1)) / (control_rate + 0.5 / max(n_dc, 1))
        if error_hits >= min_discovery_hits and ratio >= discovery_risk_ratio:
            candidates.append((bucket, ratio, error_hits, control_hits))
    candidates.sort(key=lambda item: (-item[1], -item[2], item[0]))
    candidates = candidates[:max_region_buckets]

    confirm_error = _bucket_counts(by_split_error["confirm"])
    confirm_control = _bucket_counts(by_split_control["confirm"])
    n_ce = len(by_split_error["confirm"])
    n_cc = len(by_split_control["confirm"])
    confirmed: list[dict[str, Any]] = []
    for bucket, discovery_ratio, discovery_hits, discovery_control_hits in candidates:
        error_hits = confirm_error.get(bucket, 0)
        control_hits = confirm_control.get(bucket, 0)
        error_rate = error_hits / max(n_ce, 1)
        control_rate = control_hits / max(n_cc, 1)
        ratio = (error_rate + 0.5 / max(n_ce, 1)) / (control_rate + 0.5 / max(n_cc, 1))
        error_ci = _wilson(error_hits, n_ce)
        control_ci = _wilson(control_hits, n_cc)
        if error_hits >= 2 and ratio >= confirm_risk_ratio and error_ci[0] > control_ci[1]:
            confirmed.append(
                {
                    "full_pattern_column": bucket,
                    "discovery": {
                        "error_hits": discovery_hits,
                        "control_hits": discovery_control_hits,
                        "risk_ratio": discovery_ratio,
                    },
                    "confirm": {
                        "error_hits": error_hits,
                        "control_hits": control_hits,
                        "error_rate": error_rate,
                        "control_rate": control_rate,
                        "error_ci95": list(error_ci),
                        "control_ci95": list(control_ci),
                        "risk_ratio": ratio,
                    },
                }
            )
    confirmed_columns = sorted(item["full_pattern_column"] for item in confirmed)
    fit_authorized = bool(
        symmetry_ok
        and len(errors) >= min_error_openings
        and matched_fraction >= 0.8
        and n_de > 0
        and n_ce > 0
        and len(confirmed_columns) >= min_confirmed_buckets
    )
    error_seeds = [
        row for row in errors if set(_pattern_columns(str(row["fen"]))) & set(confirmed_columns)
    ]
    seeds_payload = JNNW_MAGIC + struct.pack("<I", len(error_seeds)) + b"".join(
        _seed_record(str(row["fen"])) for row in error_seeds
    )
    def authenticated_shard_value(field: str) -> str:
        values = {str(shard.get(field, "")) for shard in shards}
        if len(values) != 1 or not next(iter(values)):
            raise ValueError(f"shards do not authenticate one byte-identical {field}")
        return next(iter(values))

    champion_sha256 = authenticated_shard_value("champion_sha256")
    jass_sha256 = authenticated_shard_value("jass_sha256")
    search_params_sha256 = authenticated_shard_value("search_params_sha256")
    teacher_depths = {int(shard.get("teacher_depth", -1)) for shard in shards}
    judge_depths = {int(shard.get("judge_depth", -1)) for shard in shards}
    if len(teacher_depths) != 1 or len(judge_depths) != 1:
        raise ValueError("shard depth contract drift")
    teacher_depth = next(iter(teacher_depths))
    judge_depth = next(iter(judge_depths))
    if teacher_depth <= 0 or judge_depth <= teacher_depth:
        raise ValueError("invalid authenticated teacher/judge depths")
    region = {
        "schema": SCHEMA_REGION,
        "fold": "exact_rot180_colour_swap",
        "fit_authorized": fit_authorized,
        "selection_sha256": selection_sha,
        "champion_sha256": champion_sha256,
        "jass_sha256": jass_sha256,
        "search_params_sha256": search_params_sha256,
        "pattern_columns_full": confirmed_columns,
        "extras": [],
        "selection": {
            "kind": "discovery_then_sealed_confirmation",
            "unit": "opening_id",
            "one_decisive_error_per_opening": True,
            "terminal_loss_alone_is_not_a_training_signal": True,
            "min_regret_cp": min_regret_cp,
        },
        "confirmation": confirmed,
        "strict_fit_contract": {
            "train_dense_extras": False,
            "train_pattern_mg_and_eg": True,
            "freeze_everything_else_at_champion": True,
        },
        "promotion_authorized": False,
    }
    report = {
        "schema": SCHEMA_REPORT,
        "verdict": (
            "JASS_CURRICULUM_ERROR_REGION_CONFIRMED"
            if fit_authorized
            else "JASS_CURRICULUM_ERROR_REGION_NOT_ESTABLISHED"
        ),
        "fit_authorized": fit_authorized,
        "selection_sha256": selection_sha,
        "champion_sha256": champion_sha256,
        "jass_sha256": jass_sha256,
        "search_params_sha256": search_params_sha256,
        "teacher_depth": teacher_depth,
        "judge_depth": judge_depth,
        "decisions": len(rows),
        "loss_error_openings": len(errors),
        "matched_control_openings": len(controls),
        "matched_fraction": matched_fraction,
        "splits": {
            split: {
                "errors": len(by_split_error[split]),
                "controls": len(by_split_control[split]),
            }
            for split in ("discovery", "confirm")
        },
        "candidate_buckets": len(candidates),
        "confirmed_buckets": len(confirmed_columns),
        "seed_positions": len(error_seeds),
        "perspective_guard": {
            "probes": len(symmetry),
            "max_abs_exact_symmetry_delta_cp": max(map(abs, symmetry), default=None),
            "passed": symmetry_ok,
            "root_value_conversion": "root_value=-child_stm_value",
        },
        "gates": {
            "min_error_openings": min_error_openings,
            "min_matched_fraction": 0.8,
            "min_discovery_hits": min_discovery_hits,
            "discovery_risk_ratio": discovery_risk_ratio,
            "confirm_risk_ratio": confirm_risk_ratio,
            "min_confirmed_buckets": min_confirmed_buckets,
            "max_region_buckets": max_region_buckets,
        },
        "external_teacher_inputs": 0,
        "self_play_games": 0,
        "fits": 0,
        "strength_games": 0,
        "frozen_reads": 0,
        "promotion_authorized": False,
        "automatic_continuation": False,
    }
    return report, region, seeds_payload


def _publish(outputs: list[tuple[Path, bytes]]) -> None:
    resolved = [path.resolve(strict=False) for path, _payload in outputs]
    if len(resolved) != len(set(resolved)):
        raise ValueError("output paths must be distinct")
    if any(path.exists() for path, _payload in outputs):
        raise ValueError("refusing to overwrite an output")
    staged: list[tuple[Path, Path]] = []
    published: list[Path] = []
    try:
        for destination, payload in outputs:
            destination.parent.mkdir(parents=True, exist_ok=True)
            descriptor, name = tempfile.mkstemp(dir=destination.parent, prefix=f".{destination.name}.")
            temporary = Path(name)
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            staged.append((temporary, destination))
        for temporary, destination in staged:
            os.link(temporary, destination)
            published.append(destination)
    except BaseException:
        for path in published:
            path.unlink(missing_ok=True)
        raise
    finally:
        for temporary, _destination in staged:
            temporary.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    prepare = sub.add_parser("prepare")
    prepare.add_argument("--games-dir", action="append", type=Path, required=True)
    prepare.add_argument("--split-seed", type=int, default=2026082209)
    prepare.add_argument("--out", type=Path, required=True)
    worker = sub.add_parser("worker")
    worker.add_argument("--selection", required=True)
    worker.add_argument("--jass", required=True)
    worker.add_argument("--champion", required=True)
    worker.add_argument("--search-params", required=True)
    worker.add_argument("--teacher-depth", type=int, default=10)
    worker.add_argument("--judge-depth", type=int, default=12)
    worker.add_argument("--symmetry-rows", type=int, default=32)
    worker.add_argument("--shard", type=int, required=True)
    worker.add_argument("--nshards", type=int, required=True)
    worker.add_argument("--out", type=Path, required=True)
    combine = sub.add_parser("aggregate")
    combine.add_argument("--selection", type=Path, required=True)
    combine.add_argument("--shard", action="append", type=Path, required=True)
    combine.add_argument("--min-regret-cp", type=int, default=50)
    combine.add_argument("--max-control-regret-cp", type=int, default=10)
    combine.add_argument("--min-error-openings", type=int, default=64)
    combine.add_argument("--min-discovery-hits", type=int, default=4)
    combine.add_argument("--discovery-risk-ratio", type=float, default=1.5)
    combine.add_argument("--confirm-risk-ratio", type=float, default=1.5)
    combine.add_argument("--min-confirmed-buckets", type=int, default=8)
    combine.add_argument("--max-region-buckets", type=int, default=512)
    combine.add_argument("--match-seed", type=int, default=2026082210)
    combine.add_argument("--report", type=Path, required=True)
    combine.add_argument("--region", type=Path, required=True)
    combine.add_argument("--seeds", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == "prepare":
        payload = prepare_games(args.games_dir, split_seed=args.split_seed)
        _publish([(args.out, _canonical(payload))])
        summary = {"schema": payload["schema"], "decisions": payload["decisions"]}
    elif args.command == "worker":
        payload = analyse_shard(args)
        _publish([(args.out, _canonical(payload))])
        summary = {"schema": payload["schema"], "rows": len(payload["rows"])}
    else:
        selection = json.loads(args.selection.read_text(encoding="utf-8"))
        shards = [json.loads(path.read_text(encoding="utf-8")) for path in args.shard]
        report, region, seeds = aggregate(
            selection,
            shards,
            min_regret_cp=args.min_regret_cp,
            max_control_regret_cp=args.max_control_regret_cp,
            min_error_openings=args.min_error_openings,
            min_discovery_hits=args.min_discovery_hits,
            discovery_risk_ratio=args.discovery_risk_ratio,
            confirm_risk_ratio=args.confirm_risk_ratio,
            min_confirmed_buckets=args.min_confirmed_buckets,
            max_region_buckets=args.max_region_buckets,
            match_seed=args.match_seed,
        )
        _publish(
            [
                (args.report, _canonical(report)),
                (args.region, _canonical(region)),
                (args.seeds, seeds),
            ]
        )
        summary = {
            "schema": report["schema"],
            "verdict": report["verdict"],
            "fit_authorized": report["fit_authorized"],
        }
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
