#!/usr/bin/env python3
from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "jobs/templates/salvage-stable-conversion-matrix-v1.sh"
WRAPPER = ROOT / (
    "jobs/prepared/salvage-0908-20260723/"
    "cpx62-0920-salvage-0908-stable-top3-matrix-v1.sh"
)


class SalvageStableConversionJobTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.template = TEMPLATE.read_text(encoding="utf-8")
        cls.wrapper = WRAPPER.read_text(encoding="utf-8")

    def test_source_and_cap_are_fully_pinned(self) -> None:
        for token in (
            "20260723T131042Z-e4f1b5f7",
            "e4f1b5f74df637e41c000906d1852fd3b7a41005",
            "9fa4bedd93df491bd0a46828dd5da30abf74fd53b116354869d453d70f2a5277",
            "g4_g4",
            "5caae5749ee56f08fba806798ed5499f45b8755209ab665fb0d36bd1605403c6",
            "18v20|adv=B|stm=W",
        ):
            self.assertIn(token, self.wrapper)

    def test_job_is_no_replay_and_keeps_original_gate_failed(self) -> None:
        for token in (
            "--expected-state failed",
            "salvage-single-ply-cap",
            "original_0908_zero_cap_gate=FAILED",
            "replay_performed=false",
            "training_continuation_authorized=false",
            "promotion_authorized=false",
            "automatic_next_job=null",
            '[ "${#RESULT_FILES[@]}" -eq 112 ]',
            "BOOTSTRAP:-10000",
            "ETA 2-5min",
        ):
            self.assertIn(token, self.template)
        self.assertNotIn("cmake", self.template)
        self.assertNotIn("stable_conversion_matrix.py run", self.template)

    def test_runner_safety_contract(self) -> None:
        for token in (
            'find /root -maxdepth 1 -name \'cw-*\'',
            '[ "$NPROC" -eq 16 ]',
            'RES="$W/RESULTS.txt"',
            'PROG="$W/PROGRESS.txt"',
            "bash -n",
            "python3 -m py_compile",
            "tarfile.open",
            "path.parts[0] != \"matrix\"",
            "exec timeout -k 30s 600s",
        ):
            self.assertIn(token, self.template + self.wrapper)


if __name__ == "__main__":
    unittest.main()
