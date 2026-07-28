#!/usr/bin/env python3
"""Aggregate the preregistered VOL8M independent readout."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from typing import Any

try:
    from l3_corrected_conversion_matrix import paired_conversion
except ModuleNotFoundError:
    from jobs.tools.l3_corrected_conversion_matrix import paired_conversion


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: expected JSON object")
    return value


def force(path: Path) -> dict[str, Any]:
    x = load(path)
    if int(x["n"]) != 3000:
        raise ValueError(f"{path}: expected 3000 games")
    return {
        key: x[key]
        for key in ("n", "wins_a", "draws", "wins_b", "rate", "elo", "ci_low", "ci_high")
    }


def compact_coverage(path: Path) -> dict[str, Any]:
    report = load(path)
    if (
        report.get("stage") != "l3_bucket_visits"
        or int(report["geometry"]["trained_buckets_total"]) != 2_125_768
    ):
        raise ValueError(f"{path}: unexpected coverage report")
    coverage = report["coverage"]
    return {
        "records": int(report["corpus"]["total_records"]),
        "visited_buckets": int(coverage["visited_buckets"]),
        "visited_pct": 100.0 * float(coverage["coverage_fraction"]),
        "ge_100": int(coverage["buckets_with_at_least"]["ge_100"]),
        "gini": float(report["concentration"]["gini"]),
    }


def build(
    art: Path,
    training: Path,
    preflight: Path,
    *,
    bootstrap_samples: int = 200_000,
) -> dict[str, Any]:
    tr, pre = load(training), load(preflight)
    if (
        tr.get("verdict") != "L3_PURE_VOLUME8M_FIT_CONVERGED"
        or tr.get("training", {}).get("records") != 12_000_000
        or tr.get("training", {}).get("converged") is not True
        or tr.get("holdout_loss_is_a_diagnostic_not_a_selection_criterion") is not True
        or tr.get("promotion_authorized") is not False
        or tr.get("automatic_next_job") is not None
        or pre.get("verdict") != "L3_PURE_VOLUME8M_PREFLIGHT_READY"
        or pre.get("promotion_authorized") is not False
        or pre.get("automatic_next_job") is not None
    ):
        raise ValueError("VOL8M training/preflight contract mismatch")

    rows = {
        f"{view}_vs_{opponent}": force(
            art / "force" / f"force-{view}-VOL8M-vs-{opponent}.json"
        )
        for view in ("q00", "native")
        for opponent in ("TURNOVER", "M2", "F2M", "GEN2")
    }
    conv: dict[str, Any] = {}
    conv_reg = False
    for stratum_index, stratum in enumerate(("p3_mince", "p4_egal")):
        cand = load(art / "conversion" / f"VOL8M-{stratum}.json")
        conv[stratum] = {
            "VOL8M": {
                key: cand[key]
                for key in ("n_pos", "n_win", "n_draw", "n_loss", "conversion")
            }
        }
        for control_index, opponent in enumerate(("TURNOVER", "M2", "F2M")):
            base = load(art / "conversion" / f"{opponent}-{stratum}.json")
            delta = paired_conversion(
                cand,
                base,
                bootstrap_samples=bootstrap_samples,
                seed=1007 + stratum_index * 10 + control_index,
            )
            conv[stratum][opponent] = {
                key: base[key]
                for key in ("n_pos", "n_win", "n_draw", "n_loss", "conversion")
            }
            conv[stratum][f"paired_delta_vol8m_minus_{opponent.lower()}"] = delta
            if opponent == "TURNOVER" and delta["ci_high"] < 0:
                conv_reg = True

    coverage = {
        model: compact_coverage(art / "coverage" / f"{model}-coverage.json")
        for model in ("VOL8M", "TURNOVER", "M2", "F2M")
    }
    certified = pre["coverage"]
    if (
        coverage["VOL8M"]["records"] != 12_000_000
        or coverage["VOL8M"]["visited_buckets"] != certified["visited_buckets"]
        or round(coverage["VOL8M"]["visited_pct"], 3) != certified["visited_pct"]
    ):
        raise ValueError("VOL8M coverage differs from the preflight certificate")

    force_reg = any(
        rows[f"{view}_vs_{opponent}"]["ci_high"] < 0.5
        for view in ("q00", "native")
        for opponent in ("M2", "F2M", "GEN2")
    )
    turnover = [rows[f"{view}_vs_TURNOVER"] for view in ("q00", "native")]
    gain = all(row["ci_low"] > 0.5 for row in turnover)
    directional = all(row["rate"] > 0.5 for row in turnover)
    coverage_gain = (
        coverage["VOL8M"]["visited_buckets"] > coverage["TURNOVER"]["visited_buckets"]
    )
    if force_reg or conv_reg:
        verdict = "VOL8M_REGRESSION_DIAGNOSIS_REQUIRED"
    elif gain:
        verdict = "VOL8M_FORCE_GAIN_CONFIRMED_REVIEW"
    elif directional:
        verdict = "VOL8M_DIRECTIONAL_CONFIRMATION_REVIEW"
    else:
        verdict = "VOL8M_AXIS_FLAT_REVIEW"
    out = {
        "schema": 1,
        "verdict": verdict,
        "candidate_model": tr["model"],
        "training": tr["training"],
        "holdout_loss_is_a_diagnostic_not_a_selection_criterion": True,
        "coverage": coverage,
        "force": rows,
        "conversion": conv,
        "decision": {
            "gain_confirmed": gain,
            "directional_both_views": directional,
            "coverage_gain_vs_turnover": coverage_gain,
            "force_regression_established": force_reg,
            "conversion_regression_established": conv_reg,
        },
        "declared_corpus_deviations": tr.get("corpus_deviations", []),
        "promotion_authorized": False,
        "automatic_next_job": None,
    }
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artefact-dir", type=Path, required=True)
    parser.add_argument("--training", type=Path, required=True)
    parser.add_argument("--preflight", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--summary-out", type=Path, required=True)
    args = parser.parse_args()
    out = build(args.artefact_dir, args.training, args.preflight)
    text = json.dumps(out, indent=2, sort_keys=True) + "\n"
    args.out.write_text(text, encoding="utf-8")
    args.summary_out.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
