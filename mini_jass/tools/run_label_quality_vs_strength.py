#!/usr/bin/env python3
"""M20 — les etiquettes et la force vont-elles vraiment en sens oppose ?

M18 et M19 laissent le meme dessin sur quatre bras : plus les etiquettes WDL
sont exactes, plus le modele final est FAIBLE en arena. C'est le signal le plus
fort de la campagne labo, et il n'est pas teste -- quatre bras qui different par
des choses differentes, et des scores d'arena sans le moindre IC.

M20 en fait deux paires a UN SEUL FACTEUR, et mesure les DEUX criteres en
apparie avec IC. La revendication n'est etablie que si, DANS UNE MEME PAIRE,
l'ecart d'etiquettes et l'ecart de force sont de signes OPPOSES avec les deux IC
excluant zero : c'est l'OPPOSITION qui est le resultat, pas chacun des cotes.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import json
from pathlib import Path
import platform
import sys
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np  # noqa: E402
import yaml  # noqa: E402

from mini_jass_lab.game_graph import GameGraph  # noqa: E402
from mini_jass_lab.learning_gate import resolve_learning_gate_config  # noqa: E402
from mini_jass_lab.oracle import load_oracle  # noqa: E402
from mini_jass_lab.split import build_split  # noqa: E402

from m18_wdl_config import _digest, _mean, _paired_summary  # noqa: E402
from m18_wdl_execution import _run_arm_seed  # noqa: E402
from m18_wdl_mechanics import _development_tensors  # noqa: E402

SCHEMA = "mini_jass.label_quality_vs_strength.v1"
ARM_ORDER = ("gate_arena", "forced_advance", "depth32", "depth1")


def _label(row: dict[str, Any], rung: int) -> float:
    return float(row["by_rung"][str(rung)]["probe_start_wdl"]["exact_rate"])


def _arena(row: dict[str, Any]) -> float:
    return float(row["final_arena_vs_initial"]["score"])


def assert_paired_probe_schedules(
    arm_rows: dict[str, list[dict[str, Any]]], seeds: list[int]
) -> None:
    """Appariement ENTRE BRAS, a graine egale -- jamais uniformite entre graines.

    `probe_seed = seed_base + seed` : chaque graine tire son propre calendrier de
    departs PAR CONSTRUCTION. Exiger une signature unique sur toutes les lignes a
    tue `cpx62-1208` a la derniere assertion, apres 28 minutes de science.
    """
    for seed in seeds:
        per_seed = {
            row["probe_start_signature"]
            for rows in arm_rows.values()
            for row in rows
            if int(row["seed"]) == seed
        }
        if len(per_seed) != 1:
            raise ValueError(
                f"M20 fixed probe start schedule diverged across arms at seed={seed}"
            )


def assert_reference_arms_agree(
    arm_rows: dict[str, list[dict[str, Any]]], seeds: list[int], tolerance: float
) -> float:
    """`gate_arena` et `depth32` ont la MEME specification : ils doivent coincider.

    Ce n'est pas une redondance mais le controle de determinisme du harnais : deux
    bras identiques executes separement doivent rendre le meme modele. S'ils
    divergent, aucun contraste de la cellule n'est interpretable -- l'ecart
    mesure contiendrait du bruit d'execution et non le facteur.
    """
    worst = 0.0
    by_seed = {
        arm: {int(row["seed"]): row for row in rows} for arm, rows in arm_rows.items()
    }
    for seed in seeds:
        for endpoint in (lambda row: _label(row, 8), _arena):
            gap = abs(
                endpoint(by_seed["gate_arena"][seed])
                - endpoint(by_seed["depth32"][seed])
            )
            worst = max(worst, gap)
    if worst > tolerance:
        raise ValueError(
            "M20 reference arms gate_arena and depth32 diverged by "
            f"{worst} despite identical specifications"
        )
    return worst


def build_pair_contrasts(
    arm_rows: dict[str, list[dict[str, Any]]],
    pairs: dict[str, Any],
    seeds: list[int],
    critical: float,
) -> dict[str, Any]:
    by_seed = {
        arm: {int(row["seed"]): row for row in rows} for arm, rows in arm_rows.items()
    }
    out: dict[str, Any] = {}
    for name, spec in pairs.items():
        high, ref = spec["high_label_arm"], spec["reference_arm"]
        labels = [
            _label(by_seed[high][seed], 8) - _label(by_seed[ref][seed], 8)
            for seed in seeds
        ]
        arenas = [
            _arena(by_seed[high][seed]) - _arena(by_seed[ref][seed]) for seed in seeds
        ]
        rung0 = [
            _label(by_seed[high][seed], 0) - _label(by_seed[ref][seed], 0)
            for seed in seeds
        ]
        # Correlation appariee : le motif au niveau de la GRAINE, pas seulement
        # celui des moyennes. Deux moyennes de signes opposes peuvent tres bien
        # cacher une absence totale de lien graine par graine.
        correlation = None
        if float(np.std(labels)) > 0.0 and float(np.std(arenas)) > 0.0:
            correlation = float(np.corrcoef(labels, arenas)[0, 1])
        out[name] = {
            "single_factor": spec["single_factor"],
            "high_label_arm": high,
            "reference_arm": ref,
            "label_delta": _paired_summary(labels, critical),
            "arena_delta": _paired_summary(arenas, critical),
            "rung0_label_delta": _paired_summary(rung0, critical),
            "within_pair_correlation": correlation,
        }
    return out


def _excludes_zero(row: dict[str, Any]) -> bool:
    low, high = row["confidence_95"]
    return low > 0.0 or high < 0.0


def _sign(value: float) -> int:
    return (value > 0.0) - (value < 0.0)


def build_recommendation(
    aggregate: dict[str, Any], gate: dict[str, Any]
) -> dict[str, Any]:
    """L'opposition EST le resultat : un seul cote ne prouve rien."""
    execution = aggregate["execution"]
    common = {
        "reference_arm_divergence": float(execution["reference_arm_divergence"]),
        "promotable": False,
    }
    pairs = aggregate["pairs"]
    worst_rung0 = max(
        abs(float(row["rung0_label_delta"]["mean"])) for row in pairs.values()
    )
    if worst_rung0 > float(gate["maximum_rung0_level_gap"]):
        return {
            **common,
            "status": "INCONCLUSIVE",
            "finding": "probe_was_not_common_rung0_label_levels_differ",
            "anti_correlation_established": None,
            "worst_rung0_label_gap": worst_rung0,
            "pairs": {},
            "next_step": "fix_the_common_probe_before_reading_any_level_contrast",
        }

    verdicts: dict[str, Any] = {}
    for name, row in pairs.items():
        label, arena = row["label_delta"], row["arena_delta"]
        label_ok = (
            abs(float(label["mean"])) > float(gate["minimum_practical_label_gap"])
            and _excludes_zero(label)
        )
        arena_ok = (
            abs(float(arena["mean"])) > float(gate["minimum_practical_arena_gap"])
            and _excludes_zero(arena)
        )
        opposed = _sign(float(label["mean"])) == -_sign(float(arena["mean"])) != 0
        verdicts[name] = {
            "label_gap_practical_and_confident": label_ok,
            "arena_gap_practical_and_confident": arena_ok,
            "signs_opposed": opposed,
            # Les trois ensemble, jamais un sous-ensemble : un ecart
            # d'etiquettes seul, ou une opposition dont un cote traverse zero,
            # ne dit rien sur l'anticorrelation.
            "anti_correlated": bool(label_ok and arena_ok and opposed),
        }
    established = [name for name, v in verdicts.items() if v["anti_correlated"]]
    return {
        **common,
        "status": "PASS" if established else "FAIL",
        "finding": (
            "label_exactness_and_playing_strength_are_ANTI_CORRELATED"
            if established
            else "the_anti_correlation_pattern_did_not_survive_a_paired_test"
        ),
        "anti_correlation_established": bool(established),
        "established_in_pairs": established,
        "worst_rung0_label_gap": worst_rung0,
        "pairs": verdicts,
        "next_step": (
            "stop_using_label_exactness_as_a_proxy_for_strength_anywhere"
            if established
            else "the_four_arm_pattern_was_a_between_arm_artefact_not_a_law"
        ),
    }


