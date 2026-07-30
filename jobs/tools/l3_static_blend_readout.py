#!/usr/bin/env python3
"""Aggregate the preregistered BLEND50-vs-TURNOVER force readout."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

from jobs.tools import l3_reverse_seed_readout as common


ABOVE_95 = "L3_PURE_BLEND50_ABOVE_TURNOVER_IC95"
ABOVE_90 = "L3_PURE_BLEND50_ABOVE_TURNOVER_IC90"
DIRECTIONAL = "L3_PURE_BLEND50_DIRECTIONAL"
BELOW = "L3_PURE_BLEND50_BELOW_TURNOVER"
INCONCLUSIVE = "L3_PURE_BLEND50_VS_TURNOVER_INCONCLUSIVE"


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
    )
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def validate_build(
    summary: dict[str, Any],
    *,
    source_code_sha: str,
    champion_sha: str,
    reverse_sha: str,
    blend_sha: str,
) -> None:
    models = summary.get("models", {})
    construction = summary.get("construction", {})
    probe = summary.get("static_linearity_probe", {})
    if (
        summary.get("schema") != 1
        or summary.get("verdict") != "L3_PURE_REVERSE_SEED_BLEND50_READY"
        or summary.get("code_sha") != source_code_sha
        or summary.get("primary_contrast")
        != "BLEND50(TURNOVER,REVERSE_SEED) minus TURNOVER"
        or construction.get("mode") != "convex-weight-interpolation"
        or construction.get("single_factor") != "static_pjtw_weight_blend"
        or construction.get("alpha_champion") != 0.5
        or construction.get("alpha_reverse_seed") != 0.5
        or construction.get("training_records") != 0
        or construction.get("self_play_games") != 0
        or models.get("champion_sha256") != champion_sha
        or models.get("reverse_seed_sha256") != reverse_sha
        or models.get("blend_sha256") != blend_sha
        or probe.get("passed") is not True
        or probe.get("positions", 0) < 32
        or probe.get("max_abs_residual", 99) > 8.0
        or summary.get("scientific_result") is not False
        or summary.get("promotion_authorized") is not False
        or summary.get("automatic_next_job", "missing") is not None
    ):
        raise ValueError("static blend build certificate mismatch")


def choose_verdict(
    force: dict[str, dict[str, Any]], summed: dict[str, Any]
) -> tuple[str, dict[str, bool]]:
    both_point_positive = all(
        force[view]["rate_treatment"] > 0.5 for view in force
    )
    any_view_regressed_90 = any(
        force[view]["ci90"][1] < 0.5 for view in force
    )
    if both_point_positive and summed["ci95"][0] > 0.5:
        verdict = ABOVE_95
    elif both_point_positive and summed["ci90"][0] > 0.5:
        verdict = ABOVE_90
    elif summed["ci90"][1] < 0.5 or any_view_regressed_90:
        verdict = BELOW
    elif summed["rate_treatment"] > 0.5 and not any_view_regressed_90:
        verdict = DIRECTIONAL
    else:
        verdict = INCONCLUSIVE
    return verdict, {
        "both_force_views_point_positive": both_point_positive,
        "summed_force_superiority_90": summed["ci90"][0] > 0.5,
        "summed_force_superiority_95": summed["ci95"][0] > 0.5,
        "any_force_view_regressed_90": any_view_regressed_90,
    }


def build_readout(
    *,
    force_dir: Path,
    build_summary_path: Path,
    opening_manifest_path: Path,
    expected_games_per_view: int,
    expected_openings: int,
    code_sha: str,
    source_job: str,
    source_attempt: str,
    source_code_sha: str,
    expected_champion_sha: str,
    expected_reverse_sha: str,
    expected_blend_sha: str,
) -> dict[str, Any]:
    build_summary = common.load(build_summary_path)
    openings = common.load(opening_manifest_path)
    validate_build(
        build_summary,
        source_code_sha=source_code_sha,
        champion_sha=expected_champion_sha,
        reverse_sha=expected_reverse_sha,
        blend_sha=expected_blend_sha,
    )
    if (
        openings.get("records") != expected_openings
        or openings.get("unique_records") != expected_openings
        or openings.get("overlap_records") != 0
    ):
        raise ValueError("independent opening-pool contract mismatch")

    force = {
        view: common.force_cell(
            force_dir / f"force-{view}-BLEND50-vs-TURNOVER.json",
            expected_games_per_view,
        )
        for view in ("q00", "native")
    }
    summed = common.summarize_counts(
        sum(force[view]["wins_treatment"] for view in force),
        sum(force[view]["draws"] for view in force),
        sum(force[view]["wins_control"] for view in force),
    )
    verdict, evidence = choose_verdict(force, summed)
    return {
        "schema": 1,
        "verdict": verdict,
        "code_sha": code_sha,
        "source": {
            "job_id": source_job,
            "attempt_id": source_attempt,
            "code_sha": source_code_sha,
        },
        "models": {
            "control_name": "TURNOVER",
            "control_sha256": expected_champion_sha,
            "reverse_seed_parent_sha256": expected_reverse_sha,
            "treatment_name": "BLEND50",
            "treatment_sha256": expected_blend_sha,
        },
        "protocol": {
            "primary_contrast":
            "BLEND50(TURNOVER,REVERSE_SEED) minus TURNOVER",
            "single_factor": "static_pjtw_weight_blend",
            "alpha_champion": 0.5,
            "alpha_reverse_seed": 0.5,
            "paired_colours": True,
            "fresh_disjoint_openings": True,
            "openings": expected_openings,
            "games_per_view": expected_games_per_view,
            "views": ["q00_depth9", "native_movetime_0.1"],
            "alpha_selected_on_force_pool": False,
            "holdout_used_for_selection": False,
        },
        "opening_manifest": openings,
        "force": force,
        "force_views_summed": summed,
        "decision_evidence": evidence,
        "scientific_result": True,
        "promotion_authorized": False,
        "automatic_next_job": None,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force-dir", required=True, type=Path)
    parser.add_argument("--build-summary", required=True, type=Path)
    parser.add_argument("--opening-manifest", required=True, type=Path)
    parser.add_argument("--expected-games-per-view", required=True, type=int)
    parser.add_argument("--expected-openings", required=True, type=int)
    parser.add_argument("--code-sha", required=True)
    parser.add_argument("--source-job", required=True)
    parser.add_argument("--source-attempt", required=True)
    parser.add_argument("--source-code-sha", required=True)
    parser.add_argument("--champion-model-sha", required=True)
    parser.add_argument("--reverse-model-sha", required=True)
    parser.add_argument("--blend-model-sha", required=True)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--summary-out", type=Path)
    args = parser.parse_args(argv)
    try:
        payload = build_readout(
            force_dir=args.force_dir,
            build_summary_path=args.build_summary,
            opening_manifest_path=args.opening_manifest,
            expected_games_per_view=args.expected_games_per_view,
            expected_openings=args.expected_openings,
            code_sha=args.code_sha,
            source_job=args.source_job,
            source_attempt=args.source_attempt,
            source_code_sha=args.source_code_sha,
            expected_champion_sha=args.champion_model_sha,
            expected_reverse_sha=args.reverse_model_sha,
            expected_blend_sha=args.blend_model_sha,
        )
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"l3_static_blend_readout: {exc}", file=sys.stderr)
        return 2
    serialized = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    atomic_write_text(args.out, serialized)
    if args.summary_out:
        atomic_write_text(args.summary_out, serialized)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
