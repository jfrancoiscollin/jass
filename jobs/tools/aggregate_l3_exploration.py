#!/usr/bin/env python3
"""Validate and aggregate realised L3 exploration counters from shard logs."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

CONFIG_KEYS = ("random_open_plies", "explore_eps", "decay_plies")
COUNT_KEYS = (
    "openings",
    "games",
    "random_open_moves",
    "play_plies",
    "eps_events",
    "eps_changed_best",
    "games_with_eps",
)
REQUIRED_KEYS = set(CONFIG_KEYS + COUNT_KEYS)


def parse_log(path: Path) -> dict[str, int]:
    matches = [
        line.strip() for line in path.read_text(encoding="utf-8", errors="replace").splitlines()
        if line.startswith("EXPLORATION ")
    ]
    if len(matches) != 1:
        raise ValueError(f"{path}: expected exactly one EXPLORATION line, got {len(matches)}")
    values: dict[str, int] = {}
    for token in matches[0].split()[1:]:
        if "=" not in token:
            raise ValueError(f"{path}: malformed EXPLORATION token {token!r}")
        key, raw = token.split("=", 1)
        if key in values:
            raise ValueError(f"{path}: duplicate EXPLORATION key {key}")
        values[key] = int(raw)
    missing = REQUIRED_KEYS - values.keys()
    extra = values.keys() - REQUIRED_KEYS
    if missing or extra:
        raise ValueError(f"{path}: exploration keys missing={sorted(missing)} extra={sorted(extra)}")
    if any(value < 0 for value in values.values()):
        raise ValueError(f"{path}: exploration counters/config must be non-negative")
    if values["eps_changed_best"] > values["eps_events"]:
        raise ValueError(f"{path}: eps_changed_best exceeds eps_events")
    if values["eps_events"] > values["play_plies"]:
        raise ValueError(f"{path}: eps_events exceeds play_plies")
    if values["games_with_eps"] > values["games"]:
        raise ValueError(f"{path}: games_with_eps exceeds games")
    if values["random_open_moves"] > values["openings"] * values["random_open_plies"]:
        raise ValueError(f"{path}: random_open_moves exceeds configured maximum")
    return values


def ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def build_payload(
    log_paths: list[Path],
    *,
    expected_random_open: int,
    expected_eps: int,
    expected_decay: int,
) -> dict:
    expected = {
        "random_open_plies": expected_random_open,
        "explore_eps": expected_eps,
        "decay_plies": expected_decay,
    }
    parsed = []
    sources = []
    for path in log_paths:
        values = parse_log(path)
        actual = {key: values[key] for key in CONFIG_KEYS}
        if actual != expected:
            raise ValueError(f"{path}: configured exploration {actual} != expected {expected}")
        parsed.append(values)
        sources.append({
            "path": str(path),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "counts": {key: values[key] for key in COUNT_KEYS},
        })
    if not parsed:
        raise ValueError("at least one --log is required")
    totals = {key: sum(row[key] for row in parsed) for key in COUNT_KEYS}
    if totals["play_plies"] == 0:
        raise ValueError("zero realised play plies")
    if expected_eps > 0 and totals["eps_events"] == 0:
        raise ValueError("positive configured epsilon but zero realised epsilon events")
    return {
        "schema": 1,
        "operation": "aggregate_l3_exploration",
        "configured": expected,
        "shards": len(parsed),
        "counts": totals,
        "rates": {
            "random_open_moves_per_opening": ratio(
                totals["random_open_moves"], totals["openings"]),
            "epsilon_event_per_play_ply": ratio(
                totals["eps_events"], totals["play_plies"]),
            "epsilon_changed_best_per_play_ply": ratio(
                totals["eps_changed_best"], totals["play_plies"]),
            "epsilon_changed_best_given_event": ratio(
                totals["eps_changed_best"], totals["eps_events"]),
            "games_with_epsilon": ratio(
                totals["games_with_eps"], totals["games"]),
        },
        "activation_proven": totals["eps_events"] > 0,
        "sources": sources,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log", nargs="+", required=True)
    parser.add_argument("--expected-random-open", type=int, required=True)
    parser.add_argument("--expected-eps", type=int, required=True)
    parser.add_argument("--expected-decay", type=int, required=True)
    parser.add_argument("--manifest", required=True)
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    payload = build_payload(
        [Path(path) for path in args.log],
        expected_random_open=args.expected_random_open,
        expected_eps=args.expected_eps,
        expected_decay=args.expected_decay,
    )
    output = Path(args.manifest)
    output.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
