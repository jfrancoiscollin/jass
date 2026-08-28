from __future__ import annotations

import unittest

from jobs.tools import micro_search_m5_catalog_select_runner as m5


class MicroSearchM5SelectorContractTests(unittest.TestCase):
    def test_frozen_phase_quotas_and_seed(self) -> None:
        self.assertEqual(m5.M5_SELECTION_SEED, 2026090220)
        self.assertEqual(
            m5.M5_PHASES,
            {
                "P0": (30, 40, 1000),
                "P1": (20, 29, 1000),
                "P2": (12, 19, 1000),
                "P3": (9, 11, 1000),
            },
        )
        self.assertEqual(m5.m3.base.PHASES, m5.M5_PHASES)


if __name__ == "__main__":
    unittest.main()
