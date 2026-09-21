#!/usr/bin/env python3
"""Exploratory Chinook-style blind-spot miner over frozen Jass/Scan artifacts."""
from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from collections import defaultdict
from pathlib import Path

PRIMARY = "b2000000_parent_regret"
DELTA = "b2000000_hier_minus_parent"
NROOTS = 512
TAIL = 64
MIN_SUPPORT = 16
MIN_GROSS = 4


def need(cond: bool, msg: str) -> None:
    if not cond:
        raise ValueError(msg)


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        r = csv.DictReader(f, delimiter="\t")
        need(r.fieldnames is not None, f"{path}: missing header")
        return list(r)


def parse_fp(fp: str) -> tuple[int, int, int, int, int]:
    parts = fp.split(":")
    need(len(parts) == 5, "fingerprint field count")
    vals = tuple(int(x, 16) for x in parts[:4]) + (int(parts[4]),)
    wm, wk, bm, bk, stm = vals
    mask = (1 << 50) - 1
    need(stm in (0, 1), "fingerprint stm")
    need(all(0 <= x <= mask for x in (wm, wk, bm, bk)), "fingerprint range")
    need((wm & wk) == (wm & bm) == (wm & bk) == (wk & bm) == (wk & bk) == (bm & bk) == 0,
         "fingerprint overlap")
    return wm, wk, bm, bk, stm


def bucket_moves(n: int) -> str:
    return "2" if n <= 2 else "3-4" if n <= 4 else "5-8" if n <= 8 else "9+"


def bucket_kings(n: int) -> str:
    return "0" if n == 0 else "1" if n == 1 else "2-3" if n <= 3 else "4+"


def material_bucket(v: int) -> str:
    a = abs(v)
    return "0" if a == 0 else "1" if a == 1 else "2-3" if a <= 3 else "4+"


def descriptors(rows: list[dict[str, str]]) -> dict[str, str]:
    first = rows[0]
    wm, wk, bm, bk, stm = parse_fp(first["parent_fingerprint"])
    need(all(r["parent_fingerprint"] == first["parent_fingerprint"] for r in rows), "parent fingerprint drift")
    need(all(r["parent_stm"] == first["parent_stm"] for r in rows), "parent stm drift")
    legal = len(rows)
    need(all(int(r["parent_legal_moves"]) == legal for r in rows), "legal move count drift")
    captures = [int(r["num_captures"]) for r in rows]
    promotes = [int(r["promotes"]) for r in rows]
    moving_king = [int(r["moving_king"]) for r in rows]
    captured_kings = [int(r["captured_kings"]) for r in rows]
    need(all(x >= 0 for x in captures + promotes + moving_king + captured_kings), "negative action metadata")
    counts = [x.bit_count() for x in (wm, wk, bm, bk)]
    wmat, bmat = counts[0] + 3 * counts[1], counts[2] + 3 * counts[3]
    stm_margin = (wmat - bmat) if stm == 0 else (bmat - wmat)
    return {
        "phase": first["parent_phase"],
        "pieces": str(sum(counts)),
        "side_to_move": "white" if stm == 0 else "black",
        "white_men": str(counts[0]),
        "white_kings": str(counts[1]),
        "black_men": str(counts[2]),
        "black_kings": str(counts[3]),
        "total_kings": bucket_kings(counts[1] + counts[3]),
        "stm_material_margin": material_bucket(stm_margin),
        "stm_material_status": "ahead" if stm_margin > 0 else "behind" if stm_margin < 0 else "equal",
        "legal_moves": bucket_moves(legal),
        "capture_available": str(any(x > 0 for x in captures)).lower(),
        "capture_choices": bucket_moves(sum(x > 0 for x in captures)),
        "max_capture_length": str(max(captures)),
        "multi_capture_available": str(max(captures) >= 2).lower(),
        "promotion_available": str(any(promotes)).lower(),
        "promotion_choices": str(sum(bool(x) for x in promotes)),
        "king_move_available": str(any(moving_king)).lower(),
        "king_move_choices": bucket_moves(sum(bool(x) for x in moving_king)),
        "king_capture_available": str(any(x > 0 for x in captured_kings)).lower(),
        "king_capture_choices": str(sum(x > 0 for x in captured_kings)),
    }


