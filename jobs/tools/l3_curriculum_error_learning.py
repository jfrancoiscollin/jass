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
import subprocess
import sys
import tempfile
from typing import Any, Iterable

import numpy as np

SCHEMA_SELECTION = "jass.l3_curriculum_error_selection.v1"
SCHEMA_SHARD = "jass.l3_curriculum_error_shard.v1"
SCHEMA_REPORT = "jass.l3_curriculum_error_autopsy.v1"
SCHEMA_REGION = "jass.l3_curriculum_error_region.v1"
SCHEMA_SHAM_REPORT = "jass.l3_curriculum_sham_region.v1"
SCHEMA_REPAIR_SEEDS = "jass.l3_curriculum_repair_seeds.v1"
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


def _component_label(opening_ids: Iterable[str]) -> str:
    members = sorted(str(value) for value in opening_ids)
    if len(members) == 1:
        return members[0]
    return "exact-state-component:" + hashlib.sha256(_canonical(members)).hexdigest()


def _split_exact_state_components(
    rows: Iterable[dict[str, Any]], *, split_seed: int
) -> tuple[dict[str, str], dict[str, Any]]:
    """Keep the opening split sealed while collapsing exact transpositions.

    The graph uses only opening identities and exact-symmetry state keys.  It is
    therefore fixed before any deep score or regret exists.  Connected
    openings are an indivisible split unit, which makes cross-split state
    leakage impossible without discarding otherwise valid fresh campaigns.
    """
    materialized = list(rows)
    opening_ids = sorted({str(row["opening_id"]) for row in materialized})
    parent = {opening_id: opening_id for opening_id in opening_ids}

    def find(value: str) -> str:
        root = value
        while parent[root] != root:
            root = parent[root]
        while parent[value] != value:
            next_value = parent[value]
            parent[value] = root
            value = next_value
        return root

    def union(left: str, right: str) -> None:
        left_root, right_root = find(left), find(right)
        if left_root == right_root:
            return
        low, high = sorted((left_root, right_root))
        parent[high] = low

    state_owner: dict[str, str] = {}
    shared_state_edges = 0
    for row in materialized:
        opening_id = str(row["opening_id"])
        state_key = str(row["exact_state_key"])
        previous = state_owner.setdefault(state_key, opening_id)
        if previous != opening_id:
            union(previous, opening_id)
            shared_state_edges += 1

    components: dict[str, list[str]] = defaultdict(list)
    for opening_id in opening_ids:
        components[find(opening_id)].append(opening_id)
    component_rows = sorted(
        (sorted(members) for members in components.values()),
        key=lambda members: tuple(members),
    )
    opening_splits: dict[str, str] = {}
    component_counts: dict[str, int] = defaultdict(int)
    opening_counts: dict[str, int] = defaultdict(int)
    for members in component_rows:
        split = _split(_component_label(members), split_seed)
        component_counts[split] += 1
        opening_counts[split] += len(members)
        for opening_id in members:
            opening_splits[opening_id] = split
    if len(set(opening_splits.values())) != 2:
        raise ValueError("exact-state component split lacks discovery or confirmation rows")
    return opening_splits, {
        "method": "exact_state_components_sha256_parity",
        "components": len(component_rows),
        "shared_state_edges": shared_state_edges,
        "largest_component_openings": max(map(len, component_rows), default=0),
        "components_by_split": dict(sorted(component_counts.items())),
        "openings_by_split": dict(sorted(opening_counts.items())),
    }


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


