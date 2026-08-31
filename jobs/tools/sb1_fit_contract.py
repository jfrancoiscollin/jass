#!/usr/bin/env python3
"""Frozen SB1 trainer launcher. The only scientific A/B difference is prior basin."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import struct
import subprocess
import sys


RECIPE = {
    "target": "external",
    "loss": "logistic",
    "fold": "exact",
    "phase": "tempo-stage",
    "prior_decay": 0.0,
    "l2": 1e-5,
    "max_iter": 2000,
    "lbfgs_maxcor": 20,
    "lbfgs_gtol": 1e-4,
    "chunk": 20000,
    "prune": True,
}
ARMS = {
    "SELF_BASIN": "C",
    "SCAN_BASIN": "SCAN_EXACT",
}
FORBIDDEN_SCIENCE = (
    "PL8", "F6", "Rich-D", "D1", "NNUE", "micro-search",
    "search-label", "FM term",
)


def jnnw_count(path: str | Path) -> int:
    with open(path, "rb") as handle:
        header = handle.read(8)
    if len(header) != 8 or header[:4] != b"JNNW":
        raise ValueError(f"{path}: invalid JNNW")
    return int(struct.unpack_from("<I", header, 4)[0])


def build_train_command(
    *,
    python: str,
    train_stream: str,
    data: str,
    feat: str,
    target_values: str,
    prior: str,
    out: str,
    targets_report: str,
    optimizer_report: str,
    holdout_count: int,
    max_iter: int = RECIPE["max_iter"],
) -> list[str]:
    return [
        python, train_stream,
        "--data", data,
        "--feat", feat,
        "--out", out,
        "--target", RECIPE["target"],
        "--target-values", target_values,
        "--targets-report", targets_report,
        "--loss", RECIPE["loss"],
        "--exact-fold",
        "--tempo-stage",
        "--prior-mean", prior,
        "--prior-decay", "0",
        "--holdout-count", str(holdout_count),
        "--l2", "1e-5",
        "--max-iter", str(max_iter),
        "--chunk", "20000",
        "--lbfgs-maxcor", "20",
        "--lbfgs-gtol", "1e-4",
        "--prune",
        "--optimizer-report", optimizer_report,
    ]


def normalized_science_command(command: list[str]) -> list[str]:
    """Erase arm-local path outputs and the treatment path, retaining science flags."""
    replace_after = {
        "--out": "<OUT>",
        "--targets-report": "<TARGET_REPORT>",
        "--optimizer-report": "<OPT_REPORT>",
        "--prior-mean": "<PRIOR>",
    }
    normalized: list[str] = []
    i = 0
    while i < len(command):
        token = command[i]
        normalized.append(token)
        if token in replace_after:
            normalized.append(replace_after[token])
            i += 2
        else:
            i += 1
    return normalized


def only_prior_basin_diff(
    command_a: list[str],
    command_b: list[str],
) -> bool:
    return normalized_science_command(command_a) == normalized_science_command(command_b)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arm", choices=sorted(ARMS), required=True)
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument(
        "--train-stream",
        default="pattern_jass/tools/train_stream.py",
    )
    parser.add_argument("--data", required=True)
    parser.add_argument("--feat", required=True)
    parser.add_argument("--target-values", required=True)
    parser.add_argument("--prior-c", required=True)
    parser.add_argument("--prior-scan", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--targets-report", required=True)
    parser.add_argument("--optimizer-report", required=True)
    parser.add_argument("--holdout-count", type=int, required=True)
    parser.add_argument("--receipt", required=True)
    parser.add_argument(
        "--sizer-max-iter",
        type=int,
        help="technical-only bounded optimizer sizer; must be 1..5 and never a full 2M fit",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    records = jnnw_count(args.data)
    if not 0 < args.holdout_count < records:
        raise SystemExit("invalid holdout count")
    scientific_fit = args.sizer_max_iter is None
    if scientific_fit:
        max_iter = RECIPE["max_iter"]
        if records != 2_000_000:
            raise SystemExit("full SB1 fit requires exactly CURRENT_2M = 2,000,000 records")
    else:
        if not 1 <= args.sizer_max_iter <= 5:
            raise SystemExit("--sizer-max-iter must be in [1,5]")
        if records >= 2_000_000:
            raise SystemExit("technical sizer refuses a full CURRENT_2M corpus")
        max_iter = args.sizer_max_iter

    prior = args.prior_c if args.arm == "SELF_BASIN" else args.prior_scan
    command = build_train_command(
        python=args.python,
        train_stream=args.train_stream,
        data=args.data,
        feat=args.feat,
        target_values=args.target_values,
        prior=prior,
        out=args.out,
        targets_report=args.targets_report,
        optimizer_report=args.optimizer_report,
        holdout_count=args.holdout_count,
        max_iter=max_iter,
    )
    receipt = {
        "schema": "jass.sb1.fit_contract.v1",
        "arm": args.arm,
        "treatment": {
            "prior_basin": ARMS[args.arm],
            "prior_path": prior,
        },
        "recipe": dict(RECIPE),
        "effective_max_iter": max_iter,
        "scientific_fit": scientific_fit,
        "technical_sizer": not scientific_fit,
        "records": records,
        "holdout_count": args.holdout_count,
        "normalized_science_command": normalized_science_command(command),
        "markers": {
            "FULL_FITS": 1 if scientific_fit else 0,
            "FRESH_FORCE": 0,
            "STRENGTH_GAMES": 0,
            "SCIENTIFIC_DECISION": False,
        },
    }
    Path(args.receipt).parent.mkdir(parents=True, exist_ok=True)
    Path(args.receipt).write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    subprocess.run(command, check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