def _aggregate_arm(rows: list[dict[str, Any]], rungs: list[int]) -> dict[str, Any]:
    return {
        "successful_run_count": len(rows),
        "mean_advancing_generations": _mean(
            [float(row["advancing_generations"]) for row in rows]
        ),
        "mean_probe_start_exact_rate_by_rung": {
            str(rung): _mean([_label(row, rung) for row in rows]) for rung in rungs
        },
        "mean_final_arena_score_vs_initial": _mean([_arena(row) for row in rows]),
        "mean_loop_consumed_nodes": _mean(
            [float(row["loop_consumed_nodes"]) for row in rows]
        ),
    }


def _resolve(path: Path) -> dict[str, Any]:
    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    if config.get("schema") != SCHEMA or config.get("milestone") != "M20":
        raise ValueError("unexpected M20 schema")
    if tuple(config.get("arms", {})) != ARM_ORDER:
        raise ValueError("M20 arm definitions changed after preregistration")
    seeds = [int(seed) for seed in config["paired_seeds"]]
    if len(seeds) != 20 or len(set(seeds)) != 20:
        raise ValueError("M20 requires 20 distinct seeds — power is nearly free here")
    if set(seeds) & {180001, 180002, 180003, 180004, 180005}:
        raise ValueError(
            "M20 must not reuse the M18/M19 seeds that suggested the pattern"
        )
    boundaries = config.get("boundaries", {})
    if (
        boundaries.get("promotable") is not False
        or boundaries.get("production_jass_changes_authorized") is not False
        or boundaries.get("direct_10x10_transfer_authorized") is not False
    ):
        raise ValueError("M20 crossed a forbidden boundary")
    root = path.resolve().parent.parent
    gate_path = root / str(config["base_gate_config"])
    gate = resolve_learning_gate_config(gate_path)
    if gate.milestone != "M8":
        raise ValueError("M20 requires the frozen passing M8 L1 recipe")
    base_loop = deepcopy(gate.resolved["base_loop"])
    if int(base_loop["generations"]) != 1:
        raise ValueError("M20 expects the historical M8 recipe at one generation")
    base_loop["generations"] = int(config["ladder_max"])
    resolved = deepcopy(config)
    resolved["base_gate_config"] = str(gate_path.resolve())
    resolved["base_loop"] = base_loop
    resolved["paired_seeds"] = seeds
    return resolved


