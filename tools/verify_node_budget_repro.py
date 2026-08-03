#!/usr/bin/env python3
"""Compare deterministic fields from two node-budget self-play JSONL logs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


SEARCH_FIELDS = (
    "game_id",
    "ply",
    "side_to_move",
    "nodes_budget",
    "nodes_used",
    "effective_depth",
    "completed_depth",
    "aborted_iteration",
    "stop_reason",
    "search_best_move",
    "move_selected",
)

GAME_FIELDS = (
    "game_id",
    "plies",
    "result_white",
    "resolved",
    "ply_cap",
)


def load_events(path: Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(f"{path}:{line_number}: invalid JSON: {error}") from error
            if not isinstance(event, dict) or "event" not in event:
                raise ValueError(f"{path}:{line_number}: JSON object with event required")
            events.append(event)
    if not events or events[0].get("event") != "node_budget_manifest":
        raise ValueError(f"{path}: first event must be node_budget_manifest")
    if events[-1].get("event") != "node_budget_summary":
        raise ValueError(f"{path}: last event must be node_budget_summary")
    return events


def project(events: list[dict[str, Any]], event_name: str,
            fields: tuple[str, ...]) -> list[tuple[Any, ...]]:
    projected: list[tuple[Any, ...]] = []
    for event in events:
        if event.get("event") != event_name:
            continue
        missing = [field for field in fields if field not in event]
        if missing:
            raise ValueError(f"{event_name} event missing fields: {', '.join(missing)}")
        projected.append(tuple(event[field] for field in fields))
    return projected


def first_difference(left: list[tuple[Any, ...]], right: list[tuple[Any, ...]]) -> str:
    for index, (lhs, rhs) in enumerate(zip(left, right)):
        if lhs != rhs:
            return f"event {index}: {lhs!r} != {rhs!r}"
    if len(left) != len(right):
        return f"event counts differ: {len(left)} != {len(right)}"
    return ""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("left", type=Path)
    parser.add_argument("right", type=Path)
    args = parser.parse_args()

    try:
        left = load_events(args.left)
        right = load_events(args.right)
        left_manifest = left[0]
        right_manifest = right[0]
        if left_manifest != right_manifest:
            raise ValueError("node-budget manifests differ")

        left_searches = project(left, "selfplay_search", SEARCH_FIELDS)
        right_searches = project(right, "selfplay_search", SEARCH_FIELDS)
        difference = first_difference(left_searches, right_searches)
        if difference:
            raise ValueError(f"selfplay_search mismatch: {difference}")

        left_games = project(left, "selfplay_game", GAME_FIELDS)
        right_games = project(right, "selfplay_game", GAME_FIELDS)
        difference = first_difference(left_games, right_games)
        if difference:
            raise ValueError(f"selfplay_game mismatch: {difference}")
    except (OSError, ValueError) as error:
        parser.error(str(error))

    print(
        f"reproducible: {len(left_searches)} searches, "
        f"{len(left_games)} games, sampler v{left_manifest['sampler_version']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
