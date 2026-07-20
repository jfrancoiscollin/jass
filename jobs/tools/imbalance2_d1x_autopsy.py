#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Post-mortem for the failed D1-RC4 representation screen.

The tool consumes only immutable D1 artefacts plus feature dumps produced from the
reviewed RC4 binary.  It does not train, play games, or authorize a follow-up.  Its
purpose is to distinguish a rarely-active/ignored feature channel from an active
but non-causal representation change, and to localise the C64/D64 and generalist
regressions before a separate search-only pilot is designed.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import gzip
import json
import math
from pathlib import Path
import random
import struct
import tarfile
from typing import Any

import numpy as np

FEATURE_NAMES = (
    "safe_mobility_delta",
    "defender_confinement",
    "promotion_race_margin",
    "trade_pressure",
)
COST = {"win": 0.0, "draw": 1.0, "loss": 2.0}
JNNW_DTYPE = np.dtype([
    ("wm", "<u8"), ("wk", "<u8"), ("bm", "<u8"), ("bk", "<u8"),
    ("stm", "u1"), ("score", "<i4"), ("wdl", "i1"),
])


def _read_bytes(path: Path) -> bytes:
    return gzip.decompress(path.read_bytes()) if path.suffix == ".gz" else path.read_bytes()


def _finite(value: float) -> float | None:
    return float(value) if math.isfinite(float(value)) else None


def parse_pjtw(path: Path) -> dict[str, Any]:
    raw = _read_bytes(path)
    if len(raw) < 20 or raw[:4] != b"PJTW":
        raise ValueError(f"{path}: invalid PJTW")
    version, scale, n_pat, n_ext = struct.unpack_from("<IIII", raw, 4)
    weights = np.frombuffer(raw, dtype="<i4", offset=20)
    expected = 2 * (n_pat + n_ext)
    if len(weights) != expected:
        raise ValueError(f"{path}: {len(weights)} weights, expected {expected}")
    p_mg = weights[:n_pat]
    p_eg = weights[n_pat:2 * n_pat]
    e_mg = weights[2 * n_pat:2 * n_pat + n_ext]
    e_eg = weights[2 * n_pat + n_ext:]
    return {
        "path": str(path), "version": int(version), "scale": int(scale),
        "n_pat": int(n_pat), "n_ext": int(n_ext), "raw_bytes": len(raw),
        "pattern_mg": p_mg, "pattern_eg": p_eg,
        "extra_mg": e_mg, "extra_eg": e_eg,
    }


def vector_delta(a: np.ndarray, b: np.ndarray) -> dict[str, Any]:
    if a.shape != b.shape:
        raise ValueError(f"vector shape mismatch {a.shape} != {b.shape}")
    d = b.astype(np.float64) - a.astype(np.float64)
    denom = float(np.linalg.norm(a.astype(np.float64)) * np.linalg.norm(b.astype(np.float64)))
    cosine = float(np.dot(a.astype(np.float64), b.astype(np.float64)) / denom) if denom else None
    return {
        "n": int(d.size),
        "changed": int(np.count_nonzero(d)),
        "changed_fraction": float(np.count_nonzero(d) / d.size) if d.size else 0.0,
        "mean_absolute_delta": float(np.mean(np.abs(d))) if d.size else 0.0,
        "rms_delta": float(np.sqrt(np.mean(d * d))) if d.size else 0.0,
        "max_absolute_delta": float(np.max(np.abs(d))) if d.size else 0.0,
        "cosine_similarity": cosine,
    }


def compare_models(control_path: Path, rc4_path: Path) -> dict[str, Any]:
    control = parse_pjtw(control_path)
    rc4 = parse_pjtw(rc4_path)
    if control["n_pat"] != rc4["n_pat"] or control["n_ext"] != 120 or rc4["n_ext"] != 124:
        raise ValueError("unexpected control/RC4 model geometry")
    scale = rc4["scale"]
    rc_weights = []
    for i, name in enumerate(FEATURE_NAMES):
        mg = int(rc4["extra_mg"][120 + i])
        eg = int(rc4["extra_eg"][120 + i])
        rc_weights.append({
            "feature": name, "mg_raw": mg, "eg_raw": eg,
            "mg_scaled": mg / scale, "eg_scaled": eg / scale,
        })
    return {
        "control": {k: control[k] for k in ("version", "scale", "n_pat", "n_ext", "raw_bytes")},
        "rc4": {k: rc4[k] for k in ("version", "scale", "n_pat", "n_ext", "raw_bytes")},
        "common_weight_drift": {
            "pattern_mg": vector_delta(control["pattern_mg"], rc4["pattern_mg"]),
            "pattern_eg": vector_delta(control["pattern_eg"], rc4["pattern_eg"]),
            "extra_mg_first_120": vector_delta(control["extra_mg"], rc4["extra_mg"][:120]),
            "extra_eg_first_120": vector_delta(control["extra_eg"], rc4["extra_eg"][:120]),
        },
        "rc4_feature_weights": rc_weights,
        "max_abs_rc4_weight_raw": max(abs(item[key]) for item in rc_weights for key in ("mg_raw", "eg_raw")),
    }


