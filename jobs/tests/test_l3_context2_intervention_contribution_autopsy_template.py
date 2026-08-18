# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "jobs/templates/l3-context2-intervention-contribution-autopsy-v1.sh"


class ContributionAutopsyTemplateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = TEMPLATE.read_text(encoding="utf-8")

    def test_pins_all_three_immutable_sources(self) -> None:
        for token in (
            "cpx62-1409-l3-context2-intervention-corpus-v1/20260818T184956Z-3465ec72",
            "cpx62-1411-l3-context2-intervention-mapper-screen-v1/20260818T200558Z-9ec9195a",
            "home-1397-l3-context2-fixed-contribution-audit-v1/20260817T222724Z-f60336ca",
        ):
            self.assertIn(token, self.text)

    def test_replays_without_forbidden_scientific_actions(self) -> None:
        self.assertIn("--dump-conditional-context-v2", self.text)
        self.assertIn("l3_context2_intervention_contribution_autopsy.py", self.text)
        self.assertNotIn("--fit-pattern", self.text)
        self.assertNotIn("jass_vs_jass", self.text)
        self.assertNotIn("--gen-data-wdl", self.text)
        self.assertNotIn("frozen_test", self.text)
        self.assertIn("MAPPER_FITS_RUN__0", self.text)
        self.assertIn("PATTERNEVAL_FITS_RUN__0", self.text)
        self.assertIn("SELFPLAY_GENERATED__FALSE", self.text)
        self.assertIn("FORCE_GAMES_PLAYED__0", self.text)

    def test_fail_closed_runtime_contract(self) -> None:
        for token in (
            '"$(hostname)" = cpx62',
            '"$(nproc)" -eq 16',
            "persistent numeric runtime absent; do not reinstall",
            "less than 10 GiB free",
            "timeout 1800s",
            "NO_AUTOMATIC_CONTINUATION",
            "code SHA mismatch",
            "split hash drift against certified mapper input",
        ):
            self.assertIn(token, self.text)

    def test_monitor_does_not_use_bare_wait(self) -> None:
        self.assertNotIn("\nwait\n", self.text)
        self.assertIn('wait "$MON"', self.text)


if __name__ == "__main__":
    unittest.main()
