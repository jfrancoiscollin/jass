#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Run and aggregate the stable +2 causal conversion matrix.

The matrix is deliberately role based.  The first engine in ``ARM_ROLES``
always plays the materially advantaged side, independently of colour; the
second engine plays the disadvantaged side.  Every reported outcome is then
mapped back to the advantaged (+2) side's point of view.

The executable contract is intentionally narrow: exactly 384 independently
proven stable positions, 12 TOP3 cells of 32 positions, fixed depth 10, 16
shards, a 120 second game cap and a 400 ply cap.  A structural shortfall,
engine exception, illegal move, wall-clock cap or ply cap can therefore never
silently become a scientific draw.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import os
import random
import struct
import sys
import tempfile
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Mapping, Sequence


POSITION_COUNT = 384
SHARD_COUNT = 16
DEPTH = 10
GAME_TIMEOUT_S = 120.0
MAX_PLIES = 400
ARMS = (
    "scan_scan", "scan_g4", "g4_scan",
    "g0_g0", "g4_g0", "g0_g4", "g4_g4",
)
ARM_ROLES = {
    "scan_scan": ("scan", "scan"),
    "scan_g4": ("scan", "g4"),
    "g4_scan": ("g4", "scan"),
    "g0_g0": ("g0", "g0"),
    "g4_g0": ("g4", "g0"),
    "g0_g4": ("g0", "g4"),
    "g4_g4": ("g4", "g4"),
}
STRATA = ("16v18", "17v19", "18v20")
EXPECTED_CELLS = tuple(
    f"{stratum}|adv={adv}|stm={stm}"
    for stratum in STRATA
    for adv in ("W", "B")
    for stm in ("W", "B")
)
CAP_REASONS = {"game time cap", "ply cap"}
SALVAGE_DRAW_REASON = "adjudicated draw at 400-ply cap"
DRAW_REASONS = {"25-move rule", "3-fold repetition"}