def _dump_legal_lines(jass_path: str, fens: list[str]) -> list[str]:
    """Return lossless legal moves for each FEN without invoking search."""
    if not fens:
        return []
    with tempfile.TemporaryDirectory(prefix="curriculum-error-legal-") as tmp:
        root = Path(tmp)
        source, target = root / "positions.fen", root / "legal.txt"
        source.write_text("".join(f"{fen}\n" for fen in fens), encoding="utf-8")
        proc = subprocess.run(
            [jass_path, "--dump-legal", str(source), str(target)],
            capture_output=True,
            text=True,
            timeout=max(60, len(fens) // 100),
        )
        if proc.returncode != 0:
            raise RuntimeError(
                f"--dump-legal failed rc={proc.returncode}: {proc.stderr.strip()}"
            )
        raw = target.read_text(encoding="utf-8")
    # The C++ emitter writes exactly one newline-terminated row per FEN.  Using
    # splitlines() would drop a final empty terminal row and silently misalign
    # every later historical decision.
    lines = raw.split("\n")
    if not lines or lines[-1] != "":
        raise ValueError("--dump-legal output is not newline terminated")
    lines.pop()
    if len(lines) != len(fens):
        raise ValueError(
            f"--dump-legal alignment drift: {len(lines)} rows for {len(fens)} FENs"
        )
    return lines


def _resolve_historical_move(text: str, legal_line: str, cv: Any) -> Any:
    """Restore captured-square identity lost by historical game dumps.

    ``run_jass_gate_bounded`` historically persisted ``Move.jass_str()``.  A
    capture therefore appears as only ``fromxto`` even though Jass's lossless
    apply protocol also needs the captured-square set.  Resolve that endpoint
    pair against eval-free ``--dump-legal`` output and fail closed if it is not
    unique.  We must not guess: two legal capture paths with equal endpoints
    can lead to different children.
    """
    separator = "-" if "-" in text else "x" if "x" in text else None
    if separator is None:
        raise ValueError(f"unparseable historical move: {text!r}")
    parts = text.split(separator)
    if len(parts) < 2 or any(not part.isdigit() for part in parts):
        raise ValueError(f"unparseable historical move: {text!r}")
    frm, to = int(parts[0]), int(parts[1])
    supplied_captures = tuple(int(part) for part in parts[2:])
    candidates: list[Any] = []
    for raw_token in legal_line.split():
        token = raw_token.removesuffix("+")
        move_part, marker, capture_part = token.partition("*")
        try:
            legal_from, legal_to = map(int, move_part.split(">", 1))
            captures = tuple(int(value) for value in capture_part.split(",")) if marker else ()
        except ValueError as exc:
            raise ValueError(f"malformed --dump-legal token: {raw_token!r}") from exc
        if (legal_from, legal_to) != (frm, to):
            continue
        if separator == "-" and captures:
            continue
        if separator == "x" and not captures:
            continue
        if supplied_captures and set(captures) != set(supplied_captures):
            continue
        candidates.append(cv.Move(frm=frm, to=to, captures=captures))
    if len(candidates) != 1:
        raise ValueError(
            f"historical move {text!r} resolves to {len(candidates)} legal moves: {legal_line!r}"
        )
    return candidates[0]


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
                    "outcome": outcome,
                    "ply": ply,
                    "fen": fens[ply],
                    "exact_state_key": _exact_state_key(fens[ply]),
                    "actual_move": str(move),
                    "stratum": _stratum(fens[ply], str(move)),
                }
            )
    splits, split_components = _split_exact_state_components(rows, split_seed=split_seed)
    for row in rows:
        row["split"] = splits[str(row["opening_id"])]
    state_splits: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        state_splits[str(row["exact_state_key"])].add(str(row["split"]))
    leaked_states = [key for key, values in state_splits.items() if len(values) > 1]
    if leaked_states:
        raise AssertionError(
            f"component split invariant failed: {len(leaked_states)} state(s) leaked"
        )
    return {
        "schema": SCHEMA_SELECTION,
        "split": {
            "unit": "opening_id",
            "seed": split_seed,
            **split_components,
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
    search_params_path = Path(args.search_params)
    search_params = search_params_path.read_text(encoding="utf-8").strip()
    if not search_params or "\n" in search_params:
        raise ValueError("search-params file must contain one non-empty fingerprint line")
    source_rows = [
        source
        for source in selection["rows"]
        if int(source["ordinal"]) % args.nshards == args.shard
    ]
    if args.max_rows:
        source_rows = source_rows[: args.max_rows]
    legal_lines = _dump_legal_lines(
        args.jass, [str(source["fen"]) for source in source_rows]
    )
    engine = cv.JassEngine(
        args.jass,
        label=f"curriculum-autopsy-s{args.shard}",
        pattern_path=args.champion,
        search_params=search_params,
    )
    referee = cv.Referee(args.jass)
    output: list[dict[str, Any]] = []
    endpoint_only_captures = 0
    try:
        for source, legal_line in zip(source_rows, legal_lines, strict=True):
            ordinal = int(source["ordinal"])
            fen = str(source["fen"])
            historical_text = str(source["actual_move"])
            actual = _resolve_historical_move(historical_text, legal_line, cv)
            if "x" in historical_text and len(historical_text.split("x")) == 2:
                endpoint_only_captures += 1
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
        "search_params_sha256": sha256(search_params_path),
        "shard": args.shard,
        "nshards": args.nshards,
        "teacher_depth": args.teacher_depth,
        "judge_depth": args.judge_depth,
        "max_rows": args.max_rows,
        "historical_move_resolution": {
            "method": "dump_legal_unique_endpoints",
            "rows": len(source_rows),
            "endpoint_only_captures": endpoint_only_captures,
            "ambiguous": 0,
            "unresolved": 0,
        },
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
    resolution_rows = 0
    endpoint_only_captures = 0
    for shard in shards:
        resolution = shard.get("historical_move_resolution", {})
        if resolution.get("method") != "dump_legal_unique_endpoints":
            raise ValueError("historical move resolution method drift")
        if int(resolution.get("ambiguous", -1)) != 0 or int(resolution.get("unresolved", -1)) != 0:
            raise ValueError("historical move resolution was not lossless")
        shard_rows = len(shard.get("rows", []))
        if int(resolution.get("rows", -1)) != shard_rows:
            raise ValueError("historical move resolution row count drift")
        resolution_rows += shard_rows
        endpoint_only_captures += int(resolution.get("endpoint_only_captures", 0))
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
    max_rows = {int(shard.get("max_rows", -1)) for shard in shards}
    if len(teacher_depths) != 1 or len(judge_depths) != 1:
        raise ValueError("shard depth contract drift")
    if max_rows != {0}:
        raise ValueError("aggregate refuses cost-preflight shards")
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
        "historical_move_resolution": {
            "method": "dump_legal_unique_endpoints",
            "rows": resolution_rows,
            "endpoint_only_captures": endpoint_only_captures,
            "ambiguous": 0,
            "unresolved": 0,
            "passed": resolution_rows == len(rows),
        },
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


def make_repair_seeds(
    selection: dict[str, Any],
    shards: list[dict[str, Any]],
    error_region: dict[str, Any],
    *,
    min_regret_cp: int,
    max_per_opening: int,
    min_ply_gap: int,
    selection_seed: int,
    target_positions: int,
    max_plies: int,
    min_source_openings: int,
    max_opening_share: float,
) -> tuple[dict[str, Any], dict[str, Any], bytes]:
    """Expand a confirmed region into bounded, traceable generation seeds.

    Region inference keeps one statistical vote per opening.  Corpus generation
    has a different requirement: enough distinct causal states to support a
    finite target without replaying one state repeatedly.  This stage therefore
    admits multiple *qualified* decisions per opening, while enforcing temporal,
    canonical-identity and opening-concentration guards fixed before generation.
    """
    if min_regret_cp <= 0 or max_per_opening <= 0 or min_ply_gap < 0:
        raise ValueError("invalid repair-seed regret/cap/gap contract")
    if target_positions <= 0 or max_plies <= 0 or min_source_openings <= 0:
        raise ValueError("invalid repair-seed target/opening contract")
    if not 0.0 < max_opening_share <= 1.0:
        raise ValueError("max_opening_share must be in (0,1]")
    expected = len(shards)
    if not shards or {int(row.get("shard", -1)) for row in shards} != set(range(expected)):
        raise ValueError("repair-seed source shards are incomplete")
    if any(row.get("schema") != SCHEMA_SHARD for row in shards):
        raise ValueError("repair-seed source shard schema drift")
    if any(int(row.get("nshards", -1)) != expected for row in shards):
        raise ValueError("repair-seed shard count contract drift")
    if any(int(row.get("max_rows", -1)) != 0 for row in shards):
        raise ValueError("repair-seed builder refuses cost-preflight shards")
    selection_sha = hashlib.sha256(_canonical(selection)).hexdigest()
    if any(row.get("selection_sha256") != selection_sha for row in shards):
        raise ValueError("repair-seed selection hash mismatch")
    rows = [row for shard in shards for row in shard.get("rows", [])]
    rows.sort(key=lambda row: int(row["ordinal"]))
    if [int(row["ordinal"]) for row in rows] != list(range(int(selection["decisions"]))):
        raise ValueError("repair-seed shards do not cover every selected decision")
    if error_region.get("schema") != SCHEMA_REGION or error_region.get("fit_authorized") is not True:
        raise ValueError("repair seeds require a confirmed error region")
    if error_region.get("selection_sha256") != selection_sha:
        raise ValueError("repair region and selection differ")
    confirmed_columns = {int(value) for value in error_region.get("pattern_columns_full", [])}
    if not confirmed_columns:
        raise ValueError("repair region is empty")

    column_cache: dict[str, set[int]] = {}
    candidates: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if (
            row.get("outcome") != "loss"
            or not bool(row.get("move_differs"))
            or int(row.get("regret_cp", 0)) < min_regret_cp
        ):
            continue
        state_key = str(row["exact_state_key"])
        if _exact_state_key(str(row["fen"])) != state_key:
            raise ValueError("repair-seed FEN and exact canonical state differ")
        if state_key not in column_cache:
            column_cache[state_key] = set(_pattern_columns(str(row["fen"])))
        columns = column_cache[state_key]
        hit_columns = sorted(columns & confirmed_columns)
        if not hit_columns:
            continue
        candidates[str(row["opening_id"])].append({**row, "confirmed_columns": hit_columns})

    eligible: dict[str, list[dict[str, Any]]] = {}
    for opening_id, opening_rows in candidates.items():
        ranked = sorted(
            opening_rows,
            key=lambda row: (
                -int(row["regret_cp"]),
                hashlib.sha256(
                    f"{selection_seed}|{opening_id}|{row['game_uid']}|{row['ply']}|{row['exact_state_key']}".encode()
                ).digest(),
                int(row["ordinal"]),
            ),
        )
        by_game_plies: dict[str, list[int]] = defaultdict(list)
        kept: list[dict[str, Any]] = []
        for row in ranked:
            game_uid = str(row["game_uid"])
            ply = int(row["ply"])
            if any(abs(ply - previous) < min_ply_gap for previous in by_game_plies[game_uid]):
                continue
            by_game_plies[game_uid].append(ply)
            kept.append(row)
            if len(kept) >= max_per_opening:
                break
        if kept:
            eligible[opening_id] = kept

    opening_order = sorted(
        eligible,
        key=lambda opening_id: (
            hashlib.sha256(f"{selection_seed}|{opening_id}".encode()).digest(),
            opening_id,
        ),
    )
    selected: list[dict[str, Any]] = []
    canonical_seen: set[str] = set()
    for rank in range(max_per_opening):
        for opening_id in opening_order:
            opening_rows = eligible[opening_id]
            if rank >= len(opening_rows):
                continue
            row = opening_rows[rank]
            state_key = str(row["exact_state_key"])
            if state_key in canonical_seen:
                continue
            canonical_seen.add(state_key)
            selected.append(row)

    opening_counts: dict[str, int] = defaultdict(int)
    lineage_rows: list[dict[str, Any]] = []
    records: list[bytes] = []
    for index, row in enumerate(selected):
        opening_id = str(row["opening_id"])
        opening_counts[opening_id] += 1
        record = _seed_record(str(row["fen"]))
        records.append(record)
        lineage_rows.append(
            {
                "record_index": index,
                "opening_id": opening_id,
                "game_uid": str(row["game_uid"]),
                "split": str(row["split"]),
                "ply": int(row["ply"]),
                "regret_cp": int(row["regret_cp"]),
                "exact_state_key": str(row["exact_state_key"]),
                "confirmed_columns": list(row["confirmed_columns"]),
                "fen": str(row["fen"]),
                "record_sha256": hashlib.sha256(record).hexdigest(),
            }
        )
    seed_count = len(records)
    source_openings = len(opening_counts)
    realised_max_share = max(opening_counts.values(), default=0) / max(seed_count, 1)
    theoretical_max_positions = seed_count * 2 * (max_plies + 1)
    generation_authorized = bool(
        source_openings >= min_source_openings
        and realised_max_share <= max_opening_share
        and theoretical_max_positions >= target_positions
    )
    champion_values = {str(shard.get("champion_sha256", "")) for shard in shards}
    jass_values = {str(shard.get("jass_sha256", "")) for shard in shards}
    search_values = {str(shard.get("search_params_sha256", "")) for shard in shards}
    if any(len(values) != 1 or not next(iter(values)) for values in (champion_values, jass_values, search_values)):
        raise ValueError("repair-seed source identities are not byte-unique")
    if next(iter(champion_values)) != str(error_region.get("champion_sha256")):
        raise ValueError("repair-seed champion differs from confirmed region")
    payload = JNNW_MAGIC + struct.pack("<I", seed_count) + b"".join(records)
    lineage = {
        "schema": SCHEMA_REPAIR_SEEDS,
        "selection_sha256": selection_sha,
        "error_region_sha256": hashlib.sha256(_canonical(error_region)).hexdigest(),
        "selection_seed": selection_seed,
        "rows": lineage_rows,
    }
    report = {
        "schema": SCHEMA_REPAIR_SEEDS,
        "verdict": (
            "JASS_CURRICULUM_REPAIR_SEEDS_READY"
            if generation_authorized
            else "JASS_CURRICULUM_REPAIR_SEEDS_INSUFFICIENT"
        ),
        "generation_authorized": generation_authorized,
        "selection_sha256": selection_sha,
        "error_region_sha256": lineage["error_region_sha256"],
        "lineage_sha256": hashlib.sha256(_canonical(lineage)).hexdigest(),
        "seeds_sha256": hashlib.sha256(payload).hexdigest(),
        "champion_sha256": next(iter(champion_values)),
        "jass_sha256": next(iter(jass_values)),
        "search_params_sha256": next(iter(search_values)),
        "seed_positions": seed_count,
        "source_openings": source_openings,
        "candidate_openings": len(candidates),
        "canonical_unique": len(canonical_seen) == seed_count,
        "max_seeds_per_opening_realised": max(opening_counts.values(), default=0),
        "max_opening_share_realised": realised_max_share,
        "theoretical_max_positions": theoretical_max_positions,
        "target_positions": target_positions,
        "guards": {
            "min_regret_cp": min_regret_cp,
            "max_per_opening": max_per_opening,
            "min_ply_gap": min_ply_gap,
            "selection_seed": selection_seed,
            "pair_openings": True,
            "max_trajectories_per_exact_seed": 2,
            "max_plies": max_plies,
            "min_source_openings": min_source_openings,
            "max_opening_share": max_opening_share,
            "target_positions": target_positions,
        },
        "fit_count": 0,
        "strength_games": 0,
        "frozen_reads": 0,
        "promotion_authorized": False,
    }
    return report, lineage, payload


def make_sham_region(
    selection: dict[str, Any],
    shards: list[dict[str, Any]],
    error_region: dict[str, Any],
    *,
    min_regret_cp: int,
    max_control_regret_cp: int,
    match_seed: int,
    sham_seed: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Build an equal-size, visit-matched control region for the local-fit sham arm."""
    expected = len(shards)
    if not shards or {int(row.get("shard", -1)) for row in shards} != set(range(expected)):
        raise ValueError("sham source shards are incomplete")
    if any(row.get("schema") != SCHEMA_SHARD for row in shards):
        raise ValueError("sham source shard schema drift")
    if any(int(row.get("nshards", -1)) != expected for row in shards):
        raise ValueError("sham source shard count drift")
    if any(int(row.get("max_rows", -1)) != 0 for row in shards):
        raise ValueError("sham region refuses cost-preflight shards")
    selection_sha = hashlib.sha256(_canonical(selection)).hexdigest()
    if any(row.get("selection_sha256") != selection_sha for row in shards):
        raise ValueError("sham source selection hash mismatch")
    rows = [row for shard in shards for row in shard.get("rows", [])]
    rows.sort(key=lambda row: int(row["ordinal"]))
    if [int(row["ordinal"]) for row in rows] != list(range(int(selection["decisions"]))):
        raise ValueError("sham source shards do not cover every selected decision")
    if error_region.get("schema") != SCHEMA_REGION or error_region.get("fit_authorized") is not True:
        raise ValueError("sham region requires a confirmed error region")
    if error_region.get("selection_sha256") != selection_sha:
        raise ValueError("error region and sham selection differ")
    error_columns = sorted({int(value) for value in error_region.get("pattern_columns_full", [])})
    if not error_columns:
        raise ValueError("confirmed error region is empty")
    if len(error_columns) != len(error_region.get("confirmation", [])):
        raise ValueError("confirmed error region column/confirmation drift")

    errors = _one_per_opening(
        row for row in rows
        if row["outcome"] == "loss" and bool(row["move_differs"])
        and int(row["regret_cp"]) >= min_regret_cp
    )
    controls = _matched_controls(
        errors, rows, seed=match_seed, max_control_regret=max_control_regret_cp
    )
    if len(controls) / max(len(errors), 1) < 0.8:
        raise ValueError("matched-control fraction no longer satisfies the confirmed gate")
    error_counts = _bucket_counts(errors)
    control_counts = _bucket_counts(controls)
    candidates = [
        column for column, hits in control_counts.items()
        if hits > 0 and column not in set(error_columns)
        and hits >= error_counts.get(column, 0)
    ]
    if len(candidates) < len(error_columns):
        raise ValueError("insufficient control-typical buckets for equal-size sham region")

    available = set(candidates)
    matches: list[dict[str, Any]] = []
    for error_column in sorted(
        error_columns,
        key=lambda column: (-error_counts.get(column, 0), column),
    ):
        target_hits = error_counts.get(error_column, 0)
        chosen = min(
            available,
            key=lambda column: (
                abs(control_counts[column] - target_hits),
                hashlib.sha256(f"{sham_seed}|{error_column}|{column}".encode("utf-8")).digest(),
                column,
            ),
        )
        available.remove(chosen)
        matches.append({
            "full_pattern_column": chosen,
            "sham_source": "matched_non_loss_controls",
            "matched_to_error_column": error_column,
            "target_error_hits": target_hits,
            "control_hits": control_counts[chosen],
            "error_hits": error_counts.get(chosen, 0),
            "absolute_visit_mismatch": abs(control_counts[chosen] - target_hits),
        })
    sham_columns = sorted(int(row["full_pattern_column"]) for row in matches)
    champion_sha = {str(row.get("champion_sha256", "")) for row in shards}
    jass_sha = {str(row.get("jass_sha256", "")) for row in shards}
    search_sha = {str(row.get("search_params_sha256", "")) for row in shards}
    if any(len(values) != 1 or not next(iter(values)) for values in (champion_sha, jass_sha, search_sha)):
        raise ValueError("sham source identities are not byte-unique")
    champion = next(iter(champion_sha))
    if champion != error_region.get("champion_sha256"):
        raise ValueError("sham champion differs from confirmed error region")
    sham_region = {
        "schema": SCHEMA_REGION,
        "fold": "exact_rot180_colour_swap",
        "fit_authorized": True,
        "selection_sha256": selection_sha,
        "champion_sha256": champion,
        "jass_sha256": next(iter(jass_sha)),
        "search_params_sha256": next(iter(search_sha)),
        "pattern_columns_full": sham_columns,
        "extras": [],
        "selection": {
            "kind": "matched_control_sham",
            "unit": "opening_id",
            "same_bucket_count_as_error_region": True,
            "match_seed": match_seed,
            "sham_seed": sham_seed,
            "min_regret_cp": min_regret_cp,
            "max_control_regret_cp": max_control_regret_cp,
        },
        "confirmation": sorted(matches, key=lambda row: int(row["full_pattern_column"])),
        "strict_fit_contract": {
            "train_dense_extras": False,
            "train_pattern_mg_and_eg": True,
            "freeze_everything_else_at_champion": True,
        },
        "promotion_authorized": False,
    }
    report = {
        "schema": SCHEMA_SHAM_REPORT,
        "verdict": "JASS_CURRICULUM_SHAM_REGION_READY",
        "selection_sha256": selection_sha,
        "error_region_sha256": hashlib.sha256(_canonical(error_region)).hexdigest(),
        "champion_sha256": champion,
        "error_buckets": len(error_columns),
        "sham_buckets": len(sham_columns),
        "overlap_buckets": len(set(error_columns) & set(sham_columns)),
        "matched_error_openings": len(errors),
        "matched_control_openings": len(controls),
        "match_seed": match_seed,
        "sham_seed": sham_seed,
        "matches": matches,
        "fit_authorized": True,
        "promotion_authorized": False,
    }
    if report["overlap_buckets"] != 0 or report["error_buckets"] != report["sham_buckets"]:
        raise ValueError("sham equal-size/disjoint contract failed")
    return report, sham_region


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
    worker.add_argument("--max-rows", type=int, default=0,
                        help="bounded deterministic rows per shard for cost preflight; 0 means all")
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
    sham = sub.add_parser("sham-region")
    sham.add_argument("--selection", type=Path, required=True)
    sham.add_argument("--shard", action="append", type=Path, required=True)
    sham.add_argument("--error-region", type=Path, required=True)
    sham.add_argument("--min-regret-cp", type=int, default=50)
    sham.add_argument("--max-control-regret-cp", type=int, default=10)
    sham.add_argument("--match-seed", type=int, default=2026082216)
    sham.add_argument("--sham-seed", type=int, default=2026082217)
    sham.add_argument("--report", type=Path, required=True)
    sham.add_argument("--region", type=Path, required=True)
    repair = sub.add_parser("repair-seeds")
    repair.add_argument("--selection", type=Path, required=True)
    repair.add_argument("--shard", action="append", type=Path, required=True)
    repair.add_argument("--error-region", type=Path, required=True)
    repair.add_argument("--min-regret-cp", type=int, default=50)
    repair.add_argument("--max-per-opening", type=int, default=64)
    repair.add_argument("--min-ply-gap", type=int, default=2)
    repair.add_argument("--selection-seed", type=int, default=2026082218)
    repair.add_argument("--target-positions", type=int, default=500_000)
    repair.add_argument("--max-plies", type=int, default=200)
    repair.add_argument("--min-source-openings", type=int, default=64)
    repair.add_argument("--max-opening-share", type=float, default=0.02)
    repair.add_argument("--report", type=Path, required=True)
    repair.add_argument("--lineage", type=Path, required=True)
    repair.add_argument("--seeds", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == "prepare":
        payload = prepare_games(args.games_dir, split_seed=args.split_seed)
        _publish([(args.out, _canonical(payload))])
        summary = {"schema": payload["schema"], "decisions": payload["decisions"]}
    elif args.command == "worker":
        payload = analyse_shard(args)
        _publish([(args.out, _canonical(payload))])
        summary = {"schema": payload["schema"], "rows": len(payload["rows"])}
    elif args.command == "aggregate":
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
    elif args.command == "sham-region":
        selection = json.loads(args.selection.read_text(encoding="utf-8"))
        shards = [json.loads(path.read_text(encoding="utf-8")) for path in args.shard]
        error_region = json.loads(args.error_region.read_text(encoding="utf-8"))
        report, region = make_sham_region(
            selection,
            shards,
            error_region,
            min_regret_cp=args.min_regret_cp,
            max_control_regret_cp=args.max_control_regret_cp,
            match_seed=args.match_seed,
            sham_seed=args.sham_seed,
        )
        _publish([(args.report, _canonical(report)), (args.region, _canonical(region))])
        summary = {"schema": report["schema"], "verdict": report["verdict"], "fit_authorized": True}
    else:
        selection = json.loads(args.selection.read_text(encoding="utf-8"))
        shards = [json.loads(path.read_text(encoding="utf-8")) for path in args.shard]
        error_region = json.loads(args.error_region.read_text(encoding="utf-8"))
        report, lineage, seeds = make_repair_seeds(
            selection,
            shards,
            error_region,
            min_regret_cp=args.min_regret_cp,
            max_per_opening=args.max_per_opening,
            min_ply_gap=args.min_ply_gap,
            selection_seed=args.selection_seed,
            target_positions=args.target_positions,
            max_plies=args.max_plies,
            min_source_openings=args.min_source_openings,
            max_opening_share=args.max_opening_share,
        )
        _publish(
            [
                (args.report, _canonical(report)),
                (args.lineage, _canonical(lineage)),
                (args.seeds, seeds),
            ]
        )
        summary = {
            "schema": report["schema"],
            "verdict": report["verdict"],
            "generation_authorized": report["generation_authorized"],
        }
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
