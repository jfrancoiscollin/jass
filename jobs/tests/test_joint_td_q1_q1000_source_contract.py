from pathlib import Path


def test_q1000_source_contract():
    s = Path('src/joint_td_q1_q1000_score.cpp').read_text()
    assert "Q1000_BUDGET = 1'000" in s
    assert 'Engine engine(tt_mb);' in s
    assert 'engine.use_book(false);' in s
    assert 'run_fresh_search(engine, child, curriculum.get(), Q1000_BUDGET, tb_cap)' in s
    assert 'fresh_engine_each_sibling\\\": true' in s
    assert 'fresh_tt_each_search\\\": true' in s
    assert 'node_limit_mode\\\": \\\"exact' in s
    assert 'threads_per_search\\\": 1' in s
    assert 'score_convention\\\": \\\"higher_is_better_for_parent' in s
    assert 'JASS_TB_MOVE_ORDER_POLICY' in s
    assert 'JASS_DSSD_MOVE_ORDER_POLICY' in s
    for guard in ('fits', 'refits', 'selfplay', 'strength_games'):
        assert f'\\\"{guard}\\\": 0' in s
    assert 'promotion_authorized\\\": false' in s