def run_m20(
    config_path: Path,
    oracle_path: Path,
    run_dir: Path,
    compact_output: Path,
    execution_host: str | None = None,
) -> dict[str, Any]:
    config = _resolve(config_path)
    host = execution_host or platform.node()
    if host != config["expected_execution_host"]:
        raise ValueError(f"M20 requires cpx62, got {host}")

    oracle = load_oracle(oracle_path)
    graph = GameGraph.from_oracle(oracle)
    graph.validate()
    base_loop = deepcopy(config["base_loop"])
    split = build_split(oracle, int(base_loop["split_seed"]))
    if split.manifest["manifest_hash"] != base_loop["expected_split_manifest_hash"]:
        raise ValueError("M20 split differs from the frozen L1 contract")
    tensors = _development_tensors(oracle, graph)
    seeds = config["paired_seeds"]
    rungs = [int(rung) for rung in config["report_rungs"]]
    depth = int(config["common_probe_search_depth"])

    run_dir.mkdir(parents=True, exist_ok=True)
    arm_rows: dict[str, list[dict[str, Any]]] = {arm: [] for arm in ARM_ORDER}
    for arm in ARM_ORDER:
        spec = config["arms"][arm]
        for seed in seeds:
            arm_rows[arm].append(
                _run_arm_seed(
                    arm=arm,
                    spec=spec,
                    seed=seed,
                    base_loop=base_loop,
                    oracle=oracle,
                    graph=graph,
                    development_indices=split.indices("development"),
                    training_start_indices=split.indices("train"),
                    tensors=tensors,
                    config=config,
                    run_dir=run_dir,
                    probe_depth_override=depth,
                )
            )

    assert_paired_probe_schedules(arm_rows, seeds)
    divergence = assert_reference_arms_agree(
        arm_rows, seeds, float(config["scientific_gate"]["maximum_reference_arm_divergence"])
    )
    critical = float(config["scientific_gate"]["paired_confidence_critical_95"])
    aggregate = {
        "arms": {arm: _aggregate_arm(rows, rungs) for arm, rows in arm_rows.items()},
        "pairs": build_pair_contrasts(arm_rows, config["pairs"], seeds, critical),
        "execution": {
            "all_runs_completed": all(
                len(rows) == len(seeds) for rows in arm_rows.values()
            ),
            "seed_count": len(seeds),
            "oracle_has_no_causal_role": all(
                int(row["oracle_causal_reads"]) == 0
                for rows in arm_rows.values()
                for row in rows
            ),
            "reference_arm_divergence": divergence,
            "execution_host": host,
        },
    }
    recommendation = build_recommendation(aggregate, config["scientific_gate"])
    protocol = {
        "schema": SCHEMA,
        "milestone": "M20",
        "base_gate_config": config["base_gate_config"],
        "paired_seeds": seeds,
        "ladder_max": int(config["ladder_max"]),
        "report_rungs": rungs,
        "arms": config["arms"],
        "pairs": config["pairs"],
        "common_probe_search_depth": depth,
        "tests": "the four-arm label/strength pattern of M18 and M19",
        "boundaries": config["boundaries"],
        "execution_host": host,
    }
    result: dict[str, Any] = {
        "schema": SCHEMA,
        "milestone": "M20",
        "status": recommendation["status"],
        "protocol_hash": _digest(protocol),
        "protocol": protocol,
        "aggregate": aggregate,
        "seed_results": arm_rows,
        "recommendation": recommendation,
        "contracts": {
            "training_target": "terminal_selfplay_WDL_only",
            "oracle_used_for_training": False,
            "oracle_used_for_generation": False,
            "oracle_used_for_promotion": False,
            "oracle_used_posthoc_as_microscope": True,
            "promotable": False,
            "production_jass_changes_authorized": False,
            "direct_10x10_transfer_authorized": False,
        },
    }
    result["result_hash"] = _digest(
        {key: value for key, value in result.items() if key != "result_hash"}
    )
    (run_dir / "result.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    compact = {key: value for key, value in result.items() if key != "seed_results"}
    compact["seed_results"] = {
        "omitted_from_compact_output": True,
        "reason": "runner inlines a status summary only under 64 KiB",
        "full_record": "result.json (run_dir, published as an artefact)",
        "row_count": sum(len(rows) for rows in arm_rows.values()),
    }
    compact_output.parent.mkdir(parents=True, exist_ok=True)
    compact_output.write_text(
        json.dumps(compact, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--oracle", type=Path, required=True)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--compact-output", type=Path, required=True)
    parser.add_argument("--execution-host")
    args = parser.parse_args()
    result = run_m20(
        args.config, args.oracle, args.run_dir, args.compact_output, args.execution_host
    )
    print(
        json.dumps(
            {
                "milestone": result["milestone"],
                "status": result["status"],
                "finding": result["recommendation"]["finding"],
                "result_hash": result["result_hash"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
