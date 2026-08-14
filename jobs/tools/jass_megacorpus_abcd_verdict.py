#!/usr/bin/env python3
"""Aggregate preregistered A/B/C/D strength contrasts without promotion."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

PRIMARY = {
    "B_vs_A": "equal_volume_corpus_composition",
    "C_vs_B": "nested_volume",
    "D_vs_A": "pretrain_then_current_curriculum",
    "D_vs_C": "recentering_after_mega",
}
SECONDARY = {
    "C_vs_A": "combined_corpus_and_volume",
    "D_vs_B": "curriculum_vs_equal_volume_mega",
}
VIEWS = ("q00", "native")


def load_gate(force_dir: Path, view: str, contrast: str) -> dict:
    path = force_dir / f"force-{view}-{contrast}.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    paired = data.get("paired_opening") or {}
    if not data.get("complete") or data.get("n") != 500:
        raise ValueError(f"{path}: incomplete gate")
    if paired.get("method") != "paired_colour_opening_cluster_bootstrap":
        raise ValueError(f"{path}: missing paired opening inference")
    if paired.get("n_openings") != 250 or paired.get("games_per_opening") != 2:
        raise ValueError(f"{path}: opening/pair budget drift")
    if paired.get("bootstrap_samples") != 200000:
        raise ValueError(f"{path}: bootstrap budget drift")
    if int(paired.get("error_draws", 0)) > 10:
        raise ValueError(f"{path}: more than 2% engine-error draws")
    if abs(float(data["rate"]) - float(paired["rate"])) > 1e-6:
        raise ValueError(f"{path}: aggregate/paired rate mismatch")
    return data


def summarize_contrast(force_dir: Path, contrast: str, mechanism: str, primary: bool) -> dict:
    views = {view: load_gate(force_dir, view, contrast) for view in VIEWS}
    point_positive = all(float(item["rate"]) > 0.5 for item in views.values())
    established = all(float(item["paired_opening"]["ci_low"]) > 0.5 for item in views.values())
    point_negative = all(float(item["rate"]) < 0.5 for item in views.values())
    established_regression = all(float(item["paired_opening"]["ci_high"]) < 0.5
                                 for item in views.values())
    return {
        "mechanism": mechanism,
        "primary": primary,
        "views": views,
        "point_positive_both_views": point_positive,
        "gain_established_both_views": established,
        "point_negative_both_views": point_negative,
        "regression_established_both_views": established_regression,
        "interpretation": (
            "gain_established" if established else
            "positive_direction_not_established" if point_positive else
            "regression_established" if established_regression else
            "negative_direction_not_established" if point_negative else
            "view_dependent_or_neutral"
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force-dir", required=True)
    parser.add_argument("--static-readout", required=True)
    parser.add_argument("--abc-summary", required=True)
    parser.add_argument("--d-summary", required=True)
    parser.add_argument("--opening-manifest", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--summary-out", required=True)
    args = parser.parse_args(argv)
    force_dir = Path(args.force_dir)
    static = json.loads(Path(args.static_readout).read_text(encoding="utf-8"))
    abc = json.loads(Path(args.abc_summary).read_text(encoding="utf-8"))
    arm_d = json.loads(Path(args.d_summary).read_text(encoding="utf-8"))
    opening = json.loads(Path(args.opening_manifest).read_text(encoding="utf-8"))
    if static.get("schema") != "jass.megacorpus.abcd_static_readout.v1":
        raise ValueError("static readout schema drift")
    if abc.get("verdict") != "JASS_MEGACORPUS_ABC_FITS_READY":
        raise ValueError("ABC summary drift")
    if arm_d.get("verdict") != "JASS_MEGACORPUS_ARM_D_FIT_READY":
        raise ValueError("D summary drift")
    if opening.get("selected_openings") != 250:
        raise ValueError("opening manifest drift")

    effects = {
        name: summarize_contrast(force_dir, name, mechanism, True)
        for name, mechanism in PRIMARY.items()
    }
    effects.update({
        name: summarize_contrast(force_dir, name, mechanism, False)
        for name, mechanism in SECONDARY.items()
    })
    report = {
        "schema": "jass.megacorpus.abcd_strength_readout.v1",
        "verdict": "JASS_MEGACORPUS_ABCD_COMPARISONS_READY",
        "arms": {
            "A": "CURRENT_2M",
            "B": "MEGA_EQ_2M",
            "C": "MEGA_FULL_4M",
            "D": "C_PRIOR_THEN_CURRENT_2M",
        },
        "effects": effects,
        "static_diagnostics": static,
        "opening_manifest": opening,
        "decision_rules": {
            "positive_points_are_retained": True,
            "established_gain_requires_paired_opening_ci_low_above_half_in_both_views": True,
            "static_metrics_cannot_rescue_strength_failure": True,
            "promotion_authorized": False,
        },
        "promotion_authorized": False,
        "automatic_next_job": None,
    }
    Path(args.out).write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    Path(args.summary_out).write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
