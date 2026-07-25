#!/usr/bin/env python3
"""Locate the first root-search divergence between exact Jass and Scan."""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
from typing import Any, Iterable

try:
    from l3_internal_root_trace import ENGINES, MAX_DEPTH
except ModuleNotFoundError:  # pragma: no cover
    from jobs.tools.l3_internal_root_trace import ENGINES, MAX_DEPTH


def normalize_score(value: int) -> int | str:
    if value >= 8_000:
        return "+TERMINAL"
    if value <= -8_000:
        return "-TERMINAL"
    return value


def final_attempt(events: list[dict[str, Any]], depth: int) -> dict[str, Any]:
    selected = [event for event in events if int(event["depth"]) == depth]
    attempt = max(int(event["attempt"]) for event in selected)
    rows = [event for event in selected if int(event["attempt"]) == attempt]
    begin = rows[0]
    end = rows[-1]
    moves = [event for event in rows if event["event"] == "move"]
    return {"attempt": attempt, "begin": begin, "moves": moves, "end": end}


def compare_attempts(
    jass: dict[str, Any], scan: dict[str, Any]
) -> dict[str, Any]:
    jm = list(jass["moves"])
    sm = list(scan["moves"])
    jorder = [str(row["move"]) for row in jm]
    sorder = [str(row["move"]) for row in sm]
    moveset_equal = set(jorder) == set(sorder)
    order_equal = jorder == sorder
    result: dict[str, Any] = {
        "jass_attempt": jass["attempt"],
        "scan_attempt": scan["attempt"],
        "moveset_equal": moveset_equal,
        "order_equal": order_equal,
        "jass_order": jorder,
        "scan_order": sorder,
        "jass_bestmove": jass["end"].get("bestmove"),
        "scan_bestmove": scan["end"].get("bestmove"),
        "bestmove_equal": (
            jass["end"].get("bestmove") == scan["end"].get("bestmove")
        ),
    }
    if not moveset_equal:
        result["first_divergence"] = "ROOT_MOVESET"
        result["jass_only"] = sorted(set(jorder) - set(sorder))
        result["scan_only"] = sorted(set(sorder) - set(jorder))
        return result
    if not order_equal:
        result["first_divergence"] = "ROOT_ORDER"
        return result

    windows_equal = True
    scores_equal = True
    first_window_move = None
    first_score_move = None
    for jr, sr in zip(jm, sm):
        jw = (
            normalize_score(int(jr["alpha_before"])),
            normalize_score(int(jr["beta"])),
        )
        sw = (
            normalize_score(int(sr["alpha_before"])),
            normalize_score(int(sr["beta"])),
        )
        if jw != sw and first_window_move is None:
            windows_equal = False
            first_window_move = jr["move"]
        js = normalize_score(int(jr["score"]))
        ss = normalize_score(int(sr["score"]))
        if js != ss and first_score_move is None:
            scores_equal = False
            first_score_move = jr["move"]
    result["windows_equal"] = windows_equal
    result["scores_equal"] = scores_equal
    if not windows_equal:
        result["first_divergence"] = "ROOT_WINDOW"
        result["first_window_move"] = first_window_move
    elif not scores_equal:
        result["first_divergence"] = "RECURSIVE_SCORE"
        result["first_score_move"] = first_score_move
    elif not result["bestmove_equal"]:
        result["first_divergence"] = "ROOT_RESULT"
    else:
        result["first_divergence"] = None
    return result


def load_rows(paths: Iterable[Path]) -> dict[tuple[str, str], dict[str, Any]]:
    rows: dict[tuple[str, str], dict[str, Any]] = {}
    for path in paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("protocol") != "l3-pure-m1-root-internal-trace-replay-v1":
            raise ValueError(f"{path}: unexpected protocol")
        for row in payload.get("rows", []):
            key = (str(row["sentinel_id"]), str(row["engine"]))
            if key in rows:
                raise ValueError(f"{path}: duplicate {key}")
            if "error" in row:
                raise ValueError(f"{path}: engine failure {key}: {row['error']}")
            rows[key] = row
    return rows


def classify(counts: Counter[str | None], total: int) -> str:
    if counts["ROOT_MOVESET"]:
        return "ROOT_LEGAL_MOVE_IDENTITY_DIVERGENCE"
    if counts["ROOT_ORDER"]:
        return "ROOT_ORDERING_SELECTIVITY_DIVERGENCE"
    if counts["ROOT_WINDOW"]:
        return "ASPIRATION_OR_WINDOW_SEMANTICS_DIVERGENCE"
    if counts["RECURSIVE_SCORE"]:
        return "RECURSIVE_NODE_SCORE_SEMANTICS_DIVERGENCE"
    if counts["ROOT_RESULT"]:
        return "ROOT_RESULT_EXTRACTION_DIVERGENCE"
    if counts[None] == total:
        return "ROOT_TRACE_PARITY_INTERNAL_NODE_TRACE_REQUIRED"
    return "MIXED_ROOT_TRACE_DIVERGENCE"


