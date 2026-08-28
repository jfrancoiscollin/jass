from pathlib import Path
import os
import shutil
import subprocess


def test_q1000_source_contract():
    s = Path('src/joint_td_q1_q1000_score.cpp').read_text()
    assert "Q1000_BUDGET = 1'000" in s
    assert 'Engine engine(tt_mb);' in s
    assert 'engine.use_book(false);' in s
    assert 'run_fresh_search(engine, child, curriculum.get(), Q1000_BUDGET, tb_cap)' in s
    for token in (
        'fresh_engine_each_sibling', 'fresh_tt_each_search', 'node_limit_mode',
        'threads_per_search', 'higher_is_better_for_parent',
        'JASS_TB_MOVE_ORDER_POLICY', 'JASS_DSSD_MOVE_ORDER_POLICY',
        'fits', 'refits', 'selfplay', 'strength_games', 'promotion_authorized',
    ):
        assert token in s
    assert '1000' in s and 'false' in s


def test_q1000_source_is_syntax_valid_when_native_compiler_available():
    cxx = os.environ.get('CXX') or shutil.which('c++') or shutil.which('g++')
    if not cxx:
        return
    subprocess.run([
        cxx, '-std=c++20', '-fsyntax-only', '-Isrc', '-Ipattern_jass/src',
        'src/joint_td_q1_q1000_score.cpp',
    ], check=True)
