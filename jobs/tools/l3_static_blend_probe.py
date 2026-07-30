#!/usr/bin/env python3
"""Check static-evaluation linearity of a PJTW blend on fixed legal positions."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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


def load_fens(path: Path, expected: int) -> list[str]:
    rows = [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    if len(rows) != expected:
        raise ValueError(f"probe FEN count {len(rows)} != expected {expected}")
    if len(set(rows)) != len(rows):
        raise ValueError("probe FENs are not unique")
    return rows


def eval_position(jass: Path, model: Path, fen: str) -> int:
    proc = subprocess.run(
        [str(jass), "--eval-position", str(model), fen],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if proc.returncode != 0:
        raise ValueError(
            f"eval-position failed rc={proc.returncode}: {proc.stderr.strip()}"
        )
    value = proc.stdout.strip()
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"non-integer eval-position output: {value!r}") from exc


def summarize(
    rows: list[dict[str, Any]], alpha_a: float, max_abs_residual: float
) -> dict[str, Any]:
    if not rows:
        raise ValueError("empty static-linearity probe")
    residuals: list[float] = []
    for row in rows:
        expected = alpha_a * row["parent_a"] + (1.0 - alpha_a) * row["parent_b"]
        residual = row["blend"] - expected
        row["expected_convex_score"] = expected
        row["residual"] = residual
        residuals.append(residual)
    maximum = max(abs(value) for value in residuals)
    if maximum > max_abs_residual:
        raise ValueError(
            f"static-linearity residual {maximum} exceeds {max_abs_residual}"
        )
    return {
        "schema": 1,
        "stage": "l3_static_blend_linearity_probe",
        "alpha_a": alpha_a,
        "alpha_b": 1.0 - alpha_a,
        "positions": len(rows),
        "max_abs_residual": maximum,
        "mean_abs_residual": sum(abs(value) for value in residuals) / len(rows),
        "allowed_max_abs_residual": max_abs_residual,
        "passed": True,
        "rows": rows,
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    if not 0.0 <= args.alpha_a <= 1.0:
        raise ValueError("alpha-a must be in [0,1]")
    fens = load_fens(args.fens, args.expected_positions)
    rows = []
    for fen in fens:
        rows.append(
            {
                "fen": fen,
                "parent_a": eval_position(args.jass, args.parent_a, fen),
                "parent_b": eval_position(args.jass, args.parent_b, fen),
                "blend": eval_position(args.jass, args.blend, fen),
            }
        )
    payload = summarize(rows, args.alpha_a, args.max_abs_residual)
    payload["inputs"] = {
        "jass": str(args.jass),
        "parent_a": str(args.parent_a),
        "parent_a_sha256": sha256(args.parent_a),
        "parent_b": str(args.parent_b),
        "parent_b_sha256": sha256(args.parent_b),
        "blend": str(args.blend),
        "blend_sha256": sha256(args.blend),
        "fens": str(args.fens),
        "fens_sha256": sha256(args.fens),
    }
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jass", required=True, type=Path)
    parser.add_argument("--parent-a", required=True, type=Path)
    parser.add_argument("--parent-b", required=True, type=Path)
    parser.add_argument("--blend", required=True, type=Path)
    parser.add_argument("--alpha-a", required=True, type=float)
    parser.add_argument("--fens", required=True, type=Path)
    parser.add_argument("--expected-positions", required=True, type=int)
    parser.add_argument("--max-abs-residual", type=float, default=2.0)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        payload = run(args)
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        print(f"l3_static_blend_probe: {exc}", file=sys.stderr)
        return 2
    atomic_write_text(
        args.out, json.dumps(payload, indent=2, sort_keys=True) + "\n"
    )
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
