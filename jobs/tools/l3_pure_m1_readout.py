#!/usr/bin/env python3
"""Create status-visible markers from an L3-PURE M1 evaluation payload."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path


MODELS = ("F500", "F2M", "R2M")
STRATA = ("p1_net", "p2_moyen", "p3_mince", "p4_egal")


def bp(value: float) -> int:
    return int(round(float(value) * 10_000))


def signed_milli(value: float) -> str:
    scaled = int(round(float(value) * 1_000))
    return f"P{scaled}" if scaled >= 0 else f"M{-scaled}"


def signed_bp(value: float) -> str:
    scaled = bp(value)
    return f"P{scaled}" if scaled >= 0 else f"M{-scaled}"


def validate(payload: dict) -> None:
    if payload.get("verdict") != "M1_EVALUATION_READY_HUMAN_REVIEW":
        raise ValueError("unexpected or missing M1 evaluation verdict")
    if payload.get("promotion_authorized") is not False:
        raise ValueError("evaluation must remain non-promotable")
    for model in MODELS:
        for key in ("q00_vs_C0", "native_vs_C0", "q00_vs_GEN2"):
            row = payload["force"][model][key]
            for field in ("n", "rate", "elo"):
                if field not in row or not math.isfinite(float(row[field])):
                    raise ValueError(f"invalid force field {model}/{key}/{field}")
    for model in ("C0",) + MODELS:
        for stratum in STRATA:
            row = payload["fixed_defender_conversion"][model][stratum]
            if int(row["n_pos"]) <= 0:
                raise ValueError(f"empty conversion cell {model}/{stratum}")
            if not math.isfinite(float(row["conversion"])):
                raise ValueError(f"invalid conversion {model}/{stratum}")


def global_conversion(payload: dict, model: str) -> float:
    rows = payload["fixed_defender_conversion"][model]
    wins = sum(int(rows[s]["n_win"]) for s in STRATA)
    total = sum(int(rows[s]["n_pos"]) for s in STRATA)
    if total <= 0:
        raise ValueError(f"empty global conversion for {model}")
    return wins / total


def build_readout(payload: dict) -> dict:
    validate(payload)
    conversion = payload["fixed_defender_conversion"]
    global_rates = {
        model: global_conversion(payload, model) for model in ("C0",) + MODELS
    }
    return {
        "schema": 1,
        "verdict": "M1_READOUT_READY_HUMAN_REVIEW",
        "force": payload["force"],
        "fixed_defender_conversion": conversion,
        "global_conversion": global_rates,
        "global_delta_vs_c0": {
            model: global_rates[model] - global_rates["C0"] for model in MODELS
        },
        "stratum_delta_vs_c0": {
            model: {
                stratum: float(conversion[model][stratum]["conversion"])
                - float(conversion["C0"][stratum]["conversion"])
                for stratum in STRATA
            }
            for model in MODELS
        },
        "promotion_authorized": False,
        "automatic_next_job": None,
    }


def write_markers(readout: dict, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for model in MODELS:
        for key, label in (
            ("q00_vs_C0", "Q00_VS_C0"),
            ("native_vs_C0", "NATIVE_VS_C0"),
            ("q00_vs_GEN2", "Q00_VS_GEN2"),
        ):
            row = readout["force"][model][key]
            name = (
                f"FORCE__{model}__{label}"
                f"__RATE_BP_{bp(row['rate']):04d}"
                f"__ELO_MILLI_{signed_milli(row['elo'])}"
            )
            (out_dir / name).write_text(name + "\n", encoding="utf-8")
    for model in ("C0",) + MODELS:
        name = (
            f"CONVERSION_GLOBAL__{model}"
            f"__BP_{bp(readout['global_conversion'][model]):04d}"
        )
        (out_dir / name).write_text(name + "\n", encoding="utf-8")
    for model in MODELS:
        name = (
            f"CONVERSION_GLOBAL_DELTA_VS_C0__{model}"
            f"__BP_{signed_bp(readout['global_delta_vs_c0'][model])}"
        )
        (out_dir / name).write_text(name + "\n", encoding="utf-8")
        for stratum in STRATA:
            rate = readout["fixed_defender_conversion"][model][stratum]["conversion"]
            delta = readout["stratum_delta_vs_c0"][model][stratum]
            name = (
                f"CONVERSION__{model}__{stratum.upper()}"
                f"__BP_{bp(rate):04d}__DELTA_BP_{signed_bp(delta)}"
            )
            (out_dir / name).write_text(name + "\n", encoding="utf-8")
    for marker in (
        "VERDICT__M1_READOUT_READY_HUMAN_REVIEW",
        "PROMOTION_AUTHORIZED__FALSE",
        "AUTOMATIC_NEXT_JOB__NULL",
    ):
        (out_dir / marker).write_text(marker + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--marker-dir", required=True, type=Path)
    args = parser.parse_args()
    payload = json.loads(args.input.read_text(encoding="utf-8"))
    readout = build_readout(payload)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(readout, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    write_markers(readout, args.marker_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
