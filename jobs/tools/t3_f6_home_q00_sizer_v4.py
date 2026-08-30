#!/usr/bin/env python3
"""HOME-only technical Q00 sizer for the frozen T3-A/F6 v4 runtime.

This is deliberately not a strength test.  It reuses already-consumed R0-v4
positions that are excluded from Pool1, runs the exact frozen R0 executable in
CURRICULUM-OFF and T3-A-ON modes at depth 9, and publishes telemetry only.
Per-position scores, best moves and W/D/L are intentionally discarded.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from calibrate_vs_scan import JassEngine  # noqa: E402
from t3_f6_search_profile import (  # noqa: E402
    bestmove_record,
    fens,
    phase,
    telemetry_report,
)

DEPTH = 9
ORDER_SEED = 2026092505  # frozen R0-v4 benchmark-order seed
PHASES = ("P0", "P1")
ROOTS_PER_PHASE = 8
EXPECTED_R0_CORPUS = 4096


def choose_roots(corpus: list[str]) -> list[str]:
    """Choose a deterministic, score-blind 16-root technical subset.

    P0/P1 are representative of Pool1 material, but the identities come only
    from the already-consumed R0-v4 corpus, which Pool1 excludes in full.
    """
    if len(corpus) != EXPECTED_R0_CORPUS:
        raise ValueError(
            f"R0-v4 corpus must contain {EXPECTED_R0_CORPUS} FENs, got {len(corpus)}"
        )
    if len(set(corpus)) != len(corpus):
        raise ValueError("R0-v4 corpus contains duplicate FEN rows")

    selected: list[str] = []
    for phase_name in PHASES:
        rows = [fen for fen in corpus if phase(fen) == phase_name]
        rows.sort(
            key=lambda fen: hashlib.sha256(
                f"{ORDER_SEED}:home-q00-sizer:{phase_name}:{fen}".encode()
            ).digest()
        )
        if len(rows) < ROOTS_PER_PHASE:
            raise ValueError(
                f"R0-v4 support below {ROOTS_PER_PHASE} roots for {phase_name}"
            )
        selected.extend(rows[:ROOTS_PER_PHASE])

    selected.sort(
        key=lambda fen: hashlib.sha256(
            f"{ORDER_SEED}:home-q00-sizer:all:{fen}".encode()
        ).digest()
    )
    if len(selected) != ROOTS_PER_PHASE * len(PHASES):
        raise ValueError("technical root cardinality drift")
    return selected


def selection_sha256(roots: list[str]) -> str:
    payload = "".join(f"{fen}\n" for fen in roots).encode()
    return hashlib.sha256(payload).hexdigest()


def run(args: argparse.Namespace) -> dict[str, object]:
    corpus = fens(args.corpus)
    roots = choose_roots(corpus)

    off = JassEngine(
        args.exe,
        label="home-q00-sizer-OFF",
        pattern_path=str(args.curriculum),
        search_params=args.search_params,
        env_overrides={"JASS_T3_F6_MODEL": None},
        enforce_no_book=True,
    )
    on = JassEngine(
        args.exe,
        label="home-q00-sizer-ON",
        pattern_path=str(args.curriculum),
        search_params=args.search_params,
        env_overrides={"JASS_T3_F6_MODEL": str(args.model)},
        enforce_no_book=True,
    )

    try:
        # Alternate which arm searches first to avoid a monotonic host-load bias.
        # Search outputs are checked for technical validity and immediately
        # discarded; they are never serialized or aggregated as strength data.
        for index, fen in enumerate(roots):
            arms = (off, on) if index % 2 == 0 else (on, off)
            for engine in arms:
                record = bestmove_record(engine, fen, depth=DEPTH)
                if record["move"] is None:
                    raise ValueError(f"{engine.label}: depth-{DEPTH} returned no legal move")
                nodes = record["nodes"]
                depth = record["depth"]
                if not isinstance(nodes, int) or nodes <= 0:
                    raise ValueError(f"{engine.label}: invalid node receipt {nodes!r}")
                if not isinstance(depth, int) or depth <= 0:
                    raise ValueError(f"{engine.label}: invalid depth receipt {depth!r}")

        off_profile = telemetry_report(off)
        on_profile = telemetry_report(on)
    finally:
        off.close()
        on.close()

    expected_searches = len(roots)
    if int(off_profile.get("searches", 0)) != expected_searches:
        raise ValueError("OFF telemetry search-count drift")
    if int(on_profile.get("searches", 0)) != expected_searches:
        raise ValueError("ON telemetry search-count drift")

    off_wall = float(off_profile.get("wall_seconds", 0.0))
    on_wall = float(on_profile.get("wall_seconds", 0.0))
    if off_wall <= 0.0 or on_wall <= 0.0:
        raise ValueError("non-positive HOME telemetry wall time")

    off_nps = float(off_profile.get("nps", 0.0))
    on_nps = float(on_profile.get("nps", 0.0))
    if off_nps <= 0.0 or on_nps <= 0.0:
        raise ValueError("non-positive HOME NPS telemetry")

    return {
        "schema": "jass.t3_f6_home_q00_technical_sizer.v4",
        "passed": True,
        "verdict": "HOME_Q00_V4_TECHNICAL_SIZER_PASS",
        "technical_only": True,
        "source": "consumed_r0_v4_corpus",
        "source_pool1_excluded": True,
        "q00_depth": DEPTH,
        "order_seed": ORDER_SEED,
        "roots": len(roots),
        "roots_by_phase": {phase_name: ROOTS_PER_PHASE for phase_name in PHASES},
        "root_selection_sha256": selection_sha256(roots),
        "same_executable_on_off": True,
        "same_curriculum_on_off": True,
        "book_disabled": True,
        "search_profile": {
            "curriculum_off": off_profile,
            "t3_f6_on": on_profile,
        },
        "wall_ratio_t3_over_curriculum": on_wall / off_wall,
        "nps_ratio_t3_over_curriculum": on_nps / off_nps,
        "score_values_published": False,
        "best_moves_published": False,
        "wdl_published": False,
        "strength_games": 0,
        "pool_decision_authorized": False,
        "training": False,
        "tuning": False,
        "bake": False,
        "promotion": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exe", required=True)
    parser.add_argument("--curriculum", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--search-params", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)

    try:
        report = run(args)
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 4

    args.out.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
