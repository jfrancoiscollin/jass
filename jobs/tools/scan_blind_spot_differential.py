#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Compare the Scan-judged EXACT/8cf and Gen2/32cf blind-spot atlases.

The readout is deliberately descriptive.  It verifies that the two runs used
the same engine, Scan runtime, extras, depths, time budget, shard count and seed
schedule before reporting EXACT minus Gen2.  It can therefore compare the two
geometry/model profiles.  It cannot identify a linear-vs-nonlinear class effect
because both arms are linear, and it cannot attribute anything to features
because the 120 extras are held constant.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any


ATLAS_SCHEMA = "l3_scan_blind_spot_atlas"
PROTOCOL_SCHEMA = "l3_scan_blind_spot_atlas_protocol"
BUCKET_AXES = ("phase", "kings", "material", "tactical")
BUCKET_SEPARATOR = "|"
EXACT_MODEL_SHA256 = "d84a7fc7c3127d135d3cc150406055b9506daaa881af2959cd3721f6be66eb0a"
GEN2_GZIP_SHA256 = "01cc3ea59e9cc3ced1910d4d9054f88f92c1c4d9d220d5f28b0ebaaad33681a0"
SCAN_BINARY_SHA256 = "a634cbb44c9528eab277cdf6cdf8d29d506318ce5fba3f9bc69c2025b5941864"
SCAN_EVAL_SHA256 = "0e7161c38af605f5e367f3f8fe17525d1c40db722714c68921971b386e58abba"
EXPECTED_CMAKE_FLAGS = [
    "JASS_ENDGAME_FEATURES=ON",
    "JASS_KING_MOBILITY=ON",
    "JASS_SCAN_PARITY=ON",
    "JASS_TEMPO_STAGE=ON",
]
EXPECTED_COLLECTION = {
    "budget_s_per_shard": 1500,
    "play_depth": 8,
    "judge_depth": 10,
    "max_plies": 160,
    "games_cap": 100000,
    "min_positions": 200,
    "shards": 16,
    "seed_policy": "one_based_shard_index",
    "seeds": list(range(1, 17)),
}
COLLECTION_KEYS = (
    "budget_s_per_shard",
    "play_depth",
    "judge_depth",
    "max_plies",
    "games_cap",
    "min_positions",
    "shards",
    "seed_policy",
    "seeds",
)


class DifferentialError(ValueError):
    pass


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise DifferentialError(f"JSON object required: {path}")
    return value


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise DifferentialError(message)


