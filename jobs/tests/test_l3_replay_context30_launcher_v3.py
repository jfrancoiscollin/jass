"""Technical contracts for the materialized REPLAY25 context30 launcher v3."""

import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
V3 = ROOT / "jobs/templates/l3-replay-context30-target-gate-v3.sh"


class ReplayContext30LauncherV3Test(unittest.TestCase):
    def test_static_technical_scope(self) -> None:
        text = V3.read_text(encoding="utf-8")
        for token in (
            'EXPECTED_V2_BLOB="24dbb03bb9f1827b4777decc06c8d19f2ca013db"',
            "JASS_REPLAY_CONTEXT30_RENDER_ONLY=1",
            "JASS_REPLAY_CONTEXT30_V3_RENDER_ONLY",
            "replay-context30-v3-render-receipt.json",
            "replay-context30-v3-execution-receipt.json",
            "scientific_protocol_changed':False",
            "technical_change_only':True",
            "scientific_fit_command_count",
            'bash "$FINAL"',
        ):
            self.assertIn(token, text)
        self.assertNotIn("--gen-selfplay", text)
        self.assertNotIn("PROMOTION_AUTHORIZED__TRUE", text)

    def test_complete_v3_render_path_materialises_locked_final_script(self) -> None:
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
                    "JASS_REPLAY_CONTEXT30_V3_RENDER_ONLY": "1",
                }
            )
            subprocess.run(
                ["bash", str(V3)],
                cwd=ROOT,
                env=env,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            final = artefacts / "replay-context30-rendered.sh"
            receipt = artefacts / "replay-context30-v3-render-receipt.json"
            self.assertTrue(final.is_file())
            self.assertTrue(receipt.is_file())
            subprocess.run(["bash", "-n", str(final)], check=True)
            report = json.loads(receipt.read_text(encoding="utf-8"))
            self.assertEqual(report["render_exit_code"], 0)
            self.assertTrue(report["syntax_ok"])
            self.assertEqual(report["required_tokens_missing"], [])
            self.assertEqual(report["forbidden_tokens_surviving"], [])
            self.assertEqual(report["scientific_fit_command_count"], 1)
            self.assertFalse(report["scientific_protocol_changed"])
            self.assertTrue(report["technical_change_only"])
            text = final.read_text(encoding="utf-8")
            for token in (
                "B_REPLAY25_CONTEXT30",
                "B_REPLAY25_NATIVE",
                "CONTEXT_30_ALIGNED_alpha_0.30",
                "NOPEN=3000",
                "BOOTSTRAP=200000",
                '--pattern-a "$W/B_C30.pjtw" --pattern-b "$W/B_NATIVE.pjtw"',
                "GAMES_TOTAL__24000",
                "REFITS__1",
                "NEW_SELFPLAY__0",
                "FROZEN_COHORTS_READ__0",
                "PROMOTION_AUTHORIZED__FALSE",
            ):
                self.assertIn(token, text)
            for forbidden in (
                "stage sequential-four-arm-fits",
                "fit_arm A ",
                "fit_arm B ",
                "--gen-selfplay",
                "PROMOTION_AUTHORIZED__TRUE",
            ):
                self.assertNotIn(forbidden, text)


if __name__ == "__main__":
    unittest.main()
