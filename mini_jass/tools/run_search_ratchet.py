#!/usr/bin/env python3
"""M19 — le cliquet de recherche, mesure sur une sonde a profondeur commune.

M18 a rendu `evolving − shallow = −0,0219`, IC95 [−0,144 ; +0,101], et ce
chiffre ne veut rien dire : la sonde heritait de la profondeur du bras, donc le
bras shallow demarrait 5,3 points plus bas AVANT tout entrainement, et le
contraste — defini sur le GAIN — recompensait mecaniquement le bras parti le
plus bas. Il etait biaise CONTRE la profondeur, celle-la meme qu'on teste.

M19 ne change qu'une chose : la sonde est a profondeur COMMUNE. Le barreau 0
devient alors identique par construction dans les deux bras (meme modele
initial, memes positions, memes graines, meme profondeur), ce qui rend les
NIVEAUX comparables — et le contraste primaire porte sur le niveau final.

Le gain reste rapporte en secondaire, pour rester lisible a cote du −0,0219 de
M18, mais il ne decide pas.
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

import yaml  # noqa: E402

from mini_jass_lab.game_graph import GameGraph  # noqa: E402
from mini_jass_lab.learning_gate import resolve_learning_gate_config  # noqa: E402
from mini_jass_lab.oracle import load_oracle  # noqa: E402
from mini_jass_lab.split import build_split  # noqa: E402

from m18_wdl_config import _digest, _mean, _paired_summary  # noqa: E402
from m18_wdl_execution import _run_arm_seed  # noqa: E402
from m18_wdl_mechanics import _development_tensors  # noqa: E402

SCHEMA = "mini_jass.search_ratchet.v1"
ARM_ORDER = ("reference_depth32", "shallow_depth1")
EXPECTED_SEEDS = [180001, 180002, 180003, 180004, 180005]


def _exact(row: dict[str, Any], rung: int) -> float:
    return float(row["by_rung"][str(rung)]["probe_start_wdl"]["exact_rate"])


def build_contrasts(
    arm_rows: dict[str, list[dict[str, Any]]], critical: float
) -> dict[str, Any]:
    mapped = {
        arm: {int(row["seed"]): row for row in rows} for arm, rows in arm_rows.items()
    }
    reference = mapped["reference_depth32"]
    shallow = mapped["shallow_depth1"]
    values = {
        # PRIMAIRE : le niveau final. Comparable parce que la sonde est commune.
        "reference_minus_shallow_level_g8": [
            _exact(reference[seed], 8) - _exact(shallow[seed], 8)
            for seed in EXPECTED_SEEDS
        ],
        # SECONDAIRE, pour continuite avec M18 -- et c'est lui qui portait le biais.
        "reference_minus_shallow_gain": [
            (_exact(reference[seed], 8) - _exact(reference[seed], 0))
            - (_exact(shallow[seed], 8) - _exact(shallow[seed], 0))
            for seed in EXPECTED_SEEDS
        ],
        # LE CONTROLE : doit valoir zero. Sinon la sonde n'est pas commune.
        "reference_minus_shallow_level_g0": [
            _exact(reference[seed], 0) - _exact(shallow[seed], 0)
            for seed in EXPECTED_SEEDS
        ],
    }
    return {name: _paired_summary(v, critical) for name, v in values.items()}


def build_recommendation(
    aggregate: dict[str, Any], gate: dict[str, Any]
) -> dict[str, Any]:
    """Traduit la cellule en decision, controle de sonde commune EN PREMIER."""
    contrasts = aggregate["contrasts"]
    execution = aggregate["execution"]
    rung0_gap = abs(float(contrasts["reference_minus_shallow_level_g0"]["mean"]))
    imbalance = float(execution["consumed_node_imbalance"])
    # Forme UNIFORME de la recommandation : les sorties precoces portent les
    # memes cles que la sortie nominale. Sinon le parseur du RESULTS explose sur
    # une KeyError APRES avoir brule tout le calcul -- precisement le mode de
    # panne qui a coute le verdict de cpx62-1206.
    common = {
        "rung0_level_gap": rung0_gap,
        "consumed_node_imbalance": imbalance,
        "compute_balanced_within_m8_tolerance": (
            imbalance <= float(gate["maximum_consumed_node_imbalance"])
        ),
        "promotable": False,
    }
    # Sans sonde reellement commune, un contraste de niveau ne mesure pas ce
    # qu'il pretend -- et c'est EXACTEMENT le defaut de M18 qu'on repare ici.
    # Le repeter en le declarant repare serait pire que de ne rien mesurer.
    if rung0_gap > float(gate["maximum_rung0_level_gap"]):
        return {
            **common,
            "status": "INCONCLUSIVE",
            "finding": "probe_was_not_common_rung0_levels_differ",
            "search_is_cliquet": None,
            "next_step": "fix_the_common_probe_before_reading_any_level_contrast",
        }
    advancing = float(
        aggregate["arms"]["reference_depth32"]["mean_advancing_generations"]
    )
    if advancing < float(gate["minimum_mean_advancing_generations"]):
        return {
            **common,
            "status": "INCONCLUSIVE",
            "finding": "reference_arm_never_advanced_the_parent",
            "search_is_cliquet": None,
            "next_step": "inspect_promotion_before_reading_the_search_contrast",
        }
    level = contrasts["reference_minus_shallow_level_g8"]
    practical = float(level["mean"]) > float(gate["minimum_practical_level_gap"])
    confident = float(level["confidence_95"][0]) > 0.0
    criteria = {
        "all_runs_completed": bool(execution["all_runs_completed"]),
        "start_schedules_paired": bool(execution["start_schedules_paired"]),
        "oracle_has_no_causal_role": bool(execution["oracle_has_no_causal_role"]),
        "common_probe_verified_at_rung0": True,
        "level_gap_practical": practical,
        "level_gap_confident": confident,
    }
    passed = all(criteria.values())
    return {
        **common,
        "status": "PASS" if passed else "FAIL",
        "finding": (
            "deeper_search_produces_a_measurably_better_model"
            if passed
            else "search_depth_did_not_change_the_model_measurably"
        ),
        # `consumed_node_imbalance` est rapporte TOUJOURS et n'est JAMAIS un
        # critere : au budget de noeuds de M8 (16), une recherche profonde en
        # consomme plus qu'une recherche a profondeur 1. Un ecart de niveau
        # accompagne d'un gros desequilibre reste attribuable aux deux, et le
        # dire est plus honnete que de faire echouer la cellule dessus.
        "search_is_cliquet": passed,
        "criteria": criteria,
        "next_step": (
            "replicate_on_fresh_seeds_before_any_scale_transfer"
            if passed
            else "search_depth_is_not_the_missing_ingredient_on_L1"
        ),
    }


def _aggregate_arm(rows: list[dict[str, Any]], rungs: list[int]) -> dict[str, Any]:
    return {
        "successful_run_count": len(rows),
        "mean_advancing_generations": _mean(
            [float(row["advancing_generations"]) for row in rows]
        ),
        "seeds_with_zero_advance": sum(
            1 for row in rows if int(row["advancing_generations"]) == 0
        ),
        "mean_probe_start_exact_rate_by_rung": {
            str(rung): _mean([_exact(row, rung) for row in rows]) for rung in rungs
        },
        "mean_final_arena_score_vs_initial": _mean(
            [float(row["final_arena_vs_initial"]["score"]) for row in rows]
        ),
        "mean_loop_consumed_nodes": _mean(
            [float(row["loop_consumed_nodes"]) for row in rows]
        ),
        "probe_search_depth": sorted({int(row["probe_search_depth"]) for row in rows}),
    }


def _resolve(path: Path) -> dict[str, Any]:
    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    if config.get("schema") != SCHEMA or config.get("milestone") != "M19":
        raise ValueError("unexpected M19 search-ratchet schema")
    if config.get("paired_seeds") != EXPECTED_SEEDS:
        raise ValueError("M19 reuses the M18 seeds so the loops stay identical")
    if tuple(config.get("arms", {})) != ARM_ORDER:
        raise ValueError("M19 arm definitions changed after preregistration")
    boundaries = config.get("boundaries", {})
    if (
        boundaries.get("promotable") is not False
        or boundaries.get("production_jass_changes_authorized") is not False
        or boundaries.get("direct_10x10_transfer_authorized") is not False
    ):
        raise ValueError("M19 crossed a forbidden boundary")
    root = path.resolve().parent.parent
    gate_path = root / str(config["base_gate_config"])
    gate = resolve_learning_gate_config(gate_path)
    if gate.milestone != "M8":
        raise ValueError("M19 requires the frozen passing M8 L1 recipe")
    base_loop = deepcopy(gate.resolved["base_loop"])
    if int(base_loop["generations"]) != 1:
        raise ValueError("M19 expects the historical M8 recipe at one generation")
    base_loop["generations"] = int(config["ladder_max"])
    resolved = deepcopy(config)
    resolved["base_gate_config"] = str(gate_path.resolve())
    resolved["base_loop"] = base_loop
    return resolved


def run_m19(
    config_path: Path,
    oracle_path: Path,
    run_dir: Path,
    compact_output: Path,
    execution_host: str | None = None,
) -> dict[str, Any]:
    config = _resolve(config_path)
    host = execution_host or platform.node()
    if host != config["expected_execution_host"]:
        raise ValueError(f"M19 requires cpx62, got {host}")

    oracle = load_oracle(oracle_path)
    graph = GameGraph.from_oracle(oracle)
    graph.validate()
    base_loop = deepcopy(config["base_loop"])
    split = build_split(oracle, int(base_loop["split_seed"]))
    if split.manifest["manifest_hash"] != base_loop["expected_split_manifest_hash"]:
        raise ValueError("M19 split differs from the frozen L1 contract")
    tensors = _development_tensors(oracle, graph)
    depth = int(config["common_probe_search_depth"])
    rungs = [int(rung) for rung in config["report_rungs"]]

    run_dir.mkdir(parents=True, exist_ok=True)
    arm_rows: dict[str, list[dict[str, Any]]] = {arm: [] for arm in ARM_ORDER}
    for arm in ARM_ORDER:
        spec = config["arms"][arm]
        for seed in EXPECTED_SEEDS:
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

    # La sonde doit avoir joue les MEMES positions de depart partout, sinon le
    # « barreau 0 identique » ne prouve rien.
    signatures = {row["probe_start_signature"] for rows in arm_rows.values() for row in rows}
    if len(signatures) != 1:
        raise ValueError("M19 fixed probe start schedule differed across arms or seeds")

    critical = float(config["scientific_gate"]["paired_confidence_critical_95"])
    arms = {arm: _aggregate_arm(rows, rungs) for arm, rows in arm_rows.items()}
    nodes = [arms[arm]["mean_loop_consumed_nodes"] for arm in ARM_ORDER]
    imbalance = (
        abs(nodes[0] - nodes[1]) / max(nodes) if max(nodes) > 0.0 else 0.0
    )
    aggregate = {
        "arms": arms,
        "contrasts": build_contrasts(arm_rows, critical),
        "execution": {
            "all_runs_completed": all(
                len(rows) == len(EXPECTED_SEEDS) for rows in arm_rows.values()
            ),
            "start_schedules_paired": True,
            "oracle_has_no_causal_role": all(
                int(row["oracle_causal_reads"]) == 0
                for rows in arm_rows.values()
                for row in rows
            ),
            "consumed_node_imbalance": float(imbalance),
            "execution_host": host,
        },
    }
    recommendation = build_recommendation(aggregate, config["scientific_gate"])
    protocol = {
        "schema": SCHEMA,
        "milestone": "M19",
        "base_gate_config": config["base_gate_config"],
        "paired_seeds": EXPECTED_SEEDS,
        "ladder_max": int(config["ladder_max"]),
        "report_rungs": rungs,
        "arms": config["arms"],
        "common_probe_search_depth": depth,
        "single_factor": "selfplay_search_depth",
        "corrects": "M18 evolving_gain_minus_shallow_gain, biased by its own rung-0 level",
        "boundaries": config["boundaries"],
        "execution_host": host,
    }
    result: dict[str, Any] = {
        "schema": SCHEMA,
        "milestone": "M19",
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
    result = run_m19(
        args.config,
        args.oracle,
        args.run_dir,
        args.compact_output,
        args.execution_host,
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
