#!/usr/bin/env python3
from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MAIN = ROOT / "src/main.cpp"
SPEC = ROOT / "docs/experiments/L3_CURRICULUM_ERROR_LEARNING_V1_20260822.md"


class CurriculumErrorSeedScheduleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        source = MAIN.read_text(encoding="utf-8")
        start = source.index("int run_gen_data_wdl_mode")
        end = source.index("int run_gen_tdleaf_mode", start)
        cls.generator = source[start:end]
        cls.spec = SPEC.read_text(encoding="utf-8")

    def test_without_replacement_is_opt_in_and_fail_closed(self) -> None:
        for token in (
            'a == "--seed-without-replacement"',
            "seed_without_replacement = false",
            "requires --seed-file",
            "requires --seed-frac 100",
            "std::shuffle(seed_schedule.begin(), seed_schedule.end(), rng)",
            "--seed-without-replacement exhausted",
        ):
            self.assertIn(token, self.generator)

    def test_schedule_consumes_each_seed_index_once(self) -> None:
        self.assertIn(
            "seed_index = seed_schedule[seed_schedule_cursor++]",
            self.generator,
        )
        self.assertIn("++stat_seed_unique_used", self.generator)
        self.assertIn(
            '<< " seed_reuses=" << (seed_without_replacement ? 0 : -1)',
            self.generator,
        )
        self.assertNotIn("seed_schedule_cursor % seed_schedule.size()", self.generator)

    def test_protocol_requires_the_guard_and_audits_reuse(self) -> None:
        for token in (
            "--seed-frac 100",
            "--seed-without-replacement",
            "--pair-openings",
            "seed_unique_used",
            "seed_reuses=0",
        ):
            self.assertIn(token, self.spec)


if __name__ == "__main__":
    unittest.main()
