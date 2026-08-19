#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Read-only autopsy of the decisions changed by the CTX3 aligned model.

The tool never trains a model and never plays a game. On an immutable sample
of the two 1419 opening pools it asks the paired ALIGNED and SHUFFLED models for
one root decision. Disagreements are evaluated after the move by three deeper
judges (CURRICULUM, ALIGNED and SHUFFLED), always converted back to root
side-to-move POV. Exact rot180+colour-swap probes pin the search/eval
perspective independently of the target-building code.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Iterable

import numpy as np


BEST_FIELDS_RE = re.compile(
    r"^bestmove\s+\S+\s+score=(-?\d+)\s+depth=(\d+)\s+nodes=(\d+)"
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def clean_fens(path: Path) -> list[str]:
    rows = [
        raw.split("#", 1)[0].strip()
        for raw in path.read_text(encoding="utf-8").splitlines()
    ]
    rows = [row for row in rows if row]
    if len(rows) != len(set(rows)):
        raise ValueError(f"{path}: duplicate opening FEN")
    return rows


def select_openings(
    pools: list[tuple[str, Path]], *, per_pool: int, seed: int
) -> dict[str, Any]:
    if per_pool <= 0:
        raise ValueError("per_pool must be positive")
    selected: list[dict[str, Any]] = []
    certificates: list[dict[str, Any]] = []
    for pool_index, (label, path) in enumerate(pools, 1):
        fens = clean_fens(path)
        if len(fens) < per_pool:
            raise ValueError(f"{label}: only {len(fens)} openings for sample {per_pool}")
        ranked = sorted(
            range(len(fens)),
            key=lambda index: hashlib.sha256(
                f"{seed}|{label}|{index}|{fens[index]}".encode()
            ).digest(),
        )[:per_pool]
        for within_pool_ordinal, source_index in enumerate(ranked):
            selected.append(
                {
                    "ordinal": len(selected),
                    "pool_index": pool_index,
                    "pool_label": label,
                    "within_pool_ordinal": within_pool_ordinal,
                    "source_index": source_index,
                    "fen": fens[source_index],
                }
            )
        certificates.append(
            {
                "pool_index": pool_index,
                "label": label,
                "path": str(path),
                "sha256": sha256(path),
                "source_openings": len(fens),
                "selected_openings": per_pool,
            }
        )
    return {
        "schema": "jass.l3_context3_decision_flip_selection.v1",
        "seed": seed,
        "per_pool": per_pool,
        "total": len(selected),
        "pools": certificates,
        "rows": selected,
    }


def _calibrate_module() -> Any:
    try:
        import calibrate_vs_scan as cv  # type: ignore
    except ModuleNotFoundError:
        from jobs.tools import calibrate_vs_scan as cv  # type: ignore
    return cv


def _format_piece_list(tag: str, men: Iterable[int], kings: Iterable[int]) -> str:
    entries = [str(square) for square in sorted(men)]
    entries.extend(f"K{square}" for square in sorted(kings))
    return tag + ",".join(entries)


def exact_image_fen(fen: str) -> str:
    """rot180+colour-swap image of a HUB FEN (the exact game symmetry)."""
    cv = _calibrate_module()
    side, wm, wk, bm, bk = cv.parse_jass_fen(fen)
    rotate = lambda values: [51 - square for square in values]
    image_side = "B" if side == "W" else "W"
    return ":".join(
        (
            image_side,
            _format_piece_list("W", rotate(bm), rotate(bk)),
            _format_piece_list("B", rotate(wm), rotate(wk)),
        )
    )


def exact_image_move(move: str) -> str:
    match = re.fullmatch(r"(\d+)([x-])(\d+)", move)
    if not match:
        raise ValueError(f"invalid compact move {move!r}")
    return f"{51-int(match.group(1))}{match.group(2)}{51-int(match.group(3))}"


def parse_best_line(line: str) -> dict[str, int]:
    match = BEST_FIELDS_RE.search(line)
    if not match:
        raise ValueError(f"missing score/depth/nodes in {line!r}")
    return {
        "score": int(match.group(1)),
        "depth": int(match.group(2)),
        "nodes": int(match.group(3)),
    }


def _search(engine: Any, fen: str, depth: int) -> tuple[Any, dict[str, Any]]:
    cv = _calibrate_module()
    engine.new_game()
    engine.set_position_fen(fen)
    engine._drain()
    engine._send(f"go depth {depth}")
    lines = engine._read_until(
        lambda line: line.startswith("bestmove") or line.startswith("error"),
        timeout_s=300.0,
    )
    if lines[-1].startswith("error"):
        raise RuntimeError(lines[-1])
    move = cv.parse_jass_bestmove(lines[-1])
    terminal = next(
        (line for line in reversed(lines) if line.startswith("bestmove")), ""
    )
    fields = parse_best_line(terminal)
    return move, {
        **fields,
        "move": move.jass_str(),
        "apply": move.jass_apply_str(),
    }


def _child_fen(referee: Any, fen: str, move: Any) -> str:
    referee.set_position_fen(fen)
    if not referee.apply_move(move):
        raise RuntimeError(
            f"engine returned illegal move {move.jass_apply_str()} for {fen}"
        )
    child = referee.current_fen()
    if fen.split(":", 1)[0] == child.split(":", 1)[0]:
        raise RuntimeError("move application did not alternate side to move")
    return child


def _neteval(engine: Any, fen: str) -> int:
    engine.new_game()
    engine.set_position_fen(fen)
    engine._drain()
    engine._send("neteval")
    lines = engine._read_until(
        lambda line: line.startswith("neteval ") or line.startswith("error"),
        timeout_s=30.0,
    )
    if lines[-1].startswith("error"):
        raise RuntimeError(lines[-1])
    try:
        return int(lines[-1].split()[1])
    except (IndexError, ValueError) as exc:
        raise RuntimeError(f"invalid neteval reply {lines[-1]!r}") from exc


def analyse_shard(args: argparse.Namespace) -> dict[str, Any]:
    cv = _calibrate_module()
    selection = json.loads(Path(args.selection).read_text(encoding="utf-8"))
    rows = list(selection.get("rows", []))
    if selection.get("schema") != "jass.l3_context3_decision_flip_selection.v1":
        raise ValueError("selection schema drift")
    if not (0 <= args.shard < args.nshards):
        raise ValueError("invalid shard")
    engines = {
        "ALIGNED": cv.JassEngine(
            args.jass,
            label=f"aligned-s{args.shard}",
            pattern_path=args.aligned,
            search_params=args.search_params,
        ),
        "SHUFFLED": cv.JassEngine(
            args.jass,
            label=f"shuffled-s{args.shard}",
            pattern_path=args.shuffled,
            search_params=args.search_params,
        ),
        "CURRICULUM": cv.JassEngine(
            args.jass,
            label=f"curriculum-s{args.shard}",
            pattern_path=args.curriculum,
            search_params=args.search_params,
        ),
    }
    referee = cv.Referee(args.jass)
    output_rows: list[dict[str, Any]] = []
    try:
        for source in rows:
            ordinal = int(source["ordinal"])
            if ordinal % args.nshards != args.shard:
                continue
            fen = str(source["fen"])
            aligned_move, aligned_root = _search(
                engines["ALIGNED"], fen, args.choice_depth
            )
            shuffled_move, shuffled_root = _search(
                engines["SHUFFLED"], fen, args.choice_depth
            )
            row: dict[str, Any] = {
                **source,
                "root_side": fen.split(":", 1)[0],
                "choice_depth": args.choice_depth,
                "choices": {
                    "ALIGNED": aligned_root,
                    "SHUFFLED": shuffled_root,
                },
                "flipped": aligned_root["apply"] != shuffled_root["apply"],
                "piece_count": sum(
                    len(group) for group in cv.parse_jass_fen(fen)[1:]
                ),
            }
            if int(source["within_pool_ordinal"]) < args.symmetry_per_pool:
                image = exact_image_fen(fen)
                symmetry: dict[str, Any] = {"image_fen": image, "models": {}}
                for label in ("ALIGNED", "SHUFFLED", "CURRICULUM"):
                    original = _neteval(engines[label], fen)
                    transformed = _neteval(engines[label], image)
                    symmetry["models"][label] = {
                        "original_static_score": original,
                        "image_static_score": transformed,
                        "score_delta": transformed - original,
                    }
                row["exact_symmetry"] = symmetry
            if row["flipped"]:
                children = {
                    "ALIGNED_ACTION": _child_fen(referee, fen, aligned_move),
                    "SHUFFLED_ACTION": _child_fen(referee, fen, shuffled_move),
                }
                judgements: dict[str, Any] = {}
                for judge, engine in engines.items():
                    action_values: dict[str, int] = {}
                    action_details: dict[str, Any] = {}
                    for action, child in children.items():
                        _, result = _search(engine, child, args.judge_depth)
                        # Child STM is the opponent: negate back to root POV.
                        action_values[action] = -int(result["score"])
                        action_details[action] = result
                    delta = (
                        action_values["ALIGNED_ACTION"]
                        - action_values["SHUFFLED_ACTION"]
                    )
                    judgements[judge] = {
                        "root_pov_action_values": action_values,
                        "aligned_minus_shuffled_cp": delta,
                        "child_searches": action_details,
                    }
                row["children"] = children
                row["judgements"] = judgements
                row["consensus_aligned_minus_shuffled_cp"] = float(
                    np.mean(
                        [
                            judgements[label]["aligned_minus_shuffled_cp"]
                            for label in judgements
                        ]
                    )
                )
            output_rows.append(row)
    finally:
        referee.close()
        for engine in engines.values():
            engine.close()
    return {
        "schema": "jass.l3_context3_decision_flip_shard.v1",
        "selection_sha256": sha256(Path(args.selection)),
        "shard": args.shard,
        "nshards": args.nshards,
        "choice_depth": args.choice_depth,
        "judge_depth": args.judge_depth,
        "symmetry_per_pool": args.symmetry_per_pool,
        "rows": output_rows,
    }


def bootstrap_mean(
    values: np.ndarray, *, samples: int, seed: int
) -> dict[str, Any]:
    if values.ndim != 1 or len(values) == 0:
        raise ValueError("bootstrap requires a non-empty vector")
    rng = np.random.default_rng(seed)
    draws = np.empty(samples, dtype=np.float64)
    batch = 4096
    for start in range(0, samples, batch):
        stop = min(start + batch, samples)
        indices = rng.integers(
            0, len(values), size=(stop - start, len(values))
        )
        draws[start:stop] = values[indices].mean(axis=1)
    low, high = np.quantile(draws, (0.025, 0.975))
    return {
        "n": int(len(values)),
        "mean_cp": float(values.mean()),
        "median_cp": float(np.median(values)),
        "ci95_cp": [float(low), float(high)],
        "probability_positive": float(np.mean(draws > 0.0)),
        "positive_fraction": float(np.mean(values > 0.0)),
        "zero_fraction": float(np.mean(values == 0.0)),
        "bootstrap_samples": samples,
        "seed": seed,
    }


def aggregate(
    selection: dict[str, Any],
    shards: list[dict[str, Any]],
    *,
    bootstrap_samples: int,
    bootstrap_seed: int,
) -> dict[str, Any]:
    expected_nshards = len(shards)
    if {int(shard.get("shard", -1)) for shard in shards} != set(
        range(expected_nshards)
    ):
        raise ValueError("shard indices are incomplete")
    rows = [row for shard in shards for row in shard.get("rows", [])]
    rows.sort(key=lambda row: int(row["ordinal"]))
    if [int(row["ordinal"]) for row in rows] != list(
        range(int(selection["total"]))
    ):
        raise ValueError("autopsy rows do not exactly cover selection")
    symmetry_rows = [row for row in rows if "exact_symmetry" in row]
    symmetry_deltas = [
        int(model["score_delta"])
        for row in symmetry_rows
        for model in row["exact_symmetry"]["models"].values()
    ]
    flips = [row for row in rows if bool(row["flipped"])]
    judges: dict[str, Any] = {}
    for offset, label in enumerate(("CURRICULUM", "ALIGNED", "SHUFFLED")):
        values = np.asarray(
            [
                row["judgements"][label]["aligned_minus_shuffled_cp"]
                for row in flips
            ],
            dtype=np.float64,
        )
        if len(values):
            judges[label] = bootstrap_mean(
                values,
                samples=bootstrap_samples,
                seed=bootstrap_seed + offset,
            )
    consensus_values = np.asarray(
        [
            row["consensus_aligned_minus_shuffled_cp"]
            for row in flips
        ],
        dtype=np.float64,
    )
    consensus = (
        bootstrap_mean(
            consensus_values,
            samples=bootstrap_samples,
            seed=bootstrap_seed + 10,
        )
        if len(consensus_values)
        else None
    )
    symmetry_ok = bool(symmetry_deltas) and max(map(abs, symmetry_deltas)) == 0
    enough_flips = len(flips) >= 24
    curriculum_harmful = (
        bool(judges) and judges["CURRICULUM"]["ci95_cp"][1] < 0.0
    )
    consensus_harmful = (
        consensus is not None and consensus["ci95_cp"][1] < 0.0
    )
    if not symmetry_ok:
        verdict = "JASS_CONTEXT3_PERSPECTIVE_OR_EXACT_SYMMETRY_FAILURE"
        mechanism = "SIGN_OR_PERSPECTIVE_IMPLEMENTATION_DEFECT"
    elif not enough_flips:
        verdict = "JASS_CONTEXT3_DECISION_FLIP_AUTOPSY_INSUFFICIENT_FLIPS"
        mechanism = "INSUFFICIENT_DECISION_CHANGES"
    elif curriculum_harmful and consensus_harmful:
        verdict = "JASS_CONTEXT3_DECISION_CHANNEL_CONFIRMED_HARMFUL"
        mechanism = "OBSERVATIONAL_CONTEXT_CHANGES_ACTIONS_IN_HARMFUL_DIRECTION"
    else:
        verdict = "JASS_CONTEXT3_DECISION_FLIP_AUTOPSY_MIXED"
        mechanism = "LOCAL_DEEP_JUDGES_DO_NOT_ESTABLISH_A_SINGLE_DIRECTION"
    by_pool: dict[str, Any] = {}
    for pool_index in sorted({int(row["pool_index"]) for row in rows}):
        pool_rows = [
            row for row in rows if int(row["pool_index"]) == pool_index
        ]
        pool_flips = [row for row in pool_rows if row["flipped"]]
        by_pool[str(pool_index)] = {
            "sampled": len(pool_rows),
            "flips": len(pool_flips),
            "flip_rate": len(pool_flips) / len(pool_rows),
            "mean_piece_count": float(
                np.mean([row["piece_count"] for row in pool_rows])
            ),
        }
    return {
        "schema": "jass.l3_context3_decision_flip_autopsy.v1",
        "verdict": verdict,
        "mechanism": mechanism,
        "sample": {
            "openings": len(rows),
            "pools": by_pool,
            "flips": len(flips),
            "flip_rate": len(flips) / len(rows),
            "minimum_flips": 24,
            "enough_flips": enough_flips,
        },
        "perspective_guards": {
            "exact_symmetry_rows": len(symmetry_rows),
            "score_probes": len(symmetry_deltas),
            "max_abs_score_delta_cp": max(
                map(abs, symmetry_deltas), default=None
            ),
            "all_scores_exact": symmetry_ok,
            "probe_kind": "installed_network_static_eval_stm_pov",
            "root_to_child_value_conversion": "root_value=-child_stm_value",
        },
        "deep_judges": judges,
        "three_judge_consensus": consensus,
        "scientific_interpretation": {
            "static_information_refuted": False,
            "scalar_pattern_target_family_closed": True,
            "sign_bug_established": (
                verdict
                == "JASS_CONTEXT3_PERSPECTIVE_OR_EXACT_SYMMETRY_FAILURE"
            ),
            "recommended_next_test": (
                "repair_sign_or_perspective_and_repeat_paired_gate"
                if verdict
                == "JASS_CONTEXT3_PERSPECTIVE_OR_EXACT_SYMMETRY_FAILURE"
                else "CTX4_action_counterfactual_separate_decision_channel"
            ),
        },
        "rows": rows,
        "frozen_read": False,
        "self_play_games": 0,
        "patterneval_fits": 0,
        "strength_games": 0,
        "promotion_authorized": False,
        "automatic_promotion": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    prepare = sub.add_parser("prepare")
    prepare.add_argument(
        "--pool", action="append", required=True, help="LABEL=PATH"
    )
    prepare.add_argument("--per-pool", type=int, default=192)
    prepare.add_argument("--seed", type=int, default=2026081913)
    prepare.add_argument("--out", type=Path, required=True)
    worker = sub.add_parser("worker")
    worker.add_argument("--selection", required=True)
    worker.add_argument("--jass", required=True)
    worker.add_argument("--aligned", required=True)
    worker.add_argument("--shuffled", required=True)
    worker.add_argument("--curriculum", required=True)
    worker.add_argument("--search-params", required=True)
    worker.add_argument("--choice-depth", type=int, default=9)
    worker.add_argument("--judge-depth", type=int, default=12)
    worker.add_argument("--symmetry-per-pool", type=int, default=8)
    worker.add_argument("--shard", type=int, required=True)
    worker.add_argument("--nshards", type=int, required=True)
    worker.add_argument("--out", type=Path, required=True)
    combine = sub.add_parser("aggregate")
    combine.add_argument("--selection", type=Path, required=True)
    combine.add_argument(
        "--shard", action="append", type=Path, required=True
    )
    combine.add_argument("--bootstrap-samples", type=int, default=100000)
    combine.add_argument("--bootstrap-seed", type=int, default=2026081914)
    combine.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == "prepare":
        pools = []
        for spec in args.pool:
            label, sep, value = spec.partition("=")
            if not sep or not label or not value:
                parser.error("--pool must be LABEL=PATH")
            pools.append((label, Path(value)))
        report = select_openings(
            pools, per_pool=args.per_pool, seed=args.seed
        )
    elif args.command == "worker":
        report = analyse_shard(args)
    else:
        selection = json.loads(
            args.selection.read_text(encoding="utf-8")
        )
        shards = [
            json.loads(path.read_text(encoding="utf-8"))
            for path in args.shard
        ]
        report = aggregate(
            selection,
            shards,
            bootstrap_samples=args.bootstrap_samples,
            bootstrap_seed=args.bootstrap_seed,
        )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                key: report.get(key)
                for key in ("schema", "verdict", "total")
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
