from pathlib import Path
import re
import struct
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "jobs/templates/l3-pure-m1-abextras-validation-v1.sh"
GENERATOR = ROOT / "tools/scan_selfplay_gen.py"


class M1ABExtrasValidationContractTests(unittest.TestCase):
    def test_shell_and_scientific_contract(self):
        subprocess.run(["bash", "-n", str(TEMPLATE)], check=True)
        text = TEMPLATE.read_text(encoding="utf-8")
        self.assertIn("GEN_SEED=950027", text)
        self.assertIn("TARGET_PER_STRATUM=300", text)
        self.assertIn("GAMES_PER_SHARD=$((TOTAL_GAMES / NSH_GEN))", text)
        self.assertIn('--games "$GAMES_PER_SHARD"', text)
        self.assertIn("--player-pattern \"$W/C0.pjtw\"", text)
        self.assertIn("--val-margin-max 1", text)
        self.assertIn("--thermo \"$IN/gauge.fen\"", text)
        self.assertIn("--required-strata p3_mince p4_egal", text)
        self.assertIn("MODELS=(C0 F500 AB_EXTRAS)", text)
        self.assertIn("run_force q00 C0", text)
        self.assertIn("run_force native C0", text)
        self.assertIn("run_force q00 GEN2", text)
        self.assertIn("confirmed_recovery", text)
        self.assertIn("PROMOTION_AUTHORIZED__FALSE", text)
        self.assertIn("AUTOMATIC_NEXT_JOB__NULL", text)

    def test_candidate_and_inputs_are_immutable(self):
        text = TEMPLATE.read_text(encoding="utf-8")
        self.assertIn("c86da4bd7ce2d2cb9e1b73ccec9785a770d4727c51b875a03fe9e6edd865ba94", text)
        self.assertIn("work/AB_EXTRAS.pjtw=ab-extras.pjtw", text)
        self.assertIn("blind_to_candidates", text)
        self.assertIn("old_gauge_excluded", text)

    def test_symmetric_jass_uses_two_stateful_engines(self):
        text = GENERATOR.read_text(encoding="utf-8")
        self.assertIn("scan_peer = (_mk_player() if scan_weak is None else None)", text)
        self.assertEqual(text.count("cv.play_game(scan, scan_peer or scan"), 2)
        self.assertIn("scan_peer.close()", text)

    def test_merge_ignores_shard_logs(self):
        text = TEMPLATE.read_text(encoding="utf-8")
        match = re.search(
            r'merge_jnnw\(\)\{ python3 - "\$1" "\$2" <<\'PY\'\n(.*?)\nPY\n\}',
            text,
            re.DOTALL,
        )
        self.assertIsNotNone(match)
        merge_script = match.group(1)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prefix = root / "sp."
            for shard, records in ((0, 2), (1, 3)):
                payload = bytes([shard + 1]) * (records * 38)
                (root / f"sp.{shard}").write_bytes(
                    b"JNNW" + struct.pack("<I", records) + payload
                )
                (root / f"sp.{shard}.log").write_text(
                    "not a JNNW shard\n", encoding="utf-8"
                )

            out = root / "merged.jnnw"
            completed = subprocess.run(
                [sys.executable, "-c", merge_script, str(out), str(prefix)],
                check=True,
                capture_output=True,
                text=True,
            )

            self.assertEqual(completed.stdout.strip(), "5")
            raw = out.read_bytes()
            self.assertEqual(raw[:4], b"JNNW")
            self.assertEqual(struct.unpack_from("<I", raw, 4)[0], 5)
            self.assertEqual(len(raw), 8 + 5 * 38)


if __name__ == "__main__":
    unittest.main()
