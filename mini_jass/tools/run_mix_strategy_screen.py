#!/usr/bin/env python3
"""M23-A — quelle LOI de memoire temporelle, a volume unique egal ?

M21 → M21R → M21T ont etabli, sur trois pools chaines, que melanger les
generations produit un modele plus fort a volume de donnees UNIQUES egal :
chaine `+0,1417` se `0,0465`, `P(>0) = 99,88 %`, garde d'heterogeneite verte
(pire paire `|z| = 1,746`, Cochran `Q = 3,30` `df=2` `p ≈ 0,19`).

⛔ MAIS AVEC SA VRAIE TAILLE : `+0,1417`, pas le `+0,2375` du premier pool. La
sequence est monotone decroissante (`1,00 → 0,42 → 0,21`) et AUCUN pool n'a
jamais porte l'effet seul. Toute cellule suivante se dimensionne sur `+0,14`.

CE QUE CETTE CELLULE EST, ET CE QU'ELLE N'EST PAS.
  - UN contraste PRIMAIRE, nomme d'avance, qui peut conclure :
    `UNIFORM_HISTORY_50 − CURRENT_ONLY_WIDE`. Il est le seul a porter une
    histoire mecanique deja etayee -- `MIX − G8_ONLY` vaut `+0,3625`, `+0,1250`,
    `+0,2875` sur les trois pools de M21.
  - CINQ bras de FORME, qui ne concluent JAMAIS par eux-memes. Garder le
    maximum de six contrastes ferait passer la probabilite d'un faux positif de
    5 % a ~26 %, et la campagne vient de chiffrer trois fois ce que coute la
    selection : x0,30, x0,04, x0,42 entre selection et replication. L'ecran
    produit donc un CANDIDAT, dont seule une replication a graines fraiches
    fera un resultat.

⛔ ET TOUS LES BRAS PORTENT LE MEME NOMBRE D'ECHANTILLONS UNIQUES, verifie
fail-closed. Sans ca, « loi temporelle » et « volume de donnees uniques » se
confondent -- c'est exactement le piege que `G1_WIDE` a servi a lever, et
`CURRENT_ONLY` y retomberait : la generation 8 seule n'a qu'un `unit`
d'echantillons uniques la ou un melange en a plusieurs. D'ou
`CURRENT_ONLY_WIDE` : meme generateur (le parent deploye a la generation 8),
mais assez de parties pour atteindre la meme cible unique.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import json
import math
from pathlib import Path
import platform
import sys
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np  # noqa: E402
import yaml  # noqa: E402

import mini_jass_lab.loop as loop_module  # noqa: E402
from mini_jass_lab.arena import ArenaConfig, run_arena  # noqa: E402
from mini_jass_lab.game_graph import GameGraph  # noqa: E402
from mini_jass_lab.learning_gate import resolve_learning_gate_config  # noqa: E402
from mini_jass_lab.model import MiniJassMLP, ModelConfig  # noqa: E402
from mini_jass_lab.oracle import load_oracle  # noqa: E402
from mini_jass_lab.replay import ReplaySample  # noqa: E402
from mini_jass_lab.selfplay import generate_self_play  # noqa: E402
from mini_jass_lab.selfplay_train import train_from_replay  # noqa: E402
from mini_jass_lab.split import build_split  # noqa: E402
from mini_jass_lab.train import seed_everything  # noqa: E402

from m18_wdl_config import _digest, _mean, _paired_summary  # noqa: E402
from m18_wdl_mechanics import (  # noqa: E402
    _deployed_states_by_rung,
    _development_tensors,
    _model_metrics,
)

SCHEMA = "mini_jass.mix_strategy_screen.v1"
ARM_ORDER = (
    "UNIFORM_HISTORY_50",
    "RECENT_WINDOW_50",
    "EXP_DECAY_50",
    "RESERVOIR_50",
    "ANCHOR_50",
    "UNIFORM_ALL",
    "CURRENT_ONLY_WIDE",
)
PRIMARY = ("UNIFORM_HISTORY_50", "CURRENT_ONLY_WIDE")
CURRENT_GENERATION = 8
HISTORY = (1, 2, 3, 4, 5, 6, 7)


def _rng(seed: int, salt: int) -> np.random.Generator:
    return np.random.default_rng(seed * 1_000_003 + salt)


def _take(samples: list[ReplaySample], count: int, rng) -> list[ReplaySample]:
    """SANS remise : c'est le compte UNIQUE qui est controle.

    La remise est faite par `train_from_replay`, qui tire `steps x batch_size`
    indices dans le pool quel que soit le pool -- le budget d'updates est donc
    egal entre bras PAR CONSTRUCTION, et seule la composition varie.
    """
    if count > len(samples):
        raise ValueError(f"pool needs {count} samples, only {len(samples)} available")
    index = rng.choice(len(samples), size=count, replace=False)
    return [samples[int(i)] for i in sorted(index)]


def _spread(
    per_generation: dict[int, list[ReplaySample]],
    generations: tuple[int, ...],
    weights: list[float],
    total: int,
    seed: int,
    salt: int,
) -> list[ReplaySample]:
    """Tire `total` echantillons sur `generations`, selon des poids normalises."""
    share = np.asarray(weights, dtype=np.float64)
    share = share / share.sum()
    counts = np.floor(share * total).astype(int)
    while counts.sum() < total:  # le reste va aux plus gros poids, deterministe
        counts[int(np.argmax(share * total - counts))] += 1
    out: list[ReplaySample] = []
    for offset, (generation, count) in enumerate(zip(generations, counts)):
        if count:
            out.extend(
                _take(per_generation[generation], int(count), _rng(seed, salt + offset))
            )
    return out


def build_pools(
    per_generation: dict[int, list[ReplaySample]],
    wide_current: list[ReplaySample],
    config: dict[str, Any],
    seed: int,
) -> tuple[dict[str, list[ReplaySample]], dict[str, Any]]:
    """Sept pools de TAILLE UNIQUE IDENTIQUE, ne differant que par la loi.

    `unit` = la plus petite generation. La cible est `2 x unit` : elle permet a
    un bras « 50 % courant » de prendre TOUTE la generation 8 (`unit`) et autant
    d'historique, sans jamais demander a une generation plus d'echantillons
    uniques qu'elle n'en contient.
    """
    unit = min(len(per_generation[g]) for g in range(1, 9))
    if unit < 8:
        raise ValueError("M23 needs at least eight samples in every generation")
    target = 2 * unit
    half = target // 2
    current = _take(per_generation[CURRENT_GENERATION], half, _rng(seed, 800))

    half_life = float(config["arms"]["EXP_DECAY_50"]["half_life_generations"])
    decay = [0.5 ** ((CURRENT_GENERATION - g) / half_life) for g in HISTORY]
    window = tuple(config["arms"]["RECENT_WINDOW_50"]["recent_window_generations"])
    anchor = tuple(config["arms"]["ANCHOR_50"]["anchor_generations"])
    rolling = tuple(config["arms"]["ANCHOR_50"]["rolling_history_generations"])

    # RESERVOIR : uniforme sur les ECHANTILLONS de tout l'historique, pas sur les
    # generations. C'est ce qui le distingue de UNIFORM_HISTORY -- les
    # generations n'ont pas toutes la meme taille.
    pooled_history = [s for g in HISTORY for s in per_generation[g]]

    pools = {
        "UNIFORM_HISTORY_50": current
        + _spread(per_generation, HISTORY, [1.0] * len(HISTORY), half, seed, 100),
        "RECENT_WINDOW_50": current
        + _spread(per_generation, window, [1.0] * len(window), half, seed, 200),
        "EXP_DECAY_50": current
        + _spread(per_generation, HISTORY, decay, half, seed, 300),
        "RESERVOIR_50": current + _take(pooled_history, half, _rng(seed, 400)),
        "ANCHOR_50": current
        + _spread(per_generation, anchor, [1.0] * len(anchor), half // 2, seed, 500)
        + _spread(
            per_generation, rolling, [1.0] * len(rolling), half - half // 2, seed, 600
        ),
        "UNIFORM_ALL": _spread(
            per_generation, tuple(range(1, 9)), [1.0] * 8, target, seed, 700
        ),
        "CURRENT_ONLY_WIDE": _take(wide_current, target, _rng(seed, 900)),
    }
    census = {
        "unit_samples_per_generation": int(unit),
        "target_unique_samples": int(target),
        "unique_samples_by_arm": {a: len(p) for a, p in pools.items()},
        "unique_states_by_arm": {
            a: len({int(s.state_id) for s in p}) for a, p in pools.items()
        },
        "wide_current_available": len(wide_current),
    }
    # ⛔ FAIL-CLOSED. Sans egalite EXACTE des comptes uniques, la cellule mesure
    # « loi temporelle + volume » et ne peut plus les separer.
    sizes = set(census["unique_samples_by_arm"].values())
    if sizes != {target}:
        raise ValueError(
            f"M23 requires every arm to hold exactly {target} unique samples, got "
            f"{census['unique_samples_by_arm']}"
        )
    return pools, census


def build_contrasts(
    rows: dict[str, dict[int, dict[str, float]]],
    seeds: list[int],
    critical: float,
) -> dict[str, Any]:
    """Le primaire d'abord, puis les cinq contrastes de FORME, exploratoires."""
    out: dict[str, Any] = {}
    high, low = PRIMARY
    for arm in ARM_ORDER:
        if arm == low:
            continue
        name = f"{arm}_minus_{low}"
        out[name] = {
            endpoint: _paired_summary(
                [rows[arm][s][endpoint] - rows[low][s][endpoint] for s in seeds],
                critical,
            )
            for endpoint in ("arena_vs_initial", "learning_delta")
        }
        out[name]["role"] = "primary" if arm == high else "exploratory"
    return out