def build_report(
    sentinels: list[dict[str, Any]],
    rows: dict[tuple[str, str], dict[str, Any]],
) -> dict[str, Any]:
    expected = {
        (str(s["sentinel_id"]), engine)
        for s in sentinels
        for engine in ENGINES
    }
    if set(rows) != expected:
        raise ValueError(
            f"trace matrix mismatch missing={len(expected-set(rows))} "
            f"extra={len(set(rows)-expected)}"
        )
    cases: list[dict[str, Any]] = []
    first_counts: Counter[str | None] = Counter()
    depth_counts: dict[str, Counter[str | None]] = {
        str(depth): Counter() for depth in range(1, MAX_DEPTH + 1)
    }
    for sentinel in sentinels:
        sid = str(sentinel["sentinel_id"])
        jevents = rows[(sid, "JASS_EXACT")]["analysis"]["events"]
        sevents = rows[(sid, "SCAN_NATIVE_INSTRUMENTED")]["analysis"]["events"]
        comparisons: dict[str, Any] = {}
        first_depth = None
        first_kind = None
        for depth in range(1, MAX_DEPTH + 1):
            comparison = compare_attempts(
                final_attempt(jevents, depth), final_attempt(sevents, depth)
            )
            comparisons[str(depth)] = comparison
            kind = comparison["first_divergence"]
            depth_counts[str(depth)][kind] += 1
            if first_kind is None and kind is not None:
                first_depth = depth
                first_kind = kind
        first_counts[first_kind] += 1
        cases.append(
            {
                "sentinel_id": sid,
                "stratum": sentinel["stratum"],
                "family": sentinel["family"],
                "first_divergence_depth": first_depth,
                "first_divergence": first_kind,
                "depths": comparisons,
            }
        )
    verdict = classify(first_counts, len(cases))
    return {
        "schema": 1,
        "protocol": "l3-pure-m1-root-internal-trace-audit-v1",
        "diagnostic_only": True,
        "sentinel_count": len(cases),
        "depths": list(range(1, MAX_DEPTH + 1)),
        "first_divergence_counts": {
            str(key): value for key, value in sorted(
                first_counts.items(), key=lambda item: str(item[0])
            )
        },
        "per_depth_counts": {
            depth: {
                str(key): value for key, value in sorted(
                    counts.items(), key=lambda item: str(item[0])
                )
            }
            for depth, counts in depth_counts.items()
        },
        "localization": {
            "verdict": verdict,
            "interpretation": {
                "ROOT_LEGAL_MOVE_IDENTITY_DIVERGENCE": "root move identity differs",
                "ROOT_ORDERING_SELECTIVITY_DIVERGENCE": "same moves, first mismatch is root ordering",
                "ASPIRATION_OR_WINDOW_SEMANTICS_DIVERGENCE": "same ordered moves, first mismatch is the search window",
                "RECURSIVE_NODE_SCORE_SEMANTICS_DIVERGENCE": "same root order/window, child search returns a different score",
                "ROOT_RESULT_EXTRACTION_DIVERGENCE": "events agree but final root result differs",
                "ROOT_TRACE_PARITY_INTERNAL_NODE_TRACE_REQUIRED": "root traces agree; trace the first recursive node",
            }[verdict],
            "next_branch": {
                "ROOT_LEGAL_MOVE_IDENTITY_DIVERGENCE": "audit_move_identity_translation",
                "ROOT_ORDERING_SELECTIVITY_DIVERGENCE": "replay_scan_root_order_in_jass",
                "ASPIRATION_OR_WINDOW_SEMANTICS_DIVERGENCE": "align_aspiration_and_pvs_windows",
                "RECURSIVE_NODE_SCORE_SEMANTICS_DIVERGENCE": "instrument_first_recursive_child",
                "ROOT_RESULT_EXTRACTION_DIVERGENCE": "audit_root_result_extraction",
                "ROOT_TRACE_PARITY_INTERNAL_NODE_TRACE_REQUIRED": "instrument_first_recursive_child",
            }[verdict],
        },
        "cases": cases,
        "training_authorized": False,
        "promotion_authorized": False,
        "automatic_next_job": None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sentinels", type=Path, required=True)
    parser.add_argument("--inputs", type=Path, nargs="+", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--summary-out", type=Path, required=True)
    args = parser.parse_args()
    sentinel_payload = json.loads(args.sentinels.read_text(encoding="utf-8"))
    sentinels = list(sentinel_payload.get("sentinels", []))
    if len(sentinels) != 48:
        raise ValueError("expected 48 sentinels")
    report = build_report(sentinels, load_rows(args.inputs))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    summary = {
        "job": "0960",
        "verdict": report["localization"]["verdict"],
        "sentinel_count": report["sentinel_count"],
        "first_divergence_counts": report["first_divergence_counts"],
        "next_branch": report["localization"]["next_branch"],
        "training_authorized": False,
        "promotion_authorized": False,
        "automatic_next_job": None,
    }
    args.summary_out.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
