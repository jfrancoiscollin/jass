#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Mechanical launcher for joint_td_candidate_freeze.py.

The immutable 1614 transfer screen source contains the already-documented
single missing bracket in the colour-strata comprehension.  The 1614 screen was
run through transfer_capacity_joint_screen_runner.py, which repairs exactly that
one token before compilation.  The freeze tool imports the same implementation
as a module; preload a module with the identical one-token repair, then execute
the freeze tool unchanged.  No scientific constant, seed, candidate, fit,
metric or gate is modified here.
"""
from __future__ import annotations

from pathlib import Path
import runpy
import sys
import types

HERE = Path(__file__).resolve().parent
screen_path = HERE / "transfer_capacity_joint_screen.py"
src = screen_path.read_text(encoding="utf-8")
old = 'mask=np.asarray([int(p) in ids for p in allm["pid"])'
new = 'mask=np.asarray([int(p) in ids for p in allm["pid"]])'
if src.count(old) != 1:
    raise SystemExit(f"expected exactly one immutable 1614 mechanical syntax token, found {src.count(old)}")

module = types.ModuleType("transfer_capacity_joint_screen")
module.__file__ = str(screen_path)
module.__package__ = None
code = compile(src.replace(old, new), str(screen_path), "exec")
exec(code, module.__dict__, module.__dict__)
sys.modules["transfer_capacity_joint_screen"] = module

runpy.run_path(str(HERE / "joint_td_candidate_freeze.py"), run_name="__main__")
