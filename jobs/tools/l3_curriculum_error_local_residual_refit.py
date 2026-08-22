#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Strict rank-one repair of a confirmed CURRICULUM error region.

The input atlas has already fixed a sparse exact-fold Jacobian direction on a
discovery split and confirmed it once on sealed opening/transposition
components.  This stage does *not* reopen region selection.  It only calibrates
one integer trust-region step on discovery rows, builds an equally-sized sham
direction from matched discovery controls, and evaluates both directions on
the untouched confirmation rows.

Only exact-fold PatternEval coefficients named by the corresponding direction
may change.  The PJTW/PJSW header and every coefficient outside those exact
orbits remain byte-identical to CURRICULUM.  No game is played and no model is
promoted here; a positive result merely authorizes a fresh mechanistic replay.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
import math
from pathlib import Path
import struct
import sys
from typing import Any, Iterable

import numpy as np

try:
    from jobs.tools import l3_curriculum_error_residual_atlas as atlas
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    import l3_curriculum_error_residual_atlas as atlas  # type: ignore


SCHEMA = "jass.l3_curriculum_error_local_residual_refit.v2"
SHAM_SCHEMA = "jass.l3_curriculum_error_sham_region.v1"
PJTW_MAGIC = 0x57544A50
PJSW_MAGIC = 0x57534A50


