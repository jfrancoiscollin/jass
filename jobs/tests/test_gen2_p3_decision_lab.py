#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "jobs" / "tools"))
sys.path.insert(0, str(ROOT / "pattern_jass" / "tools"))

import conversion_teacher as ct
import gen2_p3_decision_lab as lab
import gen2_p3_decision_verdict as verdict
import p3_sibling_ranker as ranker


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_p3_filter() -> None:
    win = ct.fen_to_record("W:W31,32,33,34,35:B1,2,3,4", 1)
    loss = ct.fen_to_record("W:W31,32,33,34,35:B1,2,3,4", -1)
    check(lab.material_leader(win) == ("W", 1, 9), "material leader")
    check(lab.p3_leader_winner(win) == "W", "leader-winner accepted")
    check(lab.p3_leader_winner(loss) is None, "leader-loser rejected")


def test_paired_stats() -> None:
    got = lab.paired_stats([1, 0, 1, -1])
    check(got["n"] == 4 and abs(float(got["delta"]) - 0.25) < 1e-12, "paired mean")


def test_baseline_fail_closed() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        good = root / "good.json"
        good.write_text(json.dumps({"n_errors": 0, "position_results": [{"index": 2, "result": "win"}]}))
        check(lab.load_baseline([good]) == {2: "win"}, "baseline load")
        try:
            lab.load_baseline([good], "different-pool")
        except ValueError:
            pass
        else:
            raise AssertionError("baseline pool mismatch accepted")
        bad = root / "bad.json"
        bad.write_text(json.dumps({"n_errors": 1, "position_results": []}))
        try:
            lab.load_baseline([bad])
        except ValueError:
            pass
        else:
            raise AssertionError("baseline errors accepted")


def test_verdicts() -> None:
    aut = verdict.autopsy({"scope": "failures", "processed": 120, "hard_pairs": 60,
                           "rescue_rate": 0.2, "rerank_recovery_rate": 0.6},
                          argparse.Namespace(min_n=100, min_pairs=50,
                                             min_rescue_rate=0.1, min_recovery_rate=0.5))
    check(aut["pass"] is True, "autopsy pass")
    scr = verdict.screen({"scope": "all", "changed_move": 30, "regressions": 2,
                          "baseline_replay_mismatches": 4,
                          "paired": {"n": 500, "delta": 0.03,
                                     "ci95_low": 0.005, "ci95_high": 0.055}},
                         argparse.Namespace(min_n=400, min_delta=0.02))
    check(scr["pass"] is True, "screen pass")


def test_conv_pairing() -> None:
    base = {"n_errors": 0, "position_results": [
        {"index": 0, "result": "draw"}, {"index": 1, "result": "win"}]}
    cand = {"n_errors": 0, "position_results": [
        {"index": 0, "result": "win"}, {"index": 1, "result": "win"}]}
    got = verdict._paired_from_conv(base, cand)
    check(got["n"] == 2 and got["delta"] == 0.5, "conv pairing")


def test_ranker_shapes() -> None:
    import numpy as np
    x = np.ones((3, 16))
    check(ranker.expand(x, "linear").shape == (3, 16), "linear shape")
    check(ranker.expand(x, "quadratic").shape == (3, 152), "quadratic shape")
    m = ranker.metrics(np.asarray([[1.0], [-1.0]]), np.asarray([1.0]))
    check(m["n"] == 2 and m["accuracy"] == 0.5, "ranker metrics")


def test_templates() -> None:
    templates = [
        ROOT / "jobs/templates/gen2-p3-decision-autopsy-v1.sh",
        ROOT / "jobs/templates/gen2-p3-decision-screen-v1.sh",
        ROOT / "jobs/templates/gen2-p3-mmto-v2-v1.sh",
        ROOT / "jobs/templates/gen2-search-native-profile-v1.sh",
    ]
    for path in templates:
        text = path.read_text(encoding="utf-8")
        check("/root/jass" not in text, f"legacy path in {path.name}")
        check("jobs/queue" not in text, f"queue reference in {path.name}")
        check("JFC_GO" in text and "FULL_RUN_APPROVED" in text, f"approval guard missing in {path.name}")
        check("gen_patterns.py --variant v4 --emit" in text, f"32cf geometry not pinned in {path.name}")
        subprocess.run(["bash", "-n", str(path)], check=True)


def test_replay_is_the_paired_baseline() -> None:
    source = (ROOT / "jobs/tools/gen2_p3_decision_lab.py").read_text(encoding="utf-8")
    check('event["baseline_replay_result"]' in source, "paired baseline does not use replay")
    check('"baseline_replay_mismatches"' in source, "historical/replay drift not published")
    check("engine.new_game()" in source, "sibling searches do not reset engine state")


def main() -> None:
    tests = [value for name, value in sorted(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
        print(f"ok {test.__name__}")
    print(f"{len(tests)} tests passed")


if __name__ == "__main__":
    main()
