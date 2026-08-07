"""Command-line entrypoint for the standalone Mini-Jass laboratory."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .oracle import export_oracle, load_oracle
from .loop import run_selfplay_loop
from .experiment import run_experiment_pack
from .learning_gate import run_learning_gate
from .l2_transfer_gate import run_l2_transfer_gate
from .greedy_confirmation import run_greedy_confirmation
from .greedy_l2_replication import run_greedy_l2_replication
from .wdl_diagnosis import run_wdl_diagnosis
from .policy_gate import run_policy_gate
from .split import build_split, write_split_manifest
from .train import run_training


def main() -> int:
    parser = argparse.ArgumentParser(prog="mini-jass-lab")
    subparsers = parser.add_subparsers(dest="command", required=True)

    export_parser = subparsers.add_parser("export-oracle")
    export_parser.add_argument("--executable", type=Path, required=True)
    export_parser.add_argument("--output", type=Path, required=True)
    export_parser.add_argument("--level", choices=("l1", "l2"), default="l1")

    split_parser = subparsers.add_parser("split")
    split_parser.add_argument("--oracle", type=Path, required=True)
    split_parser.add_argument("--output", type=Path, required=True)
    split_parser.add_argument("--seed", type=int, default=20260806)

    train_parser = subparsers.add_parser("train")
    train_parser.add_argument("--config", type=Path, required=True)
    train_parser.add_argument("--oracle", type=Path, required=True)
    train_parser.add_argument("--run-dir", type=Path, required=True)

    selfplay_parser = subparsers.add_parser("selfplay")
    selfplay_parser.add_argument("--config", type=Path, required=True)
    selfplay_parser.add_argument("--oracle", type=Path, required=True)
    selfplay_parser.add_argument("--run-dir", type=Path, required=True)

    experiment_parser = subparsers.add_parser("experiment-pack")
    experiment_parser.add_argument("--config", type=Path, required=True)
    experiment_parser.add_argument("--oracle", type=Path, required=True)
    experiment_parser.add_argument("--run-dir", type=Path, required=True)

    learning_parser = subparsers.add_parser("learning-gate")
    learning_parser.add_argument("--config", type=Path, required=True)
    learning_parser.add_argument("--oracle", type=Path, required=True)
    learning_parser.add_argument("--run-dir", type=Path, required=True)
    learning_parser.add_argument("--compact-output", type=Path)

    policy_parser = subparsers.add_parser("policy-gate")
    policy_parser.add_argument("--config", type=Path, required=True)
    policy_parser.add_argument("--oracle", type=Path, required=True)
    policy_parser.add_argument("--run-dir", type=Path, required=True)
    policy_parser.add_argument("--compact-output", type=Path)

    l2_parser = subparsers.add_parser("l2-transfer-gate")
    l2_parser.add_argument("--config", type=Path, required=True)
    l2_parser.add_argument("--oracle", type=Path, required=True)
    l2_parser.add_argument("--run-dir", type=Path, required=True)
    l2_parser.add_argument("--compact-output", type=Path)

    diagnosis_parser = subparsers.add_parser("wdl-diagnosis")
    diagnosis_parser.add_argument("--config", type=Path, required=True)
    diagnosis_parser.add_argument("--oracle", type=Path, required=True)
    diagnosis_parser.add_argument("--run-dir", type=Path, required=True)
    diagnosis_parser.add_argument("--compact-output", type=Path)

    confirmation_parser = subparsers.add_parser("greedy-confirmation")
    confirmation_parser.add_argument("--config", type=Path, required=True)
    confirmation_parser.add_argument("--oracle", type=Path, required=True)
    confirmation_parser.add_argument("--run-dir", type=Path, required=True)
    confirmation_parser.add_argument("--compact-output", type=Path)

    greedy_l2_parser = subparsers.add_parser("greedy-l2-replication")
    greedy_l2_parser.add_argument("--config", type=Path, required=True)
    greedy_l2_parser.add_argument("--oracle", type=Path, required=True)
    greedy_l2_parser.add_argument("--run-dir", type=Path, required=True)
    greedy_l2_parser.add_argument("--compact-output", type=Path)

    arguments = parser.parse_args()
    if arguments.command == "export-oracle":
        digest = export_oracle(arguments.executable, arguments.output, arguments.level)
        print(json.dumps({"output": str(arguments.output), "sha256": digest}))
        return 0
    if arguments.command == "split":
        split = build_split(load_oracle(arguments.oracle), arguments.seed)
        write_split_manifest(split, arguments.output)
        print(json.dumps(split.manifest, sort_keys=True))
        return 0
    if arguments.command == "train":
        result = run_training(arguments.config, arguments.oracle, arguments.run_dir)
        print(json.dumps(result, sort_keys=True))
        return 0 if result["gate"]["status"] == "PASS" else 1
    if arguments.command == "selfplay":
        result = run_selfplay_loop(arguments.config, arguments.oracle, arguments.run_dir)
        print(json.dumps(result, sort_keys=True))
        return 0 if result["gate"]["status"] == "PASS" else 1
    if arguments.command == "experiment-pack":
        result = run_experiment_pack(
            arguments.config, arguments.oracle, arguments.run_dir
        )
        print(json.dumps(result, sort_keys=True))
        return 0 if result["gate"]["status"] == "PASS" else 1
    if arguments.command == "learning-gate":
        result = run_learning_gate(
            arguments.config,
            arguments.oracle,
            arguments.run_dir,
            arguments.compact_output,
        )
        print(json.dumps(result, sort_keys=True))
        return 0 if result["gate"]["status"] == "PASS" else 1
    if arguments.command == "policy-gate":
        result = run_policy_gate(
            arguments.config,
            arguments.oracle,
            arguments.run_dir,
            arguments.compact_output,
        )
        print(json.dumps(result, sort_keys=True))
        return 0 if result["gate"]["status"] == "PASS" else 1
    if arguments.command == "l2-transfer-gate":
        result = run_l2_transfer_gate(
            arguments.config,
            arguments.oracle,
            arguments.run_dir,
            arguments.compact_output,
        )
        print(json.dumps(result, sort_keys=True))
        return 0 if result["scientific_gate"]["status"] == "PASS" else 1
    if arguments.command == "wdl-diagnosis":
        result = run_wdl_diagnosis(
            arguments.config,
            arguments.oracle,
            arguments.run_dir,
            arguments.compact_output,
        )
        print(json.dumps(result, sort_keys=True))
        return 0 if result["execution_gate"]["status"] == "PASS" else 1
    if arguments.command == "greedy-confirmation":
        result = run_greedy_confirmation(
            arguments.config,
            arguments.oracle,
            arguments.run_dir,
            arguments.compact_output,
        )
        print(json.dumps(result, sort_keys=True))
        return 0 if result["execution_gate"]["status"] == "PASS" else 1
    if arguments.command == "greedy-l2-replication":
        result = run_greedy_l2_replication(
            arguments.config,
            arguments.oracle,
            arguments.run_dir,
            arguments.compact_output,
        )
        print(json.dumps(result, sort_keys=True))
        return 0 if result["execution_gate"]["status"] == "PASS" else 1
    raise AssertionError("unreachable")


if __name__ == "__main__":
    raise SystemExit(main())
