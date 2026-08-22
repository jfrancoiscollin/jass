#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Exactly-symmetrised CURRICULUM search-error atlas.

The source is the sealed all-decision autopsy.  This tool deliberately leaves
PatternEval byte-identical and asks a narrower question: are the observed
regrets caused by identifiable search instability, and can a depth controller
reallocate the same mean node budget from stable to risky roots?

Stages are fail-closed and opening-disjoint:

``prepare``  select the original >=50 cp loss errors and a broad decision-level
             control risk set from other openings;
``profile``  collect exact-image paired root traces and matching covariates;
``match``    pair errors and controls without replacement inside sealed splits;
``atlas``    symmetrise every deep action judgement and replay pruning ablations;
``aggregate`` choose a controller on discovery and evaluate it once on confirm.

No stage creates training records, changes weights, plays games or authorises a
promotion.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sys
import tempfile
from typing import Any, Iterable

import numpy as np

try:
    from jobs.tools import calibrate_vs_scan as cv
    from jobs.tools import l3_context3_decision_flip_autopsy as ctx
    from jobs.tools import l3_curriculum_error_learning as learning
    from jobs.tools.l3_internal_root_trace import parse_root_events
    from jobs.tools.l3_internal_root_trace_report import final_attempt
    from jobs.tools.l3_search_variants import parse_fingerprint, render
except ModuleNotFoundError:  # pragma: no cover - direct job execution
    import calibrate_vs_scan as cv  # type: ignore
    import l3_context3_decision_flip_autopsy as ctx  # type: ignore
    import l3_curriculum_error_learning as learning  # type: ignore
    from l3_internal_root_trace import parse_root_events  # type: ignore
    from l3_internal_root_trace_report import final_attempt  # type: ignore
    from l3_search_variants import parse_fingerprint, render  # type: ignore


SCHEMA_SELECTION = "jass.l3_curriculum_search_error_profile_selection.v1"
SCHEMA_PROFILE_SHARD = "jass.l3_curriculum_search_error_profile_shard.v1"
SCHEMA_PAIRS = "jass.l3_curriculum_search_error_pairs.v1"
SCHEMA_ATLAS_SHARD = "jass.l3_curriculum_search_error_atlas_shard.v1"
SCHEMA_REPORT = "jass.l3_curriculum_search_error_atlas.v1"
TRACE_DEPTH = 12
MATCH_DEPTH = 10
PROFILE_DEPTH = 12
POLICY_DEPTHS = (8, 9, 10, 11, 12)

ACTION_RE = re.compile(
    r"^(\d+)([-x])(\d+)(?:x([0-9x]+)|\s+captures=([0-9,]+))?$"
)

ARM_OVERRIDES: dict[str, dict[str, int]] = {
    "NO_FORWARD": {
        "rfp_max_depth": 0,
        "nmp_min_depth": 99,
        "razor_max_depth": 0,
        "probcut_min_depth": 99,
        "multicut_min_depth": 99,
    },
    "NO_LMR": {"lmr_min_depth": 99},
    "NO_LMP": {"lmp_max_depth": 0},
    "NO_ASP_PVS": {"use_pvs": 0, "aspiration_initial": 20000},
    "FULL_WIDTH": {
        "rfp_max_depth": 0,
        "nmp_min_depth": 99,
        "razor_max_depth": 0,
        "probcut_min_depth": 99,
        "multicut_min_depth": 99,
        "lmr_min_depth": 99,
        "lmp_max_depth": 0,
        "use_pvs": 0,
        "aspiration_initial": 20000,
        "use_conthist": 0,
    },
}


