"""Standalone Mini-Jass learning laboratory."""

from .model import ACTION_COUNT, INPUT_COUNT, MiniJassMLP, ModelConfig
from .oracle import OracleArrays, encode_features, load_oracle
from .game_graph import GameGraph
from .experiment import run_experiment_pack
from .loop import run_selfplay_loop
from .split import SplitDefinition, build_split

__all__ = [
    "ACTION_COUNT",
    "INPUT_COUNT",
    "MiniJassMLP",
    "ModelConfig",
    "OracleArrays",
    "GameGraph",
    "SplitDefinition",
    "build_split",
    "encode_features",
    "load_oracle",
    "run_selfplay_loop",
    "run_experiment_pack",
]
