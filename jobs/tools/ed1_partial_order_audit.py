#!/usr/bin/env python3
"""ED1: sealed low-budget partial-order labels, then stronger-budget audit only.

No engine, fit, model selection or training payload is produced. The empirical
5k/50k envelope is NOT a confidence interval or a proof of minimax value.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import itertools
import json
import math
from pathlib import Path
import sys

PHASES = ("P0", "P1", "P2", "P3")
LOW = (5000, 50000)
AUDIT = 200000
REPS = 20000
SEED = 2026090804
ID_SHA = {
    "A": "ac33eac505c1bbf316718d2976d151fa51f8e87de5ce96e6d0ecf00a97a5357c",
    "B": "e0befc1c5ad0ad1e8d4f396a6162bfd3d3ec7378a80e099f31e60252df1112ba",
}
GUARDS = dict(new_teacher_searches=0, new_scan_searches=0, new_jass_nodes=0,
              fits=0, strength_games=0, selfplay_games=0, promotions=0, bakes=0)


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def write_new(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as f:
        json.dump(value, f, sort_keys=True, separators=(",", ":"), allow_nan=False)
        f.write("\n")


def load_ids(path: Path, expected_sha: str) -> list[int]:
    if sha(path) != expected_sha:
        raise ValueError("cohort identity hash drift")
    ids = [int(x) for x in path.read_text().split()]
    if len(ids) != 512 or len(set(ids)) != 512 or any(x < 0 or x > 1999 for x in ids):
        raise ValueError("cohort must contain 512 distinct BASE2000 ids")
    return sorted(ids)


def load_groups(path: Path):
    parents, owner = {}, {}
    with path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f, delimiter="\t")
        req = {"parent_id", "row_index", "parent_fingerprint", "parent_phase"}
        if not req.issubset(reader.fieldnames or []):
            raise ValueError("sibling metadata schema drift")
        for row in reader:
            pid, rid = int(row["parent_id"]), int(row["row_index"])
            fp, phase = row["parent_fingerprint"], row["parent_phase"]
            if not fp or phase not in PHASES or rid < 0 or rid in owner:
                raise ValueError("duplicate row or invalid parent metadata")
            p = parents.setdefault(pid, dict(fingerprint=fp, phase=phase, rows=[]))
            if (p["fingerprint"], p["phase"]) != (fp, phase):
                raise ValueError("inconsistent parent metadata")
            p["rows"].append(rid)
            owner[rid] = pid
    if sorted(parents) != list(range(2000)):
        raise ValueError("BASE2000 parent coverage drift")
    if len({p["fingerprint"] for p in parents.values()}) != 2000:
        raise ValueError("canonical parent duplication")
    for phase in PHASES:
        if sum(p["phase"] == phase for p in parents.values()) != 500:
            raise ValueError("BASE2000 phase support drift")
    if any(not 2 <= len(p["rows"]) <= 16 for p in parents.values()):
        raise ValueError("sibling cardinality drift")
    return parents


def load_scores(paths: list[Path], wanted: set[int], budgets: tuple[int, ...]):
    """Never access score fields for unselected rows or unrequested budgets."""
    out = {}
    for path in paths:
        opener = gzip.open if path.suffix == ".gz" else open
        with opener(path, "rt", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f, delimiter="\t")
            req = {"row_index", "budget_nodes", "parent_score_centi"}
            if not req.issubset(reader.fieldnames or []):
                raise ValueError("Scan score schema drift")
            for row in reader:
                rid = int(row["row_index"])
                if rid not in wanted:
                    continue
                budget = int(row["budget_nodes"])
                if budget not in budgets:
                    continue
                key = (rid, budget)
                value = float(row["parent_score_centi"])
                if key in out or not math.isfinite(value):
                    raise ValueError("duplicate/nonfinite Scan label")
                out[key] = value
    required = {(rid, budget) for rid in wanted for budget in budgets}
    if set(out) != required:
        raise ValueError(f"incomplete Scan coverage: missing {len(required-set(out))}")
    return out


def lower_labels(rows: list[int], scores: dict) -> dict:
    point, retained = [], []
    for a, b in itertools.combinations(sorted(rows), 2):
        a50, b50 = scores[a, 50000], scores[b, 50000]
        if a50 == b50:
            continue  # no invented winner for a point-score tie
        win, lose = (a, b) if a50 > b50 else (b, a)
        point.append([win, lose])
        if min(scores[win, n] for n in LOW) > max(scores[lose, n] for n in LOW):
            retained.append([win, lose])
    best = max(scores[rid, 50000] for rid in rows)
    return dict(rows=sorted(rows), point=point, retained=retained,
                best50=[rid for rid in sorted(rows) if scores[rid, 50000] == best])


def freeze(groups: Path, cohort_paths: dict[str, Path], paths: list[Path], out: Path):
    ids = {c: load_ids(p, ID_SHA[c]) for c, p in cohort_paths.items()}
    if set(ids) != {"A", "B"} or set(ids["A"]) & set(ids["B"]):
        raise ValueError("cohort names or disjointness drift")
    meta = load_groups(groups)
    for cohort in ids.values():
        if any(sum(meta[p]["phase"] == ph for p in cohort) != 128 for ph in PHASES):
            raise ValueError("512-parent phase quota drift")
    wanted = {r for cohort in ids.values() for p in cohort for r in meta[p]["rows"]}
    scores = load_scores(paths, wanted, LOW)
    payload = dict(schema="jass.ed1.low_budget_labels.v1", lower_budgets=list(LOW),
                   audit_score_values_accessed=0, unused_parent_score_values_accessed=0,
                   training_allowed=False, groups_sha256=sha(groups),
                   source_files=[dict(name=p.name, sha256=sha(p)) for p in paths],
                   cohort_ids_sha256=ID_SHA, parents=[])
    for c in ("A", "B"):
        for pid in ids[c]:
            p = meta[pid]
            payload["parents"].append(dict(cohort=c, parent_id=pid, phase=p["phase"],
                                           **lower_labels(p["rows"], scores)))
    write_new(out, payload)
    write_new(out.with_suffix(".seal.json"), dict(schema="jass.ed1.label_seal.v1",
              labels_sha256=sha(out), parents=1024, audit_score_values_accessed=0))
    return payload


def parent_result(p: dict, audit: dict) -> dict:
    def rates(pairs):
        if not pairs:
            return dict(contradiction=None, tie=None)
        delta = [audit[w, AUDIT] - audit[l, AUDIT] for w, l in pairs]
        return dict(contradiction=sum(x < 0 for x in delta)/len(delta),
                    tie=sum(x == 0 for x in delta)/len(delta))
    point, retained = p["point"], p["retained"]
    best200 = max(audit[r, AUDIT] for r in p["rows"])
    winners200 = {r for r in p["rows"] if audit[r, AUDIT] == best200}
    return dict(parent_id=p["parent_id"], cohort=p["cohort"], phase=p["phase"],
                point_pairs=len(point), retained_pairs=len(retained),
                coverage=len(retained)/len(point) if point else 0.0,
                point=rates(point), retained=rates(retained),
                top50_tied=len(p["best50"]) > 1,
                top50_set_disjoint_from_200=not bool(set(p["best50"]) & winners200))


def cohort_summary(rows: list[dict], seed: int) -> dict:
    import numpy as np
    eligible = [r for r in rows if r["retained_pairs"] > 0]
    phase_n = {p: sum(r["phase"] == p for r in eligible) for p in PHASES}
    coverage = sum(r["coverage"] for r in rows)/len(rows)
    support = len(eligible) >= 256 and min(phase_n.values()) >= 32
    summary = dict(parents=len(rows), retained_parents=len(eligible), phase_support=phase_n,
                   mean_parent_pair_coverage=coverage,
                   point_pairs=sum(r["point_pairs"] for r in rows),
                   retained_pairs=sum(r["retained_pairs"] for r in rows),
                   top50_tie_rate=sum(r["top50_tied"] for r in rows)/len(rows),
                   top50_set_disjoint_rate=sum(r["top50_set_disjoint_from_200"] for r in rows)/len(rows),
                   support_sufficient=support, point_contradiction=None,
                   retained_contradiction=None, contradiction_reduction_ci95=None,
                   point_tie_at_200=None, retained_tie_at_200=None)
    gates = dict(support=support, coverage_ge_0p25=coverage >= 0.25,
                 point_noise_ge_0p02=False, noise_halved=False, reduction_lcb95_gt_0=False,
                 retained_tie_rate_not_increased=False)
    if eligible:
        # Same parent population for baseline and retained-label comparison.
        pc = float(np.mean([r["point"]["contradiction"] for r in eligible]))
        rc = float(np.mean([r["retained"]["contradiction"] for r in eligible]))
        pt = float(np.mean([r["point"]["tie"] for r in eligible]))
        rt = float(np.mean([r["retained"]["tie"] for r in eligible]))
        summary.update(point_contradiction=pc, retained_contradiction=rc,
                       point_tie_at_200=pt, retained_tie_at_200=rt)
        gates.update(point_noise_ge_0p02=pc >= .02, noise_halved=rc <= .5*pc,
                     retained_tie_rate_not_increased=rt <= pt)
        if support:
            rng = np.random.default_rng(seed)
            boots = np.zeros(REPS)
            for ph in PHASES:
                x = np.asarray([r["point"]["contradiction"]-r["retained"]["contradiction"]
                                for r in eligible if r["phase"] == ph])
                for start in range(0, REPS, 250):
                    end = min(start+250, REPS)
                    idx = rng.integers(0, len(x), size=(end-start, len(x)))
                    boots[start:end] += np.sum(x[idx], axis=1)/len(eligible)
            ci = np.percentile(boots, [2.5, 97.5]).tolist()
            summary["contradiction_reduction_ci95"] = ci
            gates["reduction_lcb95_gt_0"] = ci[0] > 0
    summary.update(gates=gates, supported=all(gates.values()))
    return summary


def audit_labels(labels: Path, paths: list[Path], out: Path, details: Path) -> dict:
    seal = json.loads(labels.with_suffix(".seal.json").read_text())
    if seal.get("labels_sha256") != sha(labels):
        raise ValueError("low-budget label seal mismatch")
    p = json.loads(labels.read_text())
    if p.get("schema") != "jass.ed1.low_budget_labels.v1" or len(p["parents"]) != 1024:
        raise ValueError("label manifest schema/cardinality drift")
    actual = [dict(name=f.name, sha256=sha(f)) for f in paths]
    if actual != p["source_files"] or p["audit_score_values_accessed"] != 0:
        raise ValueError("score identity / information barrier drift")
    wanted = {r for parent in p["parents"] for r in parent["rows"]}
    values = load_scores(paths, wanted, (AUDIT,))
    rows = [parent_result(parent, values) for parent in p["parents"]]
    cohorts = {c: cohort_summary([r for r in rows if r["cohort"] == c], SEED+i)
               for i, c in enumerate(("A", "B"))}
    sufficient = all(c["support_sufficient"] for c in cohorts.values())
    supported = all(c["supported"] for c in cohorts.values())
    verdict = ("ED1_PARTIAL_ORDER_SUPPORT_INSUFFICIENT_V1" if not sufficient else
               "ED1_PARTIAL_ORDER_LABEL_SIGNAL_V1" if supported else
               "ED1_PARTIAL_ORDER_NOT_SUPPORTED_V1")
    result = dict(schema="jass.ed1.partial_order_terminal.v1", verdict=verdict,
                  cohorts=cohorts, guards=GUARDS, labels_sha256=sha(labels),
                  bootstrap=dict(repetitions=REPS, seeds=[SEED, SEED+1], unit="parent_within_phase"),
                  source="previously_exposed_Scan_ceiling_benchmark",
                  reference_is_exact_truth=False, envelope_is_confidence_interval=False,
                  causal_eval_improvement_established=False, benchmark_training_allowed=False,
                  remaining_976_parent_scores_accessed=0, strength_authorized=False,
                  fit_authorized=False,
                  next_stage="PREREG_INDEPENDENT_DATA_AND_ONE_PAIRED_FIT" if supported else "STOP_ED1_REVIEW")
    write_new(details, rows)
    write_new(out, result)
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="command", required=True)
    f = sub.add_parser("freeze")
    f.add_argument("--groups", type=Path, required=True)
    f.add_argument("--cohort-a", type=Path, required=True)
    f.add_argument("--cohort-b", type=Path, required=True)
    f.add_argument("--scan-score", type=Path, action="append", required=True)
    f.add_argument("--out", type=Path, required=True)
    a = sub.add_parser("audit")
    a.add_argument("--labels", type=Path, required=True)
    a.add_argument("--scan-score", type=Path, action="append", required=True)
    a.add_argument("--out", type=Path, required=True)
    a.add_argument("--details", type=Path, required=True)
    args = ap.parse_args()
    try:
        if len(args.scan_score) != 16 or len(set(args.scan_score)) != 16:
            raise ValueError("exactly sixteen distinct authenticated score shards required")
        if args.command == "freeze":
            freeze(args.groups, {"A": args.cohort_a, "B": args.cohort_b}, args.scan_score, args.out)
            print("ED1_LOW_BUDGET_LABELS_SEALED_V1")
        else:
            print(audit_labels(args.labels, args.scan_score, args.out, args.details)["verdict"])
        return 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"ED1_TECHNICAL_FAILURE: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
