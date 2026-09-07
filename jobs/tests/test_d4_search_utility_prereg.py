import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "docs/experiments/L3_D4_SEARCH_UTILITY_ORDERING_PREREGISTRATION_V1_20260907.json"
DOC = ROOT / "docs/experiments/L3_D4_SEARCH_UTILITY_ORDERING_PREREGISTRATION_V1_20260907.md"


def load_contract():
    return json.loads(CONTRACT.read_text(encoding="utf-8"))


def test_d4_search_utility_contract_is_frozen():
    c = load_contract()
    assert c["schema"] == "jass.d4.search_utility_ordering_preregistration.v1"
    assert c["predecessor"]["autopsy_verdict"] == "D3_RUNTIME_TERMINAL_AUTOPSY_COMPLETE_V1"
    assert c["predecessor"]["autopsy_classification"] == "BROAD_EQUAL_NODE_SEARCH_EFFICIENCY_DEGRADATION"
    assert c["preregistration_side_effects"] == {
        "fresh_positions": 0,
        "teacher_searches": 0,
        "fits": 0,
        "strength_games": 0,
        "promotions": 0,
        "bakes": 0,
    }

    d = c["dataset"]
    assert d["candidate_roots"] == 30000
    assert d["generation_seed"] == 2026111501
    assert d["selector_prefix"] == "2026111502:"
    assert d["selected_roots"] == 4000
    assert d["root_split"] == {"train": 3200, "valid": 400, "test": 400}
    assert d["teacher_exact_nodes"] == 50000
    assert d["examples"] == {"train": 96000, "valid": 12000, "test": 12000}
    assert d["eligibility"]["candidate_scope"] == 4
    assert d["eligibility"]["label"] == "observed_beta_cutoff_causing_move_within_legacy_top4_non_tt"

    assert c["phases"] == {"P0": [33, 40], "P1": [25, 32], "P2": [17, 24], "P3": [9, 16]}
    assert c["canonicalization"]["white_square_map"] == "51-sq"
    assert len(c["features"]) == 24
    assert c["model"]["trainable_parameters"] == 96
    assert c["model"]["fits"] == 1
    assert c["model"]["model_searches"] == 0
    assert c["model"]["l2"] == 0.001
    assert c["model"]["max_iter"] == 500
    assert c["model"]["maxcor"] == 10
    assert c["model"]["gtol"] == 1e-6
    assert c["model"]["temperature"] is None
    assert c["model"]["runtime_scale"] is None

    assert c["offline_gate"]["bootstrap_repetitions"] == 200000
    assert c["offline_gate"]["bootstrap_seed"] == 2026111503
    assert c["runtime"]["tt_priority"] == "unchanged_absolute"
    assert c["runtime"]["scope"] == "first_up_to_4_legacy_non_tt_moves"
    assert c["runtime"]["evaluation_calls_for_scoring"] == 0
    assert c["runtime"]["d3_calls"] == 0

    p = c["zero_game_preflight"]
    assert p["fixtures"] == 256
    assert p["seed"] == 2026111599
    assert p["exact_nodes"] == 20000
    assert p["median_wall_ratio_max"] == 1.05
    assert p["strength_games"] == 0

    en = c["equal_node"]
    assert en["generation_seed"] == 2026111601
    assert en["selector_prefix"] == "2026111602:"
    assert en["primary_openings"] == 1000
    assert en["harness_openings"] == 100
    assert en["exact_nodes_per_move"] == 20000
    assert en["bootstrap_repetitions"] == 200000
    assert en["bootstrap_seed"] == 2026111603

    et = c["equal_time"]
    assert et["authorized_only_after"] == "D4_RUNTIME_EQUAL_NODE_ESTABLISHED_V1"
    assert et["generation_seed"] == 2026111701
    assert et["selector_prefix"] == "2026111702:"
    assert et["games"] == 6000
    assert et["movetime_seconds"] == 0.1
    assert et["bootstrap_seed"] == 2026111703
    assert et["automatic_promotion"] is False
    assert et["automatic_bake"] is False

    forbidden = set(c["forbidden"])
    for key in (
        "1857_game_outcomes_as_labels_weights_filters_or_model_selection",
        "qscore",
        "B3_full_ladder_1843_targets",
        "D3_retuning",
        "D3_D4_blending",
        "hyperparameter_sweep",
        "automatic_promotion",
        "automatic_bake",
    ):
        assert key in forbidden
    assert c["authorization"] == "implementation_and_preflight_plumbing_only_no_execution"


def test_human_prereg_repeats_non_negotiable_boundaries():
    text = DOC.read_text(encoding="utf-8")
    for needle in (
        "D3 is scientifically closed",
        "observed beta-cutoff",
        "exactly 96 trainable",
        "median over fixture-level candidate/control wall-time ratios",
        "D4_RUNTIME_EQUAL_NODE_ESTABLISHED_V1",
        "does **not** authorize automatic promotion or bake",
        "1857 game outcomes",
    ):
        assert needle in text