def _rows(atlas: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for key in ("buckets_ranked", "buckets_below_floor"):
        value = atlas.get(key)
        _require(isinstance(value, list), f"atlas field {key!r} must be a list")
        for row in value:
            _require(isinstance(row, dict), f"invalid row in {key}")
            bucket = row.get("bucket")
            _require(isinstance(bucket, str) and bucket, "bucket name missing")
            _require(bucket not in rows, f"duplicate bucket: {bucket}")
            rows[bucket] = row
    return rows


def _conversion_rows(atlas: dict[str, Any]) -> dict[str, dict[str, Any]]:
    value = atlas.get("conversion_family")
    _require(isinstance(value, list),
             "atlas field 'conversion_family' must be a list")
    rows: dict[str, dict[str, Any]] = {}
    for row in value:
        _require(isinstance(row, dict), "invalid conversion row")
        bucket = row.get("bucket")
        _require(isinstance(bucket, str) and bucket,
                 "conversion bucket name missing")
        _require(bucket not in rows, f"duplicate conversion bucket: {bucket}")
        rows[bucket] = row
    return rows


def _validate_atlas(atlas: dict[str, Any], protocol: dict[str, Any],
                    variant: str) -> dict[str, dict[str, Any]]:
    _require(atlas.get("schema") == ATLAS_SCHEMA,
             f"{variant}: unexpected atlas schema")
    _require(int(atlas.get("version", 0)) >= 2,
             f"{variant}: atlas version < 2")
    _require(int(atlas.get("positions_seen", 0)) > 0,
             f"{variant}: zero positions")
    _require(int(atlas.get("disagreements_judged", 0)) > 0,
             f"{variant}: zero judged disagreements")
    embedded = atlas.get("run_protocol")
    _require(embedded == protocol,
             f"{variant}: embedded protocol differs from protocol.json")
    return _rows(atlas)


def _validate_protocol(protocol: dict[str, Any], variant: str) -> None:
    _require(protocol.get("schema") == PROTOCOL_SCHEMA,
             f"{variant}: unexpected protocol schema")
    _require(protocol.get("version") == 1,
             f"{variant}: unexpected protocol version")
    _require(protocol.get("variant") == variant,
             f"{variant}: protocol variant mismatch")
    model = protocol.get("model")
    _require(isinstance(model, dict), f"{variant}: model block missing")
    want_patterns = 8 if variant == "exact" else 32
    _require(model.get("label") == variant.upper(),
             f"{variant}: model label mismatch")
    _require(int(model.get("num_patterns", 0)) == want_patterns,
             f"{variant}: expected {want_patterns} patterns")
    _require(int(model.get("n_pat", 0)) == 531441 * want_patterns,
             f"{variant}: n_pat mismatch")
    _require(int(model.get("n_ext", 0)) == 120,
             f"{variant}: n_ext must be 120")
    _require(len(str(model.get("sha256", ""))) == 64,
             f"{variant}: model sha256 missing")
    _require(len(str(model.get("gzip_sha256", ""))) == 64,
             f"{variant}: model gzip sha256 missing")
    if variant == "exact":
        _require(model.get("sha256") == EXACT_MODEL_SHA256,
                 "exact: champion model hash mismatch")
        _require(model.get("source_job") ==
                 "cpx62-1117-l3-exact-fold-refit-v1",
                 "exact: champion source job mismatch")
    else:
        _require(model.get("gzip_sha256") == GEN2_GZIP_SHA256,
                 "gen2: frozen model gzip hash mismatch")
        _require(model.get("source_job") == "frozen-t1bis-gen2",
                 "gen2: frozen source identity mismatch")
    engine = protocol.get("engine")
    scan = protocol.get("scan")
    collection = protocol.get("collection")
    _require(isinstance(engine, dict), f"{variant}: engine block missing")
    _require(isinstance(scan, dict), f"{variant}: scan block missing")
    _require(isinstance(collection, dict), f"{variant}: collection block missing")
    _require(len(str(engine.get("code_sha", ""))) == 40,
             f"{variant}: engine code SHA missing")
    _require(engine.get("cmake_flags") == EXPECTED_CMAKE_FLAGS,
             f"{variant}: engine feature flags drift")
    _require(engine.get("egdb") is False, f"{variant}: EGDB must be off")
    _require(scan.get("binary_sha256") == SCAN_BINARY_SHA256,
             f"{variant}: Scan binary hash mismatch")
    _require(scan.get("eval_sha256") == SCAN_EVAL_SHA256,
             f"{variant}: Scan eval hash mismatch")
    _require(scan.get("bb_size") == 0 and scan.get("book") is False,
             f"{variant}: Scan must use bb-size=0 and no book")
    for key, expected in EXPECTED_COLLECTION.items():
        _require(collection.get(key) == expected,
                 f"{variant}: collection setting {key} drift")
    shards = int(collection.get("shards", 0))
    _require(collection.get("seeds") == list(range(1, shards + 1)),
             f"{variant}: shard seeds are not 1..N")
    _require(protocol.get("diagnostic_only") is True,
             f"{variant}: diagnostic-only guard missing")
    _require(protocol.get("promotion_authorized") is False,
             f"{variant}: promotion guard missing")
    _require(protocol.get("automatic_next_job") is None,
             f"{variant}: automatic continuation must be null")


def _assert_same_protocol(exact: dict[str, Any], gen2: dict[str, Any]) -> None:
    _require(exact.get("engine") == gen2.get("engine"),
             "engine/code/build flags differ between EXACT and Gen2")
    _require(exact.get("scan") == gen2.get("scan"),
             "Scan runtime or options differ between EXACT and Gen2")
    ec, gc = exact["collection"], gen2["collection"]
    for key in COLLECTION_KEYS:
        _require(ec.get(key) == gc.get(key),
                 f"collection protocol differs for {key}")
    _require(exact["model"]["n_ext"] == gen2["model"]["n_ext"] == 120,
             "n_ext is not held at 120")
    _require(exact["model"]["n_pat"] != gen2["model"]["n_pat"],
             "n_pat did not change between geometry arms")


def _ratio(num: float, den: float) -> float | None:
    return round(num / den, 6) if den else None


def _global(atlas: dict[str, Any], rows: dict[str, dict[str, Any]]) -> dict[str, Any]:
    positions = int(atlas["positions_seen"])
    agreed = int(atlas.get("moves_agreed", 0))
    judged = int(atlas["disagreements_judged"])
    ordinary = sum(int(row.get("ordinary_positions", 0)) for row in rows.values())
    cost = sum(float(row.get("cost_sum", 0.0)) for row in rows.values())
    conv_positions = int(atlas.get("conversion_positions", 0))
    conv_misses = int(atlas.get("conversion_misses", 0))
    clipped = int(atlas.get("costs_clipped", 0))
    return {
        "positions": positions,
        "moves_agreed": agreed,
        "agreement_rate": _ratio(agreed, positions),
        "disagreement_rate": _ratio(positions - agreed, positions),
        "judged_disagreements": judged,
        "ordinary_positions": ordinary,
        "ordinary_cost_sum": round(cost, 6),
        "ordinary_cost_per_position": _ratio(cost, ordinary),
        "costs_clipped": clipped,
        "clipped_share_of_judged": _ratio(clipped, judged),
        "conversion_positions": conv_positions,
        "conversion_misses": conv_misses,
        "conversion_miss_rate": _ratio(conv_misses, conv_positions),
    }


def _delta(exact: float | int | None, gen2: float | int | None) -> float | None:
    if exact is None or gen2 is None:
        return None
    return round(float(exact) - float(gen2), 6)


def _bucket_delta(bucket: str, exact: dict[str, Any], gen2: dict[str, Any],
                  exact_total_cost: float, gen2_total_cost: float) -> dict[str, Any]:
    e_cost = float(exact.get("cost_sum", 0.0))
    g_cost = float(gen2.get("cost_sum", 0.0))
    e_cpp = _ratio(e_cost, int(exact.get("ordinary_positions", 0)))
    g_cpp = _ratio(g_cost, int(gen2.get("ordinary_positions", 0)))
    e_disagreement = _ratio(int(exact.get("disagreements", 0)),
                            int(exact.get("positions", 0)))
    g_disagreement = _ratio(int(gen2.get("disagreements", 0)),
                            int(gen2.get("positions", 0)))
    return {
        "bucket": bucket,
        "exact_positions": int(exact.get("ordinary_positions", 0)),
        "gen2_positions": int(gen2.get("ordinary_positions", 0)),
        "exact_cost_per_position": e_cpp,
        "gen2_cost_per_position": g_cpp,
        "delta_cost_per_position_exact_minus_gen2": _delta(e_cpp, g_cpp),
        "exact_disagreement_rate": e_disagreement,
        "gen2_disagreement_rate": g_disagreement,
        "delta_disagreement_rate_exact_minus_gen2": _delta(
            e_disagreement, g_disagreement),
        "exact_cost_mass_share": _ratio(e_cost, exact_total_cost),
        "gen2_cost_mass_share": _ratio(g_cost, gen2_total_cost),
        "delta_cost_mass_share_exact_minus_gen2": _delta(
            _ratio(e_cost, exact_total_cost), _ratio(g_cost, gen2_total_cost)),
    }


def _conversion_bucket_delta(bucket: str, exact: dict[str, Any],
                             gen2: dict[str, Any]) -> dict[str, Any]:
    ep, gp = int(exact.get("positions", 0)), int(gen2.get("positions", 0))
    ed, gd = int(exact.get("disagreements", 0)), int(gen2.get("disagreements", 0))
    em, gm = int(exact.get("misses", 0)), int(gen2.get("misses", 0))
    epos, gpos = _ratio(em, ep), _ratio(gm, gp)
    edis, gdis = _ratio(em, ed), _ratio(gm, gd)
    return {
        "bucket": bucket,
        "exact_positions": ep,
        "gen2_positions": gp,
        "exact_misses": em,
        "gen2_misses": gm,
        "exact_miss_rate_over_positions": epos,
        "gen2_miss_rate_over_positions": gpos,
        "delta_miss_rate_over_positions_exact_minus_gen2": _delta(epos, gpos),
        "exact_miss_rate_over_disagreements": edis,
        "gen2_miss_rate_over_disagreements": gdis,
        "delta_miss_rate_over_disagreements_exact_minus_gen2": _delta(edis, gdis),
    }


def _axis_rows(rows: dict[str, dict[str, Any]], total_cost: float) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, dict[str, dict[str, float]]] = {
        axis: defaultdict(lambda: {"positions": 0.0, "cost": 0.0})
        for axis in BUCKET_AXES
    }
    for bucket, row in rows.items():
        parts = [part.strip() for part in bucket.split(BUCKET_SEPARATOR)]
        if len(parts) != len(BUCKET_AXES):
            raise DifferentialError(f"unexpected bucket shape: {bucket}")
        for axis, value in zip(BUCKET_AXES, parts):
            grouped[axis][value]["positions"] += int(row.get("ordinary_positions", 0))
            grouped[axis][value]["cost"] += float(row.get("cost_sum", 0.0))
    result: dict[str, list[dict[str, Any]]] = {}
    for axis, values in grouped.items():
        result[axis] = [
            {
                "value": value,
                "positions": int(data["positions"]),
                "cost_sum": round(data["cost"], 6),
                "cost_per_position": _ratio(data["cost"], data["positions"]),
                "cost_mass_share": _ratio(data["cost"], total_cost),
            }
            for value, data in sorted(values.items())
        ]
    return result