def _canonical(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _publish(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise FileExistsError(f"refusing to overwrite {path}")
    temporary = path.with_name(
        path.name + ".tmp." + hashlib.sha256(payload).hexdigest()[:12]
    )
    temporary.write_bytes(payload)
    temporary.replace(path)


def _patterns() -> tuple[Any, Any]:
    tools = Path(__file__).resolve().parents[2] / "pattern_jass" / "tools"
    sys.path.insert(0, str(tools))
    import patterns  # type: ignore
    import train_stream  # type: ignore
    return patterns, train_stream


def _vector(row: dict[str, Any]) -> dict[int, float]:
    values = {
        int(item["coordinate"]): float(item["value"])
        for item in row.get("gradient", [])
    }
    if len(values) != len(row.get("gradient", [])):
        raise ValueError("duplicate gradient coordinate")
    return values


def _dot(vector: dict[int, float], weights: dict[int, float]) -> float:
    return sum(value * weights.get(key, 0.0) for key, value in vector.items())


def _bootstrap(values: Iterable[float], *, samples: int, seed: int) -> dict[str, Any]:
    array = np.asarray(list(values), dtype=np.float64)
    if not len(array):
        return {"n": 0, "mean": None, "ci95": [None, None], "probability_positive": None}
    rng = np.random.default_rng(seed)
    means = np.empty(samples, dtype=np.float64)
    for start in range(0, samples, 2048):
        stop = min(samples, start + 2048)
        indices = rng.integers(0, len(array), size=(stop - start, len(array)))
        means[start:stop] = array[indices].mean(axis=1)
    low, high = np.quantile(means, (0.025, 0.975))
    return {
        "n": len(array),
        "mean": float(array.mean()),
        "ci95": [float(low), float(high)],
        "probability_positive": float(np.mean(means > 0.0)),
    }


def _load_model(path: Path) -> tuple[bytes, np.ndarray, int, int, int]:
    raw = path.read_bytes()
    if len(raw) < 20:
        raise ValueError(f"{path}: truncated pattern model")
    magic, version, scale, n_pat, n_ext = struct.unpack_from("<5I", raw, 0)
    if magic not in (PJTW_MAGIC, PJSW_MAGIC) or (version & 0xFF) != 3:
        raise ValueError(f"{path}: expected PJTW/PJSW v3")
    count = 2 * (n_pat + n_ext)
    if len(raw) != 20 + 4 * count:
        raise ValueError(f"{path}: model geometry/size mismatch")
    values = np.frombuffer(raw, dtype="<i4", offset=20, count=count).copy()
    return raw[:20], values, int(scale), int(n_pat), int(n_ext)


def _rows(shards: list[dict[str, Any]], report: dict[str, Any]) -> list[dict[str, Any]]:
    if not shards or any(row.get("schema") != atlas.SCHEMA_SHARD for row in shards):
        raise ValueError("residual shard schema drift")
    nshards = len(shards)
    if {int(row.get("shard", -1)) for row in shards} != set(range(nshards)):
        raise ValueError("residual shards are incomplete")
    if any(int(row.get("nshards", -1)) != nshards for row in shards):
        raise ValueError("residual shard count drift")
    identities = ("champion_sha256", "jass_sha256", "search_params_sha256")
    for key in identities:
        values = {str(row.get(key, "")) for row in shards}
        if values != {str(report.get(key, ""))}:
            raise ValueError(f"atlas/report {key} mismatch")
    result = [item for shard in shards for item in shard.get("rows", [])]
    result.sort(key=lambda row: int(row["pair_id"]))
    if [int(row["pair_id"]) for row in result] != list(range(len(result))):
        raise ValueError("residual rows are not contiguous")
    if len(result) != int(report.get("pairs", -1)):
        raise ValueError("residual row/report cardinality drift")
    return result


def _informative_rows(
    rows: list[dict[str, Any]], report: dict[str, Any]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Authenticate and remove pairs reclassified by the exact judge.

    Pair matching predates exact re-judging, so the sealed atlas still contains
    every one of the 353 authenticated source pairs.  A source error later
    reclassified below the preregistered 50 cp threshold must remove the whole
    pair (including its matched control) from every fit, sham, calibration and
    confirmation statistic.  Keeping its empty error gradient as a favourable
    zero would bias all four screens.
    """
    expected = int(report.get("informative_error_pairs", -1))
    reclassification = report.get("reclassified_exact_non_errors")
    if expected != 290:
        raise ValueError("atlas informative exact-error cardinality is not 290")
    if not isinstance(reclassification, dict):
        raise ValueError("atlas exact non-error reclassification audit is absent")
    if reclassification.get("excluded_with_their_controls_from_fit_statistics") is not True:
        raise ValueError("atlas does not exclude reclassified matched controls")
    if reclassification.get("zero_vectors_used_as_observations") is not False:
        raise ValueError("atlas admits reclassified zero vectors as observations")

    excluded = [
        pair for pair in rows
        if bool(pair.get("error", {}).get("reclassified_exact_non_error", False))
    ]
    informative = [
        pair for pair in rows
        if not bool(pair.get("error", {}).get("reclassified_exact_non_error", False))
    ]
    if len(excluded) != int(reclassification.get("total", -1)):
        raise ValueError("atlas reclassified exact non-error cardinality drift")
    if len(informative) != expected or len(excluded) != len(rows) - expected:
        raise ValueError("atlas informative/reclassified pair partition drift")
    for pair in excluded:
        error = pair["error"]
        if (
            error.get("informative_ranking") is not False
            or error.get("gradient") != []
            or error.get("rival_action") is not None
            or error.get("reclassification_reason") not in {
                "exact_reclassified_historical_optimal",
                "exact_reclassified_below_50cp",
            }
        ):
            raise ValueError("reclassified exact non-error row contract drift")
    if any(
        bool(pair["error"].get("reclassified_exact_non_error", False))
        for pair in informative
    ):
        raise ValueError("reclassified pair leaked into informative rows")
    return informative, excluded


def _representatives(rows: Iterable[dict[str, Any]], total: int) -> dict[int, int]:
    result: dict[int, int] = {}
    for pair in rows:
        for label in ("error", "control"):
            for item in pair[label].get("gradient", []):
                coordinate = int(item["coordinate"])
                if not 0 <= coordinate < 2 * total:
                    raise ValueError("gradient coordinate outside phased pattern geometry")
                bucket = coordinate % total
                representative = int(item["representative_full_column"])
                if not 0 <= representative < total:
                    raise ValueError("representative full column outside pattern geometry")
                result[bucket] = min(result.get(bucket, representative), representative)
    return result


def _error_direction(report: dict[str, Any], total: int) -> dict[int, int]:
    selected = report.get("selected_coordinates")
    if not isinstance(selected, list) or not selected:
        raise ValueError("confirmed atlas has no selected coordinates")
    direction: dict[int, int] = {}
    for item in selected:
        coordinate = int(item["coordinate"])
        sign = float(item["sign"])
        if not 0 <= coordinate < 2 * total or sign not in (-1.0, 1.0):
            raise ValueError("invalid confirmed coordinate")
        direction[coordinate] = 1 if sign > 0 else -1
    if len(direction) != len(selected):
        raise ValueError("duplicate confirmed coordinate")
    return direction


def _match_sham_direction(
    rows: list[dict[str, Any]],
    error_direction: dict[int, int],
    representatives: dict[int, int],
    *,
    total: int,
    buckets_per_pattern: int,
) -> tuple[dict[int, int], list[dict[str, Any]]]:
    """Match one control-active canonical bucket to every error bucket.

    Matching preserves the representative pattern and the selected MG/EG
    phase set.  It minimizes discovery-control support mismatch and never uses
    a bucket from the error region.
    """
    stats: dict[int, dict[str, float]] = defaultdict(lambda: {"hits": 0.0, "sum": 0.0})
    error_hits: dict[int, int] = defaultdict(int)
    for pair in rows:
        if pair["split"] != "discovery":
            continue
        for coordinate, value in _vector(pair["error"]).items():
            if value:
                error_hits[coordinate] += 1
        control = pair["control"]
        if bool(control.get("forced_single_action", False)):
            continue
        for coordinate, value in _vector(control).items():
            if value:
                stats[coordinate]["hits"] += 1.0
                stats[coordinate]["sum"] += value

    error_by_bucket: dict[int, list[int]] = defaultdict(list)
    for coordinate in sorted(error_direction):
        error_by_bucket[coordinate % total].append(coordinate // total)
    forbidden = set(error_by_bucket)
    available = sorted({coordinate % total for coordinate in stats} - forbidden)
    used: set[int] = set()
    sham: dict[int, int] = {}
    matching: list[dict[str, Any]] = []
    for error_bucket, phases in sorted(error_by_bucket.items()):
        error_rep = representatives.get(error_bucket)
        if error_rep is None:
            raise ValueError("confirmed error bucket lacks an unfolded representative")
        pattern = error_rep // buckets_per_pattern
        candidates = []
        for candidate in available:
            if candidate in used:
                continue
            candidate_rep = representatives.get(candidate)
            if candidate_rep is None or candidate_rep // buckets_per_pattern != pattern:
                continue
            coordinates = [phase * total + candidate for phase in phases]
            if any(stats.get(coordinate, {}).get("hits", 0.0) <= 0 for coordinate in coordinates):
                continue
            mismatch = sum(
                abs(
                    math.log1p(stats[phase * total + candidate]["hits"])
                    - math.log1p(error_hits[phase * total + error_bucket])
                )
                for phase in phases
            )
            candidates.append((mismatch, candidate_rep, candidate))
        if not candidates:
            raise ValueError(
                f"no same-pattern discovery-control sham for canonical bucket {error_bucket}"
            )
        mismatch, candidate_rep, chosen = min(candidates)
        used.add(chosen)
        phase_rows = []
        for phase in phases:
            source = phase * total + error_bucket
            target = phase * total + chosen
            summed = stats[target]["sum"]
            if summed == 0.0:
                raise ValueError("matched sham coordinate has zero signed control mean")
            sham[target] = 1 if summed > 0 else -1
            phase_rows.append(
                {
                    "phase": "mg" if phase == 0 else "eg",
                    "error_hits": error_hits[source],
                    "sham_hits": int(stats[target]["hits"]),
                    "sham_sign": sham[target],
                }
            )
        matching.append(
            {
                "error_canonical_bucket": error_bucket,
                "error_representative_full_column": error_rep,
                "sham_canonical_bucket": chosen,
                "sham_representative_full_column": candidate_rep,
                "support_distance": mismatch,
                "phases": phase_rows,
            }
        )
    if len(sham) != len(error_direction) or len(used) != len(error_by_bucket):
        raise AssertionError("sham matching cardinality drift")
    return sham, matching


def _canonical_weights(
    model: np.ndarray,
    direction_coordinates: Iterable[int],
    representatives: dict[int, int],
    folder: Any,
    *,
    total: int,
    scale: int,
) -> dict[int, float]:
    result: dict[int, float] = {}
    for coordinate in sorted(set(direction_coordinates)):
        phase, canonical = divmod(coordinate, total)
        representative = representatives[canonical]
        pattern, bucket = divmod(representative, folder.rf_canon.shape[1])
        if int(folder.rf_canon[pattern, bucket]) != canonical:
            raise ValueError("representative does not map to its canonical exact-fold bucket")
        sign = int(folder.rf_sign[pattern, bucket])
        if sign not in (-1, 1):
            raise ValueError("exact-fold sign outside {-1,+1}")
        result[coordinate] = float(model[phase * total + representative]) * sign / scale
    return result


def _row_margin(vector: dict[int, float], canonical: dict[int, float]) -> float:
    return sum(value * canonical.get(coordinate, 0.0) for coordinate, value in vector.items())


def _delta(direction: dict[int, int], ticks: int, scale: int) -> dict[int, float]:
    amount = float(ticks) / float(scale)
    return {coordinate: sign * amount for coordinate, sign in direction.items()}


def _objective(
    rows: list[dict[str, Any]],
    canonical: dict[int, float],
    direction: dict[int, int],
    *,
    ticks: int,
    scale: int,
    rank_scale: float,
    control_anchor: float,
    trust_anchor: float,
    max_ticks: int,
) -> dict[str, float]:
    delta = _delta(direction, ticks, scale)
    error_losses = []
    error_updates = []
    control_updates = []
    for pair in rows:
        error = _vector(pair["error"])
        margin = _row_margin(error, canonical)
        update = _dot(error, delta)
        error_updates.append(update)
        error_losses.append(float(np.logaddexp(0.0, -rank_scale * (margin + update))))
        control = pair["control"]
        if not bool(control.get("forced_single_action", False)):
            control_updates.append(_dot(_vector(control), delta))
    rank_loss = float(np.mean(error_losses))
    control_loss = float(np.mean(np.square(control_updates))) if control_updates else math.inf
    trust_loss = (float(ticks) / float(max_ticks)) ** 2
    return {
        "objective": rank_loss + control_anchor * control_loss + trust_anchor * trust_loss,
        "rank_loss": rank_loss,
        "control_anchor_loss": control_loss,
        "trust_anchor_loss": trust_loss,
        "mean_error_update": float(np.mean(error_updates)),
        "mean_control_update": float(np.mean(control_updates)) if control_updates else math.nan,
    }


def _calibration_split(rows: list[dict[str, Any]], *, seed: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    fit, calibration = [], []
    for pair in rows:
        if pair["split"] != "discovery":
            continue
        opening = str(pair["error"].get("source", {}).get("opening_id", pair["pair_id"]))
        digest = hashlib.sha256(f"{seed}|{opening}".encode()).digest()
        (calibration if int.from_bytes(digest[:8], "big") % 5 == 0 else fit).append(pair)
    if not fit or not calibration:
        raise ValueError("discovery fit/calibration split is empty")
    return fit, calibration


def _choose_step(
    rows: list[dict[str, Any]],
    canonical: dict[int, float],
    direction: dict[int, int],
    *,
    scale: int,
    grid: list[int],
    rank_scale: float,
    control_anchor: float,
    trust_anchor: float,
) -> tuple[int, list[dict[str, float]]]:
    if not grid or grid[0] != 0 or any(left >= right for left, right in zip(grid, grid[1:])):
        raise ValueError("trust grid must be strictly increasing from zero")
    metrics = []
    for ticks in grid:
        row = _objective(
            rows, canonical, direction, ticks=ticks, scale=scale,
            rank_scale=rank_scale, control_anchor=control_anchor,
            trust_anchor=trust_anchor, max_ticks=grid[-1],
        )
        metrics.append({"ticks": ticks, **row})
    chosen = min(metrics, key=lambda row: (row["objective"], row["ticks"]))
    baseline = metrics[0]
    if int(chosen["ticks"]) == 0 or chosen["objective"] >= baseline["objective"] - 1e-9:
        raise ValueError("anchored discovery objective does not authorize a non-zero step")
    return int(chosen["ticks"]), metrics


def _apply_direction_ints(
    source: np.ndarray,
    direction: dict[int, int],
    *,
    ticks: int,
    folder: Any,
    total: int,
) -> tuple[np.ndarray, dict[str, Any]]:
    target = source.copy()
    buckets = sorted({coordinate % total for coordinate in direction})
    flat_canonical = np.asarray(folder.rf_canon).ravel()
    flat_sign = np.asarray(folder.rf_sign).ravel().astype(np.int64)
    selected = np.flatnonzero(np.isin(flat_canonical, np.asarray(buckets, dtype=np.int64)))
    by_bucket: dict[int, np.ndarray] = {
        bucket: selected[flat_canonical[selected] == bucket] for bucket in buckets
    }
    allowed = np.zeros(len(source), dtype=bool)
    for coordinate, sign in direction.items():
        phase, bucket = divmod(coordinate, total)
        indices = by_bucket[bucket]
        if not len(indices):
            raise ValueError(f"exact-fold orbit is empty for bucket {bucket}")
        model_indices = phase * total + indices
        delta = flat_sign[indices] * int(sign) * int(ticks)
        widened = target[model_indices].astype(np.int64) + delta
        if np.any(widened < -(2**31)) or np.any(widened > 2**31 - 1):
            raise OverflowError("local residual step overflows int32")
        target[model_indices] = widened.astype(np.int32)
        allowed[model_indices] = True
        canonical_values = target[model_indices].astype(np.int64) * flat_sign[indices]
        if len(np.unique(canonical_values)) != 1:
            raise ValueError("candidate violates exact-fold orbit coherence")
    changed = target != source
    changed_outside = int(np.count_nonzero(changed & ~allowed))
    if changed_outside:
        raise AssertionError("local residual fit changed a frozen coefficient")
    return target, {
        "direction_coordinates": len(direction),
        "canonical_buckets": len(buckets),
        "allowed_full_coefficients": int(np.count_nonzero(allowed)),
        "changed_inside_region": int(np.count_nonzero(changed & allowed)),
        "changed_outside_region": changed_outside,
        "frozen_region_exact": True,
        "exact_fold_orbits_coherent": True,
    }


def _evaluate(
    rows: list[dict[str, Any]],
    error_delta: dict[int, float],
    sham_delta: dict[int, float],
    *,
    bootstrap_samples: int,
    seed: int,
    control_tolerance: float,
) -> tuple[dict[str, Any], dict[str, bool]]:
    error_gain, sham_gain, contrast, controls, paired = [], [], [], [], []
    for pair in rows:
        if pair["split"] != "confirm":
            continue
        error = _vector(pair["error"])
        eg = _dot(error, error_delta)
        sg = _dot(error, sham_delta)
        error_gain.append(eg); sham_gain.append(sg); contrast.append(eg - sg)
        control = pair["control"]
        if not bool(control.get("forced_single_action", False)):
            cg = _dot(_vector(control), error_delta)
            controls.append(cg); paired.append(eg - cg)
    metrics = {
        "error_region_gain": _bootstrap(error_gain, samples=bootstrap_samples, seed=seed),
        "sham_region_gain": _bootstrap(sham_gain, samples=bootstrap_samples, seed=seed + 1),
        "error_minus_sham": _bootstrap(contrast, samples=bootstrap_samples, seed=seed + 2),
        "control_gain": _bootstrap(controls, samples=bootstrap_samples, seed=seed + 3),
        "paired_error_minus_control": _bootstrap(paired, samples=bootstrap_samples, seed=seed + 4),
    }
    gates = {
        "confirm_error_gain_positive_95": metrics["error_region_gain"]["ci95"][0] > 0.0,
        "confirm_error_minus_sham_positive_95": metrics["error_minus_sham"]["ci95"][0] > 0.0,
        "confirm_controls_not_harmed_95": metrics["control_gain"]["ci95"][0] >= -control_tolerance,
        "confirm_paired_error_minus_control_positive_95": metrics["paired_error_minus_control"]["ci95"][0] > 0.0,
    }
    return metrics, gates


def fit(args: argparse.Namespace) -> dict[str, Any]:
    report = json.loads(args.atlas_report.read_text())
    region = json.loads(args.region.read_text())
    shards = [json.loads(path.read_text()) for path in args.shard]
    if report.get("schema") != atlas.SCHEMA_REPORT or report.get("passed") is not True:
        raise ValueError("atlas did not authorize a local residual fit")
    if report.get("verdict") != "JASS_CURRICULUM_ERROR_RESIDUAL_REGION_CONFIRMED":
        raise ValueError("atlas confirmed verdict drift")
    if region.get("schema") != atlas.SCHEMA_REGION or region.get("fit_authorized") is not True:
        raise ValueError("trainable error region is not authorized")
    if region.get("promotion_authorized") is not False:
        raise ValueError("region promotion guard drift")
    if sha256(args.champion) != str(region.get("champion_sha256")):
        raise ValueError("champion differs from confirmed error region")
    source_rows = _rows(shards, report)
    rows, excluded_rows = _informative_rows(source_rows, report)
    patterns, train_stream = _patterns()
    total = int(patterns.TOTAL_BUCKETS)
    header, model, scale, n_pat, n_ext = _load_model(args.champion)
    if n_pat != total:
        raise ValueError("champion pattern geometry differs from active 8cf geometry")
    folder = train_stream.Folder("exact")
    representatives = _representatives(rows, total)
    error_direction = _error_direction(report, total)
    region_canonical = {
        int(folder.rf_canon[divmod(int(column), patterns.BUCKETS_PER_PATTERN)])
        for column in region.get("pattern_columns_full", [])
    }
    if region_canonical != {coordinate % total for coordinate in error_direction}:
        raise ValueError("atlas direction and authorized region differ")
    sham_direction, sham_matching = _match_sham_direction(
        rows, error_direction, representatives, total=total,
        buckets_per_pattern=int(patterns.BUCKETS_PER_PATTERN),
    )
    all_coordinates = set(error_direction) | set(sham_direction)
    canonical = _canonical_weights(
        model, all_coordinates, representatives, folder, total=total, scale=scale
    )
    discovery_fit, calibration = _calibration_split(rows, seed=args.split_seed)
    grid = [int(value) for value in args.trust_grid.split(",")]
    ticks, grid_metrics = _choose_step(
        discovery_fit, canonical, error_direction, scale=scale, grid=grid,
        rank_scale=args.rank_scale, control_anchor=args.control_anchor,
        trust_anchor=args.trust_anchor,
    )
    error_delta = _delta(error_direction, ticks, scale)
    sham_delta = _delta(sham_direction, ticks, scale)
    calibration_error = [_dot(_vector(pair["error"]), error_delta) for pair in calibration]
    calibration_controls = [
        _dot(_vector(pair["control"]), error_delta) for pair in calibration
        if not bool(pair["control"].get("forced_single_action", False))
    ]
    calibration_gates = {
        "calibration_error_mean_positive": float(np.mean(calibration_error)) > 0.0,
        "calibration_control_mean_not_harmed": float(np.mean(calibration_controls)) >= -args.control_tolerance,
    }
    confirm, confirm_gates = _evaluate(
        rows, error_delta, sham_delta, bootstrap_samples=args.bootstrap_samples,
        seed=args.bootstrap_seed, control_tolerance=args.control_tolerance,
    )
    gates = {**calibration_gates, **confirm_gates}
    passed = all(gates.values())
    output: dict[str, Any] = {
        "schema": SCHEMA,
        "verdict": (
            "JASS_CURRICULUM_ERROR_LOCAL_RESIDUAL_REFIT_READY"
            if passed else "JASS_CURRICULUM_ERROR_LOCAL_RESIDUAL_REFIT_NOT_ESTABLISHED"
        ),
        "passed": passed,
        "atlas": {"path": str(args.atlas_report), "sha256": sha256(args.atlas_report)},
        "region": {"path": str(args.region), "sha256": sha256(args.region)},
        "champion": {"path": str(args.champion), "sha256": sha256(args.champion)},
        "shards": [{"path": str(path), "sha256": sha256(path)} for path in args.shard],
        "source_pairs": len(source_rows),
        "informative_error_pairs": len(rows),
        "reclassified_exact_non_error_pairs_excluded": len(excluded_rows),
        "reclassified_pairs_used_in_fit_or_statistics": 0,
        "split": {
            "unit": "sealed opening_transposition_component then discovery opening hash",
            "seed": args.split_seed,
            "fit_pairs": len(discovery_fit),
            "calibration_pairs": len(calibration),
            "confirm_pairs": sum(pair["split"] == "confirm" for pair in rows),
            "confirm_used_for_step_selection": False,
        },
        "directions": {
            "error_coordinates": len(error_direction),
            "error_buckets": len({coordinate % total for coordinate in error_direction}),
            "sham_coordinates": len(sham_direction),
            "sham_buckets": len({coordinate % total for coordinate in sham_direction}),
            "sham_matching": sham_matching,
        },
        "trust_region": {
            "grid_ticks": grid,
            "selected_ticks": ticks,
            "scale": scale,
            "selected_float_step_per_coordinate": ticks / scale,
            "rank_scale": args.rank_scale,
            "control_anchor": args.control_anchor,
            "trust_anchor": args.trust_anchor,
            "grid_metrics": grid_metrics,
        },
        "calibration": {
            "mean_error_gain": float(np.mean(calibration_error)),
            "mean_control_gain": float(np.mean(calibration_controls)),
        },
        "confirm": confirm,
        "gates": gates,
        "failed_gates": [key for key, value in gates.items() if not value],
        "fit_count": 2 if passed else 0,
        "strength_games": 0,
        "selfplay_games": 0,
        "frozen_reads": 0,
        "promotion_authorized": False,
        "next_stage": "fresh_error_replay_validation" if passed else None,
    }
    if passed:
        error_model, error_audit = _apply_direction_ints(
            model, error_direction, ticks=ticks, folder=folder, total=total
        )
        sham_model, sham_audit = _apply_direction_ints(
            model, sham_direction, ticks=ticks, folder=folder, total=total
        )
        _publish(args.error_out, header + error_model.astype("<i4").tobytes())
        _publish(args.sham_out, header + sham_model.astype("<i4").tobytes())
        sham_region = {
            "schema": SHAM_SCHEMA,
            "champion_sha256": sha256(args.champion),
            "atlas_sha256": sha256(args.atlas_report),
            "selection": "same-pattern_phase-and-support_matched_discovery_controls",
            "canonical_buckets": sorted({coordinate % total for coordinate in sham_direction}),
            "coordinates": [
                {"coordinate": coordinate, "sign": sign}
                for coordinate, sign in sorted(sham_direction.items())
            ],
            "matching": sham_matching,
            "promotion_authorized": False,
        }
        _publish(args.sham_region, _canonical(sham_region))
        output["models"] = {
            "error": {"path": str(args.error_out), "sha256": sha256(args.error_out), **error_audit},
            "sham": {"path": str(args.sham_out), "sha256": sha256(args.sham_out), **sham_audit},
        }
    _publish(args.report, _canonical(output))
    return output


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    root.add_argument("--atlas-report", type=Path, required=True)
    root.add_argument("--region", type=Path, required=True)
    root.add_argument("--shard", action="append", type=Path, required=True)
    root.add_argument("--champion", type=Path, required=True)
    root.add_argument("--error-out", type=Path, required=True)
    root.add_argument("--sham-out", type=Path, required=True)
    root.add_argument("--sham-region", type=Path, required=True)
    root.add_argument("--report", type=Path, required=True)
    root.add_argument("--trust-grid", default="0,1,2,4,8,16,32,64")
    root.add_argument("--rank-scale", type=float, default=1.0)
    root.add_argument("--control-anchor", type=float, default=0.25)
    root.add_argument("--trust-anchor", type=float, default=0.01)
    root.add_argument("--control-tolerance", type=float, default=0.002)
    root.add_argument("--split-seed", type=int, default=2026082223)
    root.add_argument("--bootstrap-samples", type=int, default=100_000)
    root.add_argument("--bootstrap-seed", type=int, default=2026082224)
    return root


def main() -> int:
    args = parser().parse_args()
    result = fit(args)
    print(json.dumps({"verdict": result["verdict"], "failed_gates": result["failed_gates"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
