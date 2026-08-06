from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "jobs" / "templates" / "l3-trajectory-equal-ab-refit-v1.sh"
PREREG = (
    ROOT
    / "docs"
    / "experiments"
    / "L3_TRAJECTORY_EQUAL_WEIGHT_PREREGISTRATION_20260806.md"
)


def test_template_keeps_a_single_shared_corpus_and_feature_dump() -> None:
    text = TEMPLATE.read_text(encoding="utf-8")
    assert text.count('--data "$W/corpus.jnnw" --feat "$W/corpus.feat"') == 1
    assert 'fit_arm row \\\n  --sample-weights "$W/row-weights.npy"' in text
    assert 'fit_arm game \\\n  --sample-weights "$W/game-weights.npy"' in text
    assert text.count('jobs/tools/l3_trajectory_equal_weights.py') == 1
    assert '--holdout-count "$HOLDOUT"' in text
    assert '--weight-normalization mean-train-1' in text
    assert '--prior-decay 0' in text
    assert 'FOLD_FLAG="${FOLD_FLAG:---exact-fold}"' in text
    assert 'NUMERIC_STACK="${NUMERIC_STACK:-current}"' in text
    assert 'FIT_TIMEOUT="${FIT_TIMEOUT:-21600}"' in text
    assert "ancre HOME home-1314" in text


def test_template_is_fail_closed_and_cannot_promote() -> None:
    text = TEMPLATE.read_text(encoding="utf-8")
    for guard in (
        "FULL_RUN_APPROVED",
        "SCIENTIFIC_GO",
        "NO_AUTOMATIC_CONTINUATION",
        "games_crossing_boundary",
        "openings_crossing_boundary",
        "PGTOL",
        '"row_weights"',
        '"game_weights"',
        "holdout_weighted",
        "uniform_after_normalization",
        "sw_all_used",
        'git show "$EXPECTED_CODE_SHA:$f"',
        'grep -q "g_emasks"',
        "preflight_check",
    ):
        assert guard in text
    assert text.count('grep -q "has_any_capture"') == 2
    assert "src/search.cpp" in text and "src/movegen.cpp" in text
    assert "PROMOTION_AUTHORIZED__FALSE" in text
    assert "AUTOMATIC_NEXT_JOB__NULL" in text
    assert "promotion=true" not in text


def test_preregistration_fixes_two_pools_before_readout() -> None:
    text = PREREG.read_text(encoding="utf-8")
    assert "home-1311" in text
    assert "home-1312" in text
    assert "P(Elo > 0) > 95 %" in text
    assert "Les deux réplications sont exécutées même si A est plate ou négative" in text
    assert "1/sqrt(m_g)" in text
    assert "~17 h 30" in text