def _axis_differential(exact: dict[str, list[dict[str, Any]]],
                       gen2: dict[str, list[dict[str, Any]]]) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    for axis in BUCKET_AXES:
        e = {row["value"]: row for row in exact[axis]}
        g = {row["value"]: row for row in gen2[axis]}
        rows = []
        for value in sorted(set(e) & set(g)):
            er, gr = e[value], g[value]
            rows.append({
                "value": value,
                "exact_positions": er["positions"],
                "gen2_positions": gr["positions"],
                "exact_cost_per_position": er["cost_per_position"],
                "gen2_cost_per_position": gr["cost_per_position"],
                "delta_cost_per_position_exact_minus_gen2": _delta(
                    er["cost_per_position"], gr["cost_per_position"]),
                "exact_cost_mass_share": er["cost_mass_share"],
                "gen2_cost_mass_share": gr["cost_mass_share"],
                "delta_cost_mass_share_exact_minus_gen2": _delta(
                    er["cost_mass_share"], gr["cost_mass_share"]),
            })
        rows.sort(key=lambda row: abs(row["delta_cost_mass_share_exact_minus_gen2"] or 0),
                  reverse=True)
        out[axis] = rows
    return out


def compare(exact_atlas: dict[str, Any], exact_protocol: dict[str, Any],
            gen2_atlas: dict[str, Any], gen2_protocol: dict[str, Any]) -> dict[str, Any]:
    _validate_protocol(exact_protocol, "exact")
    _validate_protocol(gen2_protocol, "gen2")
    _assert_same_protocol(exact_protocol, gen2_protocol)
    erows = _validate_atlas(exact_atlas, exact_protocol, "exact")
    grows = _validate_atlas(gen2_atlas, gen2_protocol, "gen2")
    econv = _conversion_rows(exact_atlas)
    gconv = _conversion_rows(gen2_atlas)

    eg = _global(exact_atlas, erows)
    gg = _global(gen2_atlas, grows)
    floor = int(exact_protocol["collection"]["min_positions"])
    common = sorted(
        bucket for bucket in set(erows) & set(grows)
        if int(erows[bucket].get("ordinary_positions", 0)) >= floor
        and int(grows[bucket].get("ordinary_positions", 0)) >= floor
    )
    _require(common, "no bucket reaches the ranking floor in both atlases")
    bucket_rows = [
        _bucket_delta(bucket, erows[bucket], grows[bucket],
                      eg["ordinary_cost_sum"], gg["ordinary_cost_sum"])
        for bucket in common
    ]
    bucket_rows.sort(
        key=lambda row: abs(row["delta_cost_per_position_exact_minus_gen2"] or 0),
        reverse=True,
    )
    eaxes = _axis_rows(erows, eg["ordinary_cost_sum"])
    gaxes = _axis_rows(grows, gg["ordinary_cost_sum"])
    common_conversion = sorted(
        bucket for bucket in set(econv) & set(gconv)
        if int(econv[bucket].get("positions", 0)) >= floor
        and int(gconv[bucket].get("positions", 0)) >= floor
    )
    conversion_rows = [
        _conversion_bucket_delta(bucket, econv[bucket], gconv[bucket])
        for bucket in common_conversion
    ]
    conversion_rows.sort(
        key=lambda row: abs(
            row["delta_miss_rate_over_positions_exact_minus_gen2"] or 0),
        reverse=True,
    )

    return {
        "schema": "l3_scan_blind_spot_differential",
        "version": 1,
        "verdict": "L3_SCAN_BLIND_SPOT_DIFFERENTIAL_MEASURED",
        "arms": {
            "exact": {"protocol": exact_protocol, "global": eg},
            "gen2": {"protocol": gen2_protocol, "global": gg},
        },
        "global_differential_exact_minus_gen2": {
            key: _delta(eg.get(key), gg.get(key))
            for key in (
                "agreement_rate",
                "disagreement_rate",
                "ordinary_cost_per_position",
                "clipped_share_of_judged",
                "conversion_miss_rate",
            )
        },
        "common_ranked_bucket_count": len(common),
        "bucket_differentials": bucket_rows,
        "axis_differentials": _axis_differential(eaxes, gaxes),
        "axis_values_only_one_arm": {
            axis: {
                "exact": sorted(
                    {row["value"] for row in eaxes[axis]} -
                    {row["value"] for row in gaxes[axis]}
                ),
                "gen2": sorted(
                    {row["value"] for row in gaxes[axis]} -
                    {row["value"] for row in eaxes[axis]}
                ),
            }
            for axis in BUCKET_AXES
        },
        "common_ranked_conversion_bucket_count": len(common_conversion),
        "conversion_bucket_differentials": conversion_rows,
        "interpretation": {
            "geometry_profile_comparison_authorized": True,
            "n_pat_changed": [531441 * 8, 531441 * 32],
            "n_ext_held_constant": 120,
            "features_held_constant": True,
            "feature_attribution_authorized": False,
            "both_arms_linear": True,
            "linear_vs_nonlinear_class_attribution_authorized": False,
            "independent_model_trajectories": True,
            "causal_weight_ablation": False,
            "statistical_significance_claimed": False,
            "note": (
                "Differential descriptif normalisé par position. Les trajectoires "
                "et les poids diffèrent avec les modèles ; aucune p-value iid ni "
                "attribution aux features ou à une classe non-linéaire n'est faite."
            ),
        },
        "diagnostic_only": True,
        "promotion_authorized": False,
        "automatic_next_job": None,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exact-atlas", required=True, type=Path)
    parser.add_argument("--exact-protocol", required=True, type=Path)
    parser.add_argument("--gen2-atlas", required=True, type=Path)
    parser.add_argument("--gen2-protocol", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        result = compare(
            _load(args.exact_atlas), _load(args.exact_protocol),
            _load(args.gen2_atlas), _load(args.gen2_protocol),
        )
    except (DifferentialError, KeyError, TypeError, ValueError) as exc:
        print(f"scan_blind_spot_differential: ABORT: {exc}")
        return 2
    args.out.write_text(
        json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "verdict": result["verdict"],
        "global_differential_exact_minus_gen2":
            result["global_differential_exact_minus_gen2"],
        "common_ranked_bucket_count": result["common_ranked_bucket_count"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
