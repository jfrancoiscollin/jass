#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
V1 = ROOT / "jobs" / "templates" / "l3-replay-b-vs-curriculum-promotion-v1.sh"
V2 = ROOT / "jobs" / "templates" / "l3-replay-b-vs-curriculum-promotion-v2.sh"


class PromotionTemplateContractTest(unittest.TestCase):
    def test_shell_syntax(self) -> None:
        for path in (V1, V2):
            subprocess.run(["bash", "-n", str(path)], check=True)

    def test_v1_science_is_locked(self) -> None:
        text = V1.read_text(encoding="utf-8")
        required = (
            'EXPECTED_BASE_BLOB="ffec746c56930c6236017fe0742017969d27aa5b"',
            'SOURCE_1449_ROOT="r2:jass-data/runs/cpx62-1449-l3-exploratory-replay-four-arm-doe-v1/20260820T224246Z-7b22be6f"',
            "cpx62-1341-jass-megacorpus-arm-d-fit-v1",
            "319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1",
            'one("NOPEN=1500", "NOPEN=3000"',
            'one("CANDIDATES=20000", "CANDIDATES=40000"',
            'one("BOOTSTRAP=100000", "BOOTSTRAP=200000"',
            "2026082201",
            "2026082202",
            "2026082203",
            "2026082204",
            "2026082205",
            "2026082206",
            "2026082207",
            "2026082208",
            "pool-replay-doe-1451-pool1",
            "pool-replay-doe-1451-pool2",
            'historical_exclusion_count\':len(exclusions)',
            '--pattern-a "$W/B.pjtw" --pattern-b "$W/curriculum.pjtw"',
            "native_movetime_0.1",
            "Q00_depth9",
            "combined_native_probability_above_half_min",
            "l3_replay_b_promotion_readout.py",
            "PROMOTION_AUTHORIZED__FALSE",
            "promotion_review_recommended",
            'for forbidden in ("fit_arm A ", "stage sequential-four-arm-fits", "--prior-mean", "--target wdl")',
        )
        for token in required:
            self.assertIn(token, text)

    def test_v2_is_only_a_pinned_technical_normalizer(self) -> None:
        text = V2.read_text(encoding="utf-8")
        v1_blob = hashlib.sha1(
            b"blob " + str(V1.stat().st_size).encode() + b"\0" + V1.read_bytes()
        ).hexdigest()
        self.assertEqual(v1_blob, "a2691c7221bc9dd89b3835fda5007da37a914451")
        for token in (
            'EXPECTED_V1_BLOB="a2691c7221bc9dd89b3835fda5007da37a914451"',
            "self_check_token_specificity",
            '"scientific_protocol_changed": False',
            '"refits": 0',
            '"automatic_promotion": False',
            "JASS_PROMOTION_RENDER_ONLY",
            "remove_self_referential_outer_forbidden_scan",
            "inner_generated_script_scan_preserved",
            "bash -n \"$PATCHED\"",
            "exec bash \"$PATCHED\"",
        ):
            self.assertIn(token, text)
        self.assertNotIn(
            'for forbidden in ("fit_arm A ", "stage sequential-four-arm-fits", "--target wdl"):',
            text,
        )

    def test_complete_two_stage_renderer_produces_fit_free_script(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = root / "result"
            artefacts = root / "artefacts"
            result.mkdir()
            artefacts.mkdir()
            env = os.environ.copy()
            env.update(
                {
                    "JASS_CODE_DIR": str(ROOT),
                    "JASS_RESULT_DIR": str(result),
                    "JASS_ARTEFACT_DIR": str(artefacts),
                    "JASS_PROMOTION_RENDER_ONLY": "1",
                }
            )
            subprocess.run(
                ["bash", str(V2)],
                cwd=ROOT,
                env=env,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            rendered = artefacts / "promotion-rendered.sh"
            self.assertTrue(rendered.is_file())
            subprocess.run(["bash", "-n", str(rendered)], check=True)
            text = rendered.read_text(encoding="utf-8")
            for token in (
                'NOPEN=3000',
                'CANDIDATES=40000',
                'BOOTSTRAP=200000',
                'POOL_SEED_1=2026082201',
                'POOL_SEED_2=2026082202',
                '--pattern-a "$W/B.pjtw" --pattern-b "$W/curriculum.pjtw"',
                'JASS_REPLAY_B_PROMOTION_TWO_FRESH_POOLS_READY',
                'GAMES_TOTAL__24000',
                'PROMOTION_AUTHORIZED__FALSE',
            ):
                self.assertIn(token, text)
            for forbidden in (
                "fit_arm A ",
                "stage sequential-four-arm-fits",
                "--prior-mean",
                "--target wdl",
            ):
                self.assertNotIn(forbidden, text)


if __name__ == "__main__":
    unittest.main()