def analyze(diag: list[dict[str, str]], siblings: list[dict[str, str]]) -> tuple[dict, list[dict]]:
    need(len(diag) == NROOTS, f"diagnostic root count != {NROOTS}")
    required = {"root_id", PRIMARY, DELTA}
    need(required.issubset(diag[0]), "diagnostic fields")
    by_root: dict[str, list[dict[str, str]]] = defaultdict(list)
    for r in siblings:
        by_root[r["parent_id"]].append(r)
    ids = [r["root_id"] for r in diag]
    need(len(set(ids)) == NROOTS and set(ids).issubset(by_root), "root identity coverage")

    regrets = {r["root_id"]: int(r[PRIMARY]) for r in diag}
    ordered = sorted(regrets.values(), reverse=True)
    threshold = ordered[TAIL - 1]
    gross = {rid for rid, v in regrets.items() if v >= threshold}
    baseline = len(gross) / NROOTS
    need(baseline > 0, "empty gross tail")

    delta = {r["root_id"]: int(r[DELTA]) for r in diag}
    root_features = {rid: descriptors(by_root[rid]) for rid in ids}
    groups: dict[tuple[str, str], list[str]] = defaultdict(list)
    for rid, feat in root_features.items():
        for name, value in feat.items():
            groups[(name, value)].append(rid)

    patterns = []
    for (feature, value), rids in sorted(groups.items()):
        vals = [regrets[r] for r in rids]
        gc = sum(r in gross for r in rids)
        rate = gc / len(rids)
        row = {
            "feature": feature,
            "value": value,
            "support": len(rids),
            "gross_error_count": gc,
            "gross_error_rate": rate,
            "baseline_gross_error_rate": baseline,
            "lift": rate / baseline,
            "mean_curriculum_regret_centi_scan": statistics.fmean(vals),
            "median_curriculum_regret_centi_scan": statistics.median(vals),
            "mean_hier_minus_curriculum_centi_scan": statistics.fmean(delta[r] for r in rids),
            "shortlisted": len(rids) >= MIN_SUPPORT and gc >= MIN_GROSS,
        }
        need(all(math.isfinite(float(row[k])) for k in ("gross_error_rate","baseline_gross_error_rate","lift",
             "mean_curriculum_regret_centi_scan","median_curriculum_regret_centi_scan",
             "mean_hier_minus_curriculum_centi_scan")), "nonfinite pattern metric")
        patterns.append(row)

    patterns.sort(key=lambda r: (
        not r["shortlisted"], -r["lift"], -r["gross_error_count"], -r["support"], r["feature"], r["value"]
    ))
    summary = {
        "schema": "jass.chinook_error_mining.v1",
        "classification": "EXPLORATORY_CONSUMED_DATA",
        "diagnostic_only": True,
        "reference_is_ground_truth": False,
        "scientific_verdict": None,
        "promotion_authorized": False,
        "automatic_feature_implementation_authorized": False,
        "new_scan_searches": 0,
        "new_jass_searches": 0,
        "fits": 0,
        "strength_games": 0,
        "roots": NROOTS,
        "gross_tail_nominal_roots": TAIL,
        "gross_tail_tie_inclusive_roots": len(gross),
        "gross_tail_threshold_centi_scan": threshold,
        "baseline_gross_error_rate": baseline,
        "minimum_pattern_support": MIN_SUPPORT,
        "minimum_pattern_gross_errors": MIN_GROSS,
        "patterns_total": len(patterns),
        "patterns_shortlisted": sum(r["shortlisted"] for r in patterns),
        "shortlist": [r for r in patterns if r["shortlisted"]],
    }
    return summary, patterns


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--diagnostic", type=Path, required=True)
    p.add_argument("--siblings", type=Path, required=True)
    p.add_argument("--json-out", type=Path, required=True)
    p.add_argument("--csv-out", type=Path, required=True)
    a = p.parse_args()
    need(not a.json_out.exists() and not a.csv_out.exists(), "no-clobber")
    summary, rows = analyze(read_tsv(a.diagnostic), read_tsv(a.siblings))
    a.json_out.write_text(json.dumps(summary, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    with a.csv_out.open("x", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
        w.writeheader(); w.writerows(rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
