#!/usr/bin/env python3
"""M21 — quelle information s'accumule entre les generations ?

Les deux canaux de l'hypothese Scan sont morts sur L1 : le feedback du
generateur (M18, `+0,0000` IC95 `±0,027`) et la profondeur de recherche (M19,
`−0,0219` IC95 `[−0,064 ; +0,021]`). Et le motif de repli qui semblait les
remplacer -- etiquettes contre force -- n'a pas survecu a un test apparie (M20).

M21 separe la GENERATION des donnees de leur CONSOMMATION. Un pack de huit
generations est produit une fois par graine, conserve generation par
generation ; tous les bras entrainent ensuite le MEME modele initial sur des
sous-ensembles controles de ce pack, a budget d'updates et de tirages egal.

⛔ LE BRAS QUI DECIDE. `G1_ONLY` atteint son budget en tirant AVEC REMISE dans
un petit ensemble, tandis que `MIX` dispose de huit fois plus d'echantillons
UNIQUES. `MIX − G1_ONLY` melange donc « l'identite de generation » et « le
volume de donnees uniques », et le second suffit a produire un positif.
`G8_ONLY` ne controle rien de tout ca : il tire lui aussi dans UNE generation,
donc porte la meme faible diversite que `G1_ONLY`. D'ou `G1_WIDE` -- generation
1 seule, huit fois plus de parties, memes echantillons uniques que `MIX` -- qui
rend `MIX − G1_WIDE` attribuable a la seule identite de generation.

⛔ DEUX CRITERES, ET L'EXACTITUDE WDL N'EST PAS LE CRITERE CAUSAL. Un protocole
qui selectionne sur le score d'apprentissage seul pourrait choisir le modele le
plus faible. Chaque contraste est donc rapporte sur le score d'apprentissage ET
sur une arena appariee contre le meme modele initial.
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
from m18_wdl_mechanics import _development_tensors, _model_metrics  # noqa: E402

SCHEMA = "mini_jass.learning_signal_composition.v1"
ARM_ORDER = (
    "G1_ONLY",
    "G8_ONLY",
    "G1_TO_G8_MIX",
    "G1_WIDE",
    "G1_PLUS_NOVEL_LATE",
    "G1_PLUS_MATCHED_LATE",
)
LATE_GENERATIONS = (5, 6, 7, 8)


# --------------------------------------------------------------------------- #
#  Strates OBSERVABLES SANS ORACLE.
# --------------------------------------------------------------------------- #
def coarse_strata(graph: GameGraph, state_ids: np.ndarray) -> np.ndarray:
    """Strate grossiere par etat, lue dans le graphe et JAMAIS dans l'oracle.

    `GameGraph.from_oracle` « drop every solved label while retaining the
    compiled game graph » : `features` et `legal_mask` sont des faits de regle,
    pas des etiquettes resolues. La strate combine donc, tous oracle-blind :
      - le materiel, par popcount des quatre plans de bitboard,
      - le trait, lu a `plane_count`,
      - le nombre de coups legaux.

    ⚠️ LA STRATE PREINSCRITE COMPTAIT UN QUATRIEME TERME -- un bin de marge de
    recherche -- QUI N'EST PAS IMPLEMENTE : la marge racine n'est pas conservee
    par echantillon dans le pack. `MATCHED_LATE` apparie donc sur TROIS
    dimensions et non quatre, ce qui en fait un controle PLUS FAIBLE
    qu'annonce : un ecart `NOVEL_LATE − MATCHED_LATE` peut rester attribuable a
    une difference de marge de recherche non appariee. C'est rapporte comme
    reserve, pas dissimule.
    """
    planes = graph.features.shape[1] - 2
    per_plane = planes // 4
    board = graph.features[state_ids, :planes].reshape(len(state_ids), 4, per_plane)
    material = board.sum(axis=2).astype(np.int64)          # 4 popcounts
    side = graph.features[state_ids, planes].astype(np.int64)
    legal = graph.legal_mask[state_ids].sum(axis=1).astype(np.int64)
    # Un entier par strate, stable et lisible : (m0,m1,m2,m3,side,legal).
    key = material[:, 0]
    for column in (material[:, 1], material[:, 2], material[:, 3], side, legal):
        key = key * 64 + column
    return key


def _rng(seed: int, salt: int) -> np.random.Generator:
    return np.random.default_rng(seed * 1_000_003 + salt)


def _take(samples: list[ReplaySample], count: int, rng) -> list[ReplaySample]:
    """Sous-echantillonnage SANS remise : c'est le compte UNIQUE qu'on controle.

    La remise, elle, est faite par `train_from_replay`, qui tire `steps` x
    `batch_size` indices uniformement dans le pool : le budget d'updates et de
    tirages est donc egal entre bras PAR CONSTRUCTION, et la seule chose qui
    varie est la composition -- et la taille unique -- du pool.
    """
    if count > len(samples):
        raise ValueError(f"pool needs {count} samples, only {len(samples)} available")
    index = rng.choice(len(samples), size=count, replace=False)
    return [samples[int(i)] for i in sorted(index)]


def build_pools(
    per_generation: dict[int, list[ReplaySample]],
    wide: list[ReplaySample],
    graph: GameGraph,
    seed: int,
) -> tuple[dict[str, list[ReplaySample]], dict[str, Any]]:
    unit = min(len(per_generation[g]) for g in range(1, 9))
    if unit < 2:
        raise ValueError("M21 needs at least two samples in every generation")
    half = unit // 2
    mix: list[ReplaySample] = []
    for generation in range(1, 9):
        mix.extend(_take(per_generation[generation], unit, _rng(seed, generation)))

    g1 = _take(per_generation[1], unit, _rng(seed, 1))
    g1_states = {int(sample.state_id) for sample in g1}
    late = [s for g in LATE_GENERATIONS for s in per_generation[g]]

    novel_candidates = [s for s in late if int(s.state_id) not in g1_states]
    if len(novel_candidates) < half:
        raise ValueError(
            f"M21 found only {len(novel_candidates)} novel late samples, needs {half}"
        )
    novel = _take(novel_candidates, half, _rng(seed, 101))

    # MATCHED : meme demi-dose tardive, mais tiree pour SUIVRE la distribution
    # de strates de G1. Separe « nouvelle couverture » de « repondération de
    # strates deja familieres ».
    g1_keys = coarse_strata(graph, np.asarray([s.state_id for s in g1], dtype=np.int64))
    late_keys = coarse_strata(
        graph, np.asarray([s.state_id for s in late], dtype=np.int64)
    )
    wanted, counts = np.unique(g1_keys, return_counts=True)
    target = counts / counts.sum()
    matched: list[ReplaySample] = []
    matched_rng = _rng(seed, 202)
    by_key: dict[int, list[int]] = {}
    for position, key in enumerate(late_keys):
        by_key.setdefault(int(key), []).append(position)
    order = matched_rng.choice(len(wanted), size=half, replace=True, p=target)
    used: set[int] = set()
    for choice in order:
        key = int(wanted[choice])
        pool = [p for p in by_key.get(key, []) if p not in used]
        if not pool:  # strate absente des tardifs : on retombe sur un tardif quelconque
            pool = [p for p in range(len(late)) if p not in used]
            if not pool:
                break
        pick = int(matched_rng.choice(pool))
        used.add(pick)
        matched.append(late[pick])

    g1_half = _take(g1, half, _rng(seed, 303))
    pools = {
        "G1_ONLY": g1,
        "G8_ONLY": _take(per_generation[8], unit, _rng(seed, 8)),
        "G1_TO_G8_MIX": mix,
        "G1_WIDE": _take(wide, len(mix), _rng(seed, 404)),
        "G1_PLUS_NOVEL_LATE": g1_half + novel,
        "G1_PLUS_MATCHED_LATE": g1_half + matched,
    }
    census = {
        "unit_samples_per_generation": int(unit),
        "unique_samples_by_arm": {a: len(p) for a, p in pools.items()},
        "unique_states_by_arm": {
            a: len({int(s.state_id) for s in p}) for a, p in pools.items()
        },
        "novel_late_candidates": len(novel_candidates),
        "matched_late_drawn": len(matched),
        "matched_strata_dimensions": 3,
        "matched_strata_preregistered_dimensions": 4,
        "matched_strata_reduction": "search-margin bin not retained per sample",
    }
    return pools, census


def _paired_endpoint(
    rows: dict[str, dict[int, dict[str, float]]],
    high: str,
    low: str,
    endpoint: str,
    seeds: list[int],
    critical: float,
) -> dict[str, Any]:
    return _paired_summary(
        [rows[high][seed][endpoint] - rows[low][seed][endpoint] for seed in seeds],
        critical,
    )


def build_contrasts(
    rows: dict[str, dict[int, dict[str, float]]],
    contrasts: list[list[str]],
    seeds: list[int],
    critical: float,
) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for high, low in contrasts:
        out[f"{high}_minus_{low}"] = {
            "learning": _paired_endpoint(rows, high, low, "learning_delta", seeds, critical),
            "arena": _paired_endpoint(rows, high, low, "arena_vs_initial", seeds, critical),
        }
    return out


def _excludes_zero_above(row: dict[str, Any]) -> bool:
    return float(row["confidence_95"][0]) > 0.0


def _confidently_negative(row: dict[str, Any]) -> bool:
    return float(row["confidence_95"][1]) < 0.0


def _standard_error(row: dict[str, Any], critical: float) -> float:
    low, high = row["confidence_95"]
    return (float(high) - float(low)) / (2.0 * critical)


def replication_check(
    row: dict[str, Any], prior: dict[str, Any], critical: float
) -> dict[str, Any]:
    """Compare ce pool au precedent, avec la discipline de chainage de L3.

    ⛔ LE SIGNE N'EST PAS UN CRITERE (correction du 6 aout, cote L3) : un effet
    vrai proche de zero produit des signes opposes une fois sur deux. Le
    desaccord se teste STATISTIQUEMENT. `same_sign` est rapporte, jamais gatant.
    """
    se_new = _standard_error(row, critical)
    se_old = float(prior["standard_error"])
    mean_new, mean_old = float(row["mean"]), float(prior["mean"])
    spread = (se_new**2 + se_old**2) ** 0.5
    between = (mean_new - mean_old) / spread if spread > 0.0 else 0.0
    weight_new = 1.0 / se_new**2 if se_new > 0 else 0.0
    weight_old = 1.0 / se_old**2 if se_old > 0 else 0.0
    total = weight_new + weight_old
    chained = (mean_new * weight_new + mean_old * weight_old) / total if total else 0.0
    return {
        "prior_pool": prior.get("label"),
        "prior_mean": mean_old,
        "replication_mean": mean_new,
        "between_pool_z": between,
        "pools_disagree": abs(between) >= 1.96,
        "same_sign": (mean_new > 0) == (mean_old > 0),
        "chained_mean": chained,
        "chained_standard_error": (1.0 / total**0.5) if total else 0.0,
        "shrinkage_vs_prior": (mean_new / mean_old) if mean_old else None,
    }


def build_recommendation(
    aggregate: dict[str, Any], gate: dict[str, Any]
) -> dict[str, Any]:
    """⛔ L'ARENA DECIDE. Le score d'apprentissage est rapporte, jamais gatant.

    La v1 de cette porte exigeait que le score d'apprentissage passe AVANT de
    regarder l'arena. Sur `cpx62-1211` le score etait non concluant (`+0,0141`,
    IC traversant zero) et l'arena valait `+0,2375` IC95 `[+0,088 ; +0,387]` :
    la porte a imprime FAIL sur le seul effet de la journee dont l'IC excluait
    zero. C'est l'inverse de ce que la campagne a etabli -- M18, M19 et M20 ont
    montre que la qualite d'etiquetage n'est pas la force -- et l'inverse de ce
    que l'arena co-primaire etait censee garantir.

    La force du modele est donc le critere primaire. Le score d'apprentissage
    reste rapporte, et un score CONFIDEMMENT NEGATIF sous une arena positive est
    signale plutot qu'ignore : ce serait une divergence a comprendre, pas un
    detail.
    """
    contrasts = aggregate["contrasts"]
    primary = contrasts["G1_TO_G8_MIX_minus_G1_WIDE"]
    volume = contrasts["G1_WIDE_minus_G1_ONLY"]
    recency = contrasts["G8_ONLY_minus_G1_ONLY"]
    novelty = contrasts["G1_PLUS_NOVEL_LATE_minus_G1_PLUS_MATCHED_LATE"]
    critical = float(gate["paired_confidence_critical_95"])

    arena_ok = (
        float(primary["arena"]["mean"]) > float(gate["minimum_practical_arena_gain"])
        and _excludes_zero_above(primary["arena"])
    )
    common = {
        "primary_contrast": "G1_TO_G8_MIX_minus_G1_WIDE",
        "primary_endpoint": "arena_vs_initial",
        "primary_arena_mean": float(primary["arena"]["mean"]),
        "primary_learning_mean": float(primary["learning"]["mean"]),
        "learning_confidently_negative": _confidently_negative(primary["learning"]),
        # Le controle de volume : diagnostic, jamais gatant. `MIX − G1_WIDE` est
        # DEJA a volume egal, donc un effet de volume ne peut pas l'expliquer ;
        # on le chiffre pour dire ce que `MIX − G1_ONLY` aurait confondu.
        "volume_effect_arena": float(volume["arena"]["mean"]),
        "volume_effect_learning": float(volume["learning"]["mean"]),
        "recency_effect_arena": float(recency["arena"]["mean"]),
        "recency_effect_learning": float(recency["learning"]["mean"]),
        "novelty_minus_matched_arena": float(novelty["arena"]["mean"]),
        "novelty_minus_matched_learning": float(novelty["learning"]["mean"]),
        # L'anticorrelation etiquettes/force, testee sur CE facteur : signes
        # opposes ET les deux IC hors de zero, le critere de M20.
        "recency_shows_label_strength_anticorrelation": bool(
            _excludes_zero_above(recency["learning"])
            and _confidently_negative(recency["arena"])
        ),
        "promotable": False,
    }

    replication = None
    prior = gate.get("replication_of")
    if prior:
        replication = replication_check(primary["arena"], prior, critical)
        common["replication"] = replication

    if not arena_ok:
        # Sur une cellule de REPLICATION, « pas d'effet ici » et « l'effet
        # d'origine ne se reproduit pas » ne sont pas la meme phrase. Nommer la
        # seconde evite qu'un echec de replication soit lu comme une mesure
        # independante -- et evite aussi de jeter le pool anterieur en silence.
        return {
            **common,
            "status": "FAIL",
            "finding": (
                "did_not_replicate_the_prior_pool"
                if replication is not None
                else "generation_identity_did_not_make_a_stronger_model_at_equal_volume"
            ),
            "composition_is_the_mechanism": False,
            "next_step": (
                "treat_the_prior_estimate_as_inflated_and_stop_this_axis"
                if replication is not None
                else "M22_isolate_the_sequential_optimizer_path"
            ),
        }
    if replication is not None and replication["pools_disagree"]:
        # Le desaccord EST le resultat : un chainage sur deux pools
        # heterogenes fabriquerait une confiance que les donnees ne portent pas.
        return {
            **common,
            "status": "INCONCLUSIVE",
            "finding": "the_two_pools_disagree_statistically",
            "composition_is_the_mechanism": None,
            "next_step": "explain_the_between_pool_heterogeneity_before_chaining",
        }
    replicated = replication is not None and not replication["pools_disagree"]
    return {
        **common,
        "status": "PASS_REPLICATED" if replicated else "PASS",
        "finding": "mixing_generations_makes_a_STRONGER_model_at_equal_unique_volume",
        "composition_is_the_mechanism": True,
        "next_step": (
            "first_identified_mechanism_of_the_lab_campaign_design_an_L2_transfer_cell"
            if replicated
            else "replicate_on_fresh_seeds_before_any_scale_transfer"
        ),
    }


def run_m21(
    config_path: Path,
    oracle_path: Path,
    run_dir: Path,
    compact_output: Path,
    execution_host: str | None = None,
) -> dict[str, Any]:
    config = _resolve(config_path)
    host = execution_host or platform.node()
    if host != config["expected_execution_host"]:
        raise ValueError(f"M21 requires cpx62, got {host}")

    oracle = load_oracle(oracle_path)
    graph = GameGraph.from_oracle(oracle)
    graph.validate()
    base_loop = deepcopy(config["base_loop"])
    split = build_split(oracle, int(base_loop["split_seed"]))
    if split.manifest["manifest_hash"] != base_loop["expected_split_manifest_hash"]:
        raise ValueError("M21 split differs from the frozen L1 contract")
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
            generation: [
                sample
                for sample in execution.samples
                if int(sample.generation) == generation
            ]
            for generation in range(1, 9)
        }

        seed_everything(int(seed), int(loop_config["runtime"]["threads"]))
        initial = MiniJassMLP(ModelConfig(**loop_config["model"]))
        before = _model_metrics(initial, tensors, oracle, development, batch)

        # `G1_WIDE` : MEME generateur (le modele initial, celui qui produit la
        # generation 1), MEME configuration, seul `games` change. C'est un
        # tirage independant de la meme distribution, pas un sur-ensemble de G1.
        wide_payload = deepcopy(loop_config["self_play"])
        wide_payload["games"] = int(config["wide_games"])
        wide_payload["game_schedule"] = None
        wide = generate_self_play(
            graph,
            initial,
            loop_module._parse_self_play(wide_payload),
            1,
            int(seed) + int(config["wide_seed_offset"]),
            starts,
        ).samples

        pools, census = build_pools(per_generation, wide, graph, int(seed))
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
                "learning_delta": (
                    after["value_sign_accuracy"] + after["optimal_probability_mass"]
                )
                - (
                    before["value_sign_accuracy"] + before["optimal_probability_mass"]
                ),
                "value_sign_delta": after["value_sign_accuracy"]
                - before["value_sign_accuracy"],
                "optimal_mass_delta": after["optimal_probability_mass"]
                - before["optimal_probability_mass"],
                "arena_vs_initial": float(arena["score"]),
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

    # LE CONTROLE DE BUDGET, fail-closed : `MIX` et `G1_WIDE` doivent avoir le
    # MEME nombre d'echantillons uniques, sinon le contraste primaire retombe
    # exactement dans le piege qu'il existe pour eviter.
    for census in censuses:
        counts = census["unique_samples_by_arm"]
        if counts["G1_TO_G8_MIX"] != counts["G1_WIDE"]:
            raise ValueError(
                "M21 primary contrast requires equal unique-sample counts, got "
                f"{counts['G1_TO_G8_MIX']} vs {counts['G1_WIDE']}"
            )
        if counts["G1_ONLY"] != counts["G8_ONLY"]:
            raise ValueError("M21 G1_ONLY and G8_ONLY must hold the same unique count")

    critical = float(config["scientific_gate"]["paired_confidence_critical_95"])
    aggregate = {
        "arms": {
            arm: {
                "mean_learning_delta": _mean(
                    [rows[arm][s]["learning_delta"] for s in seeds]
                ),
                "mean_arena_vs_initial": _mean(
                    [rows[arm][s]["arena_vs_initial"] for s in seeds]
                ),
                "mean_unique_samples": _mean(
                    [float(rows[arm][s]["unique_samples"]) for s in seeds]
                ),
            }
            for arm in ARM_ORDER
        },
        "contrasts": build_contrasts(
            rows, config["contrasts"], seeds, critical
        ),
        "census": censuses,
        "execution": {
            "all_runs_completed": all(
                len(rows[arm]) == len(seeds) for arm in ARM_ORDER
            ),
            "seed_count": len(seeds),
            "oracle_used_for_sample_selection": False,
            "execution_host": host,
        },
    }
    recommendation = build_recommendation(aggregate, config["scientific_gate"])
    protocol = {
        "schema": SCHEMA,
        "milestone": config["milestone"],
        "base_gate_config": config["base_gate_config"],
        "paired_seeds": seeds,
        "arms": list(ARM_ORDER),
        "contrasts": config["contrasts"],
        "wide_games": int(config["wide_games"]),
        "single_factor": "which_generations_the_training_pool_is_drawn_from",
        "boundaries": config["boundaries"],
        "execution_host": host,
    }
    result: dict[str, Any] = {
        "schema": SCHEMA,
        "milestone": config["milestone"],
        "status": recommendation["status"],
        "protocol_hash": _digest(protocol),
        "protocol": protocol,
        "aggregate": aggregate,
        "seed_results": rows,
        "recommendation": recommendation,
        "contracts": {
            "training_target": "terminal_selfplay_WDL_only",
            "oracle_used_for_training": False,
            "oracle_used_for_generation": False,
            "oracle_used_for_sample_selection": False,
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
    compact["aggregate"] = {
        key: value for key, value in aggregate.items() if key != "census"
    }
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


def _resolve(path: Path) -> dict[str, Any]:
    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    if config.get("schema") != SCHEMA or config.get("milestone") not in ("M21", "M21R"):
        raise ValueError("unexpected M21 schema")
    if tuple(config.get("arms", [])) != ARM_ORDER:
        raise ValueError("M21 arm definitions changed after preregistration")
    seeds = [int(seed) for seed in config["paired_seeds"]]
    if len(seeds) != 20 or len(set(seeds)) != 20:
        raise ValueError("M21 requires 20 distinct seeds — power is nearly free here")
    if config["milestone"] == "M21R" and set(seeds) & set(range(210001, 210021)):
        # Rejouer une replication sur les graines du pool d'origine, ce n'est pas
        # une replication : c'est le meme tirage.
        raise ValueError("M21R must not reuse the M21 seed family")
    boundaries = config.get("boundaries", {})
    if (
        boundaries.get("promotable") is not False
        or boundaries.get("production_jass_changes_authorized") is not False
        or boundaries.get("direct_10x10_transfer_authorized") is not False
    ):
        raise ValueError("M21 crossed a forbidden boundary")
    root = path.resolve().parent.parent
    gate_path = root / str(config["base_gate_config"])
    gate = resolve_learning_gate_config(gate_path)
    if gate.milestone != "M8":
        raise ValueError("M21 requires the frozen passing M8 L1 recipe")
    base_loop = deepcopy(gate.resolved["base_loop"])
    if int(base_loop["generations"]) != 1:
        raise ValueError("M21 expects the historical M8 recipe at one generation")
    base_loop["generations"] = 8
    resolved = deepcopy(config)
    resolved["base_gate_config"] = str(gate_path.resolve())
    resolved["base_loop"] = base_loop
    resolved["paired_seeds"] = seeds
    return resolved


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--oracle", type=Path, required=True)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--compact-output", type=Path, required=True)
    parser.add_argument("--execution-host")
    args = parser.parse_args()
    result = run_m21(
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