def build_recommendation(
    aggregate: dict[str, Any], gate: dict[str, Any]
) -> dict[str, Any]:
    """UN contraste conclut. Les autres designent au mieux un CANDIDAT."""
    contrasts = aggregate["contrasts"]
    high, low = PRIMARY
    primary = contrasts[f"{high}_minus_{low}"]["arena_vs_initial"]
    practical = float(gate["minimum_practical_arena_gain"])
    primary_ok = (
        float(primary["mean"]) > practical
        and float(primary["confidence_95"][0]) > 0.0
    )
    shapes = {
        name: row
        for name, row in contrasts.items()
        if row["role"] == "exploratory"
    }
    ranked = sorted(
        shapes.items(), key=lambda kv: -float(kv[1]["arena_vs_initial"]["mean"])
    )
    best_name, best_row = ranked[0] if ranked else (None, None)
    # ⛔ Le meilleur bras de forme n'est JAMAIS un resultat. Six contrastes
    # portent ~26 % de chance qu'au moins un IC95 exclue zero sous H0, et la
    # campagne a mesure trois fois le degonflement entre selection et
    # replication : x0,30, x0,04, x0,42.
    candidate = {
        "arm": best_name.replace(f"_minus_{low}", "") if best_name else None,
        "arena_mean_AT_SELECTION": (
            float(best_row["arena_vs_initial"]["mean"]) if best_row else None
        ),
        "is_a_result": False,
        "requires_fresh_seed_replication": True,
        "expected_shrinkage_band": "x0,04 to x0,42 measured on this bench",
    }
    common = {
        "primary_contrast": f"{high}_minus_{low}",
        "primary_arena_mean": float(primary["mean"]),
        "primary_arena_ci95": list(primary["confidence_95"]),
        "screen_never_concludes_on_shape": True,
        "shape_candidate": candidate,
        "arms_compared": len(shapes) + 1,
        "promotable": False,
    }
    if not primary_ok:
        return {
            **common,
            "status": "FAIL",
            "finding": "mixing_history_did_not_beat_current_only_at_equal_unique_volume",
            "mixing_beats_current_only": False,
            "next_step": "the_chained_M21_effect_does_not_carry_to_this_contrast_stop_and_re_read",
        }
    return {
        **common,
        "status": "PASS_PRIMARY_SHAPE_UNRESOLVED",
        "finding": "mixing_history_beats_current_only_the_best_SHAPE_is_only_a_candidate",
        "mixing_beats_current_only": True,
        "next_step": "replicate_the_candidate_shape_on_fresh_seeds_sized_on_its_replicated_effect",
    }


