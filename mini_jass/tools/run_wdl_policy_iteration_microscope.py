#!/usr/bin/env python3
"""M18: causal microscope of a Scan-like self-improving WDL loop."""
from __future__ import annotations

import argparse
from copy import deepcopy
import json
from pathlib import Path
import platform
from typing import Any

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from mini_jass_lab.game_graph import GameGraph  # noqa: E402
from mini_jass_lab.oracle import load_oracle  # noqa: E402
from mini_jass_lab.split import build_split  # noqa: E402

from m18_wdl_analysis import (  # noqa: E402,F401
    _assert_paired_start_schedules,
    _build_contrasts,
    build_recommendation,
)
from m18_wdl_config import (  # noqa: E402,F401
    ARM_ORDER,
    EXPECTED_ARMS,
    EXPECTED_SEEDS,
    SCHEMA,
    _digest,
    _paired_summary,
    _resolve_config,
)
from m18_wdl_execution import _aggregate_arm, _run_arm_seed  # noqa: E402
from m18_wdl_mechanics import (  # noqa: E402,F401
    _deployed_states_by_rung,
    _development_tensors,
    _frozen_generator,
    _verify_promotion_contract,
    _wdl_quality,
)


STATUS_SUMMARY_MAX_FILE_BYTES = 64 * 1024


def compact_result(result: dict[str, Any], row_count: int) -> dict[str, Any]:
    """Le summary que le plan de controle peut reellement inliner.

    Le runner n'inline un summary dans le statut GitOps que sous 64 KiB, et il
    saute le fichier EN SILENCE au-dela : `cpx62-1206` a rendu 530 KiB -- 20
    lignes bras x graine, chacune avec ses matrices de confusion par barreau --
    et son verdict n'a existe que dans le stockage objet. On garde donc
    l'agregat, les contrastes, la recommandation et les hashes (tout ce qui
    decide) et on renvoie au `run_dir` pour les lignes par graine, qui partent
    de toute facon en artefacts.
    """
    compact = {key: value for key, value in result.items() if key != "seed_results"}
    compact["seed_results"] = {
        "omitted_from_compact_output": True,
        "reason": "runner inlines a status summary only under 64 KiB",
        "full_record": "result.json (run_dir, published as an artefact)",
        "row_count": row_count,
    }
    return compact


def run_m18(
    config_path: Path,
    oracle_path: Path,
    run_dir: Path,
    compact_output: Path,
    execution_host: str | None = None,
) -> dict[str, Any]:
    config = _resolve_config(config_path)
    host = execution_host or platform.node()
    if host != config["expected_execution_host"]:
        raise ValueError(f"M18 requires cpx62, got {host}")

    oracle = load_oracle(oracle_path)
    graph = GameGraph.from_oracle(oracle)
    graph.validate()
    base_loop = deepcopy(config["base_loop"])
    split = build_split(oracle, int(base_loop["split_seed"]))
    if split.manifest["manifest_hash"] != base_loop["expected_split_manifest_hash"]:
        raise ValueError("M18 split differs from the frozen L1 contract")
    development_indices = split.indices("development")
    train_indices = split.indices("train")
    tensors = _development_tensors(oracle, graph)

    run_dir.mkdir(parents=True, exist_ok=True)
    arm_rows: dict[str, list[dict[str, Any]]] = {arm: [] for arm in ARM_ORDER}
    for arm in ARM_ORDER:
        spec = EXPECTED_ARMS[arm]
        for seed in EXPECTED_SEEDS:
            arm_rows[arm].append(
                _run_arm_seed(
                    arm=arm,
                    spec=spec,
                    seed=seed,
                    base_loop=base_loop,
                    oracle=oracle,
                    graph=graph,
                    development_indices=development_indices,
                    training_start_indices=train_indices,
                    tensors=tensors,
                    config=config,
                    run_dir=run_dir,
                )
            )

    _assert_paired_start_schedules(arm_rows)
    rungs = [int(rung) for rung in config["report_rungs"]]
    arms = {arm: _aggregate_arm(rows, rungs) for arm, rows in arm_rows.items()}
    critical = float(config["scientific_gate"]["paired_confidence_critical_95"])
    contrasts = _build_contrasts(arm_rows, critical)
    aggregate = {
        "arms": arms,
        "contrasts": contrasts,
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
            "execution_host": host,
        },
    }
    recommendation = build_recommendation(aggregate, config["scientific_gate"])
    protocol = {
        "schema": SCHEMA,
        "milestone": "M18",
        "base_ladder_config": config["base_ladder_config"],
        "base_gate_config": config["base_gate_config"],
        "paired_seeds": EXPECTED_SEEDS,
        "ladder_max": 8,
        "report_rungs": rungs,
        "arms": EXPECTED_ARMS,
        "primary_contrasts": config["primary_contrasts"],
        "secondary_contrasts": config["secondary_contrasts"],
        "observer_contract": config["observer_contract"],
        "boundaries": config["boundaries"],
        "execution_host": host,
    }
    result: dict[str, Any] = {
        "schema": SCHEMA,
        "milestone": "M18",
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
    compact = compact_result(result, sum(len(rows) for rows in arm_rows.values()))
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
    result = run_m18(
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