def open_feat(path: Path) -> tuple[np.memmap, int, int]:
    with path.open("rb") as handle:
        head = handle.read(12)
    if head[:4] != b"FEAT":
        raise ValueError(f"{path}: invalid FEAT")
    count, width = struct.unpack_from("<II", head, 4)
    need = 12 + count * width * 4
    if path.stat().st_size != need:
        raise ValueError(f"{path}: FEAT size mismatch")
    mm = np.memmap(path, dtype="<f4", mode="r", offset=12, shape=(count, width))
    return mm, int(count), int(width)


def role_domain_rate(data_path: Path) -> dict[str, Any]:
    raw = _read_bytes(data_path)
    if raw[:4] != b"JNNW":
        raise ValueError(f"{data_path}: invalid JNNW")
    count = struct.unpack_from("<I", raw, 4)[0]
    rows = np.frombuffer(raw, dtype=JNNW_DTYPE, offset=8, count=count)
    if len(rows) != count:
        raise ValueError("JNNW row count mismatch")
    wm = np.fromiter((int(x).bit_count() for x in rows["wm"]), dtype=np.int16, count=count)
    wk = np.fromiter((int(x).bit_count() for x in rows["wk"]), dtype=np.int16, count=count)
    bm = np.fromiter((int(x).bit_count() for x in rows["bm"]), dtype=np.int16, count=count)
    bk = np.fromiter((int(x).bit_count() for x in rows["bk"]), dtype=np.int16, count=count)
    mask = (np.abs(bm - wm) == 2) & (bk == wk)
    return {"records": int(count), "role_domain_records": int(mask.sum()), "role_domain_rate": float(mask.mean())}


def inspect_features(feat_path: Path, data_path: Path, expected_width: int = 124) -> dict[str, Any]:
    feat, count, width = open_feat(feat_path)
    if width != expected_width:
        raise ValueError(f"{feat_path}: width {width}, expected {expected_width}")
    domain = role_domain_rate(data_path)
    if domain["records"] != count:
        raise ValueError("FEAT/JNNW count mismatch")
    x = np.asarray(feat[:, -4:], dtype=np.float64)
    any_nonzero = np.any(x != 0.0, axis=1)
    items = []
    for i, name in enumerate(FEATURE_NAMES):
        col = x[:, i]
        items.append({
            "feature": name,
            "nonzero_records": int(np.count_nonzero(col)),
            "nonzero_rate": float(np.count_nonzero(col) / count),
            "mean": float(np.mean(col)), "std": float(np.std(col)),
            "mean_absolute": float(np.mean(np.abs(col))),
            "min": float(np.min(col)), "max": float(np.max(col)),
            "q05": float(np.quantile(col, 0.05)),
            "q50": float(np.quantile(col, 0.50)),
            "q95": float(np.quantile(col, 0.95)),
        })
    corr = np.corrcoef(x, rowvar=False)
    corr_clean = [[_finite(v) for v in row] for row in np.atleast_2d(corr)]
    return {
        **domain, "feature_width": width,
        "any_rc4_nonzero_records": int(any_nonzero.sum()),
        "any_rc4_nonzero_rate": float(any_nonzero.mean()),
        "features": items, "correlation_matrix": corr_clean,
    }


def load_tar_json(path: Path) -> list[tuple[str, dict[str, Any]]]:
    out = []
    with tarfile.open(path, "r:gz") as archive:
        for member in archive.getmembers():
            if not member.isfile() or not member.name.endswith(".json"):
                continue
            handle = archive.extractfile(member)
            if handle is None:
                continue
            out.append((member.name, json.loads(handle.read().decode("utf-8"))))
    return out


