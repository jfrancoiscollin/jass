#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Deterministically resample L3-IMBALANCE2 training rows with W0 stratum weights.

The terminal WDL label is never changed.  Only training-row sampling probability
changes inside the exact specialist domain: two men of difference and equal king
counts.  Holdout rows are copied byte-for-byte and remain in their original order.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
import random
import struct
from pathlib import Path
from typing import Any

MAGIC = b"JNNW"
REC_SIZE = 38
EXPECTED_STRATA = tuple(f"{n}v{n + 2}" for n in range(1, 19))


def read_jnnw(path: Path) -> list[bytearray]:
    raw = path.read_bytes()
    if len(raw) < 8 or raw[:4] != MAGIC:
        raise ValueError(f"{path}: invalid JNNW")
    count = struct.unpack_from("<I", raw, 4)[0]
    body = raw[8:]
    if len(body) != count * REC_SIZE:
        raise ValueError(f"{path}: size/count mismatch")
    return [bytearray(body[i * REC_SIZE:(i + 1) * REC_SIZE]) for i in range(count)]


def write_jnnw(path: Path, records: list[bytes | bytearray]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(MAGIC + struct.pack("<I", len(records)) + b"".join(records))


def load_policy(path: Path) -> tuple[dict[str, dict[str, float]], dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("decision") != "W0_ORACLE_WEIGHT_CALIBRATION_READY":
        raise ValueError("W0 decision is not ready")
    if payload.get("classification") != "STRATUM_ORACLE_WEIGHTING_SUPPORTED_DENSITY_ONLY_NOT_SUPPORTED":
        raise ValueError("W0 classification does not support the preregistered stratum screen")
    diagnostics = payload.get("diagnostics", {})
    if diagnostics.get("pool_stability_pass") is not True:
        raise ValueError("W0 pool stability did not pass")
    if diagnostics.get("density_only_hypothesis_pass") is not False:
        raise ValueError("W0 unexpectedly supports a density-only rule")
    rows = payload.get("strata", [])
    if not isinstance(rows, list) or len(rows) != 18:
        raise ValueError("W0 policy must contain exactly 18 strata")
    weights: dict[str, dict[str, float]] = {}
    for row in rows:
        stratum = str(row.get("stratum"))
        proposed = row.get("proposed_weights_absolute", {})
        if stratum in weights or stratum not in EXPECTED_STRATA:
            raise ValueError(f"invalid or duplicate W0 stratum {stratum!r}")
        expected = float(proposed.get("expected_result"))
        draw = float(proposed.get("draw"))
        upset = float(proposed.get("upset_result"))
        if expected != 1.0 or not (1.0 <= draw <= 2.0) or not (1.0 <= upset <= 4.0):
            raise ValueError(f"unsafe W0 weights for {stratum}: {proposed}")
        if abs(upset - (1.0 + 3.0 * (draw - 1.0))) > 2e-6:
            raise ValueError(f"W0 formula mismatch for {stratum}")
        weights[stratum] = {"expected_result": expected, "draw": draw, "upset_result": upset}
    if tuple(sorted(weights, key=lambda s: int(s.split("v", 1)[0]))) != EXPECTED_STRATA:
        raise ValueError("W0 strata are incomplete")
    return weights, payload


def classify(rec: bytes | bytearray) -> tuple[str | None, str]:
    wm, wk, bm, bk = struct.unpack_from("<QQQQ", rec, 0)
    stm = rec[32]
    wdl = struct.unpack_from("<b", rec, 37)[0]
    if stm not in (0, 1) or wdl not in (-1, 0, 1):
        raise ValueError("invalid STM/WDL record")
    nwm, nwk = wm.bit_count(), wk.bit_count()
    nbm, nbk = bm.bit_count(), bk.bit_count()
    if abs(nwm - nbm) != 2 or nwk != nbk:
        return None, "anchor_outside_exact_2men_equal_kings"
    low, high = sorted((nwm, nbm))
    stratum = f"{low}v{high}"
    if stratum not in EXPECTED_STRATA:
        raise ValueError(f"specialist record outside 1v3..18v20: {stratum}")
    up_colour = 0 if nwm > nbm else 1
    role = "up" if stm == up_colour else "down"
    outcome = {1: "win", 0: "draw", -1: "loss"}[wdl]
    return stratum, f"{role}_{outcome}"


def bucket_weight(bucket: str, policy: dict[str, float]) -> tuple[float, str]:
    if bucket.startswith("anchor_"):
        return 1.0, "anchor"
    if bucket in ("up_draw", "down_draw"):
        return policy["draw"], "draw"
    if bucket in ("up_win", "down_loss"):
        return policy["expected_result"], "expected_result"
    if bucket in ("up_loss", "down_win"):
        return policy["upset_result"], "upset_result"
    raise ValueError(f"unknown role bucket: {bucket}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--policy", required=True, type=Path)
    parser.add_argument("--holdout-count", required=True, type=int)
    parser.add_argument("--seed", required=True, type=int)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()
    try:
        records = read_jnnw(args.input)
        weights_by_stratum, policy_payload = load_policy(args.policy)
        if not 0 <= args.holdout_count < len(records):
            raise ValueError("invalid holdout count")
        train_n = len(records) - args.holdout_count
        holdout_bytes = b"".join(records[train_n:])
        sample_weights: list[float] = []
        labels: list[tuple[str, str, str]] = []
        source_counts: Counter[str] = Counter()
        source_by_stratum: dict[str, Counter[str]] = defaultdict(Counter)
        for rec in records[:train_n]:
            stratum, bucket = classify(rec)
            if stratum is None:
                weight, semantic = 1.0, "anchor"
                stratum_key = "outside_domain"
            else:
                weight, semantic = bucket_weight(bucket, weights_by_stratum[stratum])
                stratum_key = stratum
            sample_weights.append(weight)
            labels.append((stratum_key, bucket, semantic))
            source_counts[semantic] += 1
            source_by_stratum[stratum_key][semantic] += 1
        domain_records = sum(1 for stratum, _, _ in labels if stratum != "outside_domain")
        if domain_records == 0:
            raise ValueError("adaptive policy found no exact specialist-domain records")
        rng = random.Random(args.seed)
        sampled_indices = rng.choices(range(train_n), weights=sample_weights, k=train_n)
        out = [records[index] for index in sampled_indices]
        out.extend(records[train_n:])
        write_jnnw(args.output, out)
        if b"".join(out[train_n:]) != holdout_bytes:
            raise RuntimeError("holdout bytes changed")
        sampled_counts: Counter[str] = Counter()
        sampled_by_stratum: dict[str, Counter[str]] = defaultdict(Counter)
        for index in sampled_indices:
            stratum, _, semantic = labels[index]
            sampled_counts[semantic] += 1
            sampled_by_stratum[stratum][semantic] += 1
        policy_sha = hashlib.sha256(args.policy.read_bytes()).hexdigest()
        report = {
            "schema": 1,
            "protocol": "l3-imbalance2-w1-stratum-adaptive-resample",
            "policy": "w0-absolute-shrunk-stratum-weights",
            "teacher_calibrated_specialist_only": True,
            "forbidden_for_l3_pure": True,
            "records_total": len(records),
            "training_records": train_n,
            "holdout_records_untouched": args.holdout_count,
            "holdout_sha256": hashlib.sha256(holdout_bytes).hexdigest(),
            "domain_records": domain_records,
            "outside_domain_anchor_records": train_n - domain_records,
            "source_semantic_counts": dict(sorted(source_counts.items())),
            "resampled_semantic_counts": dict(sorted(sampled_counts.items())),
            "source_by_stratum": {k: dict(sorted(v.items())) for k, v in sorted(source_by_stratum.items())},
            "resampled_by_stratum": {k: dict(sorted(v.items())) for k, v in sorted(sampled_by_stratum.items())},
            "weights_by_stratum": weights_by_stratum,
            "policy_sha256": policy_sha,
            "policy_decision": policy_payload["decision"],
            "policy_classification": policy_payload["classification"],
            "seed": args.seed,
            "wdl_labels_changed": False,
            "training_size_changed": False,
        }
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps({"records": len(records), "domain_records": domain_records, "policy_sha256": policy_sha}, sort_keys=True))
        return 0
    except (OSError, RuntimeError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
