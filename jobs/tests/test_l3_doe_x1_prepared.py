#!/usr/bin/env python3
from __future__ import annotations

import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PREPARED = ROOT / "jobs/prepared/l3-c2x1-20260718"
RUNNER = ROOT / "jobs/templates/l3-pure-x1-runner-v5.sh"
SEARCH_PARAMS = ROOT / "src/search_params.hpp"
MAIN = ROOT / "src/main.cpp"
PLAN = ROOT / "docs/L3_PURE_PLAN.md"
CURRENT = ROOT / "docs/L3_CURRENT.md"
RESULTS = ROOT / "docs/PROJECT_RESULTS.md"
ARCHIVED_PLAN = ROOT / "docs/archives/l3/L3_PURE_PLAN_V4_1_20260718.md"

EXPECTED = {
    "X_LLH": (4, 4, 60),
    "X_HLL": (8, 4, 30),
    "X_LHL": (4, 8, 30),
    "X_HHH_CONTROL": (8, 8, 60),
    "X_CENTER": (6, 6, 45),
}
Q00 = {
    "qs_threat_ext": "0",
    "qs_sacs": "0",
    "qs_sacs_depth0_only": "1",
    "qs_forcing_depth": "0",
    "qs_promo_depth": "0",
}


class L3DoeX1PreparedTests(unittest.TestCase):
    def scripts(self):
        return sorted(PREPARED.glob("*.sh"))

    def test_five_scripts_are_shell_valid_and_not_queued(self):
        scripts = self.scripts()
        self.assertEqual(len(scripts), 5)
        for script in (RUNNER, *scripts):
            subprocess.run(["bash", "-n", str(script)], check=True)
            self.assertNotIn("/jobs/queue/", str(script))
        for script in scripts:
            text = script.read_text()
            self.assertNotIn("FULL_RUN_APPROVED=1", text)
            self.assertIn("do not queue without explicit go", text)

    def test_design_is_half_fraction_plus_centre(self):
        seen = {}
        for script in self.scripts():
            text = script.read_text()
            variant = re.search(r"^export L3_VARIANT=(\S+)$", text, re.M).group(1)
            match = re.search(
                r"^export RANDOM_OPEN_PLIES=(\d+) EXPLORE_EPS=(\d+) "
                r"EXPLORE_DECAY_PLIES=(\d+)$", text, re.M)
            seen[variant] = tuple(map(int, match.groups()))
        self.assertEqual(seen, EXPECTED)

        corners = {name: values for name, values in seen.items() if name != "X_CENTER"}
        for _, (opening, epsilon, decay) in corners.items():
            a = -1 if opening == 4 else 1
            b = -1 if epsilon == 4 else 1
            c = -1 if decay == 30 else 1
            self.assertEqual(c, a * b)
        self.assertEqual(seen["X_HHH_CONTROL"], (8, 8, 60))
        self.assertEqual(seen["X_CENTER"], (6, 6, 45))

    def test_all_cells_use_q00_and_same_training_contract(self):
        for script in self.scripts():
            text = script.read_text()
            spec = re.search(r'^export L3_SEARCH_OVERRIDES="([^"]+)"$', text, re.M)
            params = dict(token.split("=", 1) for token in spec.group(1).split(","))
            self.assertEqual(params, Q00)
            for invariant in (
                "ARM=A",
                "FRONTIER_FRAC=0",
                "NGEN=2 FRESH=150000 NSHARDS=8 PAR_GEN=8",
                "BASE_SEED=271828",
            ):
                self.assertIn(invariant, text)

    def test_all_search_params_are_pinned_not_inherited(self):
        runner = RUNNER.read_text()
        source = SEARCH_PARAMS.read_text()
        match = re.search(r'^L3_BASE_SEARCH_PARAMS="([^"]+)"$', runner, re.M)
        self.assertIsNotNone(match)
        tokens = match.group(1).split(",")
        pinned = dict(token.split("=", 1) for token in tokens)
        parser_keys = re.findall(r'key == "([^"]+)"', source)
        self.assertEqual(len(tokens), 63)
        self.assertEqual(set(pinned), set(parser_keys))
        self.assertIn('"search_params_inherited_defaults": False', runner)

    def test_instrumentation_and_manifests_are_required(self):
        runner = RUNNER.read_text()
        main = MAIN.read_text()
        self.assertIn('L3_EXPERIMENT="C2-X1"', runner)
        self.assertIn('"schema": 3', runner)
        self.assertIn('"generator": "C=AB"', runner)
        self.assertIn('"aliases": ["A=BC", "B=AC", "C=AB"]', runner)
        self.assertIn("aggregate_l3_exploration.py", runner)
        self.assertIn("selfplay_frontier.py profile", runner)
        self.assertIn("g${generation}-exploration.json", runner)
        self.assertIn("g${generation}-profile.json", runner)
        self.assertIn('std::cout << "EXPLORATION"', main)
        for counter in (
            "stat_random_open_moves",
            "stat_play_plies",
            "stat_eps_events",
            "stat_eps_changed_best",
            "stat_games_with_eps",
        ):
            self.assertIn(counter, main)

    def test_scientific_guards_keep_external_inputs_out(self):
        text = RUNNER.read_text()
        self.assertIn("FULL_RUN_APPROVED", text)
        self.assertIn("--wdl-zero-score", text)
        self.assertIn("--drop-plycap", text)
        self.assertIn("--pair-openings", text)
        self.assertIn('"external_teacher_inputs": 0', text)
        self.assertIn('"automatic_next_job": None', text)
        for forbidden in (
            "--deep-relabel",
            "--adjud-material",
            "--tb-relabel",
            "--drop-post-eps",
            "--pv-extract",
            "--seed-file",
        ):
            self.assertNotIn(forbidden, text)

    def test_three_active_docs_record_the_same_next_block(self):
        plan = PLAN.read_text()
        current = CURRENT.read_text()
        results = RESULTS.read_text()
        self.assertIn("Version : 5.0", plan)
        self.assertIn("C2-X1 — exploration immédiate", plan)
        self.assertIn("Q2 n'est pas déclenché", plan)
        self.assertIn("c2_x1_prepared_not_launched", current)
        self.assertIn("Bloc préparé : C2-X1", current)
        self.assertIn("C2-X1 : quelle distribution", results)
        self.assertTrue(ARCHIVED_PLAN.is_file())


if __name__ == "__main__":
    unittest.main()
