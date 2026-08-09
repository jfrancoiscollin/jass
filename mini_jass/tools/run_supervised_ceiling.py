#!/usr/bin/env python3
"""M24 — le PLAFOND : jusqu'ou ce modele peut-il repondre comme l'oracle ?

POURQUOI CETTE CELLULE EXISTE. JFC veut boucler des generations d'autojeu a
recette figee sur le 5x5 jusqu'a l'optimum, ou jusqu'a un plateau, et estimer le
nombre de generations necessaires. ⛔ Or un plateau, seul, est ININTERPRETABLE :
il peut venir de la BOUCLE qui sature, ou du MODELE qui ne peut pas representer
l'optimum. Deux explications incompatibles, une seule courbe.

M24 mesure la seconde directement : le meme MLP, entraine en SUPERVISE sur les
etiquettes exactes du solveur. C'est le mieux que cette architecture puisse
faire, oracle en main. La courbe de convergence se lira ensuite CONTRE ce trait.

  plateau AU plafond    → la boucle a fait tout ce que le modele permet
  plateau SOUS le plafond → c'est la BOUCLE qui sature, et l'ecart est le gisement
  plafond loin de l'oracle → il faut de la capacite avant toute conclusion

⛔ CE N'EST PAS UN CANDIDAT. L'oracle est ici le signal d'entrainement, ce qui
est une traversee de frontiere DELIBEREE : aucune boucle d'autojeu ne peut
produire ces etiquettes. Meme statut que le bras `exact_oracle` de M14 -- une
BORNE SUPERIEURE, jamais un modele promouvable.

⛔ ET LE PLAFOND DOIT ETRE SATURE POUR VALOIR QUELQUE CHOSE. Un fit sous-entraine
rendrait « le plafond » = « la duree qu'on a bien voulu payer ». La cellule
balaie donc la dose et REFUSE de publier un plafond si la derniere marche
progresse encore -- meme faute que `EXACT` et `PRIOR` sous-convergees a L3, ou
le solveur s'arretait a 141 iterations en rendant `success=True`.
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
import torch  # noqa: E402
import yaml  # noqa: E402

from mini_jass_lab.game_graph import GameGraph  # noqa: E402
from mini_jass_lab.model import MiniJassMLP, ModelConfig  # noqa: E402
from mini_jass_lab.oracle import load_oracle  # noqa: E402
from mini_jass_lab.split import build_split  # noqa: E402
from mini_jass_lab.train import evaluate, seed_everything, train_epoch  # noqa: E402
from mini_jass_lab.train import uniform_optimal_targets  # noqa: E402

from m18_wdl_config import _digest, _mean  # noqa: E402

SCHEMA = "mini_jass.supervised_ceiling.v1"
# `zero_regret_rate` est la reponse a la question posee : « le coup choisi
# perd-il quelque chose ? ». `optimal_top1_accuracy` dit « l'argmax est-il DANS
# l'ensemble optimal ». Les deux sont rapportes ; le premier decide.
PRIMARY_METRIC = "zero_regret_rate"
REPORTED = (
    "zero_regret_rate",
    "optimal_top1_accuracy",
    "optimal_probability_mass",
    "value_sign_accuracy",
    "mean_selected_regret",
)
COHORTS = ("train", "development", "frozen_test")


def _tensors(oracle, graph: GameGraph) -> dict[str, torch.Tensor]:
    return {
        "features": torch.from_numpy(graph.features),
        "values": torch.from_numpy(oracle.values.astype(np.float32)),
        "legal": torch.from_numpy(graph.legal_mask),
        "optimal": torch.from_numpy(uniform_optimal_targets(oracle.optimal_mask)),
    }


def fit_ceiling(
    oracle,
    graph: GameGraph,
    tensors: dict[str, torch.Tensor],
    cohorts: dict[str, np.ndarray],
    model_config: dict[str, Any],
    training: dict[str, Any],
    epochs: int,
    seed: int,
) -> dict[str, Any]:
    """Un fit supervise complet, evalue sur les TROIS cohortes.

    ⚠️ L'entrainement ne voit que `train`. `development` reste comparable a tous
    les jalons M17-M23, qui l'ont utilisee ; `frozen_test` est le seul chiffre de
    generalisation honnete, et il n'est lu ICI QUE POUR DECRIRE -- jamais pour
    choisir quoi que ce soit.
    """
    seed_everything(int(seed), int(training.get("threads", 1)))
    model = MiniJassMLP(ModelConfig(**model_config))
    optimizer = torch.optim.AdamW(
        model.parameters(),
        float(training["learning_rate"]),
        weight_decay=float(training["weight_decay"]),
    )
    for epoch in range(int(epochs)):
        train_epoch(
            model,
            optimizer,
            tensors,
            cohorts["train"],
            int(training["batch_size"]),
            seed + epoch * 7_919,
            float(training["value_weight"]),
            float(training["policy_weight"]),
        )
    out: dict[str, Any] = {"epochs": int(epochs), "seed": int(seed)}
    for name in COHORTS:
        raw = evaluate(model, tensors, oracle, cohorts[name], int(training["batch_size"]))
        out[name] = {key: raw[key] for key in REPORTED}
        out[name]["count"] = raw["count"]
    return out


def build_recommendation(
    aggregate: dict[str, Any], gate: dict[str, Any]
) -> dict[str, Any]:
    """⛔ Un plafond non sature n'est pas un plafond."""
    doses = aggregate["by_dose"]
    ladder = sorted(doses, key=lambda d: int(d))
    frozen = [
        float(doses[d]["frozen_test"][PRIMARY_METRIC]) for d in ladder
    ]
    last_step = frozen[-1] - frozen[-2] if len(frozen) > 1 else float("inf")
    tolerance = float(gate["saturation_tolerance"])
    saturated = abs(last_step) <= tolerance
    common = {
        "primary_metric": PRIMARY_METRIC,
        "dose_ladder": [int(d) for d in ladder],
        "frozen_test_by_dose": frozen,
        "last_dose_step": last_step,
        "saturation_tolerance": tolerance,
        # ⛔ L'oracle est le signal d'ENTRAINEMENT ici : borne, jamais candidat.
        "is_an_upper_bound_not_a_candidate": True,
        "promotable": False,
    }
    if not saturated:
        return {
            **common,
            "status": "CEILING_NOT_SATURATED",
            "finding": "the_largest_dose_was_still_improving_this_is_not_a_ceiling",
            "ceiling": None,
            "next_step": "extend_the_dose_ladder_before_reading_any_ceiling",
        }
    ceiling = {
        cohort: {key: doses[ladder[-1]][cohort][key] for key in REPORTED}
        for cohort in COHORTS
    }
    capacity = aggregate.get("by_capacity") or {}
    # Le plafond de la recette gelee est LE chiffre attendu ; la capacite dit
    # seulement si l'architecture est ce qui borne, ou si c'est autre chose.
    frozen_size = int(gate["frozen_recipe_hidden_size"])
    bigger = [
        (int(size), float(row["frozen_test"][PRIMARY_METRIC]))
        for size, row in capacity.items()
        if int(size) > frozen_size
    ]
    reference = float(ceiling["frozen_test"][PRIMARY_METRIC])
    # ⚠️ Sans echelle de capacite, la question « l'architecture borne-t-elle ? »
    # n'a pas ete POSEE. Rendre `False` la ferait passer pour repondue par la
    # negative -- c'est `None`, et le lecteur doit le voir.
    if not bigger:
        capacity_gain = None
        architecture_binds = None
    else:
        capacity_gain = max(v - reference for _, v in bigger)
        architecture_binds = capacity_gain > float(gate["capacity_relevance_threshold"])
    return {
        **common,
        "status": "PASS",
        "finding": "representational_ceiling_measured_and_saturated",
        "ceiling": ceiling,
        "ceiling_primary_frozen_test": reference,
        "distance_to_oracle": 1.0 - reference,
        "capacity_gain_from_bigger_models": capacity_gain,
        "architecture_is_the_binding_constraint": architecture_binds,
        "next_step": (
            "read_every_self_play_convergence_curve_against_this_line"
        ),
    }