def _canonical(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _publish(path: Path, payload: object) -> None:
    if path.exists():
        raise ValueError(f"refusing to overwrite {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    data = _canonical(payload)
    descriptor, name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _source_rows(selection: dict[str, Any], shards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if selection.get("schema") != learning.SCHEMA_SELECTION:
        raise ValueError("selection schema drift")
    expected = len(shards)
    if expected == 0 or {int(s.get("shard", -1)) for s in shards} != set(range(expected)):
        raise ValueError("source shard indices are incomplete")
    digest = hashlib.sha256(_canonical(selection)).hexdigest()
    if any(s.get("schema") != learning.SCHEMA_SHARD for s in shards):
        raise ValueError("source shard schema drift")
    if any(s.get("selection_sha256") != digest for s in shards):
        raise ValueError("source selection hash mismatch")
    rows = [row for shard in shards for row in shard.get("rows", [])]
    rows.sort(key=lambda row: int(row["ordinal"]))
    if [int(row["ordinal"]) for row in rows] != list(range(int(selection["decisions"]))):
        raise ValueError("source rows do not exactly cover the sealed selection")
    return rows


def _piece_features(fen: str) -> dict[str, Any]:
    side, wm, wk, bm, bk = cv.parse_jass_fen(fen)
    white, black = len(wm) + len(wk), len(bm) + len(bk)
    total = white + black
    stm_balance = (white - black) if side == "W" else (black - white)
    return {
        "phase": learning._phase(total),
        "piece_count": total,
        "king_count": len(wk) + len(bk),
        "stm_material_balance": stm_balance,
    }


def _coarse_distance(error: dict[str, Any], control: dict[str, Any]) -> tuple[int, bytes] | None:
    ef, cf = _piece_features(str(error["fen"])), _piece_features(str(control["fen"]))
    if str(error["split"]) != str(control["split"]):
        return None
    if ef["phase"] != cf["phase"]:
        return None
    if ("x" in str(error["actual_move"])) != ("x" in str(control["actual_move"])):
        return None
    if abs(ef["piece_count"] - cf["piece_count"]) > 3:
        return None
    if abs(ef["king_count"] - cf["king_count"]) > 2:
        return None
    if abs(int(error["ply"]) - int(control["ply"])) > 16:
        return None
    cost = (
        8 * abs(ef["piece_count"] - cf["piece_count"])
        + 6 * abs(ef["king_count"] - cf["king_count"])
        + 3 * abs(ef["stm_material_balance"] - cf["stm_material_balance"])
        + abs(int(error["ply"]) - int(control["ply"]))
    )
    tie = hashlib.sha256(
        f"{error['ordinal']}|{control['ordinal']}|{control['opening_id']}".encode()
    ).digest()
    return cost, tie


def prepare_profile_selection(
    selection: dict[str, Any],
    shards: list[dict[str, Any]],
    *,
    min_regret_cp: int,
    max_control_regret_cp: int,
    candidates_per_error: int,
    budget_rows_per_split: int = 0,
) -> dict[str, Any]:
    rows = _source_rows(selection, shards)
    errors = learning._one_per_opening(
        row
        for row in rows
        if row["outcome"] == "loss"
        and bool(row["move_differs"])
        and int(row["regret_cp"]) >= min_regret_cp
    )
    budget_rows = []
    for split in ("discovery", "confirm"):
        candidates = [
            row for row in rows
            if str(row["split"]) == split
        ]
        candidates.sort(
            key=lambda row: hashlib.sha256(
                f"budget|{split}|{row['ordinal']}|{row['opening_id']}".encode()
            ).digest()
        )
        budget_rows.extend(candidates[:budget_rows_per_split])
    budget_ordinals = {int(row["ordinal"]) for row in budget_rows}
    error_openings = {str(row["opening_id"]) for row in errors}
    # A decision-level risk set is intentional: the terminal outcome is not a
    # matching variable, and a stable move remains a valid control even when a
    # different move in its game was difficult.  Entire error openings remain
    # excluded, so no opening can appear on both sides of a pair.
    controls = [
        row
        for row in rows
        if str(row["opening_id"]) not in error_openings
        and int(row["ordinal"]) not in budget_ordinals
        and int(row["regret_cp"]) <= max_control_regret_cp
    ]
    selected_controls: dict[int, dict[str, Any]] = {}
    candidate_map: dict[str, list[int]] = {}
    for error in errors:
        ranked = []
        for control in controls:
            result = _coarse_distance(error, control)
            if result is not None:
                ranked.append((*result, control))
        ranked.sort(key=lambda item: (item[0], item[1]))
        # Matching consumes whole openings, not rows.  Keep only the best
        # decision from each candidate opening so one prolific game/opening
        # cannot crowd all 16 slots and manufacture a matching shortage.
        chosen = []
        candidate_openings: set[str] = set()
        for _cost, _tie, row in ranked:
            opening = str(row["opening_id"])
            if opening in candidate_openings:
                continue
            candidate_openings.add(opening)
            chosen.append(row)
            if len(chosen) == candidates_per_error:
                break
        candidate_map[str(error["ordinal"])] = [int(row["ordinal"]) for row in chosen]
        for row in chosen:
            selected_controls[int(row["ordinal"])] = row
    output_rows = [
        {"role": "error", "source": row} for row in sorted(errors, key=lambda r: int(r["ordinal"]))
    ] + [
        {"role": "control_candidate", "source": selected_controls[key]}
        for key in sorted(selected_controls)
    ] + [
        {"role": "budget_calibration", "source": row}
        for row in sorted(budget_rows, key=lambda r: int(r["ordinal"]))
    ]
    for profile_ordinal, row in enumerate(output_rows):
        row["profile_ordinal"] = profile_ordinal
    return {
        "schema": SCHEMA_SELECTION,
        "source_selection_sha256": hashlib.sha256(_canonical(selection)).hexdigest(),
        "source_decisions": len(rows),
        "source_shards": len(shards),
        "error_openings": len(errors),
        "control_candidate_decisions": len(selected_controls),
        "candidates_per_error": candidates_per_error,
        "budget_rows_per_split": budget_rows_per_split,
        "budget_calibration_decisions": len(budget_rows),
        "budget_selection_uses_regret_or_outcome": False,
        "candidate_map": candidate_map,
        "rows": output_rows,
        "split_unit": "opening_id_exact_state_component",
        "decision_level_controls": True,
        "error_openings_excluded_from_controls": True,
        "fit_count": 0,
        "strength_games": 0,
        "promotion_authorized": False,
    }


def _parse_action(text: str) -> Any:
    match = ACTION_RE.fullmatch(text.strip())
    if not match:
        raise ValueError(f"invalid action {text!r}")
    sep = match.group(2)
    capture_text = match.group(4) or match.group(5) or ""
    captures = tuple(
        int(value) for value in re.split(r"[x,]", capture_text) if value
    )
    if sep == "x" and not captures:
        raise ValueError(f"capture action lacks captured identities: {text!r}")
    if sep == "-" and captures:
        raise ValueError(f"quiet action has captures: {text!r}")
    return cv.Move(int(match.group(1)), int(match.group(3)), captures)


def _action_key(move: Any) -> str:
    return move.jass_apply_str()


def _image_move(move: Any) -> Any:
    return cv.Move(
        51 - int(move.frm),
        51 - int(move.to),
        tuple(sorted(51 - int(square) for square in move.captures)),
    )


def _mapped_image_action(text: str) -> str:
    # The transform is an involution, so the same mapping returns an image
    # action to the original root coordinates.
    return _action_key(_image_move(_parse_action(text)))


def _trace_search(engine: Any, fen: str, depth: int, timeout: float = 600.0) -> dict[str, Any]:
    engine.new_game()
    engine.set_position_fen(fen)
    engine._drain()
    engine._send(f"go depth {depth}")
    lines = engine._read_until(
        lambda line: line.startswith("bestmove") or line.startswith("error"),
        timeout_s=timeout,
    )
    if not lines or lines[-1].startswith("error"):
        raise RuntimeError(lines[-1] if lines else "empty search trace")
    events = parse_root_events(lines)
    terminal = ctx.parse_best_line(lines[-1])
    move = cv.parse_jass_bestmove(lines[-1])
    depths: dict[str, Any] = {}
    for current in range(1, depth + 1):
        attempt = final_attempt(events, current)
        end = attempt["end"]
        if int(end.get("complete", 0)) != 1:
            raise ValueError(f"incomplete final root attempt at depth {current}")
        if "nodes" not in end:
            raise ValueError("root trace lacks cumulative nodes instrumentation")
        moves = [
            {
                "action": _action_key(_parse_action(str(row["move"]))),
                "score": int(row["score"]),
            }
            for row in attempt["moves"]
        ]
        scores = sorted((row["score"] for row in moves), reverse=True)
        depths[str(current)] = {
            "best_action": _action_key(_parse_action(str(end["bestmove"]))),
            "score": int(end["score"]),
            "nodes": int(end["nodes"]),
            "moves": moves,
            "root_margin_proxy_cp": scores[0] - scores[1] if len(scores) >= 2 else None,
        }
    return {
        "terminal": {**terminal, "action": _action_key(move)},
        "depths": depths,
        "root_trace_sha256": hashlib.sha256(
            "\n".join(line for line in lines if line.startswith("info roottrace ")).encode()
        ).hexdigest(),
    }


def _combined_profile(original: dict[str, Any], image: dict[str, Any]) -> dict[str, Any]:
    depth = str(MATCH_DEPTH)
    original_row, image_row = original["depths"][depth], image["depths"][depth]
    mapped_image_best = _mapped_image_action(str(image_row["best_action"]))
    scores: dict[str, list[int]] = defaultdict(list)
    for row in original_row["moves"]:
        scores[str(row["action"])].append(int(row["score"]))
    for row in image_row["moves"]:
        scores[_mapped_image_action(str(row["action"]))].append(int(row["score"]))
    means = sorted(
        ((sum(values) / len(values), action) for action, values in scores.items()),
        reverse=True,
    )
    margin = means[0][0] - means[1][0] if len(means) >= 2 else None

    def flips(trace: dict[str, Any]) -> int:
        actions = [trace["depths"][str(d)]["best_action"] for d in range(8, 11)]
        return sum(left != right for left, right in zip(actions, actions[1:]))

    def volatility(trace: dict[str, Any]) -> int:
        values = [int(trace["depths"][str(d)]["score"]) for d in range(8, 11)]
        return max((abs(right - left) for left, right in zip(values, values[1:])), default=0)

    return {
        "original_best_action": original_row["best_action"],
        "mapped_image_best_action": mapped_image_best,
        "exact_image_best_agreement": original_row["best_action"] == mapped_image_best,
        "root_margin_proxy_cp": margin,
        "depth_flip_count_8_10": flips(original) + flips(image),
        "score_volatility_8_10_cp": max(volatility(original), volatility(image)),
    }


def profile_shard(args: argparse.Namespace) -> dict[str, Any]:
    selection_path = Path(args.selection)
    selection = json.loads(selection_path.read_text(encoding="utf-8"))
    if selection.get("schema") != SCHEMA_SELECTION:
        raise ValueError("profile selection schema drift")
    if not 0 <= args.shard < args.nshards:
        raise ValueError("invalid profile shard")
    rows = [
        row for row in selection["rows"]
        if int(row["profile_ordinal"]) % args.nshards == args.shard
    ]
    if args.max_rows:
        rows = rows[: args.max_rows]
    legal = learning._dump_legal_lines(args.jass, [str(row["source"]["fen"]) for row in rows])
    image_legal = learning._dump_legal_lines(
        args.jass, [ctx.exact_image_fen(str(row["source"]["fen"])) for row in rows]
    )
    os.environ["JASS_TRACE_ROOT"] = "1"
    spec = Path(args.search_params).read_text(encoding="utf-8").strip()
    engine = cv.JassEngine(
        args.jass,
        label=f"curriculum-search-profile-s{args.shard}",
        pattern_path=args.champion,
        search_params=spec,
    )
    output = []
    try:
        for selected, legal_line, image_line in zip(rows, legal, image_legal, strict=True):
            if len(legal_line.split()) != len(image_line.split()):
                raise ValueError("exact image legal-count mismatch")
            source = selected["source"]
            fen = str(source["fen"])
            original = _trace_search(engine, fen, PROFILE_DEPTH)
            image = _trace_search(engine, ctx.exact_image_fen(fen), PROFILE_DEPTH)
            output.append(
                {
                    **selected,
                    "piece_features": _piece_features(fen),
                    "legal_moves": len(legal_line.split()),
                    "trace": {"original": original, "exact_image": image},
                    "matching_features": _combined_profile(original, image),
                }
            )
    finally:
        engine.close()
    return {
        "schema": SCHEMA_PROFILE_SHARD,
        "selection_sha256": sha256(selection_path),
        "champion_sha256": sha256(Path(args.champion)),
        "jass_sha256": sha256(Path(args.jass)),
        "search_params_sha256": sha256(Path(args.search_params)),
        "shard": args.shard,
        "nshards": args.nshards,
        "max_rows": args.max_rows,
        "rows": output,
    }


def _margin_bin(value: float | None) -> int:
    if value is None:
        return 5
    for index, boundary in enumerate((10.0, 20.0, 50.0, 100.0, 200.0)):
        if value <= boundary:
            return index
    return 5


def _fine_distance(error: dict[str, Any], control: dict[str, Any]) -> tuple[int, bytes] | None:
    e, c = error["source"], control["source"]
    ep, cp = error["piece_features"], control["piece_features"]
    em, cm = error["matching_features"], control["matching_features"]
    if str(e["split"]) != str(c["split"]) or ep["phase"] != cp["phase"]:
        return None
    if ("x" in str(e["actual_move"])) != ("x" in str(c["actual_move"])):
        return None
    differences = {
        "pieces": abs(int(ep["piece_count"]) - int(cp["piece_count"])),
        "kings": abs(int(ep["king_count"]) - int(cp["king_count"])),
        "balance": abs(int(ep["stm_material_balance"]) - int(cp["stm_material_balance"])),
        "legal": abs(int(error["legal_moves"]) - int(control["legal_moves"])),
        "ply": abs(int(e["ply"]) - int(c["ply"])),
        "margin_bin": abs(_margin_bin(em["root_margin_proxy_cp"]) - _margin_bin(cm["root_margin_proxy_cp"])),
        "flips": abs(int(em["depth_flip_count_8_10"]) - int(cm["depth_flip_count_8_10"])),
    }
    if (
        differences["pieces"] > 2
        or differences["kings"] > 1
        or differences["balance"] > 2
        or differences["legal"] > 3
        or differences["ply"] > 12
        or differences["margin_bin"] > 1
        or differences["flips"] > 2
    ):
        return None
    cost = (
        12 * differences["pieces"]
        + 10 * differences["kings"]
        + 8 * differences["balance"]
        + 7 * differences["legal"]
        + differences["ply"]
        + 6 * differences["margin_bin"]
        + 4 * differences["flips"]
        + 5 * (em["exact_image_best_agreement"] != cm["exact_image_best_agreement"])
    )
    tie = hashlib.sha256(f"{e['ordinal']}|{c['ordinal']}".encode()).digest()
    return cost, tie


def match_profiles(selection: dict[str, Any], shards: list[dict[str, Any]]) -> dict[str, Any]:
    expected = len(shards)
    if expected == 0 or {int(s.get("shard", -1)) for s in shards} != set(range(expected)):
        raise ValueError("profile shards are incomplete")
    if any(s.get("schema") != SCHEMA_PROFILE_SHARD for s in shards):
        raise ValueError("profile shard schema drift")
    if any(int(s.get("max_rows", -1)) != 0 for s in shards):
        raise ValueError("matching refuses preflight shards")
    digest = hashlib.sha256(_canonical(selection)).hexdigest()
    if any(s.get("selection_sha256") != digest for s in shards):
        raise ValueError("profile selection hash mismatch")
    rows = [row for shard in shards for row in shard["rows"]]
    rows.sort(key=lambda row: int(row["profile_ordinal"]))
    if [int(row["profile_ordinal"]) for row in rows] != list(range(len(selection["rows"]))):
        raise ValueError("profile rows do not exactly cover selection")
    # A representative budget row may intentionally duplicate an error row.
    # Candidate lookup is therefore role-qualified rather than last-write-wins
    # on source ordinal.
    by_source = {
        int(row["source"]["ordinal"]): row
        for row in rows if row["role"] == "control_candidate"
    }
    errors = [row for row in rows if row["role"] == "error"]
    feasible: dict[int, list[tuple[int, bytes, dict[str, Any]]]] = {}
    for error in errors:
        eid = int(error["source"]["ordinal"])
        candidates = []
        for cid in selection["candidate_map"].get(str(eid), []):
            control = by_source.get(int(cid))
            if control is None:
                continue
            result = _fine_distance(error, control)
            if result is not None:
                candidates.append((*result, control))
        candidates.sort(key=lambda item: (item[0], item[1]))
        feasible[eid] = candidates
    ordered = sorted(
        errors,
        key=lambda row: (
            len(feasible[int(row["source"]["ordinal"])]),
            hashlib.sha256(str(row["source"]["opening_id"]).encode()).digest(),
        ),
    )
    # Maximum-cardinality deterministic bipartite matching.  A plain greedy
    # pass can report <80% even when a valid assignment exists; augmenting
    # paths distinguish an actual lack of controls from an allocator artefact.
    error_by_id = {int(row["source"]["ordinal"]): row for row in errors}
    owner_by_opening: dict[str, int] = {}
    assignment: dict[int, tuple[int, dict[str, Any]]] = {}

    def augment(eid: int, visited: set[str]) -> bool:
        for cost, _tie, control in feasible[eid]:
            opening = str(control["source"]["opening_id"])
            if opening in visited:
                continue
            visited.add(opening)
            incumbent = owner_by_opening.get(opening)
            if incumbent is None or augment(incumbent, visited):
                owner_by_opening[opening] = eid
                assignment[eid] = (cost, control)
                return True
        return False

    for error in ordered:
        augment(int(error["source"]["ordinal"]), set())

    pairs = []
    for eid, (cost, control) in sorted(assignment.items()):
        error = error_by_id[eid]
        pairs.append(
            {
                "pair_id": len(pairs),
                "split": error["source"]["split"],
                "distance": cost,
                "error": error,
                "control": control,
            }
        )
    pairs.sort(key=lambda row: (str(row["split"]), int(row["error"]["source"]["ordinal"])))
    for index, pair in enumerate(pairs):
        pair["pair_id"] = index
    fraction = len(pairs) / len(errors) if errors else 0.0
    budget_calibration = []
    for row in rows:
        if row["role"] != "budget_calibration":
            continue
        policy_depths = {
            str(depth): {
                "original_nodes": int(row["trace"]["original"]["depths"][str(depth)]["nodes"]),
                "exact_image_nodes": int(row["trace"]["exact_image"]["depths"][str(depth)]["nodes"]),
                "mean_exact_image_nodes": (
                    int(row["trace"]["original"]["depths"][str(depth)]["nodes"])
                    + int(row["trace"]["exact_image"]["depths"][str(depth)]["nodes"])
                ) / 2.0,
            }
            for depth in POLICY_DEPTHS
        }
        budget_calibration.append(
            {
                "ordinal": int(row["source"]["ordinal"]),
                "opening_id": str(row["source"]["opening_id"]),
                "split": str(row["source"]["split"]),
                "risk_features": _risk_features(row["trace"]),
                "policy_depths": policy_depths,
            }
        )
    error_openings = {str(row["source"]["opening_id"]) for row in errors}
    control_openings = {str(pair["control"]["source"]["opening_id"]) for pair in pairs}
    opening_overlap = len(error_openings & control_openings)
    if len(control_openings) != len(pairs) or opening_overlap:
        raise ValueError("opening-disjoint matching invariant failed")
    return {
        "schema": SCHEMA_PAIRS,
        "profile_selection_sha256": hashlib.sha256(_canonical(selection)).hexdigest(),
        "profile_shard_hashes": sorted(hashlib.sha256(_canonical(s)).hexdigest() for s in shards),
        "error_openings": len(errors),
        "matched_pairs": len(pairs),
        "matched_fraction": fraction,
        "matching_passed": bool(errors) and fraction >= 0.8,
        "matching_gate": 0.8,
        "pairs_by_split": {
            split: sum(pair["split"] == split for pair in pairs)
            for split in ("discovery", "confirm")
        },
        "pairs": pairs,
        "budget_calibration": budget_calibration,
        "budget_calibration_by_split": {
            split: sum(row["split"] == split for row in budget_calibration)
            for split in ("discovery", "confirm")
        },
        "opening_overlap": opening_overlap,
        "maximum_cardinality_matching": True,
        "fit_count": 0,
        "strength_games": 0,
        "promotion_authorized": False,
    }


def build_search_arms(base_spec: str) -> dict[str, str]:
    order, base = parse_fingerprint(base_spec)
    return {"Q00": base_spec, **{name: render(order, base, overrides) for name, overrides in ARM_OVERRIDES.items()}}


def _plain_search(engine: Any, fen: str, depth: int) -> dict[str, Any]:
    _move, result = ctx._search(engine, fen, depth)
    return result


def _symmetrised_action_values(
    engine: Any,
    referee: Any,
    fen: str,
    action_keys: Iterable[str],
    *,
    judge_depth: int,
) -> tuple[dict[str, dict[str, Any]], int]:
    image_fen = ctx.exact_image_fen(fen)
    values: dict[str, dict[str, Any]] = {}
    verified = 0
    for key in sorted(set(action_keys)):
        move = _parse_action(key)
        child = ctx._child_fen(referee, fen, move)
        image_child = ctx._child_fen(referee, image_fen, _image_move(move))
        if learning._fen_bits(image_child) != learning._fen_bits(ctx.exact_image_fen(child)):
            raise ValueError("exact-image child commutation failed")
        verified += 1
        original_result = _plain_search(engine, child, judge_depth)
        image_result = _plain_search(engine, image_child, judge_depth)
        twice_root_cp = -int(original_result["score"]) - int(image_result["score"])
        values[key] = {
            "twice_root_cp": twice_root_cp,
            "root_cp": twice_root_cp / 2.0,
            "child_original": original_result,
            "child_exact_image": image_result,
        }
    return values, verified


def _risk_features(trace: dict[str, Any]) -> dict[str, Any]:
    original, image = trace["original"], trace["exact_image"]
    def orientation(row: dict[str, Any]) -> dict[str, Any]:
        d8, d9 = row["depths"]["8"], row["depths"]["9"]
        margin = d9["root_margin_proxy_cp"]
        margin_value = float(margin) if margin is not None else 10_000.0
        volatility = abs(int(d9["score"]) - int(d8["score"]))
        flags = {
            "depth_flip_d8_d9": str(d8["best_action"]) != str(d9["best_action"]),
            "low_root_margin_d9": margin_value <= 50.0,
            "score_volatile_d8_d9": volatility >= 50,
        }
        return {
            **flags,
            "risk_score": sum(bool(value) for value in flags.values()),
            "root_margin_proxy_cp": margin,
            "score_volatility_cp": volatility,
        }

    original_features = orientation(original)
    image_features = orientation(image)
    o9, i9 = original["depths"]["9"], image["depths"]["9"]
    return {
        "original": original_features,
        "exact_image": image_features,
        "exact_image_disagreement_d9": str(o9["best_action"]) != _mapped_image_action(str(i9["best_action"])),
        "uses_depths_at_most": 9,
        "runtime_uses_exact_image": False,
    }


def _analyse_root(
    selected: dict[str, Any],
    *,
    judge_engine: Any,
    trace_engines: dict[str, Any],
    referee: Any,
    judge_depth: int,
) -> dict[str, Any]:
    source = selected["source"]
    fen = str(source["fen"])
    image_fen = ctx.exact_image_fen(fen)
    qtrace = {
        "original": _trace_search(trace_engines["Q00"], fen, TRACE_DEPTH),
        "exact_image": _trace_search(trace_engines["Q00"], image_fen, TRACE_DEPTH),
    }
    actions = {str(source["actual_apply"])}
    for depth in POLICY_DEPTHS:
        actions.add(str(qtrace["original"]["depths"][str(depth)]["best_action"]))
        actions.add(_mapped_image_action(str(qtrace["exact_image"]["depths"][str(depth)]["best_action"])))
    # The final complete root attempt contains every legal action.  Re-judge
    # the entire set rather than a Q00 top-k subset: an ablation is allowed to
    # recover a move that Q00 ranked low, and that move must be eligible to
    # become the exact teacher.
    original_legal = {
        str(row["action"])
        for row in qtrace["original"]["depths"][str(TRACE_DEPTH)]["moves"]
    }
    mapped_image_legal = {
        _mapped_image_action(str(row["action"]))
        for row in qtrace["exact_image"]["depths"][str(TRACE_DEPTH)]["moves"]
    }
    if original_legal != mapped_image_legal:
        raise ValueError("exact-image legal action set mismatch")
    actions.update(original_legal)
    values, verified = _symmetrised_action_values(
        judge_engine, referee, fen, actions, judge_depth=judge_depth
    )
    ranked = sorted(values, key=lambda action: (int(values[action]["twice_root_cp"]), action), reverse=True)
    teacher = ranked[0]
    actual = str(source["actual_apply"])
    policy_rows = {}
    for depth in POLICY_DEPTHS:
        key = str(depth)
        original_action = str(qtrace["original"]["depths"][key]["best_action"])
        image_action = _mapped_image_action(str(qtrace["exact_image"]["depths"][key]["best_action"]))
        teacher_cp = float(values[teacher]["root_cp"])
        original_regret = teacher_cp - float(values[original_action]["root_cp"])
        image_regret = teacher_cp - float(values[image_action]["root_cp"])
        o_nodes = int(qtrace["original"]["depths"][key]["nodes"])
        i_nodes = int(qtrace["exact_image"]["depths"][key]["nodes"])
        policy_rows[key] = {
            "original_action": original_action,
            "mapped_image_action": image_action,
            "original_regret_cp": original_regret,
            "exact_image_regret_cp": image_regret,
            "mean_regret_cp": (original_regret + image_regret) / 2.0,
            "original_nodes": o_nodes,
            "exact_image_nodes": i_nodes,
            "mean_exact_image_nodes": (o_nodes + i_nodes) / 2.0,
        }
    arms = {}
    for name, engine in trace_engines.items():
        if name == "Q00":
            trace = qtrace
        else:
            trace = {
                "original": _trace_search(engine, fen, MATCH_DEPTH),
                "exact_image": _trace_search(engine, image_fen, MATCH_DEPTH),
            }
        original_action = str(trace["original"]["depths"][str(MATCH_DEPTH)]["best_action"])
        mapped_action = _mapped_image_action(str(trace["exact_image"]["depths"][str(MATCH_DEPTH)]["best_action"]))
        arms[name] = {
            "original_action": original_action,
            "mapped_image_action": mapped_action,
            "exact_image_agreement": original_action == mapped_action,
            "teacher_in_paired_choices": teacher in {original_action, mapped_action},
            "mean_nodes": (
                int(trace["original"]["depths"][str(MATCH_DEPTH)]["nodes"])
                + int(trace["exact_image"]["depths"][str(MATCH_DEPTH)]["nodes"])
            ) / 2.0,
        }
    actual_regret = int(values[teacher]["twice_root_cp"]) - int(values[actual]["twice_root_cp"])
    top_gap = int(values[ranked[0]]["twice_root_cp"]) - int(values[ranked[1]]["twice_root_cp"]) if len(ranked) > 1 else None
    return {
        "source": source,
        "profile": {
            "piece_features": selected["piece_features"],
            "legal_moves": selected["legal_moves"],
            "matching_features": selected["matching_features"],
        },
        "exact_teacher_action": teacher,
        "historical_action": actual,
        "historical_regret_twice_cp": actual_regret,
        "historical_regret_cp": actual_regret / 2.0,
        "exact_top1_top2_gap_twice_cp": top_gap,
        "exact_top1_top2_gap_cp": top_gap / 2.0 if top_gap is not None else None,
        "action_values": values,
        "policy_depths": policy_rows,
        "risk_features": _risk_features(qtrace),
        "ablation_arms": arms,
        "exact_image_child_commutations": verified,
        "exact_symmetrised_judge": True,
    }


def atlas_shard(args: argparse.Namespace) -> dict[str, Any]:
    pairs_path = Path(args.pairs)
    pairs = json.loads(pairs_path.read_text(encoding="utf-8"))
    if pairs.get("schema") != SCHEMA_PAIRS or pairs.get("matching_passed") is not True:
        raise ValueError("atlas requires a passed pair selection")
    if not 0 <= args.shard < args.nshards:
        raise ValueError("invalid atlas shard")
    selected_pairs = [pair for pair in pairs["pairs"] if int(pair["pair_id"]) % args.nshards == args.shard]
    if args.max_pairs:
        selected_pairs = selected_pairs[: args.max_pairs]
    spec = Path(args.search_params).read_text(encoding="utf-8").strip()
    arms = build_search_arms(spec)
    os.environ["JASS_TRACE_ROOT"] = "0"
    judge = cv.JassEngine(
        args.jass,
        label=f"curriculum-symm-judge-s{args.shard}",
        pattern_path=args.champion,
        search_params=spec,
    )
    os.environ["JASS_TRACE_ROOT"] = "1"
    trace_engines = {
        name: cv.JassEngine(
            args.jass,
            label=f"curriculum-{name}-s{args.shard}",
            pattern_path=args.champion,
            search_params=arm_spec,
        )
        for name, arm_spec in arms.items()
    }
    referee = cv.Referee(args.jass)
    output = []
    try:
        for pair in selected_pairs:
            output.append(
                {
                    "pair_id": int(pair["pair_id"]),
                    "split": pair["split"],
                    "error": _analyse_root(
                        pair["error"], judge_engine=judge, trace_engines=trace_engines,
                        referee=referee, judge_depth=args.judge_depth,
                    ),
                    "control": _analyse_root(
                        pair["control"], judge_engine=judge, trace_engines=trace_engines,
                        referee=referee, judge_depth=args.judge_depth,
                    ),
                }
            )
    finally:
        referee.close()
        judge.close()
        for engine in trace_engines.values():
            engine.close()
    return {
        "schema": SCHEMA_ATLAS_SHARD,
        "pairs_sha256": sha256(pairs_path),
        "champion_sha256": sha256(Path(args.champion)),
        "jass_sha256": sha256(Path(args.jass)),
        "search_params_sha256": sha256(Path(args.search_params)),
        "search_arms": {name: hashlib.sha256(value.encode()).hexdigest() for name, value in arms.items()},
        "shard": args.shard,
        "nshards": args.nshards,
        "max_pairs": args.max_pairs,
        "judge_depth": args.judge_depth,
        "rows": output,
    }


def _bootstrap(values: list[float], *, samples: int, seed: int) -> dict[str, Any]:
    if not values:
        return {"n": 0, "mean": None, "ci95": [None, None], "probability_positive": None}
    array = np.asarray(values, dtype=np.float64)
    rng = np.random.default_rng(seed)
    means = np.empty(samples, dtype=np.float64)
    batch = 2048
    for start in range(0, samples, batch):
        stop = min(start + batch, samples)
        indices = rng.integers(0, len(array), size=(stop - start, len(array)))
        means[start:stop] = array[indices].mean(axis=1)
    low, high = np.quantile(means, (0.025, 0.975))
    return {
        "n": len(values),
        "mean": float(array.mean()),
        "ci95": [float(low), float(high)],
        "probability_positive": float(np.mean(means > 0.0)),
    }


def _simulate(rows: list[dict[str, Any]], policy: dict[str, int]) -> dict[str, Any]:
    outputs = []
    for row in rows:
        original_risky = int(row["risk_features"]["original"]["risk_score"]) >= int(policy["risk_threshold"])
        image_risky = int(row["risk_features"]["exact_image"]["risk_score"]) >= int(policy["risk_threshold"])
        original_depth = int(policy["risky_depth"] if original_risky else policy["stable_depth"])
        image_depth = int(policy["risky_depth"] if image_risky else policy["stable_depth"])
        baseline = row["policy_depths"]["10"]
        original_adaptive = row["policy_depths"][str(original_depth)]
        image_adaptive = row["policy_depths"][str(image_depth)]
        baseline_regret = float(baseline["mean_regret_cp"])
        adaptive_regret = (
            float(original_adaptive["original_regret_cp"])
            + float(image_adaptive["exact_image_regret_cp"])
        ) / 2.0
        baseline_nodes = float(baseline["mean_exact_image_nodes"])
        adaptive_nodes = (
            float(original_adaptive["original_nodes"])
            + float(image_adaptive["exact_image_nodes"])
        ) / 2.0
        outputs.append(
            {
                "baseline_regret_cp": baseline_regret,
                "adaptive_regret_cp": adaptive_regret,
                "baseline_error": float(baseline_regret >= 50.0),
                "adaptive_error": float(adaptive_regret >= 50.0),
                "baseline_nodes": baseline_nodes,
                "adaptive_nodes": adaptive_nodes,
                "original_risky": original_risky,
                "exact_image_risky": image_risky,
                "original_depth": original_depth,
                "exact_image_depth": image_depth,
            }
        )
    mean = lambda key: float(np.mean([row[key] for row in outputs])) if outputs else None
    baseline_nodes, adaptive_nodes = mean("baseline_nodes"), mean("adaptive_nodes")
    return {
        "n": len(outputs),
        "baseline_mean_regret_cp": mean("baseline_regret_cp"),
        "adaptive_mean_regret_cp": mean("adaptive_regret_cp"),
        "mean_regret_reduction_cp": (
            mean("baseline_regret_cp") - mean("adaptive_regret_cp") if outputs else None
        ),
        "baseline_error_rate_50cp": mean("baseline_error"),
        "adaptive_error_rate_50cp": mean("adaptive_error"),
        "error_rate_reduction": mean("baseline_error") - mean("adaptive_error") if outputs else None,
        "baseline_mean_nodes": baseline_nodes,
        "adaptive_mean_nodes": adaptive_nodes,
        "node_budget_ratio": adaptive_nodes / baseline_nodes if baseline_nodes else None,
        "risky_orientation_fraction": (
            float(np.mean([value for row in outputs for value in (row["original_risky"], row["exact_image_risky"])]))
            if outputs else None
        ),
        "depth_counts": {
            str(depth): sum(
                int(row["original_depth"] == depth) + int(row["exact_image_depth"] == depth)
                for row in outputs
            )
            for depth in POLICY_DEPTHS
        },
        "rows": outputs,
    }


def _simulate_costs(rows: list[dict[str, Any]], policy: dict[str, int]) -> dict[str, Any]:
    baseline_nodes = []
    adaptive_nodes = []
    depth_counts = {str(depth): 0 for depth in POLICY_DEPTHS}
    for row in rows:
        original_risky = int(row["risk_features"]["original"]["risk_score"]) >= int(policy["risk_threshold"])
        image_risky = int(row["risk_features"]["exact_image"]["risk_score"]) >= int(policy["risk_threshold"])
        original_depth = int(policy["risky_depth"] if original_risky else policy["stable_depth"])
        image_depth = int(policy["risky_depth"] if image_risky else policy["stable_depth"])
        baseline = row["policy_depths"]["10"]
        baseline_nodes.append(float(baseline["mean_exact_image_nodes"]))
        adaptive_nodes.append((
            float(row["policy_depths"][str(original_depth)]["original_nodes"])
            + float(row["policy_depths"][str(image_depth)]["exact_image_nodes"])
        ) / 2.0)
        depth_counts[str(original_depth)] += 1
        depth_counts[str(image_depth)] += 1
    baseline_mean = float(np.mean(baseline_nodes)) if rows else None
    adaptive_mean = float(np.mean(adaptive_nodes)) if rows else None
    return {
        "n": len(rows),
        "baseline_mean_nodes": baseline_mean,
        "adaptive_mean_nodes": adaptive_mean,
        "node_budget_ratio": adaptive_mean / baseline_mean if baseline_mean else None,
        "depth_counts": depth_counts,
    }


def select_controller(
    discovery_errors: list[dict[str, Any]],
    discovery_controls: list[dict[str, Any]],
    discovery_budget: list[dict[str, Any]],
) -> dict[str, Any] | None:
    candidates = []
    for threshold in range(1, 5):
        for risky_depth in (11, 12):
            # Risk is observed only once depth 9 is complete.  Stopping at
            # depth 8 would retroactively refund work already spent and would
            # therefore fake budget neutrality.
            for stable_depth in (9, 10):
                policy = {"risk_threshold": threshold, "risky_depth": risky_depth, "stable_depth": stable_depth}
                error = _simulate(discovery_errors, policy)
                control = _simulate(discovery_controls, policy)
                budget = _simulate_costs(discovery_budget, policy)
                ratio = budget["node_budget_ratio"]
                if ratio is None or not 0.98 <= ratio <= 1.0:
                    continue
                if float(error["mean_regret_reduction_cp"] or 0.0) <= 0.0:
                    continue
                if float(error["error_rate_reduction"] or 0.0) <= 0.0:
                    continue
                if float(control["adaptive_mean_regret_cp"] or 0.0) > float(control["baseline_mean_regret_cp"] or 0.0):
                    continue
                if float(control["adaptive_error_rate_50cp"] or 0.0) > float(control["baseline_error_rate_50cp"] or 0.0):
                    continue
                candidates.append((
                    float(error["mean_regret_reduction_cp"]),
                    float(error["error_rate_reduction"]),
                    -abs(1.0 - float(ratio)),
                    -threshold,
                    policy,
                ))
    if not candidates:
        return None
    candidates.sort(reverse=True)
    return candidates[0][-1]


def aggregate_atlas(
    pairs: dict[str, Any],
    shards: list[dict[str, Any]],
    *,
    bootstrap_samples: int,
    bootstrap_seed: int,
) -> dict[str, Any]:
    expected = len(shards)
    if expected == 0 or {int(s.get("shard", -1)) for s in shards} != set(range(expected)):
        raise ValueError("atlas shards are incomplete")
    if any(s.get("schema") != SCHEMA_ATLAS_SHARD for s in shards):
        raise ValueError("atlas shard schema drift")
    if any(int(s.get("max_pairs", -1)) != 0 for s in shards):
        raise ValueError("aggregate refuses atlas preflight shards")
    digest = hashlib.sha256(_canonical(pairs)).hexdigest()
    if any(s.get("pairs_sha256") != digest for s in shards):
        raise ValueError("atlas pair hash mismatch")
    rows = [row for shard in shards for row in shard["rows"]]
    rows.sort(key=lambda row: int(row["pair_id"]))
    if [int(row["pair_id"]) for row in rows] != list(range(int(pairs["matched_pairs"]))):
        raise ValueError("atlas rows do not exactly cover matched pairs")
    all_roots = [row[role] for row in rows for role in ("error", "control")]
    exact = all(bool(row["exact_symmetrised_judge"]) and int(row["exact_image_child_commutations"]) > 0 for row in all_roots)
    errors = [row["error"] for row in rows]
    controls = [row["control"] for row in rows]
    symm_errors = [row for row in errors if float(row["historical_regret_cp"]) >= 50.0]
    by_split = {
        split: {
            "errors": [row["error"] for row in rows if row["split"] == split and float(row["error"]["historical_regret_cp"]) >= 50.0],
            "controls": [row["control"] for row in rows if row["split"] == split],
        }
        for split in ("discovery", "confirm")
    }
    budget_by_split = {
        split: [row for row in pairs.get("budget_calibration", []) if row.get("split") == split]
        for split in ("discovery", "confirm")
    }
    policy = select_controller(
        by_split["discovery"]["errors"],
        by_split["discovery"]["controls"],
        budget_by_split["discovery"],
    )
    simulations: dict[str, Any] = {}
    bootstrap: dict[str, Any] = {}
    if policy is not None:
        for split in ("discovery", "confirm"):
            error_sim = _simulate(by_split[split]["errors"], policy)
            control_sim = _simulate(by_split[split]["controls"], policy)
            budget_sim = _simulate_costs(budget_by_split[split], policy)
            simulations[split] = {
                "errors": error_sim,
                "controls": control_sim,
                "budget_population": budget_sim,
            }
        confirm_error_rows = simulations["confirm"]["errors"]["rows"]
        bootstrap = {
            "confirm_regret_reduction_cp": _bootstrap(
                [row["baseline_regret_cp"] - row["adaptive_regret_cp"] for row in confirm_error_rows],
                samples=bootstrap_samples,
                seed=bootstrap_seed,
            ),
            "confirm_error_rate_reduction": _bootstrap(
                [row["baseline_error"] - row["adaptive_error"] for row in confirm_error_rows],
                samples=bootstrap_samples,
                seed=bootstrap_seed + 1,
            ),
        }

    arm_summary: dict[str, Any] = {}
    for name in ("Q00", *ARM_OVERRIDES):
        arm_summary[name] = {}
        for split in ("discovery", "confirm"):
            subset = by_split[split]["errors"]
            hits = sum(bool(row["ablation_arms"][name]["teacher_in_paired_choices"]) for row in subset)
            agreements = sum(bool(row["ablation_arms"][name]["exact_image_agreement"]) for row in subset)
            arm_summary[name][split] = {
                "n": len(subset),
                "teacher_choice_hit_rate": hits / len(subset) if subset else None,
                "exact_image_agreement_rate": agreements / len(subset) if subset else None,
                "mean_nodes": float(np.mean([row["ablation_arms"][name]["mean_nodes"] for row in subset])) if subset else None,
            }
    localized = []
    for name in ARM_OVERRIDES:
        if all(
            arm_summary[name][split]["teacher_choice_hit_rate"] is not None
            and arm_summary["Q00"][split]["teacher_choice_hit_rate"] is not None
            and arm_summary[name][split]["teacher_choice_hit_rate"]
            >= arm_summary["Q00"][split]["teacher_choice_hit_rate"] + 0.05
            for split in ("discovery", "confirm")
        ):
            localized.append(name)
    mechanism = localized[0] if len(localized) == 1 else (
        "MULTIPLE_SEARCH_FAMILIES" if localized else "NO_SINGLE_PRUNING_FAMILY"
    )

    confirm = simulations.get("confirm", {})
    error_confirm = confirm.get("errors", {})
    control_confirm = confirm.get("controls", {})
    budget_confirm = confirm.get("budget_population", {})
    regret_boot = bootstrap.get("confirm_regret_reduction_cp", {})
    error_boot = bootstrap.get("confirm_error_rate_reduction", {})
    gates = {
        "matching_fraction_ge_0_80": float(pairs.get("matched_fraction", 0.0)) >= 0.8,
        "exact_symmetrised_judging": exact,
        "at_least_64_symmetrised_errors": len(symm_errors) >= 64,
        "both_sealed_splits_nonempty": all(by_split[s]["errors"] and by_split[s]["controls"] for s in ("discovery", "confirm")),
        "representative_budget_sample_ge_512_per_split": all(len(budget_by_split[s]) >= 512 for s in ("discovery", "confirm")),
        "discovery_selected_budget_neutral_policy": policy is not None,
        "confirm_budget_ratio_0_98_to_1_00": policy is not None and 0.98 <= float(budget_confirm.get("node_budget_ratio") or 0.0) <= 1.0,
        "confirm_regret_reduction_positive_95": policy is not None and (regret_boot.get("ci95") or [None])[0] is not None and float(regret_boot["ci95"][0]) > 0.0,
        "confirm_error_rate_reduction_positive_95": policy is not None and (error_boot.get("ci95") or [None])[0] is not None and float(error_boot["ci95"][0]) > 0.0,
        "confirm_controls_no_mean_regret_regression": policy is not None and float(control_confirm.get("adaptive_mean_regret_cp") or 0.0) <= float(control_confirm.get("baseline_mean_regret_cp") or 0.0),
        "confirm_controls_no_error_rate_regression": policy is not None and float(control_confirm.get("adaptive_error_rate_50cp") or 0.0) <= float(control_confirm.get("baseline_error_rate_50cp") or 0.0),
    }
    passed = all(gates.values())
    identities = {
        field: next(iter(values))
        for field in ("champion_sha256", "jass_sha256", "search_params_sha256")
        for values in [{str(shard[field]) for shard in shards}]
        if len(values) == 1
    }
    if len(identities) != 3:
        raise ValueError("atlas shards do not authenticate one engine/model/profile")
    return {
        "schema": SCHEMA_REPORT,
        "verdict": "JASS_CURRICULUM_SEARCH_ERROR_CONTROLLER_SCREEN_PASSED" if passed else "JASS_CURRICULUM_SEARCH_ERROR_CONTROLLER_NOT_ESTABLISHED",
        "passed": passed,
        **identities,
        "source": {
            "decisions": 79_110,
            "original_error_openings": int(pairs["error_openings"]),
            "matched_pairs": int(pairs["matched_pairs"]),
            "matched_fraction": float(pairs["matched_fraction"]),
            "symmetrised_error_openings": len(symm_errors),
        },
        "splits": {
            split: {"errors": len(by_split[split]["errors"]), "controls": len(by_split[split]["controls"])}
            for split in ("discovery", "confirm")
        },
        "controller": {"policy": policy, "simulations": simulations, "bootstrap": bootstrap},
        "controller_observation_depth": 9,
        "controller_runtime_uses_exact_image": False,
        "search_ablation": {"localized_mechanism": mechanism, "passing_arms": localized, "arms": arm_summary},
        "gates": gates,
        "failed_gates": [name for name, value in gates.items() if not value],
        "weights_bit_identical": True,
        "new_selfplay_games": 0,
        "fits": 0,
        "strength_games": 0,
        "frozen_reads": 0,
        "promotion_authorized": False,
        "next_stage_authorized": passed,
        "automatic_continuation": False,
        "next_stage": "implement_budget_neutral_search_controller" if passed else None,
    }


def _load_many(paths: Iterable[Path]) -> list[dict[str, Any]]:
    return [json.loads(path.read_text(encoding="utf-8")) for path in paths]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    prepare = sub.add_parser("prepare")
    prepare.add_argument("--selection", type=Path, required=True)
    prepare.add_argument("--source-shard", action="append", type=Path, required=True)
    prepare.add_argument("--min-regret-cp", type=int, default=50)
    prepare.add_argument("--max-control-regret-cp", type=int, default=10)
    prepare.add_argument("--candidates-per-error", type=int, default=16)
    prepare.add_argument("--budget-rows-per-split", type=int, default=1024)
    prepare.add_argument("--out", type=Path, required=True)
    profile = sub.add_parser("profile")
    profile.add_argument("--selection", required=True)
    profile.add_argument("--jass", required=True)
    profile.add_argument("--champion", required=True)
    profile.add_argument("--search-params", required=True)
    profile.add_argument("--shard", type=int, required=True)
    profile.add_argument("--nshards", type=int, required=True)
    profile.add_argument("--max-rows", type=int, default=0)
    profile.add_argument("--out", type=Path, required=True)
    match = sub.add_parser("match")
    match.add_argument("--selection", type=Path, required=True)
    match.add_argument("--profile-shard", action="append", type=Path, required=True)
    match.add_argument("--out", type=Path, required=True)
    atlas = sub.add_parser("atlas")
    atlas.add_argument("--pairs", required=True)
    atlas.add_argument("--jass", required=True)
    atlas.add_argument("--champion", required=True)
    atlas.add_argument("--search-params", required=True)
    atlas.add_argument("--judge-depth", type=int, default=12)
    atlas.add_argument("--shard", type=int, required=True)
    atlas.add_argument("--nshards", type=int, required=True)
    atlas.add_argument("--max-pairs", type=int, default=0)
    atlas.add_argument("--out", type=Path, required=True)
    aggregate = sub.add_parser("aggregate")
    aggregate.add_argument("--pairs", type=Path, required=True)
    aggregate.add_argument("--atlas-shard", action="append", type=Path, required=True)
    aggregate.add_argument("--bootstrap-samples", type=int, default=100_000)
    aggregate.add_argument("--bootstrap-seed", type=int, default=2026082221)
    aggregate.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == "prepare":
        payload = prepare_profile_selection(
            json.loads(args.selection.read_text(encoding="utf-8")),
            _load_many(args.source_shard),
            min_regret_cp=args.min_regret_cp,
            max_control_regret_cp=args.max_control_regret_cp,
            candidates_per_error=args.candidates_per_error,
            budget_rows_per_split=args.budget_rows_per_split,
        )
    elif args.command == "profile":
        payload = profile_shard(args)
    elif args.command == "match":
        payload = match_profiles(
            json.loads(args.selection.read_text(encoding="utf-8")),
            _load_many(args.profile_shard),
        )
    elif args.command == "atlas":
        payload = atlas_shard(args)
    else:
        payload = aggregate_atlas(
            json.loads(args.pairs.read_text(encoding="utf-8")),
            _load_many(args.atlas_shard),
            bootstrap_samples=args.bootstrap_samples,
            bootstrap_seed=args.bootstrap_seed,
        )
    _publish(args.out, payload)
    print(json.dumps({"schema": payload["schema"], "verdict": payload.get("verdict")}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
