"""Command-line entrypoint for Mini-Jass M3."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .oracle import export_oracle, load_oracle
from .split import build_split, write_split_manifest
from .train import run_training


def main() -> int:
    parser = argparse.ArgumentParser(prog="mini-jass-lab")
    subparsers = parser.add_subparsers(dest="command", required=True)

    export_parser = subparsers.add_parser("export-oracle")
    export_parser.add_argument("--executable", type=Path, required=True)
    export_parser.add_argument("--output", type=Path, required=True)

    split_parser = subparsers.add_parser("split")
    split_parser.add_argument("--oracle", type=Path, required=True)
    split_parser.add_argument("--output", type=Path, required=True)
    split_parser.add_argument("--seed", type=int, default=20260806)

    train_parser = subparsers.add_parser("train")
    train_parser.add_argument("--config", type=Path, required=True)
    train_parser.add_argument("--oracle", type=Path, required=True)
    train_parser.add_argument("--run-dir", type=Path, required=True)

    arguments = parser.parse_args()
    if arguments.command == "export-oracle":
        digest = export_oracle(arguments.executable, arguments.output)
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
    raise AssertionError("unreachable")


if __name__ == "__main__":
    raise SystemExit(main())
