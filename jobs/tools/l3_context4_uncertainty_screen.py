#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Read-only CTX4 uncertainty-band decision-channel screen.

The screen keeps the certified CURRICULUM scalar value unchanged.  It evaluates
1417's nonlinear contextual mapper only on legal child positions and lets that
separate channel intervene solely when the CURRICULUM top-two search margin is
inside a preregistered uncertainty band.  A pool-preserving permutation of the
same contextual deltas is the causal shuffled control.

No PatternEval fit, self-play, strength game, frozen cohort, or promotion occurs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct
from typing import Any

import numpy as np


def _load(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _write(path: str | Path, payload: dict[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _sha256(path: str | Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _clean_fens(path: Path) -> list[str]:
    rows = [raw.split("#", 1)[0].strip() for raw in path.read_text(encoding="utf-8").splitlines()]
    rows = [row for row in rows if row]
    if len(rows) != len(set(rows)):
        raise ValueError(f"{path}: duplicate FENs")
    return rows


def prepare_selection(pools: list[tuple[str, Path]], *, per_pool: int, seed: int) -> dict[str, Any]:
    if per_pool <= 0:
        raise ValueError("per_pool must be positive")
    rows: list[dict[str, Any]] = []
    certificates: list[dict[str, Any]] = []
    for pool_index, (label, path) in enumerate(pools, 1):
        fens = _clean_fens(path)
        if len(fens) < per_pool:
            raise ValueError(f"{label}: only {len(fens)} rows for per_pool={per_pool}")
        ranked = sorted(
            range(len(fens)),
            key=lambda index: hashlib.sha256(
                f"{seed}|{label}|{index}|{fens[index]}".encode()
            ).digest(),
        )[:per_pool]
        for within_pool_ordinal, source_index in enumerate(ranked):
            rows.append(
                {
                    "ordinal": len(rows),
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
                "sha256": _sha256(path),
                "source_openings": len(fens),
                "selected_openings": per_pool,
            }
        )
    return {
        "schema": "jass.l3_context4_uncertainty_selection.v1",
        "seed": seed,
        "per_pool": per_pool,
        "total": len(rows),
        "pools": certificates,
        "rows": rows,
    }


def build_children(
    selection_path: Path, *, jass: Path, work_dir: Path, out_json: Path, out_jnnw: Path
) -> dict[str, Any]:
    try:
        from conversion_teacher import dump_children, fen_to_record  # type: ignore
    except ModuleNotFoundError:
        from jobs.tools.conversion_teacher import dump_children, fen_to_record  # type: ignore

    selection = _load(selection_path)
    if selection.get("schema") != "jass.l3_context4_uncertainty_selection.v1":
        raise ValueError("selection schema drift")
    parents = list(selection["rows"])
    child_groups = dump_children(str(jass), [str(row["fen"]) for row in parents], work_dir, "ctx4-screen")
    if len(child_groups) != len(parents):
        raise RuntimeError("child dump lost parent alignment")

    flat: list[dict[str, Any]] = []
    records: list[bytes] = []
    parent_rows: list[dict[str, Any]] = []
    for source, children in zip(parents, child_groups):
        start = len(flat)
        for local_index, child in enumerate(children):
            fen = str(child["fen"])
            record = fen_to_record(fen, 0)
            if len(record) != 38:
                raise RuntimeError("unexpected JNNW record width")
            child_id = len(flat)
            flat.append(
                {
                    "child_id": child_id,
                    "parent_ordinal": int(source["ordinal"]),
                    "local_index": local_index,
                    "move": str(child["move"]),
                    "fen": fen,
                    "capture": bool(child.get("capture", False)),
                }
            )
            records.append(record)
        parent_rows.append(
            {
                **source,
                "child_start": start,
                "child_count": len(flat) - start,
            }
        )

    out_jnnw.parent.mkdir(parents=True, exist_ok=True)
    with out_jnnw.open("wb") as handle:
        handle.write(struct.pack("<4sI", b"JNNW", len(records)))
        for record in records:
            handle.write(record)
    payload = {
        "schema": "jass.l3_context4_children.v1",
        "selection_sha256": _sha256(selection_path),
        "parents": parent_rows,
        "children": flat,
        "child_count": len(flat),
        "jnnw_sha256": _sha256(out_jnnw),
    }
    _write(out_json, payload)
    return payload


def score_context(
    *,
    children_json: Path,
    child_jnnw: Path,
    features_path: Path,
    mapper_report_path: Path,
    out_path: Path,
) -> dict[str, Any]:
    try:
        from l3_conditional_targets import JNNW_DTYPE, _open_counted, _open_feat, tempo_phase_from_records  # type: ignore
        from l3_context3_independent_information_screen import CANDIDATE_COLUMNS, feature_bank  # type: ignore
    except ModuleNotFoundError:
        from jobs.tools.l3_conditional_targets import JNNW_DTYPE, _open_counted, _open_feat, tempo_phase_from_records  # type: ignore
        from jobs.tools.l3_context3_independent_information_screen import CANDIDATE_COLUMNS, feature_bank  # type: ignore

    children = _load(children_json)
    mapper = _load(mapper_report_path)
    if children.get("schema") != "jass.l3_context4_children.v1":
        raise ValueError("children schema drift")
    if mapper.get("schema") != "jass.l3_context3_exact_tanh_mapper_screen.v1":
        raise ValueError("mapper schema drift")
    if mapper.get("verdict") != "JASS_CONTEXT3_EXACT_TANH_MAPPER_SCREEN_PASSED":
        raise ValueError("1417 mapper did not pass")
    if not mapper.get("screen_passed") or not all((mapper.get("guards") or {}).values()):
        raise ValueError("1417 mapper guards are not all green")
    selected = str((mapper.get("protocol") or {}).get("selected_candidate"))
    if selected not in CANDIDATE_COLUMNS:
        raise ValueError("selected mapper candidate drift")
    columns = np.asarray(CANDIDATE_COLUMNS[selected], dtype=np.int64)
    fit = (((mapper.get("mappings") or {}).get("aligned_ctx3") or {}).get("final_train_fit") or {})
    theta = np.asarray(fit.get("theta_raw"), dtype=np.float64)
    if theta.shape != (len(columns),) or not np.all(np.isfinite(theta)):
        raise ValueError("1417 final mapper coefficient drift")

    records = _open_counted(child_jnnw, b"JNNW", JNNW_DTYPE)
    features, width = _open_feat(features_path, len(records))
    if width != 30 or len(records) != int(children.get("child_count", -1)):
        raise ValueError("child context-feature alignment drift")
    tempo = tempo_phase_from_records(records)
    bank = feature_bank(np.asarray(features, dtype=np.float64), tempo)
    child_stm = np.tanh(bank[:, columns] @ theta)
    parent_pov = -child_stm
    if not np.all(np.isfinite(parent_pov)) or np.any(np.abs(parent_pov) > 1.0 + 1e-12):
        raise RuntimeError("context score left finite WDL range")
    payload = {
        "schema": "jass.l3_context4_child_context_scores.v1",
        "children_sha256": _sha256(children_json),
        "child_jnnw_sha256": _sha256(child_jnnw),
        "features_sha256": _sha256(features_path),
        "mapper_report_sha256": _sha256(mapper_report_path),
        "mapper_selected_candidate": selected,
        "mapper_width": int(len(columns)),
        "pov": "parent_side_to_move",
        "scores": [
            {"child_id": index, "parent_context_wdl": float(value)}
            for index, value in enumerate(parent_pov)
        ],
    }
    _write(out_path, payload)
    return payload


def _search(engine: Any, fen: str, depth: int) -> dict[str, Any]:
    import re

    engine.new_game()
    engine.set_position_fen(fen)
    engine._drain()
    engine._send(f"go depth {depth}")
    lines = engine._read_until(
        lambda line: line.startswith("bestmove") or line.startswith("error"),
        timeout_s=300.0,
    )
    raw = lines[-1]
    if raw.startswith("error"):
        raise RuntimeError(raw)
    score_match = re.search(r"\bscore=(-?\d+)\b", raw)
    depth_match = re.search(r"\bdepth=(\d+)\b", raw)
    nodes_match = re.search(r"\bnodes=(\d+)\b", raw)
    if not score_match or not depth_match or not nodes_match:
        raise RuntimeError(f"missing score/depth/nodes in {raw!r}")
    return {
        "child_stm_score_cp": int(score_match.group(1)),
        "depth": int(depth_match.group(1)),
        "nodes": int(nodes_match.group(1)),
        "raw": raw,
    }


def analyse_shard(args: argparse.Namespace) -> dict[str, Any]:
    try:
        import calibrate_vs_scan as cv  # type: ignore
    except ModuleNotFoundError:
        from jobs.tools import calibrate_vs_scan as cv  # type: ignore

    selection = _load(args.selection)
    children = _load(args.children)
    scores = _load(args.context_scores)
    if selection.get("schema") != "jass.l3_context4_uncertainty_selection.v1":
        raise ValueError("selection schema drift")
    if children.get("schema") != "jass.l3_context4_children.v1":
        raise ValueError("children schema drift")
    if scores.get("schema") != "jass.l3_context4_child_context_scores.v1":
        raise ValueError("context-score schema drift")
    by_parent = {int(row["ordinal"]): row for row in children["parents"]}
    flat = {int(row["child_id"]): row for row in children["children"]}
    context = {
        int(row["child_id"]): float(row["parent_context_wdl"])
        for row in scores["scores"]
    }
    engine = cv.JassEngine(
        args.jass,
        label=f"ctx4-curriculum-s{args.shard}",
        pattern_path=args.curriculum,
        search_params=args.search_params,
    )
    rows: list[dict[str, Any]] = []
    try:
        for source in selection["rows"]:
            ordinal = int(source["ordinal"])
            if ordinal % args.nshards != args.shard:
                continue
            parent = by_parent[ordinal]
            count = int(parent["child_count"])
            if count < 2:
                continue
            child_rows = [
                flat[index]
                for index in range(int(parent["child_start"]), int(parent["child_start"]) + count)
            ]
            choice_rows: list[dict[str, Any]] = []
            for child in child_rows:
                result = _search(engine, str(child["fen"]), int(args.choice_depth))
                choice_rows.append(
                    {
                        **child,
                        "choice_parent_score_cp": -int(result["child_stm_score_cp"]),
                        "choice_depth": int(result["depth"]),
                        "choice_nodes": int(result["nodes"]),
                        "parent_context_wdl": context[int(child["child_id"])],
                    }
                )
            choice_rows.sort(key=lambda row: (-int(row["choice_parent_score_cp"]), str(row["move"])))
            top1, top2 = choice_rows[:2]
            margin = int(top1["choice_parent_score_cp"]) - int(top2["choice_parent_score_cp"])
            if margin < 0:
                raise RuntimeError("negative top-two margin")
            if margin > int(args.uncertainty_cp):
                continue
            judge1 = _search(engine, str(top1["fen"]), int(args.judge_depth))
            judge2 = _search(engine, str(top2["fen"]), int(args.judge_depth))
            judge1_parent = -int(judge1["child_stm_score_cp"])
            judge2_parent = -int(judge2["child_stm_score_cp"])
            side, wm, wk, bm, bk = cv.parse_jass_fen(str(source["fen"]))
            piece_count = sum(map(len, (wm, wk, bm, bk)))
            rows.append(
                {
                    "ordinal": ordinal,
                    "pool_index": int(source["pool_index"]),
                    "pool_label": str(source["pool_label"]),
                    "fen": str(source["fen"]),
                    "root_side": side,
                    "piece_count": int(piece_count),
                    "legal_children": count,
                    "choice_depth": int(args.choice_depth),
                    "judge_depth": int(args.judge_depth),
                    "uncertainty_cp": int(args.uncertainty_cp),
                    "baseline_top1_move": str(top1["move"]),
                    "baseline_top2_move": str(top2["move"]),
                    "baseline_top1_cp": int(top1["choice_parent_score_cp"]),
                    "baseline_top2_cp": int(top2["choice_parent_score_cp"]),
                    "baseline_margin_cp": margin,
                    "context_top1_wdl": float(top1["parent_context_wdl"]),
                    "context_top2_wdl": float(top2["parent_context_wdl"]),
                    "context_delta_top2_minus_top1": float(
                        top2["parent_context_wdl"] - top1["parent_context_wdl"]
                    ),
                    "judge_top1_cp": judge1_parent,
                    "judge_top2_cp": judge2_parent,
                    "judge_delta_top2_minus_top1_cp": judge2_parent - judge1_parent,
                    "top1_capture": bool(top1["capture"]),
                    "top2_capture": bool(top2["capture"]),
                }
            )
    finally:
        engine.close()
    return {
        "schema": "jass.l3_context4_uncertainty_shard.v1",
        "shard": int(args.shard),
        "nshards": int(args.nshards),
        "choice_depth": int(args.choice_depth),
        "judge_depth": int(args.judge_depth),
        "uncertainty_cp": int(args.uncertainty_cp),
        "rows": rows,
    }


def _paired_bootstrap(values: np.ndarray, *, samples: int, seed: int) -> dict[str, Any]:
    x = np.asarray(values, dtype=np.float64)
    if x.ndim != 1 or len(x) == 0:
        raise ValueError("bootstrap requires non-empty 1D values")
    rng = np.random.default_rng(seed)
    draws = np.empty(samples, dtype=np.float64)
    batch = 2048
    for start in range(0, samples, batch):
        stop = min(start + batch, samples)
        idx = rng.integers(0, len(x), size=(stop - start, len(x)))
        draws[start:stop] = x[idx].mean(axis=1)
    lo, hi = np.quantile(draws, (0.025, 0.975))
    return {
        "n": int(len(x)),
        "mean_cp": float(x.mean()),
        "median_cp": float(np.median(x)),
        "ci95_cp": [float(lo), float(hi)],
        "probability_positive": float(np.mean(draws > 0.0)),
        "positive_fraction": float(np.mean(x > 0.0)),
        "bootstrap_samples": int(samples),
        "seed": int(seed),
    }


def _donor_map(rows: list[dict[str, Any]], seed: int) -> tuple[dict[int, int], dict[str, Any]]:
    result: dict[int, int] = {}
    per_pool: dict[str, Any] = {}
    fixed = 0
    for pool in sorted({int(row["pool_index"]) for row in rows}):
        members = [row for row in rows if int(row["pool_index"]) == pool]
        if len(members) < 2:
            raise ValueError(f"pool {pool}: fewer than two uncertainty rows")
        ordered = sorted(
            members,
            key=lambda row: hashlib.sha256(
                f"{seed}|{pool}|{row['ordinal']}".encode()
            ).digest(),
        )
        donors = ordered[-1:] + ordered[:-1]
        for row, donor in zip(ordered, donors):
            result[int(row["ordinal"])] = int(donor["ordinal"])
            fixed += int(row["ordinal"] == donor["ordinal"])
        per_pool[str(pool)] = {
            "rows": len(members),
            "delta_multiset_preserved": True,
        }
    return result, {"seed": seed, "fixed_points": fixed, "per_pool": per_pool}


def aggregate_rows(
    rows: list[dict[str, Any]],
    *,
    shuffle_seed: int,
    bootstrap_samples: int,
    bootstrap_seed: int,
    min_total: int,
    min_per_pool: int,
    min_aligned_flips: int,
) -> dict[str, Any]:
    rows = sorted(rows, key=lambda row: int(row["ordinal"]))
    if len({int(row["ordinal"]) for row in rows}) != len(rows):
        raise ValueError("duplicate uncertainty ordinal")
    donor_map, shuffle_report = _donor_map(rows, shuffle_seed)
    by_ordinal = {int(row["ordinal"]): row for row in rows}
    enriched: list[dict[str, Any]] = []
    for row in rows:
        own = float(row["context_delta_top2_minus_top1"])
        donor = float(by_ordinal[donor_map[int(row["ordinal"])]] ["context_delta_top2_minus_top1"])
        judge = float(row["judge_delta_top2_minus_top1_cp"])
        aligned_flip = own > 0.0
        shuffled_flip = donor > 0.0
        aligned_gain = judge if aligned_flip else 0.0
        shuffled_gain = judge if shuffled_flip else 0.0
        enriched.append(
            {
                **row,
                "aligned_context_flips": aligned_flip,
                "shuffled_context_flips": shuffled_flip,
                "shuffled_donor_ordinal": donor_map[int(row["ordinal"])],
                "shuffled_context_delta": donor,
                "aligned_gain_vs_baseline_cp": aligned_gain,
                "shuffled_gain_vs_baseline_cp": shuffled_gain,
                "aligned_minus_shuffled_gain_cp": aligned_gain - shuffled_gain,
            }
        )
    contrast = np.asarray(
        [row["aligned_minus_shuffled_gain_cp"] for row in enriched], dtype=np.float64
    )
    aligned_flip_judge = np.asarray(
        [
            row["judge_delta_top2_minus_top1_cp"]
            for row in enriched
            if row["aligned_context_flips"]
        ],
        dtype=np.float64,
    )
    per_pool: dict[str, Any] = {}
    for pool in sorted({int(row["pool_index"]) for row in enriched}):
        subset = [row for row in enriched if int(row["pool_index"]) == pool]
        values = np.asarray(
            [row["aligned_minus_shuffled_gain_cp"] for row in subset], dtype=np.float64
        )
        per_pool[str(pool)] = {
            "rows": len(subset),
            "aligned_flips": int(sum(bool(row["aligned_context_flips"]) for row in subset)),
            "shuffled_flips": int(sum(bool(row["shuffled_context_flips"]) for row in subset)),
            "contrast_mean_cp": float(values.mean()),
        }
    overall = _paired_bootstrap(
        contrast, samples=bootstrap_samples, seed=bootstrap_seed
    )
    flip_stats = (
        _paired_bootstrap(
            aligned_flip_judge,
            samples=bootstrap_samples,
            seed=bootstrap_seed + 1,
        )
        if len(aligned_flip_judge)
        else None
    )
    pool_counts = [int(row["rows"]) for row in per_pool.values()]
    pool_means = [float(row["contrast_mean_cp"]) for row in per_pool.values()]
    guards = {
        "enough_uncertainty_rows": len(enriched) >= min_total,
        "enough_rows_each_pool": bool(pool_counts) and min(pool_counts) >= min_per_pool,
        "enough_aligned_flips": len(aligned_flip_judge) >= min_aligned_flips,
        "shuffle_fixed_points_zero": shuffle_report["fixed_points"] == 0,
        "aligned_vs_shuffled_ci95_positive": overall["ci95_cp"][0] > 0.0,
        "aligned_flip_judge_ci95_positive": (
            flip_stats is not None and flip_stats["ci95_cp"][0] > 0.0
        ),
        "both_pool_point_estimates_positive": len(pool_means) == 2 and min(pool_means) > 0.0,
    }
    passed = all(guards.values())
    return {
        "schema": "jass.l3_context4_uncertainty_screen.v1",
        "verdict": (
            "JASS_CONTEXT4_UNCERTAINTY_DECISION_SCREEN_PASSED"
            if passed
            else "JASS_CONTEXT4_UNCERTAINTY_DECISION_SCREEN_FAILED"
        ),
        "screen_passed": passed,
        "protocol": {
            "scalar_value": "CURRICULUM_unchanged",
            "context_channel": "1417_exact_tanh_mapper_child_WDL_only",
            "intervention": "within_uncertainty_band_choose_baseline_top2_only_when_context_prefers_top2",
            "control": "same_context_delta_marginal_cyclically_permuted_within_pool",
            "pattern_eval_refit": False,
            "selfplay": False,
            "strength_games": False,
            "frozen_read": False,
            "promotion_authorized": False,
        },
        "sample": {
            "uncertainty_rows": len(enriched),
            "aligned_flips": int(len(aligned_flip_judge)),
            "per_pool": per_pool,
        },
        "shuffle_control": shuffle_report,
        "aligned_vs_shuffled_gain": overall,
        "aligned_flip_judge_gain": flip_stats,
        "guards": guards,
        "next_stage_authorized": passed,
        "rows": enriched,
    }


def aggregate_shards(args: argparse.Namespace) -> dict[str, Any]:
    shards = [_load(path) for path in args.shards]
    if {int(row.get("shard", -1)) for row in shards} != set(range(len(shards))):
        raise ValueError("shard indices incomplete")
    rows = [row for shard in shards for row in shard.get("rows", [])]
    payload = aggregate_rows(
        rows,
        shuffle_seed=int(args.shuffle_seed),
        bootstrap_samples=int(args.bootstrap_samples),
        bootstrap_seed=int(args.bootstrap_seed),
        min_total=int(args.min_total),
        min_per_pool=int(args.min_per_pool),
        min_aligned_flips=int(args.min_aligned_flips),
    )
    payload["source"] = {
        "selection_sha256": _sha256(args.selection),
        "children_sha256": _sha256(args.children),
        "context_scores_sha256": _sha256(args.context_scores),
    }
    _write(args.out, payload)
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("prepare")
    p.add_argument("--pool", action="append", required=True, help="LABEL=PATH")
    p.add_argument("--per-pool", type=int, required=True)
    p.add_argument("--seed", type=int, required=True)
    p.add_argument("--out", required=True)

    c = sub.add_parser("children")
    c.add_argument("--selection", required=True)
    c.add_argument("--jass", required=True)
    c.add_argument("--work-dir", required=True)
    c.add_argument("--out-json", required=True)
    c.add_argument("--out-jnnw", required=True)

    s = sub.add_parser("score-context")
    s.add_argument("--children", required=True)
    s.add_argument("--child-jnnw", required=True)
    s.add_argument("--features", required=True)
    s.add_argument("--mapper-report", required=True)
    s.add_argument("--out", required=True)

    w = sub.add_parser("worker")
    w.add_argument("--selection", required=True)
    w.add_argument("--children", required=True)
    w.add_argument("--context-scores", required=True)
    w.add_argument("--jass", required=True)
    w.add_argument("--curriculum", required=True)
    w.add_argument("--search-params", default="")
    w.add_argument("--choice-depth", type=int, default=9)
    w.add_argument("--judge-depth", type=int, default=12)
    w.add_argument("--uncertainty-cp", type=int, default=20)
    w.add_argument("--shard", type=int, required=True)
    w.add_argument("--nshards", type=int, required=True)
    w.add_argument("--out", required=True)

    a = sub.add_parser("aggregate")
    a.add_argument("--selection", required=True)
    a.add_argument("--children", required=True)
    a.add_argument("--context-scores", required=True)
    a.add_argument("--shard", dest="shards", action="append", required=True)
    a.add_argument("--shuffle-seed", type=int, required=True)
    a.add_argument("--bootstrap-samples", type=int, default=100000)
    a.add_argument("--bootstrap-seed", type=int, required=True)
    a.add_argument("--min-total", type=int, default=48)
    a.add_argument("--min-per-pool", type=int, default=16)
    a.add_argument("--min-aligned-flips", type=int, default=12)
    a.add_argument("--out", required=True)

    args = parser.parse_args(argv)
    if args.command == "prepare":
        pools = []
        for item in args.pool:
            label, raw = item.split("=", 1)
            pools.append((label, Path(raw)))
        payload = prepare_selection(pools, per_pool=args.per_pool, seed=args.seed)
        _write(args.out, payload)
    elif args.command == "children":
        payload = build_children(
            Path(args.selection),
            jass=Path(args.jass),
            work_dir=Path(args.work_dir),
            out_json=Path(args.out_json),
            out_jnnw=Path(args.out_jnnw),
        )
    elif args.command == "score-context":
        payload = score_context(
            children_json=Path(args.children),
            child_jnnw=Path(args.child_jnnw),
            features_path=Path(args.features),
            mapper_report_path=Path(args.mapper_report),
            out_path=Path(args.out),
        )
    elif args.command == "worker":
        payload = analyse_shard(args)
        _write(args.out, payload)
    else:
        payload = aggregate_shards(args)
    print(json.dumps({k: v for k, v in payload.items() if k != "rows"}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
