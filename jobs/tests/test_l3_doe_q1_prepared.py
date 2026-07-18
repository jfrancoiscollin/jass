#!/usr/bin/env python3
from __future__ import annotations

import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PREPARED = ROOT / "jobs/prepared/l3-c1q1-20260718"
RUNNER = ROOT / "jobs/templates/l3-pure-runner-v4.sh"
SEARCH_PARAMS = ROOT / "src/search_params.hpp"
MAIN = ROOT / "src/main.cpp"

EXPECTED = {
    "Q00_CAPTURE": (0, 0),
    "Q10_THREAT": (1, 0),
    "Q01_SACS": (0, 1),
    "Q11_THREAT_SACS": (1, 1),
}


class L3DoeQ1PreparedTests(unittest.TestCase):
    def test_four_prepared_scripts_are_shell_valid_and_not_queued(self):
        scripts = sorted(PREPARED.glob("*.sh"))
        self.assertEqual(len(scripts), 4)
        for script in (RUNNER, *scripts):
            subprocess.run(["bash", "-n", str(script)], check=True)
            self.assertNotIn("/jobs/queue/", str(script))
        for script in scripts:
            self.assertNotIn("FULL_RUN_APPROVED=1", script.read_text())

    def test_q1_is_the_complete_threat_by_sacs_factorial(self):
        seen = {}
        for script in PREPARED.glob("*.sh"):
            text = script.read_text()
            variant = re.search(r"^export L3_VARIANT=(\S+)$", text, re.M).group(1)
            spec = re.search(r'^export L3_SEARCH_OVERRIDES="([^"]+)"$', text, re.M).group(1)
            params = dict(token.split("=", 1) for token in spec.split(","))
            seen[variant] = (
                int(params["qs_threat_ext"]),
                int(params["qs_sacs"]),
            )
            self.assertEqual(params["qs_sacs_depth0_only"], "1")
            self.assertEqual(params["qs_forcing_depth"], "0")
            self.assertEqual(params["qs_promo_depth"], "0")
            for invariant in (
                "ARM=A",
                "FRONTIER_FRAC=0",
                "NGEN=2 FRESH=150000 NSHARDS=8 PAR_GEN=8",
                "BASE_SEED=271828",
            ):
                self.assertIn(invariant, text)
        self.assertEqual(seen, EXPECTED)

    def test_all_search_params_are_pinned_not_inherited(self):
        runner = RUNNER.read_text()
        source = SEARCH_PARAMS.read_text()
        match = re.search(r'^L3_BASE_SEARCH_PARAMS="([^"]+)"$', runner, re.M)
        self.assertIsNotNone(match)
        tokens = match.group(1).split(",")
        pinned = dict(token.split("=", 1) for token in tokens)
        parser_keys = re.findall(r'key == "([^"]+)"', source)
        self.assertEqual(len(tokens), 63)
        self.assertEqual(len(pinned), 63)
        self.assertEqual(set(pinned), set(parser_keys))
        self.assertIn('"search_params_inherited_defaults": False', runner)
        self.assertIn('"search_params_count": len(params)', runner)

    def test_wdl_only_mode_skips_hidden_score_search(self):
        runner = RUNNER.read_text()
        main = MAIN.read_text()
        self.assertIn("--wdl-zero-score", runner)
        self.assertIn("--search-params-play", runner)
        self.assertNotIn('--search-params "$L3_SEARCH_PARAMS"', runner)
        self.assertIn('label_score_searches=0', runner)
        self.assertIn('a == "--wdl-zero-score"', main)
        self.assertIn("if (!wdl_zero_score)", main)
        self.assertIn("s.score  = wdl_zero_score ? 0", main)
        self.assertIn("stat_label_score_searches", main)

    def test_scientific_guards_and_manifest(self):
        text = RUNNER.read_text()
        self.assertIn("FULL_RUN_APPROVED", text)
        self.assertIn('L3_EXPERIMENT="C1-Q1"', text)
        for guard in (
            'NGEN" -eq 2',
            'FRESH" -eq 150000',
            'NSHARDS" -eq 8',
            'MAXPLIES" -eq 260',
            'RANDOM_OPEN_PLIES" -eq 8',
            'EXPLORE_EPS" -eq 8',
            'BASE_SEED" -eq 271828',
            'L2" = 3e-5',
        ):
            self.assertIn(guard, text)
        self.assertIn('"score_field_mode": "constant_zero_no_search"', text)
        self.assertIn('"frontier_game_percent": 0', text)
        self.assertIn('"external_teacher_inputs": 0', text)
        self.assertIn('"search_params_scope": "play"', text)
        self.assertIn("--drop-plycap", text)
        self.assertIn("--pair-openings", text)
        for forbidden in (
            "--deep-relabel",
            "--adjud-material",
            "--tb-relabel",
            "--drop-post-eps",
            "--pv-extract",
        ):
            self.assertNotIn(forbidden, text)


if __name__ == "__main__":
    unittest.main()
