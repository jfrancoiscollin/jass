#!/usr/bin/env python3
"""M17 — l'echelle de generations : la boucle compose-t-elle ?

Tous nos verdicts plats -- sept transformations de corpus a L3, l'echec de la
tete de valeur a L2, « l'heritage ne vaut rien » -- sont des mesures a UNE
generation. La methode de reference en suppose plusieurs. Cette cellule mesure
si la boucle gagne quelque chose en tournant, sur le seul niveau ou elle
apprend de facon etablie (L1, M8).

Un seul run par graine a `ladder_max` : la boucle est causalement en avant, donc
tronquer au barreau k redonne exactement le run `generations: k`. Les barreaux
partagent tout leur passe commun.

⚠️ Le parent n'avance que si `development_pass AND arena_pass`. Une echelle qui
ne promeut jamais mesure huit fois la meme generation : le taux de promotion
est donc rapporte, et son absence rend le resultat INCONCLUANT, pas negatif.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
from copy import deepcopy
from pathlib import Path
from typing import Any

import numpy as np
import yaml

from mini_jass_lab.learning_gate import resolve_learning_gate_config
from mini_jass_lab.loop import execute_loop
from mini_jass_lab.model import MiniJassMLP, ModelConfig
from mini_jass_lab.oracle import load_oracle
from mini_jass_lab.split import build_split
from mini_jass_lab.train import evaluate, seed_everything

SCHEMA = "mini_jass.generation_ladder.v1"


def _digest(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _mean(values: list[float]) -> float:
    return float(np.mean(np.asarray(values, dtype=np.float64)))


def _metrics(model, tensors, oracle, indices, batch) -> dict[str, float]:
    raw = evaluate(model, tensors, oracle, indices, batch)
    return {
        "value_sign_accuracy": float(raw["value_sign_accuracy"]),
        "optimal_probability_mass": float(raw["optimal_probability_mass"]),
    }


def build_ladder_recommendation(
    aggregate: dict[str, Any], gate: dict[str, Any], control: dict[str, Any]
) -> dict[str, Any]:
    """Traduit l'echelle en decision, en distinguant PLAT de NOMINAL.

    Le piege est qu'une echelle sans promotion produit un plateau parfait tout
    en n'ayant jamais itere. Ce cas doit sortir INCONCLUANT, pas « l'iteration
    ne compose pas » -- c'est exactement la sur-lecture que ce controle existe
    pour empecher.
    """
    advancing = int(aggregate["mean_advancing_generations"] > 0.0)
    if not advancing or aggregate["mean_advancing_generations"] < float(
        control["minimum_advancing_generations"]
    ):
        return {
            "finding": "ladder_never_advanced_the_parent",
            "decision": "INCONCLUSIVE_promotion_gate_blocked_iteration",
            "iteration_compounds": None,
            "promotable": False,
        }
    deltas = aggregate["mean_value_sign_delta_by_rung"]
    rungs = aggregate["rungs"]
    monotone = sum(
        1
        for index in range(1, len(rungs))
        if deltas[str(rungs[index])] >= deltas[str(rungs[index - 1])]
    )
    final = deltas[str(rungs[-1])]
    compounds = (
        monotone + 1 >= int(gate["minimum_monotone_rungs"])
        and final > float(gate["minimum_final_value_sign_delta"])
        and final > deltas[str(rungs[0])]
    )
    return {
        "finding": (
            "iteration_compounds_across_generations"
            if compounds
            else "iteration_does_not_compound_in_this_loop"
        ),
        "decision": (
            "replicate_ladder_on_fresh_seeds"
            if compounds
            else "single_generation_protocol_is_not_the_limiting_factor"
        ),
        "iteration_compounds": bool(compounds),
        "monotone_rungs": monotone + 1,
        "promotable": False,
    }


def run_generation_ladder(
    config_path: Path,
    oracle_path: Path,
    run_dir: Path,
    compact_output: Path | None = None,
    execution_host: str | None = None,
) -> dict[str, Any]:
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if config.get("schema") != SCHEMA:
        raise ValueError("unexpected generation-ladder schema")
    ladder_max = int(config["ladder_max"])
    rungs = [int(rung) for rung in config["report_rungs"]]
    if not rungs or max(rungs) != ladder_max or sorted(rungs) != rungs:
        raise ValueError("report_rungs must be sorted and reach ladder_max")

    base_dir = config_path.resolve().parent.parent
    # `resolve_learning_gate_config` rend un LearningGateConfig gele ; on lit
    # son champ `resolved`. Pas de `hasattr` defensif : si le type change, on
    # veut un AttributeError bruyant, pas un repli silencieux sur autre chose.
    gate = resolve_learning_gate_config(base_dir / config["base_gate_config"])
    if gate.milestone != "M8":
        raise ValueError(f"M17 rejoue la recette M8 gelee, recu {gate.milestone}")
    base_loop = deepcopy(gate.resolved["base_loop"])
    if int(base_loop["generations"]) != 1:
        raise ValueError(
            "M17 expects the frozen M8 recipe at generations: 1 — the whole "
            "point is that it has never iterated"
        )
    base_loop["generations"] = ladder_max

    oracle = load_oracle(oracle_path)
    split = build_split(oracle, int(base_loop["split_seed"]))
    if split.manifest["manifest_hash"] != base_loop["expected_split_manifest_hash"]:
        raise ValueError("M17 split differs from the frozen L1 contract")
    development_indices = split.indices("development")
    train_indices = split.indices("train")

    from mini_jass_lab.game_graph import GameGraph

    graph = GameGraph.from_oracle(oracle)
    graph.validate()
    import torch

    tensors = {
        "features": torch.from_numpy(graph.features),
        "values": torch.from_numpy(oracle.values.astype(np.float32)),
        "legal": torch.from_numpy(graph.legal_mask),
    }
    from mini_jass_lab.train import uniform_optimal_targets

    tensors["optimal"] = torch.from_numpy(uniform_optimal_targets(oracle.optimal_mask))

    batch = int(base_loop["development"]["batch_size"])
    seed_rows: list[dict[str, Any]] = []
    for seed in config["paired_seeds"]:
        loop_config = deepcopy(base_loop)
        loop_config["seed"] = int(seed)
        execution = execute_loop(loop_config, oracle, development_indices, train_indices)
        seed_everything(int(seed), int(loop_config["runtime"]["threads"]))
        initial = MiniJassMLP(ModelConfig(**loop_config["model"]))
        before = _metrics(initial, tensors, oracle, development_indices, batch)

        by_rung: dict[str, dict[str, float]] = {}
        for rung in rungs:
            candidate = MiniJassMLP(ModelConfig(**loop_config["model"]))
            candidate.load_state_dict(execution.candidate_states[rung - 1])
            after = _metrics(candidate, tensors, oracle, development_indices, batch)
            by_rung[str(rung)] = {
                "value_sign_delta": after["value_sign_accuracy"]
                - before["value_sign_accuracy"],
                "optimal_mass_delta": after["optimal_probability_mass"]
                - before["optimal_probability_mass"],
            }
        advancing = [
            bool(record["promotion"]["provisional_advance"])
            for record in execution.core["generations"]
        ]
        seed_rows.append(
            {
                "seed": int(seed),
                "by_rung": by_rung,
                "advancing_generations": int(sum(advancing)),
                "advance_flags": advancing,
            }
        )

    aggregate = {
        "rungs": rungs,
        "paired_seed_count": len(seed_rows),
        "mean_value_sign_delta_by_rung": {
            str(rung): _mean([row["by_rung"][str(rung)]["value_sign_delta"] for row in seed_rows])
            for rung in rungs
        },
        "mean_optimal_mass_delta_by_rung": {
            str(rung): _mean(
                [row["by_rung"][str(rung)]["optimal_mass_delta"] for row in seed_rows]
            )
            for rung in rungs
        },
        # LE controle : une echelle qui n'avance jamais mesure N fois la meme
        # generation, et son plateau ne veut rien dire.
        "mean_advancing_generations": _mean(
            [float(row["advancing_generations"]) for row in seed_rows]
        ),
        "seeds_with_zero_advance": sum(
            1 for row in seed_rows if row["advancing_generations"] == 0
        ),
    }
    recommendation = build_ladder_recommendation(
        aggregate, config["scientific_gate"], config["promotion_control"]
    )
    protocol = {
        "schema": SCHEMA,
        "ladder_max": ladder_max,
        "report_rungs": rungs,
        "paired_seeds": [int(seed) for seed in config["paired_seeds"]],
        "base_gate_config": config["base_gate_config"],
        "single_factor": "generations",
        "truncation_equivalence": "forward_causal_loop_run_at_max_contains_every_rung",
        "boundaries": config["boundaries"],
        "execution_host": execution_host or platform.node(),
    }
    result = {
        "schema": SCHEMA,
        "milestone": "M17",
        "status": "PASS" if recommendation["iteration_compounds"] else "FAIL",
        "protocol_hash": _digest(protocol),
        "protocol": protocol,
        "aggregate": aggregate,
        "seed_results": seed_rows,
        "recommendation": recommendation,
    }
    result["result_hash"] = _digest({k: v for k, v in result.items() if k != "result_hash"})
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "result.json").write_text(
        json.dumps(result, indent=2, sort_keys=True), encoding="utf-8"
    )
    if compact_output is not None:
        compact_output.parent.mkdir(parents=True, exist_ok=True)
        compact_output.write_text(
            json.dumps(result, indent=2, sort_keys=True), encoding="utf-8"
        )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--oracle", type=Path, required=True)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--compact-output", type=Path, default=None)
    parser.add_argument("--execution-host", type=str, default=None)
    args = parser.parse_args()
    result = run_generation_ladder(
        args.config, args.oracle, args.run_dir, args.compact_output, args.execution_host
    )
    print(json.dumps(result["aggregate"], indent=2, sort_keys=True))
    print(json.dumps(result["recommendation"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