def _resolve(path: Path) -> dict[str, Any]:
    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    if config.get("schema") != SCHEMA or config.get("milestone") != "M24":
        raise ValueError("unexpected M24 schema")
    boundaries = config.get("boundaries", {})
    if (
        boundaries.get("promotable") is not False
        or boundaries.get("production_jass_changes_authorized") is not False
        or boundaries.get("direct_10x10_transfer_authorized") is not False
    ):
        raise ValueError("M24 crossed a forbidden boundary")
    if boundaries.get("oracle_is_the_training_signal") is not True:
        raise ValueError(
            "M24 must declare that the oracle IS its training signal — this is a "
            "deliberate boundary crossing and it has to be written down"
        )
    doses = [int(d) for d in config["dose_ladder"]]
    if sorted(doses) != doses or len(doses) < 2:
        raise ValueError("M24 dose ladder must be sorted and hold at least two rungs")
    return deepcopy(config)


def run_m24(
    config_path: Path,
    oracle_path: Path,
    run_dir: Path,
    compact_output: Path,
    execution_host: str | None = None,
) -> dict[str, Any]:
    config = _resolve(config_path)
    host = execution_host or platform.node()
    if host != config["expected_execution_host"]:
        raise ValueError(f"M24 requires cpx62, got {host}")

    oracle = load_oracle(oracle_path)
    graph = GameGraph.from_oracle(oracle)
    graph.validate()
    split = build_split(oracle, int(config["split_seed"]))
    cohorts = {name: split.indices(name) for name in COHORTS}
    tensors = _tensors(oracle, graph)
    training = config["training"]
    seeds = [int(s) for s in config["seeds"]]
    run_dir.mkdir(parents=True, exist_ok=True)

    # 1. L'ECHELLE DE DOSE, a la capacite de la recette gelee.
    by_dose: dict[str, Any] = {}
    for epochs in config["dose_ladder"]:
        runs = [
            fit_ceiling(
                oracle, graph, tensors, cohorts,
                config["model"], training, int(epochs), seed,
            )
            for seed in seeds
        ]
        by_dose[str(int(epochs))] = {
            cohort: {
                key: _mean([float(r[cohort][key]) for r in runs]) for key in REPORTED
            }
            for cohort in COHORTS
        }
        by_dose[str(int(epochs))]["seed_count"] = len(runs)

    # 2. LA CAPACITE, a la dose la plus longue : l'architecture borne-t-elle ?
    by_capacity: dict[str, Any] = {}
    top_dose = int(config["dose_ladder"][-1])
    frozen_size = int(config["model"]["hidden_size"])
    for size in config["capacity_ladder"]:
        if int(size) == frozen_size:
            # La taille gelee a DEJA ete fittee au barreau superieur de l'echelle
            # de dose : la recalculer serait payer deux fois exactement le meme
            # travail, et laisser deux chiffres diverger si une graine derive.
            by_capacity[str(int(size))] = deepcopy(by_dose[str(top_dose)])
            by_capacity[str(int(size))]["reused_from_dose_ladder"] = True
            continue
        model_config = deepcopy(config["model"])
        model_config["hidden_size"] = int(size)
        runs = [
            fit_ceiling(
                oracle, graph, tensors, cohorts, model_config, training, top_dose, seed
            )
            for seed in seeds
        ]
        by_capacity[str(int(size))] = {
            cohort: {
                key: _mean([float(r[cohort][key]) for r in runs]) for key in REPORTED
            }
            for cohort in COHORTS
        }

    aggregate = {
        "by_dose": by_dose,
        "by_capacity": by_capacity,
        "cohort_sizes": {name: int(cohorts[name].size) for name in COHORTS},
        "execution": {
            "seed_count": len(seeds),
            "top_dose_epochs": top_dose,
            "execution_host": host,
        },
    }
    recommendation = build_recommendation(aggregate, config["scientific_gate"])
    protocol = {
        "schema": SCHEMA,
        "milestone": "M24",
        "model": config["model"],
        "training": training,
        "dose_ladder": config["dose_ladder"],
        "capacity_ladder": config["capacity_ladder"],
        "seeds": seeds,
        "primary_metric": PRIMARY_METRIC,
        "purpose": "upper bound for reading self-play convergence curves",
        "boundaries": config["boundaries"],
        "execution_host": host,
    }
    result: dict[str, Any] = {
        "schema": SCHEMA,
        "milestone": "M24",
        "status": recommendation["status"],
        "protocol_hash": _digest(protocol),
        "protocol": protocol,
        "aggregate": aggregate,
        "recommendation": recommendation,
        "contracts": {
            "oracle_is_the_training_signal": True,
            "no_self_play_loop_can_produce_these_labels": True,
            "promotable": False,
            "production_jass_changes_authorized": False,
            "direct_10x10_transfer_authorized": False,
        },
    }
    result["result_hash"] = _digest(
        {k: v for k, v in result.items() if k != "result_hash"}
    )
    (run_dir / "result.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    compact_output.parent.mkdir(parents=True, exist_ok=True)
    compact_output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
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
    result = run_m24(
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
