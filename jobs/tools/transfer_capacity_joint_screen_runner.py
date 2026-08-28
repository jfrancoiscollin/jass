#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Deterministic launcher for transfer_capacity_joint_screen.py.

The initial implementation commit contains one mechanical bracket typo in the
colour-strata list comprehension.  Keep the scientific implementation immutable
and repair exactly that syntax token before compilation.  The replacement is
asserted unique; any other source drift is fatal.  This is a technical-only shim
and changes no scientific parameter, input, target, split, arm, or gate.
"""
from __future__ import annotations
from pathlib import Path

src_path = Path(__file__).with_name("transfer_capacity_joint_screen.py")
src = src_path.read_text(encoding="utf-8")
old = 'mask=np.asarray([int(p) in ids for p in allm["pid"])'
new = 'mask=np.asarray([int(p) in ids for p in allm["pid"]])'
if src.count(old) != 1:
    raise SystemExit(f"expected exactly one mechanical screen syntax typo, found {src.count(old)}")
src = src.replace(old, new)
code = compile(src, str(src_path), "exec")
ns = {"__name__": "__main__", "__file__": str(src_path), "__package__": None}
exec(code, ns, ns)
