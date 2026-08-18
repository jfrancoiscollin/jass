# SPDX-License-Identifier: AGPL-3.0-or-later
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "jobs" / "templates" / "l3-context2-intervention-plan-v1.sh"


class Context2InterventionPlanTemplateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.script = TEMPLATE.read_text(encoding="utf-8")

    def test_authenticates_both_diagnostic_sources(self) -> None:
        for token in (
            "home-1395-l3-context2-knob-attribution-v1",
            "20260817T211534Z-f4e9fe1e",
            "f4e9fe1ef103fb52e7e3a2c10e967bc736e934f7",
            "home-1397-l3-context2-fixed-contribution-audit-v1",
            "20260817T222724Z-f60336ca",
            "f60336ca7b29e976e14c47eba92223fedd30eebf",
        ):
            self.assertIn(token, self.script)

    def test_preregisters_design_and_excludes_invalid_controls(self) -> None:
        for token in (
            "--total-records 2000000",
            "--weight-step 0.05",
            "--min-base-weight 0.15",
            "--min-intervention-weight 0.05",
            "--max-cell-weight 0.30",
            "--max-relative-draw-shift 0.15",
            "--max-wdl-side-skew 0.02",
            "'NODECAY' in corpus['weights']",
            "predicted['logdet_gain_vs_base']<=0",
        ):
            self.assertIn(token, self.script)

    def test_is_read_only_and_reuses_persistent_runtime(self) -> None:
        for token in (
            "selfplay_generated':False",
            "fits_run':0",
            "force_games_played':0",
            "frozen_read':False",
            "promotion_authorized':False",
            "automatic_next_job':None",
            "persistent numeric runtime absent; do not reinstall",
        ):
            self.assertIn(token, self.script)
        self.assertNotIn("pip install", self.script)
        self.assertNotIn("--gen-data-wdl", self.script)
        self.assertNotIn("train_stream.py", self.script)

    def test_has_sizing_host_and_fail_closed_guards(self) -> None:
        for token in (
            '"$(hostname)" = cpx62',
            '"$(nproc)" -eq 16',
            "eta_minutes=10",
            "timeout 1800s",
            "timeout 600s",
            "JASS_CONTEXT2_INTERVENTION_PLAN_READY",
        ):
            self.assertIn(token, self.script)


if __name__ == "__main__":
    unittest.main()