def _load_calibrate_module():
    path = Path(__file__).with_name("calibrate_vs_scan.py")
    name = "stable_conversion_matrix_calibrate_vs_scan"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load referee module {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


CVS = _load_calibrate_module()
SCAN_HUB_PARAMS = dict(CVS.ScanEngine.RUNTIME_PARAMS)
SCAN_HUB_PARAMS_SHA256 = hashlib.sha256(
    json.dumps(
        SCAN_HUB_PARAMS, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
).hexdigest()


@dataclass(frozen=True)
class Position:
    index: int
    position_id: str
    fen: str
    cell: str
    stratum: str
    advantaged: str
    stm: str
    source_unit: str


@dataclass(frozen=True)
class PoolContract:
    pool_path: str
    proof_path: str
    pool_sha256: str
    proof_sha256: str
    positions: tuple[Position, ...]


@dataclass
class PlayerBundle:
    advantaged_player: object
    disadvantaged_player: object
    referee: object

    def close(self) -> None:
        seen: set[int] = set()
        for engine in (
            self.advantaged_player,
            self.disadvantaged_player,
            self.referee,
        ):
            if id(engine) in seen:
                continue
            seen.add(id(engine))
            try:
                engine.close()
            except Exception:
                pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def atomic_write_json(path: Path, payload: Mapping) -> None:
    atomic_write_text(
        path,
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
    )


def _board_identity(fen: str) -> tuple[str, str, dict]:
    stm, wm, wk, bm, bk = CVS.parse_jass_fen(fen)
    if stm not in {"W", "B"}:
        raise ValueError(f"bad side to move in FEN: {fen!r}")
    groups = [set(values) for values in (wm, wk, bm, bk)]
    occupied: set[int] = set()
    for values in groups:
        if any(square < 1 or square > 50 for square in values):
            raise ValueError(f"square outside 1..50 in FEN: {fen!r}")
        if occupied.intersection(values):
            raise ValueError(f"overlapping pieces in FEN: {fen!r}")
        occupied.update(values)

    def bitboard(values: Iterable[int]) -> int:
        result = 0
        for square in values:
            result |= 1 << (square - 1)
        return result

    key = struct.pack(
        "<QQQQB",
        bitboard(wm), bitboard(wk), bitboard(bm), bitboard(bk),
        0 if stm == "W" else 1,
    )

    def pieces(men: Sequence[int], kings: Sequence[int]) -> str:
        return ",".join(
            [*(str(square) for square in sorted(men)),
             *(f"K{square}" for square in sorted(kings))]
        )

    canonical = f"{stm}:W{pieces(wm, wk)}:B{pieces(bm, bk)}"
    facts = {
        "stm": stm,
        "white_men": len(wm),
        "black_men": len(bm),
        "white_kings": len(wk),
        "black_kings": len(bk),
        "white_value": len(wm) + 3 * len(wk),
        "black_value": len(bm) + 3 * len(bk),
        "white_pieces": len(wm) + len(wk),
        "black_pieces": len(bm) + len(bk),
    }
    facts["advantaged"] = (
        "W" if facts["white_value"] > facts["black_value"] else
        "B" if facts["black_value"] > facts["white_value"] else None
    )
    facts["value_gap"] = abs(facts["white_value"] - facts["black_value"])
    facts["men_gap"] = abs(facts["white_men"] - facts["black_men"])
    facts["king_gap"] = abs(facts["white_kings"] - facts["black_kings"])
    return canonical, hashlib.sha256(key).hexdigest(), facts


def _load_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{line_number}: invalid JSON: {exc}") from exc
        if not isinstance(row, dict):
            raise ValueError(f"{path}:{line_number}: JSON row is not an object")
        rows.append(row)
    return rows


def load_pool_contract(pool_path: Path, proof_path: Path) -> PoolContract:
    fens = [
        line.split("#", 1)[0].strip()
        for line in pool_path.read_text(encoding="utf-8").splitlines()
        if line.split("#", 1)[0].strip()
    ]
    proofs = _load_jsonl(proof_path)
    if len(fens) != POSITION_COUNT or len(proofs) != POSITION_COUNT:
        raise ValueError(
            f"strict floor: expected {POSITION_COUNT} pool/proof rows, "
            f"got {len(fens)}/{len(proofs)}"
        )

    positions: list[Position] = []
    seen_ids: set[str] = set()
    seen_sources: set[str] = set()
    counts: Counter = Counter()
    for index, (fen, proof) in enumerate(zip(fens, proofs)):
        if proof.get("schema") != 1:
            raise ValueError(f"proof row {index}: unsupported schema")
        canonical, position_id, facts = _board_identity(fen)
        proof_fen, proof_id, _ = _board_identity(str(proof.get("fen", "")))
        if proof_id != position_id or proof_fen != canonical:
            raise ValueError(f"proof row {index}: FEN mismatch")
        if proof.get("position_id") != position_id:
            raise ValueError(f"proof row {index}: position_id mismatch")
        if position_id in seen_ids:
            raise ValueError(f"proof row {index}: duplicate position_id")
        seen_ids.add(position_id)

        material = proof.get("material")
        if not isinstance(material, dict):
            raise ValueError(f"proof row {index}: missing material evidence")
        keys = (
            "white_men", "black_men", "white_kings", "black_kings",
            "white_value", "black_value", "white_pieces", "black_pieces",
            "advantaged", "value_gap", "men_gap", "king_gap",
        )
        if any(material.get(key) != facts[key] for key in keys):
            raise ValueError(f"proof row {index}: material evidence mismatch")
        if (
            facts["value_gap"] != 2 or facts["men_gap"] != 2
            or facts["king_gap"] != 0 or facts["white_kings"] + facts["black_kings"] != 0
            or facts["advantaged"] not in {"W", "B"}
        ):
            raise ValueError(f"proof row {index}: not an all-men stable +2 position")

        low, high = sorted((facts["white_pieces"], facts["black_pieces"]))
        stratum = f"{low}v{high}"
        cell = f"{stratum}|adv={facts['advantaged']}|stm={facts['stm']}"
        if cell not in EXPECTED_CELLS or proof.get("cell") != cell:
            raise ValueError(f"proof row {index}: unexpected cell {proof.get('cell')!r}")
        stability = proof.get("stability") or {}
        if not (
            stability.get("scope") == "all_legal_first_plies_only"
            and stability.get("certifies_theoretical_win") is False
            and stability.get("gap_after_any_legal_first_ply") == 2
            and stability.get("quiet_white") is True
            and stability.get("quiet_black") is True
            and stability.get("immediate_promotion_white") is False
            and stability.get("immediate_promotion_black") is False
        ):
            raise ValueError(f"proof row {index}: stability proof is incomplete")
        provenance = proof.get("provenance") or {}
        if provenance.get("source_outcome_not_used_for_selection") is not True:
            raise ValueError(f"proof row {index}: outcome-blind selection proof missing")
        source_unit = provenance.get("source_unit")
        if not isinstance(source_unit, str) or not source_unit:
            raise ValueError(f"proof row {index}: source_unit missing")
        if source_unit in seen_sources:
            raise ValueError(f"proof row {index}: duplicate source_unit")
        seen_sources.add(source_unit)

        counts[cell] += 1
        positions.append(Position(
            index=index,
            position_id=position_id,
            fen=canonical,
            cell=cell,
            stratum=stratum,
            advantaged=str(facts["advantaged"]),
            stm=str(facts["stm"]),
            source_unit=source_unit,
        ))

    if set(counts) != set(EXPECTED_CELLS) or any(
        counts[cell] != 32 for cell in EXPECTED_CELLS
    ):
        raise ValueError(f"strict cells: expected 12x32, got {dict(sorted(counts.items()))}")
    return PoolContract(
        pool_path=str(pool_path),
        proof_path=str(proof_path),
        pool_sha256=sha256_file(pool_path),
        proof_sha256=sha256_file(proof_path),
        positions=tuple(positions),
    )


def outcome_from_advantaged(outcome_white: str, advantaged: str) -> str:
    if outcome_white not in {"W", "D", "L"}:
        raise ValueError(f"invalid white outcome {outcome_white!r}")
    if advantaged == "W":
        return outcome_white
    if advantaged == "B":
        return {"W": "L", "D": "D", "L": "W"}[outcome_white]
    raise ValueError(f"invalid advantaged colour {advantaged!r}")


def role_assignment(
    arm: str, advantaged: str, advantaged_player: object, disadvantaged_player: object,
) -> tuple[object, object, dict]:
    if arm not in ARM_ROLES:
        raise ValueError(f"unknown arm {arm!r}")
    if advantaged not in {"W", "B"}:
        raise ValueError(f"bad advantaged colour {advantaged!r}")
    adv_kind, disadv_kind = ARM_ROLES[arm]
    if advantaged == "W":
        white, black = advantaged_player, disadvantaged_player
    else:
        white, black = disadvantaged_player, advantaged_player
    return white, black, {
        "advantaged_engine": adv_kind,
        "disadvantaged_engine": disadv_kind,
        "white_role": "advantaged" if advantaged == "W" else "disadvantaged",
        "black_role": "disadvantaged" if advantaged == "W" else "advantaged",
    }


def _make_player(kind: str, label: str, args: argparse.Namespace):
    if kind == "scan":
        return CVS.ScanEngine(args.scan, label=label, no_book=True, bb_size=0)
    pattern = args.g0 if kind == "g0" else args.g4 if kind == "g4" else None
    if pattern is None:
        raise ValueError(f"unknown player kind {kind!r}")
    return CVS.JassEngine(
        args.jass, label=label, no_book=True, pattern_path=pattern,
        search_params=args.search_params, threads=1,
    )


def create_player_bundle(arm: str, args: argparse.Namespace) -> PlayerBundle:
    adv_kind, disadv_kind = ARM_ROLES[arm]
    made: list[object] = []
    try:
        adv = _make_player(adv_kind, f"{arm}-adv-{adv_kind}", args)
        made.append(adv)
        disadv = _make_player(disadv_kind, f"{arm}-disadv-{disadv_kind}", args)
        made.append(disadv)
        referee = CVS.Referee(args.jass)
        made.append(referee)
        return PlayerBundle(adv, disadv, referee)
    except Exception:
        for engine in made:
            try:
                engine.close()
            except Exception:
                pass
        raise


def play_game_canonical(*args, **kwargs):
    """Delegate adjudication to the single canonical referee implementation."""
    return CVS.play_game(*args, **kwargs)


def _base_result_row(
    position: Position, arm: str, shard: int, hashes: Mapping, roles: Mapping,
) -> dict:
    return {
        "schema": 1,
        "arm": arm,
        "index": position.index,
        "shard": shard,
        "shards": SHARD_COUNT,
        "position_id": position.position_id,
        "fen": position.fen,
        "cell": position.cell,
        "stratum": position.stratum,
        "advantaged": position.advantaged,
        "source_unit": position.source_unit,
        "roles": dict(roles),
        "outcome_white": None,
        "outcome_plus2": None,
        "reason": "",
        "plies": 0,
        "elapsed_s": 0.0,
        "error": None,
        "config": {
            "depth": DEPTH,
            "game_timeout_s": GAME_TIMEOUT_S,
            "max_plies": MAX_PLIES,
            "search_params_sha256": (hashes.get("search_params") or {}).get("sha256"),
            "scan_runtime_sha256": (hashes.get("scan_runtime") or {}).get("sha256"),
            "scan_hub_params_sha256": (hashes.get("scan_hub_params") or {}).get("sha256"),
        },
        "hashes": dict(hashes),
    }


def error_result_row(
    position: Position, arm: str, shard: int, hashes: Mapping, error: BaseException | str,
) -> dict:
    adv_kind, disadv_kind = ARM_ROLES[arm]
    row = _base_result_row(position, arm, shard, hashes, {
        "advantaged_engine": adv_kind,
        "disadvantaged_engine": disadv_kind,
        "white_role": "advantaged" if position.advantaged == "W" else "disadvantaged",
        "black_role": "disadvantaged" if position.advantaged == "W" else "advantaged",
    })
    detail = str(error)
    if isinstance(error, BaseException):
        detail = f"{type(error).__name__}: {error}"
    row["reason"] = "engine exception"
    row["error"] = detail
    return row


def play_position(
    position: Position,
    arm: str,
    shard: int,
    hashes: Mapping,
    bundle: PlayerBundle,
    play_game: Callable = play_game_canonical,
    clock: Callable[[], float] = time.monotonic,
) -> dict:
    white, black, roles = role_assignment(
        arm, position.advantaged,
        bundle.advantaged_player, bundle.disadvantaged_player,
    )
    row = _base_result_row(position, arm, shard, hashes, roles)
    started = clock()
    try:
        game = play_game(
            white, black, bundle.referee, position.fen,
            depth=DEPTH, max_plies=MAX_PLIES, game_timeout_s=GAME_TIMEOUT_S,
        )
        row["outcome_white"] = game.outcome
        row["outcome_plus2"] = outcome_from_advantaged(
            game.outcome, position.advantaged,
        )
        row["reason"] = game.reason
        row["plies"] = game.plies
        if str(game.reason).startswith("illegal move"):
            row["error"] = f"referee rejected engine move: {game.reason}"
        elif str(game.reason).startswith("no legal move from"):
            try:
                if bundle.referee.has_legal_moves():
                    row["error"] = (
                        "engine returned no move while referee found legal moves: "
                        + game.reason
                    )
            except Exception as exc:
                row["error"] = f"terminal-state verification failed: {type(exc).__name__}: {exc}"
    except Exception as exc:
        row["reason"] = "engine exception"
        row["error"] = f"{type(exc).__name__}: {exc}"
    row["elapsed_s"] = round(max(0.0, clock() - started), 6)
    return row


def _path_hash_record(path: str) -> dict:
    target = Path(path)
    try:
        return {"path": str(target.resolve()), "sha256": sha256_file(target), "error": None}
    except Exception as exc:
        return {"path": str(target), "sha256": None,
                "error": f"{type(exc).__name__}: {exc}"}


def _declared_sha256_record(value: str, label: str) -> dict:
    normalized = value.lower()
    valid = (
        len(normalized) == 64
        and all(char in "0123456789abcdef" for char in normalized)
    )
    return {
        "sha256": normalized if valid else None,
        "error": None if valid else f"{label} is not a lowercase SHA256",
    }


def run_hashes(contract: PoolContract, args: argparse.Namespace) -> dict:
    search_bytes = args.search_params.encode("utf-8")
    return {
        "pool_sha256": contract.pool_sha256,
        "proof_sha256": contract.proof_sha256,
        "jass": _path_hash_record(args.jass),
        "scan": _path_hash_record(args.scan),
        "scan_runtime": _declared_sha256_record(
            args.scan_runtime_sha256, "scan runtime fingerprint",
        ),
        "scan_hub_params": {
            "sha256": SCAN_HUB_PARAMS_SHA256,
            "params": SCAN_HUB_PARAMS,
            "error": None,
        },
        "g0": _path_hash_record(args.g0),
        "g4": _path_hash_record(args.g4),
        "search_params": {
            "sha256": hashlib.sha256(search_bytes).hexdigest(),
            "bytes": len(search_bytes),
        },
        "matrix_runner": _path_hash_record(str(Path(__file__))),
        "referee_harness": _path_hash_record(
            str(Path(__file__).with_name("calibrate_vs_scan.py"))
        ),
    }


def _technical_row(row: Mapping) -> bool:
    return bool(row.get("error")) or str(row.get("reason", "")).lower() in CAP_REASONS


def _write_progress(
    path: Path | None, *, arm: str, shard: int, completed: int, expected: int,
    started: float, error_count: int, final: bool = False,
) -> None:
    if path is None:
        return
    elapsed = max(0.0, time.monotonic() - started)
    rate = completed / elapsed if elapsed > 0 and completed else 0.0
    eta = (expected - completed) / rate if rate > 0 else None
    atomic_write_json(path, {
        "schema": 1,
        "arm": arm,
        "shard": shard,
        "shards": SHARD_COUNT,
        "completed": completed,
        "expected": expected,
        "elapsed_s": round(elapsed, 3),
        "games_per_second": round(rate, 6),
        "eta_s": round(eta, 3) if eta is not None else None,
        "errors_or_caps": error_count,
        "status": ("technical_failure" if error_count else "complete") if final else "running",
    })


def run_shard(
    contract: PoolContract,
    args: argparse.Namespace,
    bundle_factory: Callable[[str, argparse.Namespace], PlayerBundle] = create_player_bundle,
) -> tuple[list[dict], bool]:
    if args.arm not in ARMS:
        raise ValueError(f"unknown arm {args.arm!r}")
    if not 0 <= args.shard_index < SHARD_COUNT:
        raise ValueError(f"--shard-index must be in 0..{SHARD_COUNT - 1}")
    if (
        args.depth != DEPTH or args.max_plies != MAX_PLIES
        or args.game_timeout != GAME_TIMEOUT_S or args.nshards != SHARD_COUNT
    ):
        raise ValueError(
            "fixed contract requires depth=10, max-plies=400, "
            "game-timeout=120 and nshards=16"
        )
    selected = [
        position for position in contract.positions
        if position.index % SHARD_COUNT == args.shard_index
    ]
    if len(selected) != POSITION_COUNT // SHARD_COUNT:
        raise ValueError(
            f"shard contract broken: expected {POSITION_COUNT // SHARD_COUNT}, got {len(selected)}"
        )
    hashes = run_hashes(contract, args)
    missing = [
        name for name in (
            "jass", "scan", "scan_runtime", "scan_hub_params", "g0", "g4",
        )
        if hashes[name]["error"]
    ]
    started = time.monotonic()
    progress_path = Path(args.progress_file) if args.progress_file else None
    rows: list[dict] = []
    errors = 0
    progress_errors: list[str] = []
    bundle: PlayerBundle | None = None
    init_error: BaseException | str | None = None
    if missing:
        init_error = "missing/unhashable inputs: " + ", ".join(missing)
    else:
        try:
            bundle = bundle_factory(args.arm, args)
        except Exception as exc:
            init_error = exc

    try:
        try:
            _write_progress(
                progress_path, arm=args.arm, shard=args.shard_index,
                completed=0, expected=len(selected), started=started, error_count=0,
            )
        except Exception as exc:
            progress_errors.append(f"progress init: {type(exc).__name__}: {exc}")
        for position in selected:
            if init_error is not None or bundle is None:
                row = error_result_row(
                    position, args.arm, args.shard_index, hashes,
                    init_error or "player bundle unavailable",
                )
            else:
                row = play_position(
                    position, args.arm, args.shard_index, hashes, bundle,
                )
            rows.append(row)
            errors += int(_technical_row(row))
            try:
                _write_progress(
                    progress_path, arm=args.arm, shard=args.shard_index,
                    completed=len(rows), expected=len(selected), started=started,
                    error_count=errors,
                )
            except Exception as exc:
                progress_errors.append(
                    f"progress after game {len(rows)}: {type(exc).__name__}: {exc}"
                )
    finally:
        if bundle is not None:
            bundle.close()
        if progress_errors and rows:
            previous = rows[0].get("error")
            rows[0]["error"] = "; ".join(
                ([str(previous)] if previous else []) + progress_errors
            )
            errors = sum(_technical_row(row) for row in rows)
        atomic_write_text(
            Path(args.output),
            "".join(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n" for row in rows),
        )
        try:
            _write_progress(
                progress_path, arm=args.arm, shard=args.shard_index,
                completed=len(rows), expected=len(selected), started=started,
                error_count=errors, final=True,
            )
        except Exception:
            pass
    return rows, errors > 0


def outcome_value(outcome: str) -> int:
    try:
        return {"W": 1, "D": 0, "L": -1}[outcome]
    except KeyError as exc:
        raise ValueError(f"invalid +2 outcome {outcome!r}") from exc


def wdl_stats(outcomes: Sequence[str]) -> dict:
    if not outcomes:
        raise ValueError("n=0 is not a statistic")
    counts = Counter(outcomes)
    if set(counts) - {"W", "D", "L"}:
        raise ValueError(f"invalid outcomes: {dict(counts)}")
    n = len(outcomes)
    wins, draws, losses = counts["W"], counts["D"], counts["L"]
    decisive = wins + losses
    return {
        "n": n,
        "W": wins,
        "D": draws,
        "L": losses,
        "win_rate": wins / n,
        "draw_rate": draws / n,
        "loss_rate": losses / n,
        "score": (wins + 0.5 * draws) / n,
        "w_minus_l_raw": wins - losses,
        "w_minus_l_normalized": (wins - losses) / n,
        "decisive_win_rate": wins / decisive if decisive else None,
    }


def numeric_summary(values: Sequence[float | int]) -> dict:
    if not values:
        raise ValueError("n=0 is not a numeric summary")
    numeric = [float(value) for value in values]
    return {
        "min": min(numeric),
        "median": _quantile(numeric, 0.5),
        "p95": _quantile(numeric, 0.95),
        "max": max(numeric),
        "mean": sum(numeric) / len(numeric),
    }


def scoped_stats(rows_by_id: Mapping[str, Mapping], positions: Sequence[Position]) -> dict:
    def block(selected: Sequence[Position]) -> dict:
        return wdl_stats([str(rows_by_id[pos.position_id]["outcome_plus2"]) for pos in selected])

    global_stats = block(positions)
    global_rows = [rows_by_id[position.position_id] for position in positions]
    global_stats["termination_reasons"] = dict(sorted(Counter(
        str(row["reason"]) for row in global_rows
    ).items()))
    global_stats["plies"] = numeric_summary([int(row["plies"]) for row in global_rows])
    global_stats["elapsed_s"] = numeric_summary([
        float(row["elapsed_s"]) for row in global_rows
    ])
    return {
        "global": global_stats,
        "strata": {
            stratum: block([pos for pos in positions if pos.stratum == stratum])
            for stratum in STRATA
        },
        "cells": {
            cell: block([pos for pos in positions if pos.cell == cell])
            for cell in EXPECTED_CELLS
        },
    }


def _quantile(values: Sequence[float], q: float) -> float:
    if not values:
        raise ValueError("quantile of empty sequence")
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    point = (len(ordered) - 1) * q
    lower = int(point)
    upper = min(lower + 1, len(ordered) - 1)
    weight = point - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def _effect_values(rows: Mapping[str, Mapping[str, Mapping]], ids: Sequence[str]) -> dict[str, list[int]]:
    values = {
        arm: {pid: outcome_value(str(rows[arm][pid]["outcome_plus2"])) for pid in ids}
        for arm in ARMS
    }
    return {
        "attack": [values["g4_g0"][pid] - values["g0_g0"][pid] for pid in ids],
        "defense": [values["g0_g0"][pid] - values["g0_g4"][pid] for pid in ids],
        "joint": [values["g4_g4"][pid] - values["g0_g0"][pid] for pid in ids],
        "interaction": [
            values["g4_g4"][pid] - values["g4_g0"][pid]
            - values["g0_g4"][pid] + values["g0_g0"][pid]
            for pid in ids
        ],
        "scan_attack_vs_g4": [
            values["scan_g4"][pid] - values["g4_g4"][pid] for pid in ids
        ],
        "scan_defense_vs_g4": [
            values["g4_g4"][pid] - values["g4_scan"][pid] for pid in ids
        ],
        "scan_joint_vs_g4": [
            values["scan_scan"][pid] - values["g4_g4"][pid] for pid in ids
        ],
    }


def _bootstrap_effects(
    rows: Mapping[str, Mapping[str, Mapping]],
    selected: Sequence[Position],
    samples: int,
    seed: int,
    scope_name: str,
) -> dict:
    ids = [pos.position_id for pos in selected]
    effects = _effect_values(rows, ids)
    buckets: dict[str, list[str]] = defaultdict(list)
    for pos in selected:
        buckets[pos.cell].append(pos.position_id)
    scope_seed = seed ^ int(hashlib.sha256(scope_name.encode()).hexdigest()[:16], 16)
    rng = random.Random(scope_seed)
    boot: dict[str, list[float]] = {name: [] for name in effects}
    for _ in range(samples):
        sampled: list[str] = []
        for cell in sorted(buckets):
            cell_ids = buckets[cell]
            sampled.extend(rng.choice(cell_ids) for _ in cell_ids)
        sampled_effects = _effect_values(rows, sampled)
        for name, values in sampled_effects.items():
            boot[name].append(sum(values) / len(values))

    result = {}
    for name, values in effects.items():
        estimate = sum(values) / len(values)
        result[name] = {
            "n_pairs": len(values),
            "raw_sum": sum(values),
            "estimate": estimate,
            "ci95": (
                [_quantile(boot[name], 0.025), _quantile(boot[name], 0.975)]
                if samples else None
            ),
            "bootstrap_samples": samples,
        }
    return result


def paired_deltas(
    rows: Mapping[str, Mapping[str, Mapping]],
    positions: Sequence[Position],
    samples: int,
    seed: int,
) -> dict:
    return {
        "metric": "paired normalized W-L from the materially advantaged (+2) POV",
        "formulas": {
            "attack": "g4_g0 - g0_g0",
            "defense": "g0_g0 - g0_g4 (positive means stronger defense)",
            "joint": "g4_g4 - g0_g0",
            "interaction": "g4_g4 - g4_g0 - g0_g4 + g0_g0",
            "scan_attack_vs_g4": "scan_g4 - g4_g4",
            "scan_defense_vs_g4": "g4_g4 - g4_scan (positive means stronger Scan defense)",
            "scan_joint_vs_g4": "scan_scan - g4_g4",
        },
        "interpretation": {
            "attack": "role-localized G4-versus-G0 conversion effect",
            "defense": "role-localized G4-versus-G0 defense effect",
            "joint": "joint G4-versus-G0 same-engine effect",
            "interaction": "factorial attack-by-defense interaction",
            "scan_attack_vs_g4": "role-localized Scan-versus-G4 conversion effect",
            "scan_defense_vs_g4": "role-localized Scan-versus-G4 defense effect",
            "scan_joint_vs_g4": (
                "paired joint-regime Scan-versus-G4 contrast; both roles change"
            ),
        },
        "global": _bootstrap_effects(rows, positions, samples, seed, "global"),
        "strata": {
            stratum: _bootstrap_effects(
                rows, [pos for pos in positions if pos.stratum == stratum],
                samples, seed, f"stratum:{stratum}",
            )
            for stratum in STRATA
        },
        "cells": {
            cell: _bootstrap_effects(
                rows, [pos for pos in positions if pos.cell == cell],
                samples, seed, f"cell:{cell}",
            )
            for cell in EXPECTED_CELLS
        },
    }


def validate_arm_rows(
    contract: PoolContract,
    arm: str,
    rows: Sequence[dict],
    *,
    additional_draw_reasons: frozenset[str] = frozenset(),
) -> tuple[dict[str, dict], list[str]]:
    failures: list[str] = []
    accepted_draw_reasons = DRAW_REASONS | set(additional_draw_reasons)
    if len(rows) != POSITION_COUNT:
        failures.append(f"{arm}: strict floor expected {POSITION_COUNT} rows, got {len(rows)}")
    expected = {position.position_id: position for position in contract.positions}
    by_id: dict[str, dict] = {}
    for row_number, row in enumerate(rows):
        position_id = row.get("position_id")
        if not isinstance(position_id, str):
            failures.append(f"{arm}: row {row_number} has no position_id")
            continue
        if position_id in by_id:
            failures.append(f"{arm}: duplicate position_id {position_id}")
            continue
        by_id[position_id] = row
        position = expected.get(position_id)
        if position is None:
            failures.append(f"{arm}: foreign position_id {position_id}")
            continue
        expected_shard = position.index % SHARD_COUNT
        checks = {
            "schema": 1,
            "arm": arm,
            "index": position.index,
            "shard": expected_shard,
            "shards": SHARD_COUNT,
            "cell": position.cell,
            "stratum": position.stratum,
            "advantaged": position.advantaged,
            "source_unit": position.source_unit,
            "fen": position.fen,
        }
        for key, value in checks.items():
            if row.get(key) != value:
                failures.append(
                    f"{arm}:{position_id[:12]}: {key}={row.get(key)!r}, expected {value!r}"
                )
        config = row.get("config") or {}
        for key, value in {
            "depth": DEPTH,
            "game_timeout_s": GAME_TIMEOUT_S,
            "max_plies": MAX_PLIES,
        }.items():
            if config.get(key) != value:
                failures.append(f"{arm}:{position_id[:12]}: config {key} mismatch")
        hashes = row.get("hashes") or {}
        search_record = hashes.get("search_params") or {}
        if config.get("search_params_sha256") != search_record.get("sha256"):
            failures.append(f"{arm}:{position_id[:12]}: search params config/hash mismatch")
        scan_runtime_record = hashes.get("scan_runtime") or {}
        if config.get("scan_runtime_sha256") != scan_runtime_record.get("sha256"):
            failures.append(f"{arm}:{position_id[:12]}: Scan runtime config/hash mismatch")
        scan_params_record = hashes.get("scan_hub_params") or {}
        if config.get("scan_hub_params_sha256") != scan_params_record.get("sha256"):
            failures.append(f"{arm}:{position_id[:12]}: Scan HUB params config/hash mismatch")
        if hashes.get("pool_sha256") != contract.pool_sha256:
            failures.append(f"{arm}:{position_id[:12]}: pool hash mismatch")
        if hashes.get("proof_sha256") != contract.proof_sha256:
            failures.append(f"{arm}:{position_id[:12]}: proof hash mismatch")
        if not row.get("reason"):
            failures.append(f"{arm}:{position_id[:12]}: empty reason")
        if not isinstance(row.get("plies"), int) or row.get("plies", -1) < 0:
            failures.append(f"{arm}:{position_id[:12]}: invalid plies")
        if (
            not isinstance(row.get("elapsed_s"), (int, float))
            or row.get("elapsed_s", -1) < 0
        ):
            failures.append(f"{arm}:{position_id[:12]}: invalid elapsed_s")
        adv_kind, disadv_kind = ARM_ROLES[arm]
        expected_roles = {
            "advantaged_engine": adv_kind,
            "disadvantaged_engine": disadv_kind,
            "white_role": "advantaged" if position.advantaged == "W" else "disadvantaged",
            "black_role": "disadvantaged" if position.advantaged == "W" else "advantaged",
        }
        if row.get("roles") != expected_roles:
            failures.append(f"{arm}:{position_id[:12]}: role assignment mismatch")
        if not row.get("error"):
            outcome_white = row.get("outcome_white")
            if outcome_white not in {"W", "D", "L"}:
                failures.append(f"{arm}:{position_id[:12]}: invalid white outcome")
            else:
                expected_plus2 = outcome_from_advantaged(
                    str(outcome_white), position.advantaged,
                )
                if row.get("outcome_plus2") != expected_plus2:
                    failures.append(f"{arm}:{position_id[:12]}: +2 perspective mismatch")
                reason = str(row.get("reason", ""))
                if reason in accepted_draw_reasons | CAP_REASONS and outcome_white != "D":
                    failures.append(
                        f"{arm}:{position_id[:12]}: draw reason/result mismatch"
                    )
                if reason.startswith("no legal move from"):
                    plies = row.get("plies")
                    if isinstance(plies, int) and plies >= 0:
                        loser = position.stm if plies % 2 == 0 else (
                            "B" if position.stm == "W" else "W"
                        )
                        expected_terminal = "L" if loser == "W" else "W"
                        if outcome_white != expected_terminal:
                            failures.append(
                                f"{arm}:{position_id[:12]}: "
                                "terminal reason/result mismatch"
                            )
                        loser_role = (
                            "adv" if loser == position.advantaged else "disadv"
                        )
                        loser_kind = (
                            ARM_ROLES[arm][0]
                            if loser_role == "adv" else ARM_ROLES[arm][1]
                        )
                        expected_reason = (
                            f"no legal move from {arm}-{loser_role}-{loser_kind}"
                        )
                        if reason != expected_reason:
                            failures.append(
                                f"{arm}:{position_id[:12]}: "
                                "terminal loser label mismatch"
                            )
                elif reason.startswith("illegal move"):
                    failures.append(
                        f"{arm}:{position_id[:12]}: illegal move lacks technical error"
                    )
                elif reason not in accepted_draw_reasons | CAP_REASONS:
                    failures.append(
                        f"{arm}:{position_id[:12]}: unrecognized result reason {reason!r}"
                    )
    missing = set(expected) - set(by_id)
    extra = set(by_id) - set(expected)
    if missing:
        failures.append(f"{arm}: missing {len(missing)} expected positions")
    if extra:
        failures.append(f"{arm}: has {len(extra)} foreign positions")
    return by_id, failures


def aggregate_rows(
    contract: PoolContract,
    rows_by_arm: Mapping[str, Sequence[dict]],
    *,
    bootstrap_samples: int = 5000,
    bootstrap_seed: int = 20260723,
    result_provenance: Sequence[dict] = (),
    additional_draw_reasons: frozenset[str] = frozenset(),
) -> dict:
    failures: list[str] = []
    if set(rows_by_arm) != set(ARMS):
        failures.append(
            f"arms mismatch: expected {list(ARMS)}, got {sorted(rows_by_arm)}"
        )
    validated: dict[str, dict[str, dict]] = {}
    for arm in ARMS:
        by_id, arm_failures = validate_arm_rows(
            contract,
            arm,
            rows_by_arm.get(arm, ()),
            additional_draw_reasons=additional_draw_reasons,
        )
        validated[arm] = by_id
        failures.extend(arm_failures)

    expected_ids = {position.position_id for position in contract.positions}
    intersections = {arm: set(validated[arm]) for arm in ARMS}
    if any(ids != expected_ids for ids in intersections.values()):
        failures.append("all arms do not share the exact 384-position intersection")

    technical_rows: list[dict] = []
    for arm in ARMS:
        for position_id, row in validated[arm].items():
            if _technical_row(row):
                technical_rows.append({
                    "arm": arm,
                    "position_id": position_id,
                    "reason": row.get("reason"),
                    "error": row.get("error"),
                })
    if technical_rows:
        failures.append(
            f"zero-error/zero-cap contract failed: {len(technical_rows)} technical rows"
        )
    error_count = sum(
        bool(row.get("error"))
        for arm in ARMS for row in validated[arm].values()
    )
    game_time_caps = sum(
        str(row.get("reason", "")).lower() == "game time cap"
        for arm in ARMS for row in validated[arm].values()
    )
    ply_caps = sum(
        str(row.get("reason", "")).lower() == "ply cap"
        for arm in ARMS for row in validated[arm].values()
    )

    engine_hashes: dict[str, str | None] = {}
    expected_hash_rows = POSITION_COUNT * len(ARMS)
    for name in (
        "jass", "scan", "scan_runtime", "scan_hub_params",
        "g0", "g4", "search_params",
        "matrix_runner", "referee_harness",
    ):
        values: set[str] = set()
        missing = 0
        for arm in ARMS:
            for row in validated[arm].values():
                hashes = row.get("hashes")
                record = hashes.get(name) if isinstance(hashes, Mapping) else None
                value = record.get("sha256") if isinstance(record, Mapping) else None
                if (
                    not isinstance(value, str) or len(value) != 64
                    or any(char not in "0123456789abcdef" for char in value.lower())
                ):
                    missing += 1
                else:
                    values.add(value.lower())
        if missing:
            failures.append(
                f"provenance {name}: {missing}/{expected_hash_rows} "
                "rows have a missing or invalid SHA256"
            )
        if len(values) != 1:
            failures.append(f"provenance {name}: expected one common hash, got {sorted(values)}")
            engine_hashes[name] = None
        elif missing:
            engine_hashes[name] = None
        else:
            engine_hashes[name] = next(iter(values))

    report = {
        "schema": 1,
        "status": "technical_failure" if failures else "ok",
        "technical_status": "technical_failure" if failures else "complete",
        "gate_ready": not failures,
        "games_per_arm": POSITION_COUNT if all(
            len(rows_by_arm.get(arm, ())) == POSITION_COUNT for arm in ARMS
        ) else None,
        "total_games": sum(len(rows_by_arm.get(arm, ())) for arm in ARMS),
        "errors": error_count,
        "game_time_caps": game_time_caps,
        "ply_caps": ply_caps,
        "contract": {
            "positions": POSITION_COUNT,
            "cells": 12,
            "positions_per_cell": 32,
            "arms": list(ARMS),
            "depth": DEPTH,
            "game_timeout_s": GAME_TIMEOUT_S,
            "max_plies": MAX_PLIES,
            "shards": SHARD_COUNT,
        },
        "estimand": {
            "name": "equal_weight_12_cell_standardized",
            "population": (
                "the selected 384-position reachable selfplay-sampled pool"
            ),
            "unit": "one selected position per immutable opening_id",
            "weighting": "12 fixed cells with 32 positions each",
            "conditioning": [
                "source=cpx62-0842 standard self-play G1-G4",
                "material=exactly +2 men with no kings",
                "piece strata=16v18,17v19,18v20",
                "no capture or promotion for either colour on the first ply",
            ],
            "natural_corpus_prevalence_estimate": False,
            "theoretical_win_probability": False,
        },
        "bootstrap": {
            "samples": bootstrap_samples,
            "seed": bootstrap_seed,
            "resampling_unit": "position within cell",
            "stratification": "12 fixed cells",
            "pairing": "all arms share each resampled position",
            "scope_seed_derivation": "seed XOR sha256(scope_name)[:16]",
            "interval": "percentile_95",
        },
        "inference": {
            "primary": "paired_deltas.global.attack",
            "secondary": [
                "paired_deltas.global.defense",
                "paired_deltas.global.joint",
                "paired_deltas.global.interaction",
                "arms.scan_scan.global",
                "paired_deltas.global.scan_attack_vs_g4",
                "paired_deltas.global.scan_defense_vs_g4",
                "paired_deltas.global.scan_joint_vs_g4",
            ],
            "multiplicity": "none; every non-primary interval is exploratory",
        },
        "inputs": {
            "pool": {"path": contract.pool_path, "sha256": contract.pool_sha256},
            "proof": {"path": contract.proof_path, "sha256": contract.proof_sha256},
            "engines": engine_hashes,
            "results": list(result_provenance),
        },
        "technical_failures": failures,
        "technical_rows": technical_rows,
        "arms": {},
        "paired_deltas": None,
    }
    if not failures:
        report["arms"] = {
            arm: scoped_stats(validated[arm], contract.positions) for arm in ARMS
        }
        report["paired_deltas"] = paired_deltas(
            validated, contract.positions, bootstrap_samples, bootstrap_seed,
        )
    else:
        report["arms"] = {
            arm: {
                "rows": len(rows_by_arm.get(arm, ())),
                "unique_positions": len(validated[arm]),
                "technical_rows": sum(
                    _technical_row(row) for row in validated[arm].values()
                ),
                "stats": None,
            }
            for arm in ARMS
        }
    return report


def _sensitivity_snapshot(
    validated: Mapping[str, Mapping[str, Mapping]],
    contract: PoolContract,
    affected: Position,
) -> dict:
    arm_stats = scoped_stats(validated["g4_g4"], contract.positions)
    deltas = paired_deltas(validated, contract.positions, 0, 0)

    def effects(scope: Mapping[str, Mapping]) -> dict:
        return {
            name: {
                "estimate": value["estimate"],
                "raw_sum": value["raw_sum"],
                "n_pairs": value["n_pairs"],
            }
            for name, value in scope.items()
        }

    return {
        "g4_g4": {
            "global": arm_stats["global"],
            "affected_stratum": {
                "name": affected.stratum,
                **arm_stats["strata"][affected.stratum],
            },
            "affected_cell": {
                "name": affected.cell,
                **arm_stats["cells"][affected.cell],
            },
        },
        "paired_deltas": {
            "global": effects(deltas["global"]),
            "affected_stratum": {
                "name": affected.stratum,
                "effects": effects(deltas["strata"][affected.stratum]),
            },
            "affected_cell": {
                "name": affected.cell,
                "effects": effects(deltas["cells"][affected.cell]),
            },
        },
    }


def salvage_single_ply_cap(
    contract: PoolContract,
    rows_by_arm: Mapping[str, Sequence[dict]],
    *,
    expected_arm: str,
    expected_position_id: str,
    expected_cell: str,
    expected_plies: int = MAX_PLIES,
    bootstrap_samples: int = 10000,
    bootstrap_seed: int = 271828,
    result_provenance: Sequence[dict] = (),
    source: Mapping | None = None,
) -> dict:
    """Derive a matrix after explicitly adjudicating one pinned ply cap as D.

    The raw strict aggregation is always run first and must fail for exactly
    the one expected cap.  The returned report never upgrades the original
    zero-cap gate to passing.
    """
    strict = aggregate_rows(
        contract, rows_by_arm,
        bootstrap_samples=0,
        bootstrap_seed=bootstrap_seed,
        result_provenance=result_provenance,
    )
    expected_failure = "zero-error/zero-cap contract failed: 1 technical rows"
    expected_technical = {
        "arm": expected_arm,
        "position_id": expected_position_id,
        "reason": "ply cap",
        "error": None,
    }
    if (
        strict.get("technical_failures") != [expected_failure]
        or strict.get("technical_rows") != [expected_technical]
        or strict.get("errors") != 0
        or strict.get("game_time_caps") != 0
        or strict.get("ply_caps") != 1
    ):
        raise ValueError(
            "raw matrix is not the exact single-ply-cap failure authorized "
            f"for salvage: failures={strict.get('technical_failures')!r}, "
            f"technical_rows={strict.get('technical_rows')!r}"
        )
    if expected_arm not in ARMS:
        raise ValueError(f"invalid expected cap arm {expected_arm!r}")

    positions = {position.position_id: position for position in contract.positions}
    affected = positions.get(expected_position_id)
    if affected is None or affected.cell != expected_cell:
        raise ValueError("expected cap position/cell is absent from the pool contract")

    derived_rows = copy.deepcopy(dict(rows_by_arm))
    candidates = [
        row for row in derived_rows[expected_arm]
        if row.get("position_id") == expected_position_id
    ]
    if len(candidates) != 1:
        raise ValueError("expected exactly one matching cap row")
    cap = candidates[0]
    if (
        cap.get("reason") != "ply cap"
        or cap.get("error") is not None
        or cap.get("outcome_white") != "D"
        or cap.get("outcome_plus2") != "D"
        or cap.get("plies") != expected_plies
        or cap.get("cell") != expected_cell
    ):
        raise ValueError("pinned cap row content differs from the authorized adjudication")
    raw_row_sha256 = hashlib.sha256(
        (json.dumps(cap, sort_keys=True, separators=(",", ":")) + "\n").encode()
    ).hexdigest()
    cap["reason"] = SALVAGE_DRAW_REASON

    matrix = aggregate_rows(
        contract, derived_rows,
        bootstrap_samples=bootstrap_samples,
        bootstrap_seed=bootstrap_seed,
        result_provenance=result_provenance,
        additional_draw_reasons=frozenset({SALVAGE_DRAW_REASON}),
    )
    if not matrix["gate_ready"]:
        raise ValueError(
            "adjudicated matrix still fails structural/provenance validation: "
            f"{matrix['technical_failures']!r}"
        )
    matrix["status"] = "salvage_only"
    matrix["technical_status"] = "derived_complete"
    matrix["derived_analysis_ready"] = True
    matrix["gate_ready"] = False
    matrix["original_zero_cap_gate_ready"] = False

    validated = {
        arm: {row["position_id"]: row for row in derived_rows[arm]}
        for arm in ARMS
    }
    sensitivity = {}
    for outcome in ("W", "L"):
        scenario = copy.deepcopy(validated)
        scenario_row = scenario[expected_arm][expected_position_id]
        scenario_row["outcome_plus2"] = outcome
        scenario_row["outcome_white"] = (
            outcome if affected.advantaged == "W"
            else {"W": "L", "L": "W"}[outcome]
        )
        sensitivity[f"cap_as_{'win' if outcome == 'W' else 'loss'}"] = (
            _sensitivity_snapshot(scenario, contract, affected)
        )

    return {
        "schema": 1,
        "status": "salvage_complete",
        "scientific_matrix_ready": True,
        "original_gate": strict,
        "adjudication": {
            "policy": "single pinned 400-ply cap adjudicated as draw; no replay",
            "arm": expected_arm,
            "position_id": expected_position_id,
            "cell": expected_cell,
            "plies": expected_plies,
            "raw_outcome_white": "D",
            "raw_outcome_plus2": "D",
            "raw_reason": "ply cap",
            "raw_row_sha256": raw_row_sha256,
            "derived_reason": SALVAGE_DRAW_REASON,
            "changes_to_raw_games": 1,
        },
        "matrix": matrix,
        "sensitivity": {
            "description": (
                "point-estimate endpoints if the single capped game is "
                "assigned W or L to the materially advantaged (+2) side"
            ),
            **sensitivity,
        },
        "source": dict(source or {}),
        "authorization": {
            "training_continuation_authorized": False,
            "promotion_authorized": False,
            "automatic_next_job": None,
        },
    }


def _parse_result_spec(spec: str) -> tuple[str, Path]:
    if "=" not in spec:
        raise ValueError(f"--result must be ARM=PATH, got {spec!r}")
    arm, path = spec.split("=", 1)
    if arm not in ARMS or not path:
        raise ValueError(f"bad --result {spec!r}")
    return arm, Path(path)


def aggregate_command(args: argparse.Namespace) -> int:
    output = Path(args.output)
    try:
        if args.expected_per_arm != POSITION_COUNT:
            raise ValueError(f"--expected-per-arm must remain {POSITION_COUNT}")
        contract = load_pool_contract(Path(args.pool), Path(args.proof))
        rows_by_arm: dict[str, list[dict]] = defaultdict(list)
        provenance: list[dict] = []
        for spec in args.result or ():
            arm, path = _parse_result_spec(spec)
            rows_by_arm[arm].extend(_load_jsonl(path))
            provenance.append({
                "arm": arm,
                "path": str(path),
                "sha256": sha256_file(path),
            })
        for input_name in args.inputs or ():
            path = Path(input_name)
            rows = _load_jsonl(path)
            file_arms = {row.get("arm") for row in rows}
            if len(file_arms) != 1 or next(iter(file_arms)) not in ARMS:
                raise ValueError(f"{path}: cannot infer exactly one valid arm")
            arm = str(next(iter(file_arms)))
            rows_by_arm[arm].extend(rows)
            provenance.append({
                "arm": arm,
                "path": str(path),
                "sha256": sha256_file(path),
            })
        if not provenance:
            raise ValueError("at least one --result or --inputs path is required")
        run_config_record = None
        if args.run_config:
            run_config_path = Path(args.run_config)
            run_config = json.loads(run_config_path.read_text(encoding="utf-8"))
            if run_config.get("arms") != list(ARMS):
                raise ValueError("run config arm order/content mismatch")
            if run_config.get("games_per_arm") != POSITION_COUNT:
                raise ValueError("run config games_per_arm mismatch")
            budget = run_config.get("budget") or {}
            timeouts = run_config.get("timeouts_seconds") or {}
            if (
                budget.get("kind") != "fixed_depth" or budget.get("depth") != DEPTH
                or budget.get("max_plies") != MAX_PLIES
                or timeouts.get("game") != int(GAME_TIMEOUT_S)
                or run_config.get("nshards") != SHARD_COUNT
            ):
                raise ValueError("run config fixed-depth/runtime contract mismatch")
            configured_pool = run_config.get("pool") or {}
            if (
                configured_pool.get("pool_sha256") != contract.pool_sha256
                or configured_pool.get("proof_sha256") != contract.proof_sha256
            ):
                raise ValueError("run config pool/proof hash mismatch")
            expected_search_hash = (
                (run_config.get("evaluated_models") or {}).get("search_params_sha256")
            )
            observed_search_hashes = {
                ((row.get("hashes") or {}).get("search_params") or {}).get("sha256")
                for rows in rows_by_arm.values() for row in rows
            }
            if observed_search_hashes != {expected_search_hash}:
                raise ValueError(
                    "run config/result search fingerprint mismatch: "
                    f"expected {expected_search_hash}, got "
                    f"{sorted(map(str, observed_search_hashes))}"
                )
            scan_config = run_config.get("scan") or {}
            observed_scan_hashes = {
                ((row.get("hashes") or {}).get("scan") or {}).get("sha256")
                for rows in rows_by_arm.values() for row in rows
            }
            observed_runtime_hashes = {
                ((row.get("hashes") or {}).get("scan_runtime") or {}).get("sha256")
                for rows in rows_by_arm.values() for row in rows
            }
            observed_param_hashes = {
                ((row.get("hashes") or {}).get("scan_hub_params") or {}).get("sha256")
                for rows in rows_by_arm.values() for row in rows
            }
            if observed_scan_hashes != {scan_config.get("binary_sha256")}:
                raise ValueError("run config/result Scan binary hash mismatch")
            if observed_runtime_hashes != {scan_config.get("runtime_sha256")}:
                raise ValueError("run config/result Scan runtime hash mismatch")
            if (
                scan_config.get("hub_params") != SCAN_HUB_PARAMS
                or scan_config.get("hub_params_sha256") != SCAN_HUB_PARAMS_SHA256
                or observed_param_hashes != {SCAN_HUB_PARAMS_SHA256}
            ):
                raise ValueError("run config/result Scan HUB parameter contract mismatch")
            run_config_record = {
                "path": str(run_config_path),
                "sha256": sha256_file(run_config_path),
            }
        report = aggregate_rows(
            contract, rows_by_arm,
            bootstrap_samples=args.bootstrap_samples,
            bootstrap_seed=args.bootstrap_seed,
            result_provenance=provenance,
        )
        if run_config_record is not None:
            report["inputs"]["run_config"] = run_config_record
    except Exception as exc:
        report = {
            "schema": 1,
            "status": "technical_failure",
            "gate_ready": False,
            "technical_failures": [f"{type(exc).__name__}: {exc}"],
            "arms": {},
            "paired_deltas": None,
        }
    atomic_write_json(output, report)
    print(json.dumps({
        "status": report["status"],
        "gate_ready": report["gate_ready"],
        "output": str(output),
    }, sort_keys=True))
    return 0 if report["gate_ready"] else 2


def salvage_command(args: argparse.Namespace) -> int:
    output = Path(args.output)
    try:
        if args.expected_per_arm != POSITION_COUNT:
            raise ValueError(f"--expected-per-arm must remain {POSITION_COUNT}")
        expected_tar_sha256 = args.expected_source_tar_sha256.lower()
        if (
            len(expected_tar_sha256) != 64
            or any(char not in "0123456789abcdef" for char in expected_tar_sha256)
        ):
            raise ValueError("expected source tar SHA256 is malformed")

        source_tar = Path(args.source_tar)
        observed_tar_sha256 = sha256_file(source_tar)
        if observed_tar_sha256 != expected_tar_sha256:
            raise ValueError(
                "source tar SHA256 mismatch: "
                f"expected {expected_tar_sha256}, got {observed_tar_sha256}"
            )
        source_report_path = Path(args.source_verification_report)
        source_report = json.loads(source_report_path.read_text(encoding="utf-8"))
        expected_identity = (
            args.expected_source_job_id,
            args.expected_source_attempt_id,
            args.expected_source_code_sha,
        )
        observed_identity = (
            source_report.get("job_id"),
            source_report.get("attempt_id"),
            source_report.get("code_sha"),
        )
        if observed_identity != expected_identity:
            raise ValueError(
                f"failed source identity mismatch: {observed_identity!r}"
            )
        if (
            source_report.get("prefix") != args.source_prefix.rstrip("/")
            or source_report.get("result_state") != "failed"
            or source_report.get("exit_code") == 0
        ):
            raise ValueError("source report is not the pinned failed 0908 result")
        selected_files = {
            item.get("path"): item for item in source_report.get("files", [])
        }
        tar_record = selected_files.get(args.source_artifact_path)
        if (
            not tar_record
            or tar_record.get("sha256") != expected_tar_sha256
            or tar_record.get("local_name") != source_tar.name
        ):
            raise ValueError("source report does not authenticate the pinned raw tar")

        contract = load_pool_contract(Path(args.pool), Path(args.proof))
        rows_by_arm: dict[str, list[dict]] = defaultdict(list)
        provenance: list[dict] = []
        for input_name in args.inputs:
            path = Path(input_name)
            rows = _load_jsonl(path)
            file_arms = {row.get("arm") for row in rows}
            if len(file_arms) != 1 or next(iter(file_arms)) not in ARMS:
                raise ValueError(f"{path}: cannot infer exactly one valid arm")
            arm = str(next(iter(file_arms)))
            rows_by_arm[arm].extend(rows)
            provenance.append({
                "arm": arm,
                "path": str(path),
                "sha256": sha256_file(path),
            })
        if not provenance:
            raise ValueError("at least one --inputs path is required")

        source = {
            "prefix": args.source_prefix.rstrip("/"),
            "job_id": args.expected_source_job_id,
            "attempt_id": args.expected_source_attempt_id,
            "code_sha": args.expected_source_code_sha,
            "result_state": "failed",
            "raw_tar": {
                "path": args.source_artifact_path,
                "sha256": observed_tar_sha256,
                "verification_report": {
                    "path": str(source_report_path),
                    "sha256": sha256_file(source_report_path),
                },
            },
        }
        report = salvage_single_ply_cap(
            contract,
            rows_by_arm,
            expected_arm=args.expected_cap_arm,
            expected_position_id=args.expected_cap_position_id,
            expected_cell=args.expected_cap_cell,
            expected_plies=args.expected_cap_plies,
            bootstrap_samples=args.bootstrap_samples,
            bootstrap_seed=args.bootstrap_seed,
            result_provenance=provenance,
            source=source,
        )

        run_config_path = Path(args.run_config)
        run_config = json.loads(run_config_path.read_text(encoding="utf-8"))
        budget = run_config.get("budget") or {}
        timeouts = run_config.get("timeouts_seconds") or {}
        configured_pool = run_config.get("pool") or {}
        if (
            run_config.get("arms") != list(ARMS)
            or run_config.get("games_per_arm") != POSITION_COUNT
            or budget.get("kind") != "fixed_depth"
            or budget.get("depth") != DEPTH
            or budget.get("max_plies") != MAX_PLIES
            or timeouts.get("game") != int(GAME_TIMEOUT_S)
            or run_config.get("nshards") != SHARD_COUNT
            or configured_pool.get("pool_sha256") != contract.pool_sha256
            or configured_pool.get("proof_sha256") != contract.proof_sha256
        ):
            raise ValueError("run config fixed matrix contract mismatch")
        engines = report["matrix"]["inputs"]["engines"]
        scan_config = run_config.get("scan") or {}
        if (
            engines.get("search_params")
            != (run_config.get("evaluated_models") or {}).get("search_params_sha256")
            or engines.get("scan") != scan_config.get("binary_sha256")
            or engines.get("scan_runtime") != scan_config.get("runtime_sha256")
            or engines.get("scan_hub_params") != SCAN_HUB_PARAMS_SHA256
            or scan_config.get("hub_params") != SCAN_HUB_PARAMS
            or scan_config.get("hub_params_sha256") != SCAN_HUB_PARAMS_SHA256
        ):
            raise ValueError("run config/result engine fingerprint mismatch")
        report["source"]["run_config"] = {
            "path": str(run_config_path),
            "sha256": sha256_file(run_config_path),
        }
    except Exception as exc:
        report = {
            "schema": 1,
            "status": "salvage_failure",
            "scientific_matrix_ready": False,
            "error": f"{type(exc).__name__}: {exc}",
            "authorization": {
                "training_continuation_authorized": False,
                "promotion_authorized": False,
                "automatic_next_job": None,
            },
        }
    atomic_write_json(output, report)
    print(json.dumps({
        "status": report["status"],
        "scientific_matrix_ready": report["scientific_matrix_ready"],
        "output": str(output),
    }, sort_keys=True))
    return 0 if report["scientific_matrix_ready"] else 2


def run_command(args: argparse.Namespace) -> int:
    try:
        contract = load_pool_contract(Path(args.pool), Path(args.proof))
        _, technical = run_shard(contract, args)
        return 2 if technical else 0
    except Exception as exc:
        # A broken pool cannot be expanded into valid per-position rows.  Do
        # still publish a machine-readable shard artefact instead of a silent
        # traceback or, worse, fabricated draws.
        atomic_write_text(Path(args.output), json.dumps({
            "schema": 1,
            "arm": args.arm,
            "shard": args.shard_index,
            "fatal_error": f"{type(exc).__name__}: {exc}",
        }, sort_keys=True) + "\n")
        if args.progress_file:
            atomic_write_json(Path(args.progress_file), {
                "schema": 1,
                "arm": args.arm,
                "shard": args.shard_index,
                "status": "technical_failure",
                "fatal_error": f"{type(exc).__name__}: {exc}",
            })
        return 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="run one exact index%%16 matrix shard")
    run.add_argument("--pool", required=True)
    run.add_argument("--proof", required=True)
    run.add_argument("--arm", choices=ARMS, required=True)
    run.add_argument("--shard-index", "--shard", dest="shard_index", type=int, required=True)
    run.add_argument("--nshards", type=int, default=SHARD_COUNT)
    run.add_argument("--depth", type=int, default=DEPTH)
    run.add_argument("--max-plies", type=int, default=MAX_PLIES)
    run.add_argument("--game-timeout", type=float, default=GAME_TIMEOUT_S)
    run.add_argument("--jass", required=True)
    run.add_argument("--scan", required=True)
    run.add_argument(
        "--scan-runtime-sha256", required=True,
        help="canonical fingerprint of the frozen Scan binary/ini/eval snapshot",
    )
    run.add_argument("--g0", "--g0-pattern", dest="g0", required=True,
                     help="G0 PJTW weights")
    run.add_argument("--g4", "--g4-pattern", dest="g4", required=True,
                     help="G4 PJTW weights")
    run.add_argument("--search-params", required=True,
                     help="exact comma-separated search fingerprint for every Jass player")
    run.add_argument("--output", "--out", dest="output", required=True,
                     help="atomic shard JSONL output")
    run.add_argument("--progress-file", help="atomic per-game heartbeat JSON")
    run.set_defaults(func=run_command)

    aggregate = sub.add_parser("aggregate", help="strictly aggregate all seven arms")
    aggregate.add_argument("--pool", required=True)
    aggregate.add_argument("--proof", required=True)
    aggregate.add_argument(
        "--result", action="append", metavar="ARM=PATH",
        help="one shard JSONL; repeat for every arm/shard",
    )
    aggregate.add_argument("--inputs", nargs="+",
                           help="shard JSONL paths; arm is read from each file")
    aggregate.add_argument("--run-config",
                           help="optional pinned job-level configuration JSON")
    aggregate.add_argument("--expected-per-arm", type=int, default=POSITION_COUNT)
    aggregate.add_argument("--bootstrap-samples", "--bootstrap",
                           dest="bootstrap_samples", type=int, default=5000)
    aggregate.add_argument("--bootstrap-seed", "--seed",
                           dest="bootstrap_seed", type=int, default=20260723)
    aggregate.add_argument("--output", "--out", dest="output", required=True)
    aggregate.set_defaults(func=aggregate_command)

    salvage = sub.add_parser(
        "salvage-single-ply-cap",
        help="derive an auditable matrix by adjudicating one pinned ply cap as D",
    )
    salvage.add_argument("--pool", required=True)
    salvage.add_argument("--proof", required=True)
    salvage.add_argument("--inputs", nargs="+", required=True)
    salvage.add_argument("--run-config", required=True)
    salvage.add_argument("--source-tar", required=True)
    salvage.add_argument("--source-verification-report", required=True)
    salvage.add_argument("--source-prefix", required=True)
    salvage.add_argument("--source-artifact-path", required=True)
    salvage.add_argument("--expected-source-tar-sha256", required=True)
    salvage.add_argument("--expected-source-job-id", required=True)
    salvage.add_argument("--expected-source-attempt-id", required=True)
    salvage.add_argument("--expected-source-code-sha", required=True)
    salvage.add_argument("--expected-cap-arm", choices=ARMS, required=True)
    salvage.add_argument("--expected-cap-position-id", required=True)
    salvage.add_argument("--expected-cap-cell", required=True)
    salvage.add_argument("--expected-cap-plies", type=int, default=MAX_PLIES)
    salvage.add_argument("--expected-per-arm", type=int, default=POSITION_COUNT)
    salvage.add_argument("--bootstrap-samples", "--bootstrap",
                         dest="bootstrap_samples", type=int, default=10000)
    salvage.add_argument("--bootstrap-seed", "--seed",
                         dest="bootstrap_seed", type=int, default=271828)
    salvage.add_argument("--output", "--out", dest="output", required=True)
    salvage.set_defaults(func=salvage_command)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if getattr(args, "bootstrap_samples", 0) < 0:
        raise SystemExit("--bootstrap-samples must be >= 0")
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