def _aggregate_arm(rows: dict[int, dict[str, float]], seeds: list[int]) -> dict[str, Any]:
    return {
        "mean_arena_vs_initial": _mean([rows[s]["arena_vs_initial"] for s in seeds]),
        "mean_learning_delta": _mean([rows[s]["learning_delta"] for s in seeds]),
        "mean_unique_samples": _mean([float(rows[s]["unique_samples"]) for s in seeds]),
    }


def _resolve(path: Path) -> dict[str, Any]:
    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    if config.get("schema") != SCHEMA or config.get("milestone") != "M23":
        raise ValueError("unexpected M23 schema")
    if tuple(config.get("arms", {})) != ARM_ORDER:
        raise ValueError("M23 arm definitions changed after preregistration")
    seeds = [int(seed) for seed in config["paired_seeds"]]
    if len(seeds) < 20 or len(set(seeds)) != len(seeds):
        raise ValueError("M23 requires at least 20 distinct seeds")
    # La garde de disjonction grandit avec la chaine : 210001-20 (M21),
    # 220001-20 (M21R), 230001-20 (M21T) et 240001-20 (M23-A v1) sont consommees.
    for lower in (210001, 220001, 230001, 240001):
        if set(seeds) & set(range(lower, lower + 20)):
            raise ValueError("M23 must not reuse an earlier pool's seed family")
    boundaries = config.get("boundaries", {})
    if (
        boundaries.get("promotable") is not False
        or boundaries.get("production_jass_changes_authorized") is not False
        or boundaries.get("direct_10x10_transfer_authorized") is not False
    ):
        raise ValueError("M23 crossed a forbidden boundary")
    root = path.resolve().parent.parent
    gate_path = root / str(config["base_gate_config"])
    gate = resolve_learning_gate_config(gate_path)
    if gate.milestone != "M8":
        raise ValueError("M23 requires the frozen passing M8 L1 recipe")
    base_loop = deepcopy(gate.resolved["base_loop"])
    base_loop["generations"] = 8
    resolved = deepcopy(config)
    resolved["base_gate_config"] = str(gate_path.resolve())
    resolved["base_loop"] = base_loop
    resolved["paired_seeds"] = seeds
    return resolved