def conversion_transitions(raw_tar: Path) -> dict[str, Any]:
    arms: dict[str, dict[tuple[str, int], dict[str, Any]]] = {"control": {}, "rc4": {}}
    for name, payload in load_tar_json(raw_tar):
        parts = set(Path(name).parts)
        arm = "control" if "control" in parts else "rc4" if "rc4" in parts else None
        if arm is None:
            continue
        pool = Path(str(payload.get("pool", ""))).name
        for row in payload.get("rows", []):
            if "error" in row:
                continue
            arms[arm][(pool, int(row["index"]))] = row
    keys = sorted(set(arms["control"]) & set(arms["rc4"]))
    if len(keys) < 2300:
        raise ValueError(f"incomplete paired raw reports: {len(keys)}")
    transitions = Counter()
    strata = defaultdict(list)
    pools = defaultdict(list)
    changed = []
    for key in keys:
        c = arms["control"][key]
        r = arms["rc4"][key]
        co, ro = str(c["outcome"]), str(r["outcome"])
        delta = COST[ro] - COST[co]
        transitions[f"{co}->{ro}"] += 1
        stratum = str(c["stratum"])
        strata[stratum].append(delta)
        pools[key[0]].append(delta)
        if delta:
            changed.append({"pool": key[0], "index": key[1], "stratum": stratum,
                            "control": co, "rc4": ro, "delta_cost": delta})
    by_stratum = [
        {"stratum": s, "n": len(v), "mean_delta": float(np.mean(v)),
         "worsened": int(sum(x > 0 for x in v)), "improved": int(sum(x < 0 for x in v))}
        for s, v in strata.items()
    ]
    by_stratum.sort(key=lambda item: item["mean_delta"], reverse=True)
    return {
        "paired_positions": len(keys), "transition_counts": dict(sorted(transitions.items())),
        "pools": {p: {"n": len(v), "mean_delta": float(np.mean(v))} for p, v in sorted(pools.items())},
        "strata_ranked_worst_first": by_stratum,
        "changed_positions": len(changed),
        "worst_changed_examples": sorted(changed, key=lambda item: item["delta_cost"], reverse=True)[:24],
        "best_changed_examples": sorted(changed, key=lambda item: item["delta_cost"])[:24],
    }


def sentinel_details(path: Path) -> dict[str, Any]:
    rows: dict[tuple[str, str], dict[str, Any]] = {}
    for _, payload in load_tar_json(path):
        for row in payload.get("rows", []):
            if "error" not in row:
                rows[(str(row["sentinel_id"]), str(row["engine"]))] = row
    ids = sorted({key[0] for key in rows})
    if len(ids) != 30:
        raise ValueError(f"expected 30 sentinels, found {len(ids)}")
    details = []
    for sid in ids:
        c = dict(rows[(sid, "control")]["analysis"])
        r = dict(rows[(sid, "rc4")]["analysis"])
        score_c = c.get("score")
        score_r = r.get("score")
        details.append({
            "sentinel_id": sid, "control_move": c.get("best_move"), "rc4_move": r.get("best_move"),
            "move_changed": c.get("best_move") != r.get("best_move"),
            "control_score": score_c, "rc4_score": score_r,
            "score_delta": (float(score_r) - float(score_c)) if score_c is not None and score_r is not None else None,
            "control_nodes": c.get("nodes"), "rc4_nodes": r.get("nodes"),
        })
    return {
        "sentinels": len(details), "move_changed": sum(bool(x["move_changed"]) for x in details),
        "details": details,
    }


def load_fens(path: Path) -> list[str]:
    fens = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if line and line[0] in "WB" and ":W" in line and ":B" in line:
            fens.append(line)
    return fens


def root_material(fen: str) -> dict[str, Any]:
    counts = {"wm": 0, "wk": 0, "bm": 0, "bk": 0}
    for chunk in fen.split(":")[1:]:
        colour = chunk[:1]
        for token in chunk[1:].split(","):
            token = token.strip()
            if not token:
                continue
            king = token.startswith("K")
            token = token[1:] if king else token
            if "-" in token:
                a, b = map(int, token.split("-", 1)); n = b - a + 1
            else:
                n = 1
            counts[("w" if colour == "W" else "b") + ("k" if king else "m")] += n
    role = abs(counts["bm"] - counts["wm"]) == 2 and counts["bk"] == counts["wk"]
    return {**counts, "exact_two_man_equal_kings": role}


