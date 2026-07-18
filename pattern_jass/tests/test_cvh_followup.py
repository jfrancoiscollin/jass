# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import json
import struct
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "jobs" / "tools"))

import cvh_nps_ab as nps  # noqa: E402
import cvh_followup_verdict as verdict  # noqa: E402

TEMPLATES = (
    "cvh-p3-postfix-nps-common-v1.sh",
    "cvh-p3-movetime-v1.sh",
    "cvh-p3-confirm-v1.sh",
)


def rec(wm: int, wk: int, bm: int, bk: int, stm: int = 0, wdl: int = 0) -> bytes:
    return struct.pack("<QQQQBiB", wm, wk, bm, bk, stm, 0, wdl & 0xFF)


def write_jnnw(path: Path, records: list[bytes]) -> None:
    path.write_bytes(b"JNNW" + struct.pack("<I", len(records)) + b"".join(records))


def test_sample_filters_distinguish_p3_and_offgate(tmp_path: Path) -> None:
    # P3: black 5 men vs white 4 men, 9 pieces.
    p3 = rec(sum(1 << i for i in range(20, 24)), 0,
             sum(1 << i for i in range(0, 5)), 0)
    # Off-gate: equal material, 8 pieces.
    off = rec(sum(1 << i for i in range(24, 28)), 0,
              sum(1 << i for i in range(5, 9)), 0)
    path = tmp_path / "x.jnnw"
    write_jnnw(path, [p3, off])

    p3_samples = nps.load_samples(path, 1, 1, "p3")
    off_samples = nps.load_samples(path, 1, 1, "offgate")
    assert p3_samples[0].margin == 1
    assert off_samples[0].margin == 0


def test_match_aggregation_and_gate(tmp_path: Path) -> None:
    a = tmp_path / "a.log"
    b = tmp_path / "b.log"
    a.write_text("noise\nRESULT 10 20 10\n", encoding="utf-8")
    b.write_text("RESULT 12 18 10\n", encoding="utf-8")
    report = verdict.aggregate_match([a, b])
    assert report["n"] == 80
    assert report["rate"] > 0.5
    gate = verdict.match_gate(report, "common_search", min_n=64, min_rate=0.49)
    assert gate["pass"] is True


def test_match_aggregation_rejects_skipped_engine_game(tmp_path: Path) -> None:
    path = tmp_path / "bad.log"
    path.write_text("game skipped (TimeoutError)\nRESULT 0 1 0\n", encoding="utf-8")
    try:
        verdict.aggregate_match([path])
    except ValueError as exc:
        assert "skipped" in str(exc)
    else:
        raise AssertionError("engine skip accepted as draw")


def test_nps_gate_fails_closed_on_az_mismatch() -> None:
    cells = {
        "A": {"searches": 10, "errors": 0, "nps_ratio_vs_a": 1.0},
        "Z": {"searches": 10, "errors": 0, "nps_ratio_vs_a": 1.0},
        "C10": {"searches": 10, "errors": 0, "nps_ratio_vs_a": 0.99},
    }
    general = {"cells": cells, "az_common_searches": 10, "az_move_mismatches": 1}
    p3 = {"cells": cells, "az_common_searches": 10, "az_move_mismatches": 0}
    try:
        verdict.nps_gate(general, p3, 0.98, 0.99, 1.01)
    except ValueError as exc:
        assert "A/Z" in str(exc)
    else:
        raise AssertionError("A/Z mismatch accepted")


def test_paired_confirmation_requires_positive_lower_bound(tmp_path: Path) -> None:
    base = tmp_path / "base.json"
    cand = tmp_path / "cand.json"
    # 500 paired positions: baseline wins 250, candidate wins the same 250 plus 20.
    base_rows = []
    cand_rows = []
    for i in range(500):
        base_rows.append({"index": i, "result": "win" if i < 250 else "draw"})
        cand_rows.append({"index": i, "result": "win" if i < 270 else "draw"})
    base.write_text(json.dumps({"position_results": base_rows}), encoding="utf-8")
    cand.write_text(json.dumps({"position_results": cand_rows}), encoding="utf-8")
    report = verdict.confirmation_gate([base], [cand], min_n=400, min_delta=0.02)
    assert report["paired_n"] == 500
    assert report["delta"] == 0.04
    assert report["ci95_low"] > 0
    assert report["pass"] is True


def test_paired_confirmation_rejects_engine_errors(tmp_path: Path) -> None:
    base = tmp_path / "base.json"
    cand = tmp_path / "cand.json"
    row = [{"index": 0, "result": "win"}]
    base.write_text(json.dumps({"n_errors": 1, "n_pos": 1, "position_results": row}), encoding="utf-8")
    cand.write_text(json.dumps({"n_errors": 0, "n_pos": 1, "position_results": row}), encoding="utf-8")
    try:
        verdict.confirmation_gate([base], [cand], min_n=1, min_delta=0.0)
    except ValueError as exc:
        assert "engine errors" in str(exc)
    else:
        raise AssertionError("confirmation accepted an engine error")


def test_job_templates_are_valid_bash() -> None:
    for name in TEMPLATES:
        subprocess.run(
            ["bash", "-n", str(ROOT / "jobs" / "templates" / name)],
            check=True,
        )


def test_job_templates_pin_engine_and_harness_separately() -> None:
    for name in TEMPLATES:
        text = (ROOT / "jobs" / "templates" / name).read_text(encoding="utf-8")
        assert "CODE_SHA=" in text
        assert "HARNESS_SHA=" in text
        assert 'worktree add --detach "$W/src" "$CODE_SHA"' in text
        assert 'worktree add --detach "$W/harness" "$HARNESS_SHA"' in text
        assert "/root/jass" not in text
        assert "$W/src/tools/cvh_" not in text
        assert "$W/src/jobs/tools/cvh_" not in text