def run_m23(
    config_path: Path,
    oracle_path: Path,
    run_dir: Path,
    compact_output: Path,
    execution_host: str | None = None,
) -> dict[str, Any]:
    config = _resolve(config_path)
    host = execution_host or platform.node()
    if host != config["expected_execution_host"]:
        raise ValueError(f"M23 requires cpx62, got {host}")

    oracle = load_oracle(oracle_path)
    graph = GameGraph.from_oracle(oracle)
    graph.validate()
    base_loop = deepcopy(config["base_loop"])
    split = build_split(oracle, int(base_loop["split_seed"]))
    if split.manifest["manifest_hash"] != base_loop["expected_split_manifest_hash"]:
        raise ValueError("M23 split differs from the frozen L1 contract")
    development = split.indices("development")
    tensors = _development_tensors(oracle, graph)
    seeds = config["paired_seeds"]
    batch = int(base_loop["development"]["batch_size"])
    training = base_loop["training"]
    starts = np.asarray(
        [
            int(state_id)
            for state_id in split.indices("train")
            if graph.terminal_value(int(state_id)) is None
        ],
        dtype=np.int64,
    )

    run_dir.mkdir(parents=True, exist_ok=True)
    rows: dict[str, dict[int, dict[str, float]]] = {arm: {} for arm in ARM_ORDER}
    censuses: list[dict[str, Any]] = []
    for seed in seeds:
        loop_config = deepcopy(base_loop)
        loop_config["seed"] = int(seed)
        execution = loop_module.execute_loop(
            loop_config, oracle, development, split.indices("train")
        )
        per_generation = {
            g: [s for s in execution.samples if int(s.generation) == g]
            for g in range(1, 9)
        }

        seed_everything(int(seed), int(loop_config["runtime"]["threads"]))
        initial = MiniJassMLP(ModelConfig(**loop_config["model"]))
        before = _model_metrics(initial, tensors, oracle, development, batch)

        # `CURRENT_ONLY_WIDE` doit etre genere par le MEME modele que la
        # generation 8 du pack, c'est-a-dire le parent DEPLOYE apres sept
        # generations -- pas le modele initial. Sinon le bras de controle
        # changerait de generateur en meme temps que de volume.
        deployed = _deployed_states_by_rung(
            deepcopy(initial.state_dict()),
            execution.candidate_states,
            execution.core["generations"],
            [0, 7],
        )["7"]
        generator = MiniJassMLP(ModelConfig(**loop_config["model"]))
        generator.load_state_dict(deployed)
        wide_payload = deepcopy(loop_config["self_play"])
        wide_payload["games"] = int(config["current_only_wide_games"])
        wide_payload["game_schedule"] = None
        wide_current = generate_self_play(
            graph,
            generator,
            loop_module._parse_self_play(wide_payload),
            CURRENT_GENERATION,
            int(seed) + int(config["current_only_wide_seed_offset"]),
            starts,
        ).samples

        pools, census = build_pools(per_generation, wide_current, config, int(seed))
        census["seed"] = int(seed)
        censuses.append(census)

        arena_config = ArenaConfig(
            pairs=int(config["arena"]["pairs"]),
            max_plies=int(loop_config["arena"]["max_plies"]),
            search_depth=int(loop_config["arena"]["search_depth"]),
            node_budget=int(loop_config["arena"]["node_budget"]),
            epsilon=0.0,
            confidence_z=1.96,
        )
        for arm in ARM_ORDER:
            seed_everything(int(seed), int(loop_config["runtime"]["threads"]))
            candidate = MiniJassMLP(ModelConfig(**loop_config["model"]))
            candidate.load_state_dict(deepcopy(initial.state_dict()))
            train_from_replay(
                candidate,
                graph,
                pools[arm],
                steps=int(training["steps"]),
                batch_size=int(training["batch_size"]),
                learning_rate=float(training["learning_rate"]),
                weight_decay=float(training["weight_decay"]),
                value_weight=float(training["value_weight"]),
                policy_weight=float(training["policy_weight"]),
                seed=int(seed) + 30_000,
            )
            after = _model_metrics(candidate, tensors, oracle, development, batch)
            arena = run_arena(
                graph,
                candidate,
                initial,
                arena_config,
                int(config["arena"]["seed_base"]) + int(seed),
            )
            rows[arm][int(seed)] = {
                "arena_vs_initial": float(arena["score"]),
                "learning_delta": (
                    after["value_sign_accuracy"] + after["optimal_probability_mass"]
                )
                - (before["value_sign_accuracy"] + before["optimal_probability_mass"]),
                "unique_samples": len(pools[arm]),
            }
        (run_dir / f"seed-{seed}.json").write_text(
            json.dumps(
                {"census": census, "arms": {a: rows[a][int(seed)] for a in ARM_ORDER}},
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

    critical = float(config["scientific_gate"]["paired_confidence_critical_95"])
    aggregate = {
        "arms": {arm: _aggregate_arm(rows[arm], seeds) for arm in ARM_ORDER},
        "contrasts": build_contrasts(rows, seeds, critical),
        "census": censuses,
        "execution": {
            "all_runs_completed": all(len(rows[a]) == len(seeds) for a in ARM_ORDER),
            "seed_count": len(seeds),
            "oracle_used_for_sample_selection": False,
            "execution_host": host,
        },
    }
    recommendation = build_recommendation(aggregate, config["scientific_gate"])
    protocol = {
        "schema": SCHEMA,
        "milestone": "M23",
        "base_gate_config": config["base_gate_config"],
        "paired_seeds": seeds,
        "arms": list(ARM_ORDER),
        "primary_contrast": f"{PRIMARY[0]}_minus_{PRIMARY[1]}",
        "entry_evidence": "M21/M21R/M21T chained +0.1417 P(>0)=99.88%",
        "boundaries": config["boundaries"],
        "execution_host": host,
    }
    result: dict[str, Any] = {
        "schema": SCHEMA,
        "milestone": "M23",
        "status": recommendation["status"],
        "protocol_hash": _digest(protocol),
        "protocol": protocol,
        "aggregate": aggregate,
        "seed_results": rows,
        "recommendation": recommendation,
        "contracts": {
            "oracle_used_for_training": False,
            "oracle_used_for_generation": False,
            "oracle_used_for_sample_selection": False,
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
    compact = {k: v for k, v in result.items() if k != "seed_results"}
    compact["aggregate"] = {k: v for k, v in aggregate.items() if k != "census"}
    compact["census_summary"] = censuses[0] if censuses else {}
    compact["seed_results"] = {
        "omitted_from_compact_output": True,
        "reason": "runner inlines a status summary only under 64 KiB",
        "full_record": "result.json (run_dir, published as an artefact)",
        "row_count": len(ARM_ORDER) * len(seeds),
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
    result = run_m23(
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
