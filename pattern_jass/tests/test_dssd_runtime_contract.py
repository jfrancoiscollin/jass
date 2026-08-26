from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
PACKER = ROOT / "jobs/tools/dssd_policy_pack.py"
HEADER = ROOT / "src/dssd_move_order_policy.hpp"
MOVEGEN = ROOT / "src/movegen.cpp"
DOC = ROOT / "docs/experiments/L3_DSSD_MOVE_ORDERING_FORCE_V1_20260826.md"

spec = importlib.util.spec_from_file_location("dssd_policy_pack", PACKER)
assert spec and spec.loader
pack_mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = pack_mod
spec.loader.exec_module(pack_mod)


def payload() -> dict:
    return {
        "schema": "jass.deep_sibling_policy.v1",
        "usable": True,
        "eval_feature_width": 120,
        "move_feature_names": list(pack_mod.MOVE_FEATURES),
        "score_convention": "higher_is_better_for_parent",
        "weights": {
            "white_parent": [float(i) / 13.0 for i in range(126)],
            "black_parent": [-float(i) / 17.0 for i in range(126)],
        },
        "training": {"target": "stable_50k_200k_sibling_order"},
    }


def test_packer_is_deterministic_and_preserves_all_frozen_weights() -> None:
    p = payload()
    a = pack_mod.pack(p)
    b = pack_mod.pack(json.loads(json.dumps(p)))
    assert a == b
    lines = a.decode("ascii").splitlines()
    assert lines[0] == "JASS_DSSD_MOVE_ORDER_POLICY_V1"
    assert lines[1] == "120 6"
    white = [float(x) for x in lines[2].split()]
    black = [float(x) for x in lines[3].split()]
    assert len(white) == len(black) == 126
    assert white == p["weights"]["white_parent"]
    assert black == p["weights"]["black_parent"]


def test_packer_rejects_schema_geometry_feature_order_and_bad_weights() -> None:
    p = payload(); p["schema"] = "jass.tb_move_order_policy.v1"
    with pytest.raises(ValueError): pack_mod.pack(p)
    p = payload(); p["eval_feature_width"] = 119
    with pytest.raises(ValueError): pack_mod.pack(p)
    p = payload(); p["move_feature_names"] = list(reversed(pack_mod.MOVE_FEATURES))
    with pytest.raises(ValueError): pack_mod.pack(p)
    p = payload(); p["weights"]["white_parent"] = [0.0] * 125
    with pytest.raises(ValueError): pack_mod.pack(p)
    p = payload(); p["weights"]["black_parent"][4] = float("nan")
    with pytest.raises(ValueError): pack_mod.pack(p)


def test_runtime_loader_is_dormant_fail_closed_and_exact_120_plus_6() -> None:
    h = HEADER.read_text(encoding="utf-8")
    assert 'ENV_VAR = "JASS_DSSD_MOVE_ORDER_POLICY"' in h
    assert 'FILE_MAGIC = "JASS_DSSD_MOVE_ORDER_POLICY_V1"' in h
    assert "MOVE_FEATURES = 6" in h
    assert "TOTAL_FEATURES = scan_eval::NUM_EXTRAS + MOVE_FEATURES" in h
    assert "scan_eval::compute_extras(child, extras)" in h
    for token in (
        "move.num_captures",
        "move.captured & enemy_kings",
        "move.promotes",
        "test(own_kings, move.from)",
        "move.from) / 50.0",
        "move.to) / 50.0",
    ):
        assert token in h
    assert "if (path == nullptr || *path == '\\0') return std::nullopt;" in h
    assert "std::exit(2);" in h


def test_runtime_support_is_exactly_9_through_40_and_capture_only() -> None:
    h = HEADER.read_text(encoding="utf-8")
    m = MOVEGEN.read_text(encoding="utf-8")
    assert "MIN_PARENT_PIECES = 9" in h
    assert "MAX_PARENT_PIECES = 40" in h
    assert "pieces >= MIN_PARENT_PIECES && pieces <= MAX_PARENT_PIECES" in h
    assert "apply_dssd_capture_policy" in m
    assert "out.size() < 2" in m
    assert "dssd_policy::supports_parent(pos)" in m
    # The DSSD hook must live only in the mandatory-capture return branch.
    capture = m.index("generate_captures(pos, out);")
    dssd = m.index("apply_dssd_capture_policy(pos, out);")
    quiet = m.index("generate_quiet_moves(pos, out);")
    assert capture < dssd < quiet
    # Historical exact-8 TB hook remains a separate, disjoint mechanism.
    assert "apply_tb_capture_policy(pos, out);" in m
    assert "popcount(pos.occupied()) != 8" in m


def test_prereg_freezes_same_binary_causal_gate_and_no_value_blending() -> None:
    d = DOC.read_text(encoding="utf-8")
    for token in (
        "same native executable",
        "CURRICULUM + frozen D ordering",
        "0.1 s / move",
        "6,000 games",
        "2026083301",
        "2026083311",
        "2026083302",
        "2026083321",
        "2026083399",
        "319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1",
        "zero CURRICULUM/T refit",
        "zero D refit",
        "zero policy/value blending",
        "zero automatic promotion",
    ):
        assert token in d
    assert "TT move keeps its existing absolute ordering priority" in d
    assert "previous iterative-deepening best move remains hoisted" in d
