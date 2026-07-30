#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "jobs/tools/l3_static_blend_probe.py"
SPEC = importlib.util.spec_from_file_location("l3_static_blend_probe", TOOL)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def main() -> int:
    rows = [
        {"fen": "W:W31:B20", "parent_a": 10, "parent_b": 20, "blend": 15},
        {"fen": "B:W31:B20", "parent_a": -7, "parent_b": 4, "blend": -2},
    ]
    payload = MODULE.summarize(rows, 0.5, 2.0)
    assert payload["passed"] is True
    assert payload["positions"] == 2
    assert payload["max_abs_residual"] == 0.5

    try:
        MODULE.summarize(
            [{"fen": "W:W31:B20", "parent_a": 0, "parent_b": 0, "blend": 3}],
            0.5,
            2.0,
        )
    except ValueError as exc:
        assert "exceeds" in str(exc)
    else:
        raise AssertionError("excessive residual accepted")

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "probe.fen"
        path.write_text("W:W31:B20\nB:W31:B20\n", encoding="utf-8")
        assert MODULE.load_fens(path, 2) == ["W:W31:B20", "B:W31:B20"]
        path.write_text("W:W31:B20\nW:W31:B20\n", encoding="utf-8")
        try:
            MODULE.load_fens(path, 2)
        except ValueError as exc:
            assert "not unique" in str(exc)
        else:
            raise AssertionError("duplicate FENs accepted")
    print("ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