def generalist_autopsy(payload: dict[str, Any], openings: Path) -> dict[str, Any]:
    pairs = int(payload["pairs"]); seed = int(payload["seed"])
    fens = load_fens(openings)
    chosen = random.Random(seed).sample(fens, pairs)
    grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in payload.get("game_rows", []):
        grouped[int(row["pair"])].append(row)
    details = []
    for pair in range(pairs):
        rows = grouped[pair]
        score = sum(float(row["rc4_points"]) for row in rows) / len(rows)
        details.append({
            "pair": pair, "rc4_pair_score": score, "fen": chosen[pair],
            "root_material": root_material(chosen[pair]),
            "games": rows,
        })
    details.sort(key=lambda item: (item["rc4_pair_score"], item["pair"]))
    return {
        "pairs": pairs, "score_rate": float(payload["rc4_score_rate"]),
        "ci95": payload["paired_bootstrap_95"], "pass": bool(payload["pass"]),
        "pair_score_histogram": dict(sorted(Counter(str(x["rc4_pair_score"]) for x in details).items())),
        "root_role_domain_pairs": sum(bool(x["root_material"]["exact_two_man_equal_kings"]) for x in details),
        "worst_pairs": details[:16],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--decision", required=True)
    ap.add_argument("--generalist", required=True)
    ap.add_argument("--control-model", required=True)
    ap.add_argument("--rc4-model", required=True)
    ap.add_argument("--raw-reports", required=True)
    ap.add_argument("--sentinel-replays", required=True)
    ap.add_argument("--train-feat", required=True)
    ap.add_argument("--train-data", required=True)
    ap.add_argument("--pool-c-feat", required=True)
    ap.add_argument("--pool-c-data", required=True)
    ap.add_argument("--pool-d-feat", required=True)
    ap.add_argument("--pool-d-data", required=True)
    ap.add_argument("--openings", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    decision = json.loads(Path(args.decision).read_text(encoding="utf-8"))
    generalist = json.loads(Path(args.generalist).read_text(encoding="utf-8"))
    if decision.get("decision") != "D1_RC4_NO_GO":
        ap.error("D1-X only accepts the reviewed D1_RC4_NO_GO result")

    models = compare_models(Path(args.control_model), Path(args.rc4_model))
    activity = {
        "training_source": inspect_features(Path(args.train_feat), Path(args.train_data)),
        "C64": inspect_features(Path(args.pool_c_feat), Path(args.pool_c_data)),
        "D64": inspect_features(Path(args.pool_d_feat), Path(args.pool_d_data)),
    }
    transitions = conversion_transitions(Path(args.raw_reports))
    sentinels = sentinel_details(Path(args.sentinel_replays))
    general = generalist_autopsy(generalist, Path(args.openings))

    rate = float(activity["training_source"]["any_rc4_nonzero_rate"])
    max_weight = int(models["max_abs_rc4_weight_raw"])
    corrected = int(decision["sentinel_gate"]["corrected_representation_cases"])
    macro = float(decision["paired"]["macro_equal_stratum"]["rc4_minus_control_failure_cost"])
    if rate < 0.005:
        classification = "RC4_CHANNEL_RARELY_ACTIVE_IN_TRAINING"
    elif max_weight == 0:
        classification = "RC4_FEATURES_IGNORED_BY_FIT"
    elif corrected == 0 and abs(macro) < 0.01:
        classification = "RC4_ACTIVE_BUT_NONCAUSAL_FOR_CONVERSION"
    else:
        classification = "RC4_MIXED_FAILURE_REQUIRES_MANUAL_REVIEW"

    payload = {
        "schema": 1,
        "protocol": "l3-imbalance2-d1x-rc4-autopsy",
        "decision": "D1X_RC4_AUTOPSY_READY",
        "rc4_closure": "D1_RC4_NO_GO_CLOSED_DO_NOT_REPEAT",
        "classification": classification,
        "reviewed_d1_metrics": {
            "macro_delta": macro,
            "macro_ci95": decision["paired"]["macro_equal_stratum"]["stratified_bootstrap_95"],
            "nonworse_strata": decision["paired"]["macro_equal_stratum"]["nonworse_strata"],
            "sentinel_corrected": corrected,
            "new_divergences": decision["sentinel_gate"]["new_divergences_non_target"],
            "throughput_ratio": decision["sentinel_gate"]["throughput"]["rc4_over_control"],
            "generalist_score": generalist["rc4_score_rate"],
            "generalist_pass": generalist["pass"],
        },
        "model_analysis": models,
        "feature_activity": activity,
        "conversion_transition_analysis": transitions,
        "sentinel_analysis": sentinels,
        "generalist_analysis": general,
        "recommendation_for_human_review": "DESIGN_ONE_SEPARATE_SEARCH_ONLY_PILOT",
        "candidate_search_pilot_constraints": {
            "working_name": "S1_ROLE_STABILITY_EXTENSION",
            "evaluation_model": "immutable_D1_control_refit_or_reviewed_G4_no_refit",
            "representation_change": False,
            "training": False,
            "activation_domain": "current_exact_plus2_men_equal_kings_only",
            "mechanism": "single_selective_in_tree_extension_outside_quiescence",
            "must_compare_fixed_nodes_and_movetime": True,
            "fresh_holdout_pools": ["E64", "F64"],
            "reuse_D0_sentinels_for_mechanism_only": True,
            "generalist_and_throughput_vetoes": True,
            "note": "candidate only; D1-X does not authorize implementation or execution",
        },
        "search_pilot_authorized": False,
        "training_authorized": False,
        "promotion_authorized": False,
        "automatic_next_job": None,
    }
    Path(args.out).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(payload["decision"])
    print(f"classification={classification}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
