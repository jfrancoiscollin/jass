from pathlib import Path
import os
import shutil
import subprocess
import tempfile

from jobs.tools.joint_td_q1_teacher_source import BUDGET_NEW, BUDGET_OLD, render


def test_q1_teacher_render_contract():
    src = Path('src/deep_sibling_teacher.cpp').read_text()
    out = render(src)
    assert BUDGET_OLD not in out
    assert BUDGET_NEW in out
    assert 'q5k_parent' not in out
    assert 'q1000_parent' in out
    for token in ('q50_parent', 'q200_parent', 'fresh_tt_each_search', 'node_limit_mode'):
        assert token in out
    assert '#define load_pattern_jass_network load_eval_network' in out


def test_q1_teacher_generated_source_is_syntax_valid_when_compiler_available():
    cxx = os.environ.get('CXX') or shutil.which('c++') or shutil.which('g++')
    if not cxx:
        return
    src = Path('src/deep_sibling_teacher.cpp').read_text()
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / 'joint_td_q1_teacher.cpp'
        p.write_text(render(src))
        subprocess.run([
            cxx, '-std=c++20', '-fsyntax-only', '-Isrc', '-Ipattern_jass/src', str(p)
        ], check=True)
