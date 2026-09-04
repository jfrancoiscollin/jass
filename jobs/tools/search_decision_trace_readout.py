#!/usr/bin/env python3
"""Validate SearchDecisionTrace v1 JSONL and derive horizon-local diagnostics."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
import os
from pathlib import Path
import re
from typing import Any, Iterable


ROW_SCHEMA = "jass.search-decision-trace-export-row.v1"
TRACE_SCHEMA = "jass.search-decision-trace"
REPORT_SCHEMA = "jass.search-decision-trace-export.v1"
READOUT_SCHEMA = "jass.search-decision-trace-readout.v1"
BOUNDS = {"None", "Exact", "Lower", "Upper"}
UINT64_MAX = (1 << 64) - 1
INT32_MIN = -(1 << 31)
INT32_MAX = (1 << 31) - 1
MAX_PLY = 64
MATE_SCORE = 30_000
EMPTY_PV_HASH = 14_695_981_039_346_656_037


class ContractError(ValueError):
    """Raised when an input cannot satisfy the A3 fail-closed contract."""


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require_dict(value: Any, where: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ContractError(f"{where}: expected object")
    return value


def require_list(value: Any, where: str) -> list[Any]:
    if not isinstance(value, list):
        raise ContractError(f"{where}: expected array")
    return value


def require_bool(value: Any, where: str) -> bool:
    if type(value) is not bool:
        raise ContractError(f"{where}: expected boolean")
    return value


def require_int(
    value: Any, where: str, *, minimum: int | None = None,
    maximum: int | None = None,
) -> int:
    if type(value) is not int:
        raise ContractError(f"{where}: expected integer")
    if minimum is not None and value < minimum:
        raise ContractError(f"{where}: integer below {minimum}")
    if maximum is not None and value > maximum:
        raise ContractError(f"{where}: integer above {maximum}")
    return value


def require_string(value: Any, where: str) -> str:
    if not isinstance(value, str) or not value:
        raise ContractError(f"{where}: expected non-empty string")
    return value


def require_sha256(value: Any, where: str) -> str:
    digest = require_string(value, where)
    if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest.lower()):
        raise ContractError(f"{where}: expected SHA-256 hex")
    return digest


def move_key(value: Any, where: str, *, catalogue: bool = False) -> tuple[Any, ...]:
    move = require_dict(value, where)
    start = require_int(move.get("from"), f"{where}.from", minimum=0, maximum=50)
    end = require_int(move.get("to"), f"{where}.to", minimum=0, maximum=50)
    captures = require_int(
        move.get("num_captures"), f"{where}.num_captures", minimum=0, maximum=20,
    )
    promotes = require_bool(move.get("promotes"), f"{where}.promotes")
    captured = require_int(
        move.get("captured"), f"{where}.captured", minimum=0, maximum=(1 << 50) - 1,
    )
    if catalogue and (start == 0 or end == 0):
        raise ContractError(f"{where}: catalogue move uses null square")
    if captured.bit_count() != captures:
        raise ContractError(f"{where}: captured-square count drift")
    return start, end, captures, promotes, captured


def move_object(key: tuple[Any, ...]) -> dict[str, Any]:
    return {
        "from": key[0], "to": key[1], "num_captures": key[2],
        "promotes": key[3], "captured": key[4],
    }


def expected_bound(score: int, alpha: int, beta: int, completed: bool) -> str:
    if not completed:
        return "None"
    if score <= alpha:
        return "Upper"
    if score >= beta:
        return "Lower"
    return "Exact"


def validate_action(
    raw: Any, where: str, catalogue: set[tuple[Any, ...]], attempt_beta: int,
    attempt_depth: int,
) -> tuple[tuple[Any, ...], dict[str, Any]]:
    action = require_dict(raw, where)
    key = move_key(action.get("move"), f"{where}.move", catalogue=True)
    if key not in catalogue:
        raise ContractError(f"{where}: action is outside root catalogue")
    score = require_int(
        action.get("score"), f"{where}.score", minimum=INT32_MIN, maximum=INT32_MAX,
    )
    alpha = require_int(
        action.get("alpha"), f"{where}.alpha", minimum=INT32_MIN, maximum=INT32_MAX,
    )
    beta = require_int(
        action.get("beta"), f"{where}.beta", minimum=INT32_MIN, maximum=INT32_MAX,
    )
    if beta != attempt_beta or alpha >= beta:
        raise ContractError(f"{where}: action window drift")
    completed = require_bool(action.get("completed"), f"{where}.completed")
    bound = action.get("bound")
    if bound not in BOUNDS or bound != expected_bound(score, alpha, beta, completed):
        raise ContractError(f"{where}: action bound contract drift")
    cutoff = require_bool(action.get("cutoff"), f"{where}.cutoff")
    if cutoff != (completed and score >= beta):
        raise ContractError(f"{where}: action cutoff contract drift")
    for field in ("nodes", "eval_calls", "pvs_researches"):
        require_int(action.get(field), f"{where}.{field}", minimum=0, maximum=UINT64_MAX)
    require_int(action.get("pv_length"), f"{where}.pv_length", minimum=0)
    require_int(action.get("pv_hash"), f"{where}.pv_hash", minimum=0, maximum=UINT64_MAX)
    if completed:
        if not 1 <= action["pv_length"] <= attempt_depth:
            raise ContractError(f"{where}: completed action PV length outside horizon")
    elif action["pv_length"] != 0 or action["pv_hash"] != EMPTY_PV_HASH:
        raise ContractError(f"{where}: interrupted action has non-empty PV receipt")
    return key, action


def validate_attempt(
    raw: Any, where: str, catalogue_order: list[tuple[Any, ...]],
) -> dict[str, Any]:
    attempt = require_dict(raw, where)
    depth = require_int(attempt.get("depth"), f"{where}.depth", minimum=1)
    number = require_int(
        attempt.get("attempt"), f"{where}.attempt", minimum=1, maximum=INT32_MAX,
    )
    alpha = require_int(
        attempt.get("alpha"), f"{where}.alpha", minimum=INT32_MIN, maximum=INT32_MAX,
    )
    beta = require_int(
        attempt.get("beta"), f"{where}.beta", minimum=INT32_MIN, maximum=INT32_MAX,
    )
    if alpha >= beta:
        raise ContractError(f"{where}: invalid attempt window")
    score = require_int(
        attempt.get("score"), f"{where}.score", minimum=INT32_MIN, maximum=INT32_MAX,
    )
    completed = require_bool(attempt.get("completed"), f"{where}.completed")
    bound = attempt.get("bound")
    if bound not in BOUNDS or bound != expected_bound(score, alpha, beta, completed):
        raise ContractError(f"{where}: attempt bound contract drift")
    cutoff = require_bool(attempt.get("cutoff"), f"{where}.cutoff")
    if cutoff != (completed and score >= beta):
        raise ContractError(f"{where}: attempt cutoff contract drift")

    before_after: dict[str, tuple[int, int]] = {}
    for counter in ("nodes", "eval_calls", "pvs_researches"):
        before = require_int(
            attempt.get(f"{counter}_before"), f"{where}.{counter}_before",
            minimum=0, maximum=UINT64_MAX,
        )
        after = require_int(
            attempt.get(f"{counter}_after"), f"{where}.{counter}_after",
            minimum=0, maximum=UINT64_MAX,
        )
        if after < before:
            raise ContractError(f"{where}: decreasing {counter}")
        before_after[counter] = before, after

    catalogue = set(catalogue_order)
    actions: list[dict[str, Any]] = []
    action_keys: list[tuple[Any, ...]] = []
    for index, raw_action in enumerate(require_list(attempt.get("actions"), f"{where}.actions")):
        key, action = validate_action(
            raw_action, f"{where}.actions[{index}]", catalogue, beta, depth,
        )
        if key in action_keys:
            raise ContractError(f"{where}: duplicate semantic action")
        action_keys.append(key)
        actions.append(action)
    running_alpha = alpha
    first_maximum_key: tuple[Any, ...] | None = None
    maximum_score: int | None = None
    for index, (key, action) in enumerate(zip(action_keys, actions)):
        if action["alpha"] != running_alpha:
            raise ContractError(f"{where}: non-sequential action alpha")
        if maximum_score is None or action["score"] > maximum_score:
            maximum_score = action["score"]
            first_maximum_key = key
        running_alpha = max(running_alpha, action["score"])
        if (action["cutoff"] or not action["completed"]) and index + 1 != len(actions):
            raise ContractError(f"{where}: cutoff/incomplete action is not last")
    if not actions:
        raise ContractError(f"{where}: attempted root window contains no action")
    if completed and any(not action["completed"] for action in actions):
        raise ContractError(f"{where}: completed attempt contains incomplete action")
    if not completed and actions and actions[-1]["completed"]:
        raise ContractError(f"{where}: interrupted attempt has no interrupted last action")
    all_actions = require_bool(
        attempt.get("all_actions_searched"), f"{where}.all_actions_searched",
    )
    if all_actions != (set(action_keys) == catalogue):
        raise ContractError(f"{where}: root-action coverage drift")
    if completed and not all_actions and not cutoff:
        raise ContractError(f"{where}: completed partial attempt lacks beta cutoff")
    if bound == "Exact" and completed and not all_actions:
        raise ContractError(f"{where}: Exact attempt lacks complete catalogue")
    for counter, (before, after) in before_after.items():
        observed = sum(require_int(
            action[counter], f"{where}.actions.{counter}", minimum=0, maximum=UINT64_MAX,
        ) for action in actions)
        if observed != after - before:
            raise ContractError(f"{where}: {counter} action/attempt delta mismatch")
    best_key = move_key(attempt.get("best_move"), f"{where}.best_move")
    if actions and best_key not in set(action_keys):
        raise ContractError(f"{where}: best move was not searched")
    if completed and (
        maximum_score is None or score != maximum_score or best_key != first_maximum_key
    ):
        raise ContractError(f"{where}: completed score/best-move reduction drift")
    if cutoff != actions[-1]["cutoff"]:
        raise ContractError(f"{where}: attempt/action cutoff mismatch")
    attempt["_depth"] = depth
    attempt["_number"] = number
    attempt["_actions"] = dict(zip(action_keys, actions))
    attempt["_best_key"] = best_key
    return attempt


def validate_trace(raw: Any, where: str) -> dict[str, Any]:
    trace = require_dict(raw, where)
    if trace.get("schema") != TRACE_SCHEMA or trace.get("version") != 1:
        raise ContractError(f"{where}: unsupported trace schema/version")
    root_actions_raw = require_list(trace.get("root_actions"), f"{where}.root_actions")
    catalogue = [move_key(move, f"{where}.root_actions[{i}]", catalogue=True)
                 for i, move in enumerate(root_actions_raw)]
    if len(catalogue) != len(set(catalogue)):
        raise ContractError(f"{where}: duplicate root action")
    if require_int(trace.get("semantic_root_actions"), f"{where}.semantic_root_actions", minimum=0) != len(catalogue):
        raise ContractError(f"{where}: semantic_root_actions mismatch")
    no_moves = require_bool(trace.get("no_legal_moves"), f"{where}.no_legal_moves")
    require_bool(trace.get("root_rule_draw"), f"{where}.root_rule_draw")
    raw_attempts = require_list(trace.get("attempts"), f"{where}.attempts")
    if no_moves != (len(catalogue) == 0) or (no_moves and raw_attempts):
        raise ContractError(f"{where}: no-legal-move contract drift")

    attempts = [validate_attempt(item, f"{where}.attempts[{i}]", catalogue)
                for i, item in enumerate(raw_attempts)]
    expected_number: dict[int, int] = defaultdict(int)
    prior_depth = 0
    prior_after = {"nodes": 0, "eval_calls": 0, "pvs_researches": 0}
    for index, attempt in enumerate(attempts):
        depth = attempt["_depth"]
        if depth < prior_depth or depth > prior_depth + 1:
            raise ContractError(f"{where}: non-contiguous attempt depths")
        expected_number[depth] += 1
        if attempt["_number"] != expected_number[depth]:
            raise ContractError(f"{where}: non-contiguous attempt numbers")
        for counter in prior_after:
            if attempt[f"{counter}_before"] != prior_after[counter]:
                raise ContractError(f"{where}: non-contiguous cumulative {counter}")
            prior_after[counter] = attempt[f"{counter}_after"]
        following = attempts[index + 1] if index + 1 < len(attempts) else None
        if not attempt["completed"] or attempt["bound"] == "None":
            if following is not None:
                raise ContractError(f"{where}: interrupted/None attempt is not terminal")
        elif attempt["bound"] == "Exact":
            if following is not None and following["_depth"] == depth:
                raise ContractError(f"{where}: retry follows terminal Exact attempt")
        else:
            if following is None or following["_depth"] != depth:
                raise ContractError(f"{where}: fail bound lacks same-depth retry")
            if attempt["bound"] == "Lower" and not (
                following["alpha"] == attempt["alpha"]
                and following["beta"] > attempt["beta"]
            ):
                raise ContractError(f"{where}: Lower retry window did not widen beta only")
            if attempt["bound"] == "Upper" and not (
                following["beta"] == attempt["beta"]
                and following["alpha"] < attempt["alpha"]
            ):
                raise ContractError(f"{where}: Upper retry window did not widen alpha only")
        prior_depth = depth
    result = require_dict(trace.get("result"), f"{where}.result")
    move_key(result.get("best_move"), f"{where}.result.best_move")
    require_int(
        result.get("score"), f"{where}.result.score",
        minimum=INT32_MIN, maximum=INT32_MAX,
    )
    for field in ("nodes", "eval_calls", "pvs_researches"):
        require_int(
            result.get(field), f"{where}.result.{field}",
            minimum=0, maximum=UINT64_MAX,
        )
    for field in ("completed_depth", "effective_depth", "pv_length"):
        require_int(result.get(field), f"{where}.result.{field}", minimum=0)
    require_int(result.get("pv_hash"), f"{where}.result.pv_hash", minimum=0, maximum=UINT64_MAX)
    require_bool(result.get("aborted_iteration"), f"{where}.result.aborted_iteration")
    if result.get("stop_reason") not in {"none", "nodes", "time", "external"}:
        raise ContractError(f"{where}: invalid stop reason")
    for counter in prior_after:
        if result[counter] != prior_after[counter]:
            raise ContractError(f"{where}: final {counter} receipt mismatch")
    trace["_catalogue"] = catalogue
    trace["_attempts"] = attempts
    return trace


def validate_row(raw: Any, where: str) -> dict[str, Any]:
    row = require_dict(raw, where)
    if row.get("schema") != ROW_SCHEMA or row.get("version") != 1:
        raise ContractError(f"{where}: unsupported export-row schema/version")
    require_string(row.get("invocation_id"), f"{where}.invocation_id")
    board = require_dict(row.get("board_identity"), f"{where}.board_identity")
    require_string(board.get("canonical_fen"), f"{where}.board_identity.canonical_fen")
    root_hash = require_int(
        board.get("zobrist_hash"), f"{where}.board_identity.zobrist_hash",
        minimum=0, maximum=UINT64_MAX,
    )
    rules = require_dict(row.get("rule_state_identity"), f"{where}.rule_state_identity")
    halfmove_clock = require_int(
        rules.get("halfmove_clock"), f"{where}.rule_state_identity.halfmove_clock",
        minimum=0, maximum=(1 << 31) - 1 - MAX_PLY,
    )
    history_hashes = require_list(
        rules.get("history_hashes"), f"{where}.rule_state_identity.history_hashes",
    )
    for i, value in enumerate(history_hashes):
        require_int(value, f"{where}.rule_state_identity.history_hashes[{i}]", minimum=0, maximum=UINT64_MAX)
    context = require_dict(row.get("search_context_identity"), f"{where}.search_context_identity")
    if (context.get("threads") != 1 or context.get("book_enabled") is not False
            or context.get("fresh_tt_per_invocation") is not True
            or context.get("movetime_ms") != 0
            or context.get("search_params_source") != "compiled_defaults"):
        raise ContractError(f"{where}: unsupported search context")
    max_depth = require_int(
        context.get("max_depth"), f"{where}.search_context_identity.max_depth",
        minimum=1, maximum=MAX_PLY,
    )
    max_nodes = require_int(
        context.get("max_nodes"), f"{where}.search_context_identity.max_nodes",
        minimum=0, maximum=UINT64_MAX,
    )
    require_int(
        context.get("tt_mb"), f"{where}.search_context_identity.tt_mb",
        minimum=1, maximum=1_048_576,
    )
    evaluation = require_dict(
        context.get("evaluation"), f"{where}.search_context_identity.evaluation",
    )
    if evaluation.get("kind") == "handcrafted":
        if (evaluation.get("artifact_path") is not None
                or evaluation.get("artifact_sha256") is not None
                or evaluation.get("artifact_sha256_verified") is not False
                or evaluation.get("conversion_sidecar_present") is not False
                or evaluation.get("conversion_sidecar_path") is not None
                or evaluation.get("conversion_sidecar_sha256") is not None):
            raise ContractError(f"{where}: handcrafted evaluation identity drift")
    elif evaluation.get("kind") == "file":
        require_string(evaluation.get("artifact_path"), f"{where}.evaluation.artifact_path")
        require_sha256(evaluation.get("artifact_sha256"), f"{where}.evaluation.artifact_sha256")
        if evaluation.get("artifact_sha256_verified") is not True:
            raise ContractError(f"{where}: evaluation artifact digest is not verified")
        sidecar = require_bool(
            evaluation.get("conversion_sidecar_present"),
            f"{where}.evaluation.conversion_sidecar_present",
        )
        if sidecar:
            require_string(
                evaluation.get("conversion_sidecar_path"),
                f"{where}.evaluation.conversion_sidecar_path",
            )
            require_sha256(
                evaluation.get("conversion_sidecar_sha256"),
                f"{where}.evaluation.conversion_sidecar_sha256",
            )
        elif (evaluation.get("conversion_sidecar_path") is not None
              or evaluation.get("conversion_sidecar_sha256") is not None):
            raise ContractError(f"{where}: absent sidecar has provenance")
    else:
        raise ContractError(f"{where}: unsupported evaluation identity")
    code = require_dict(context.get("code_provenance"), f"{where}.search_context_identity.code_provenance")
    require_string(code.get("declared"), f"{where}.search_context_identity.code_provenance.declared")
    if code.get("declared_verified_by_exporter") is not False:
        raise ContractError(f"{where}: declared code provenance must remain unverified")
    require_string(
        code.get("executable_path"),
        f"{where}.search_context_identity.code_provenance.executable_path",
    )
    require_sha256(
        code.get("executable_sha256"),
        f"{where}.search_context_identity.code_provenance.executable_sha256",
    )
    if code.get("executable_sha256_verified") is not True:
        raise ContractError(f"{where}: executable digest is not verified")
    row["_trace"] = validate_trace(row.get("trace"), f"{where}.trace")
    trace = row["_trace"]
    expected_rule_draw = halfmove_clock >= 50 or root_hash in history_hashes
    if trace["root_rule_draw"] != expected_rule_draw:
        raise ContractError(f"{where}: root rule-draw identity drift")
    mode = context.get("node_limit_mode")
    if mode != ("periodic" if max_nodes == 0 else "exact"):
        raise ContractError(f"{where}: node-limit mode/max_nodes drift")
    attempts = trace["_attempts"]
    result = trace["result"]
    if any(attempt["_depth"] > max_depth for attempt in attempts):
        raise ContractError(f"{where}: attempt depth exceeds search context max_depth")
    if trace["no_legal_moves"]:
        if any(result[field] != 0 for field in (
            "completed_depth", "effective_depth", "nodes", "eval_calls", "pvs_researches",
        )) or (
            result["stop_reason"] != "none"
            or result["aborted_iteration"]
            or result["score"] != -MATE_SCORE
            or move_key(result["best_move"], f"{where}.trace.result.best_move")
            != (0, 0, 0, False, 0)
            or result["pv_length"] != 0
            or result["pv_hash"] != EMPTY_PV_HASH
        ):
            raise ContractError(f"{where}: no-legal-move result drift")
        return row
    if result["pv_length"] > max(result["completed_depth"], 1):
        raise ContractError(f"{where}: public PV length exceeds completed horizon")
    if result["pv_length"] == 0 and result["pv_hash"] != EMPTY_PV_HASH:
        raise ContractError(f"{where}: empty public PV has non-empty hash")
    settled = [
        attempt for attempt in attempts
        if attempt["completed"] and attempt["bound"] == "Exact"
        and attempt["all_actions_searched"]
    ]
    last_settled = settled[-1] if settled else None
    expected_completed_depth = last_settled["_depth"] if last_settled else 0
    expected_effective_depth = max((attempt["_depth"] for attempt in attempts), default=0)
    if (result["completed_depth"] != expected_completed_depth
            or result["effective_depth"] != expected_effective_depth):
        raise ContractError(f"{where}: completed/effective depth receipt drift")
    if result["aborted_iteration"] != (
        result["stop_reason"] != "none"
        and expected_effective_depth > expected_completed_depth
    ):
        raise ContractError(f"{where}: aborted-iteration receipt drift")
    if max_nodes == 0:
        if (result["stop_reason"] != "none"
                or expected_completed_depth != context["max_depth"]):
            raise ContractError(f"{where}: fixed-depth export did not settle")
    else:
        if result["stop_reason"] not in {"none", "nodes"}:
            raise ContractError(f"{where}: exact-node export has foreign stop reason")
        if result["nodes"] > max_nodes:
            raise ContractError(f"{where}: exact-node export exceeded cap")
        if result["stop_reason"] == "nodes" and result["nodes"] != max_nodes:
            raise ContractError(f"{where}: exact-node stop did not reach cap")
        if result["stop_reason"] == "none" and expected_completed_depth != context["max_depth"]:
            raise ContractError(f"{where}: exact-node export ended before depth/cap")
    expected_best = (
        last_settled["_best_key"] if last_settled is not None else trace["_catalogue"][0]
    )
    if move_key(result["best_move"], f"{where}.trace.result.best_move") != expected_best:
        raise ContractError(f"{where}: final best-move receipt mismatch")
    expected_score = 0 if last_settled is None else last_settled["score"]
    if trace["root_rule_draw"]:
        expected_score = 0
    if result["score"] != expected_score:
        raise ContractError(f"{where}: final score receipt mismatch")
    return row


def merge_intervals(
    attempts: list[dict[str, Any]], catalogue: list[tuple[Any, ...]], where: str,
) -> dict[tuple[Any, ...], dict[str, Any]]:
    merged = {
        key: {"lower": None, "upper": None, "completed_observations": [],
              "none_or_missing_attempts": []}
        for key in catalogue
    }
    for attempt in attempts:
        actions = attempt["_actions"]
        for key in catalogue:
            action = actions.get(key)
            if action is None or not action["completed"] or action["bound"] == "None":
                merged[key]["none_or_missing_attempts"].append(attempt["_number"])
                continue
            score = action["score"]
            bound = action["bound"]
            merged[key]["completed_observations"].append(attempt["_number"])
            if bound in {"Exact", "Lower"}:
                lower = merged[key]["lower"]
                merged[key]["lower"] = score if lower is None else max(lower, score)
            if bound in {"Exact", "Upper"}:
                upper = merged[key]["upper"]
                merged[key]["upper"] = score if upper is None else min(upper, score)
            lower = merged[key]["lower"]
            upper = merged[key]["upper"]
            if lower is not None and upper is not None and lower > upper:
                raise ContractError(f"{where}: contradictory retry bounds for action {key}")
    return merged


def derive_horizon(
    depth: int, attempts: list[dict[str, Any]], catalogue: list[tuple[Any, ...]],
) -> dict[str, Any]:
    where = f"depth {depth}"
    intervals = merge_intervals(attempts, catalogue, where)
    settled_candidates = [
        attempt for attempt in attempts
        if attempt["completed"] and attempt["bound"] == "Exact"
        and attempt["all_actions_searched"]
    ]
    if len(settled_candidates) > 1:
        raise ContractError(f"{where}: multiple settled attempts")
    settled = settled_candidates[0] if settled_candidates else None
    if settled is not None:
        if set(settled["_actions"]) != set(catalogue):
            raise ContractError(f"{where}: settled attempt catalogue drift")
        chosen_key = settled["_best_key"]
        if chosen_key not in settled["_actions"] or not settled["_actions"][chosen_key]["completed"]:
            raise ContractError(f"{where}: settled chosen action is incomplete")
    elif len(catalogue) == 1:
        chosen_key = catalogue[0]
    else:
        chosen_key = None

    actions_out = []
    for index, key in enumerate(catalogue):
        interval = intervals[key]
        actions_out.append({
            "catalogue_index": index,
            "move": move_object(key),
            "lower": interval["lower"],
            "upper": interval["upper"],
            "lower_unbounded": interval["lower"] is None,
            "upper_unbounded": interval["upper"] is None,
            "completed_observations": interval["completed_observations"],
            "none_or_missing_attempts": interval["none_or_missing_attempts"],
        })

    if len(catalogue) == 1:
        chosen_interval = intervals[catalogue[0]]
        decision = {
            "status": "SINGLE_LEGAL_ACTION",
            "chosen_move": move_object(catalogue[0]),
            "certified_at_current_horizon": True,
            "certification_basis": "legal_support_singleton",
            "chosen_value_exact": (
                chosen_interval["lower"] is not None
                and chosen_interval["lower"] == chosen_interval["upper"]
            ),
            "r_max": {"status": "FINITE_FORCED_DECISION", "value": 0},
        }
    elif settled is None:
        decision = {
            "status": "INCOMPLETE_HORIZON",
            "chosen_move": None,
            "certified_at_current_horizon": False,
            "certification_basis": "none",
            "chosen_value_exact": False,
            "r_max": {"status": "NOT_APPLICABLE_NO_SETTLED_CHOICE", "value": None},
        }
    else:
        if chosen_key is None:
            raise ContractError(f"{where}: settled horizon has no chosen action")
        chosen_interval = intervals[chosen_key]
        competitors = [intervals[key]["upper"] for key in catalogue if key != chosen_key]
        finite_certificate = chosen_interval["lower"] is not None and all(
            upper is not None for upper in competitors
        )
        certified = bool(finite_certificate and chosen_interval["lower"] > max(competitors))
        if not finite_certificate:
            basis = "unbounded_action"
        elif certified:
            basis = "strict_bound_separation"
        else:
            basis = "no_strict_separation"
        all_uppers = [intervals[key]["upper"] for key in catalogue]
        if chosen_interval["lower"] is None or any(value is None for value in all_uppers):
            r_max = {"status": "UNBOUNDED", "value": None}
        else:
            r_max = {
                "status": "FINITE",
                "value": max(value for value in all_uppers if value is not None)
                - chosen_interval["lower"],
            }
        decision = {
            "status": "MULTI_ACTION_SETTLED",
            "chosen_move": move_object(chosen_key),
            "certified_at_current_horizon": certified,
            "certification_basis": basis,
            "chosen_value_exact": (
                chosen_interval["lower"] is not None
                and chosen_interval["lower"] == chosen_interval["upper"]
            ),
            "r_max": r_max,
        }

    bound_counts = Counter(attempt["bound"] for attempt in attempts)
    pvs_total = sum(
        attempt["pvs_researches_after"] - attempt["pvs_researches_before"]
        for attempt in attempts
    )
    chosen_pv = None
    if settled is not None and chosen_key is not None:
        chosen_action = settled["_actions"][chosen_key]
        chosen_pv = {
            "hash": chosen_action["pv_hash"], "length": chosen_action["pv_length"],
        }
    return {
        "depth": depth,
        "settled": settled is not None,
        "settled_attempt": settled["_number"] if settled is not None else None,
        "search_score": settled["score"] if settled is not None else None,
        "attempts": len(attempts),
        "aspiration": {
            "upper_failures": bound_counts["Upper"],
            "lower_failures": bound_counts["Lower"],
            "exact_attempts": bound_counts["Exact"],
            "interrupted_attempts": bound_counts["None"],
            "retries_after_first": max(0, len(attempts) - 1),
        },
        "pvs_researches": pvs_total,
        "actions": actions_out,
        "decision": decision,
        "chosen_pv": chosen_pv,
        "_chosen_key": chosen_key,
    }


def derive_sequence(horizons: list[dict[str, Any]]) -> dict[str, Any]:
    sequence = [horizon for horizon in horizons if horizon["settled"]]
    flips = []
    score_steps = []
    pv_transitions = []
    for prior, current in zip(sequence, sequence[1:]):
        same_move = prior["_chosen_key"] == current["_chosen_key"]
        if not same_move:
            flips.append({
                "from_depth": prior["depth"], "to_depth": current["depth"],
                "from_move": move_object(prior["_chosen_key"]),
                "to_move": move_object(current["_chosen_key"]),
            })
        delta = current["search_score"] - prior["search_score"]
        score_steps.append({
            "from_depth": prior["depth"], "to_depth": current["depth"],
            "delta": delta, "absolute_delta": abs(delta),
        })
        if prior["chosen_pv"] is not None and current["chosen_pv"] is not None:
            changed = prior["chosen_pv"] != current["chosen_pv"]
            pv_transitions.append({
                "from_depth": prior["depth"], "to_depth": current["depth"],
                "same_chosen_action": same_move, "changed": changed,
            })

    first_stable = None
    for index, horizon in enumerate(sequence):
        if all(other["_chosen_key"] == horizon["_chosen_key"] for other in sequence[index:]):
            first_stable = horizon["depth"]
            break
    scores = [horizon["search_score"] for horizon in sequence]
    return {
        "completed_horizons": len(sequence),
        "depths": [horizon["depth"] for horizon in sequence],
        "chosen_moves": [move_object(horizon["_chosen_key"]) for horizon in sequence],
        "best_move_flips": flips,
        "first_observed_suffix_stable_depth": first_stable,
        "score_path": scores,
        "score_steps": score_steps,
        "score_range": max(scores) - min(scores) if scores else None,
        "score_max_absolute_step": max(
            (step["absolute_delta"] for step in score_steps), default=0 if scores else None,
        ),
        "pv_comparable_transitions": len(pv_transitions),
        "pv_churn_transitions": sum(item["changed"] for item in pv_transitions),
        "pv_churn_same_action_transitions": sum(
            item["changed"] and item["same_chosen_action"] for item in pv_transitions
        ),
        "pv_transitions": pv_transitions,
    }


def analyze_row(row: dict[str, Any], where: str = "row") -> dict[str, Any]:
    row = validate_row(row, where)
    trace = row["_trace"]
    attempts_by_depth: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for attempt in trace["_attempts"]:
        attempts_by_depth[attempt["_depth"]].append(attempt)
    horizons = [
        derive_horizon(depth, attempts_by_depth[depth], trace["_catalogue"])
        for depth in sorted(attempts_by_depth)
    ]
    sequence = derive_sequence(horizons)
    for horizon in horizons:
        horizon.pop("_chosen_key")
    result = trace["result"]
    return {
        "invocation_id": row["invocation_id"],
        "source_receipt": row.get("_source_receipt"),
        "board_identity": row["board_identity"],
        "rule_state_identity": row["rule_state_identity"],
        "search_context_identity": row["search_context_identity"],
        "root_rule_draw": trace["root_rule_draw"],
        "decision_scope": (
            "RULE_DRAW_SEARCH_OBSERVATION" if trace["root_rule_draw"]
            else "ORDINARY_SEARCH_OBSERVATION"
        ),
        "no_legal_moves": trace["no_legal_moves"],
        "root_decision_status": (
            "NO_LEGAL_ACTION" if trace["no_legal_moves"] else "LEGAL_ACTIONS_PRESENT"
        ),
        "semantic_root_actions": len(trace["_catalogue"]),
        "horizons": horizons,
        "sequence": sequence,
        "public_result": result,
    }


def load_jsonl(paths: Iterable[Path]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    receipts: list[dict[str, Any]] = []
    seen: set[str] = set()
    seen_digests: set[str] = set()
    for path in paths:
        count = 0
        file_rows: list[dict[str, Any]] = []
        with path.open(encoding="utf-8") as stream:
            for line_number, line in enumerate(stream, 1):
                if not line.strip():
                    raise ContractError(f"{path}:{line_number}: blank JSONL row")
                try:
                    raw = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ContractError(f"{path}:{line_number}: invalid JSON: {exc}") from exc
                invocation = require_string(
                    require_dict(raw, f"{path}:{line_number}").get("invocation_id"),
                    f"{path}:{line_number}.invocation_id",
                )
                if invocation in seen:
                    raise ContractError(f"duplicate invocation_id {invocation}")
                seen.add(invocation)
                rows.append(raw)
                file_rows.append(raw)
                count += 1
        if count == 0:
            raise ContractError(f"{path}: empty export")
        digest = sha256(path)
        if digest in seen_digests:
            raise ContractError(f"{path}: duplicate JSONL artifact digest")
        seen_digests.add(digest)
        for line_number, row in enumerate(file_rows, 1):
            row["_source_receipt"] = {
                "jsonl_path": str(path),
                "jsonl_sha256": digest,
                "jsonl_line": line_number,
            }
        receipts.append({
            "path": str(path), "sha256": digest, "rows": count,
            "_payload_rows": file_rows,
        })
    if not rows:
        raise ContractError("no export rows")
    return rows, receipts


def validate_reports(paths: Iterable[Path], receipts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_digest = {receipt["sha256"]: receipt for receipt in receipts}
    reports = []
    for path in paths:
        try:
            report = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ContractError(f"{path}: invalid report JSON: {exc}") from exc
        report = require_dict(report, str(path))
        if report.get("schema") != REPORT_SCHEMA or report.get("version") != 1:
            raise ContractError(f"{path}: unsupported export report")
        digest = require_string(report.get("output_jsonl_sha256"), f"{path}.output_jsonl_sha256")
        receipt = by_digest.pop(digest, None)
        if receipt is None:
            raise ContractError(f"{path}: report/output receipt mismatch")
        if (report.get("diagnostic_only") is not True
                or report.get("input_manifest_sha256_verified") is not True
                or report.get("output_jsonl_sha256_verified") is not True
                or not require_sha256(report.get("input_manifest_sha256"), f"{path}.input_manifest_sha256")
                or report.get("input_invocations") != receipt["rows"]
                or report.get("emitted_invocations") != receipt["rows"]):
            raise ContractError(f"{path}: report identity/cardinality drift")
        require_string(report.get("input_manifest_path"), f"{path}.input_manifest_path")
        require_string(report.get("output_jsonl_path"), f"{path}.output_jsonl_path")
        report_context = require_dict(
            report.get("search_context_identity"), f"{path}.search_context_identity",
        )
        if any(row.get("search_context_identity") != report_context
               for row in receipt["_payload_rows"]):
            raise ContractError(f"{path}: report/row search context drift")
        if (report.get("fits") != 0 or report.get("strength_games") != 0
                or report.get("bakes") != 0 or report.get("promotions") != 0
                or report.get("training_allowed") is not False
                or report.get("tuning_allowed") is not False
                or report.get("model_selection_allowed") is not False
                or report.get("promotion_authorized") is not False):
            raise ContractError(f"{path}: quarantine drift")
        report_sha256 = sha256(path)
        for row in receipt["_payload_rows"]:
            row["_source_receipt"].update({
                "export_report_path": str(path),
                "export_report_sha256": report_sha256,
            })
        reports.append({"path": str(path), "sha256": report_sha256, "payload": report})
    if by_digest:
        raise ContractError("missing export report for one or more JSONL inputs")
    return reports


def build_readout(
    rows: list[dict[str, Any]], receipts: list[dict[str, Any]] | None = None,
    reports: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    contexts = [analyze_row(row, f"rows[{index}]") for index, row in enumerate(rows)]
    scopes = ("ORDINARY_SEARCH_OBSERVATION", "RULE_DRAW_SEARCH_OBSERVATION")
    fields = (
        "contexts", "no_legal_moves", "single_action_contexts", "horizons",
        "settled_horizons", "certified_decisions",
    )
    counts_by_scope: dict[str, Counter[str]] = {
        scope: Counter({field: 0 for field in fields}) for scope in scopes
    }
    for context in contexts:
        counts = counts_by_scope[context["decision_scope"]]
        counts["contexts"] += 1
        counts["no_legal_moves"] += context["no_legal_moves"]
        counts["single_action_contexts"] += context["semantic_root_actions"] == 1
        for horizon in context["horizons"]:
            counts["horizons"] += 1
            counts["settled_horizons"] += horizon["settled"]
            counts["certified_decisions"] += horizon["decision"]["certified_at_current_horizon"]
    clean_receipts = [
        {key: value for key, value in receipt.items() if not key.startswith("_")}
        for receipt in (receipts or [])
    ]
    return {
        "schema": READOUT_SCHEMA,
        "version": 1,
        "diagnostic_only": True,
        "input_receipts": clean_receipts,
        "export_reports": reports or [],
        "summary": {
            "contexts": len(contexts),
            "by_scope": {
                scope: dict(sorted(counts.items()))
                for scope, counts in sorted(counts_by_scope.items())
            },
        },
        "contexts": contexts,
        "guards": {
            "cross_invocation_bound_merges": 0,
            "cross_context_bound_merges": 0,
            "cross_horizon_bound_merges": 0,
            "thresholds_applied": 0,
            "fits": 0,
            "strength_games": 0,
            "promotions": 0,
            "training_allowed": False,
            "tuning_allowed": False,
            "model_selection_allowed": False,
            "promotion_authorized": False,
        },
    }


def path_variants(path: Path) -> list[Path]:
    variants = [path]
    spelling = str(path).replace("\\", "/")
    if os.name == "nt":
        match = re.fullmatch(r"/mnt/([A-Za-z])(?:/(.*))?", spelling)
        if match:
            suffix = match.group(2) or ""
            variants.append(Path(f"{match.group(1)}:/{suffix}"))
    else:
        match = re.fullmatch(r"([A-Za-z]):(?:/(.*))?", spelling)
        if match:
            suffix = match.group(2) or ""
            variants.append(Path(f"/mnt/{match.group(1).lower()}/{suffix}"))
    return variants


def paths_alias(first: Path, second: Path) -> bool:
    for first_variant in path_variants(first):
        for second_variant in path_variants(second):
            try:
                if (first_variant.exists() and second_variant.exists()
                        and first_variant.samefile(second_variant)):
                    return True
            except OSError:
                pass
            if first_variant.resolve(strict=False) == second_variant.resolve(strict=False):
                return True
    return False


def output_conflicts(output: Path, protected_file: Path) -> bool:
    if paths_alias(output, protected_file):
        return True
    for output_variant in path_variants(output):
        for protected_variant in path_variants(protected_file):
            try:
                output_variant.resolve(strict=False).relative_to(
                    protected_variant.resolve(strict=False),
                )
                return True
            except ValueError:
                pass
    return False


def provenance_paths(
    rows: list[dict[str, Any]], reports: list[dict[str, Any]],
) -> list[Path]:
    protected: list[Path] = []
    for index, row in enumerate(rows):
        context = require_dict(
            row.get("search_context_identity"), f"rows[{index}].search_context_identity",
        )
        evaluation = require_dict(
            context.get("evaluation"), f"rows[{index}].search_context_identity.evaluation",
        )
        artifact = evaluation.get("artifact_path")
        if artifact is not None:
            artifact_path = Path(require_string(artifact, f"rows[{index}].evaluation.artifact_path"))
            protected.extend((artifact_path, Path(str(artifact_path) + ".cvh")))
        sidecar = evaluation.get("conversion_sidecar_path")
        if sidecar is not None:
            protected.append(Path(require_string(sidecar, f"rows[{index}].evaluation.conversion_sidecar_path")))
        code = require_dict(
            context.get("code_provenance"), f"rows[{index}].search_context_identity.code_provenance",
        )
        protected.append(Path(require_string(
            code.get("executable_path"), f"rows[{index}].code_provenance.executable_path",
        )))
    for index, wrapped in enumerate(reports):
        report = require_dict(wrapped.get("payload"), f"reports[{index}].payload")
        for field in ("input_manifest_path", "output_jsonl_path"):
            protected.append(Path(require_string(report.get(field), f"reports[{index}].{field}")))
    return protected


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, action="append", required=True)
    parser.add_argument("--export-report", type=Path, action="append", required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    args = parser.parse_args(argv)
    protected_inputs = [*args.input, *args.export_report]
    if any(output_conflicts(args.output_json, path) for path in protected_inputs):
        raise ContractError("output JSON path aliases an input artifact")
    rows, receipts = load_jsonl(args.input)
    reports = validate_reports(args.export_report, receipts)
    protected_inputs.extend(provenance_paths(rows, reports))
    if any(output_conflicts(args.output_json, path) for path in protected_inputs):
        raise ContractError("output JSON path aliases a provenance artifact")
    payload = build_readout(rows, receipts, reports)
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8",
    )
    print(json.dumps(payload["summary"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
