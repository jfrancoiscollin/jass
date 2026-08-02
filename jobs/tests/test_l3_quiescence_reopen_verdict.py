import importlib.util
import json
import re
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / "jobs" / "tools" / "l3_quiescence_reopen_verdict.py"
SPEC = importlib.util.spec_from_file_location("l3_quiescence_reopen_verdict", MODULE)
M = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(M)


def fingerprint(sacs: int) -> str:
    values = {key: 0 for key in M.CURRENT_SEARCH_KEYS}
    values.update({
        "qs_sacs": sacs,
        "qs_sacs_depth0_only": 1,
        "qs_threat_ext": 0,
        "qs_forcing_depth": 0,
        "qs_promo_depth": 0,
    })
    return ",".join(f"{key}={values[key]}" for key in M.CURRENT_SEARCH_KEYS)


class QuiescenceReopenVerdictTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.conv = self.root / "conversion"
        self.conv.mkdir()
        self.q00 = fingerprint(0)
        self.q01 = fingerprint(1)
        self.defender_q00 = ",".join(
            token
            for token in self.q00.split(",")
            if not token.startswith(("scan_verify_pruning=", "scan_threat_reentry="))
        )
        self.fixed = self.root / "fixed.json"
        self.native = self.root / "native.json"
        self.write_gate(self.fixed, wins=1500, losses=1500, native=False)
        self.write_gate(self.native, wins=1500, losses=1500, native=True)
        for stratum in M.STRATA:
            self.write_conversion("Q00", stratum, wins=set(range(150)))
            self.write_conversion("Q01", stratum, wins=set(range(150)))

    def tearDown(self):
        self.tmp.cleanup()

    def write_gate(self, path: Path, *, wins: int, losses: int, native: bool):
        payload = {
            "complete": True,
            "wins_a": wins,
            "draws": 3000 - wins - losses,
            "wins_b": losses,
            "n": 3000,
            "rate": (wins + 0.5 * (3000 - wins - losses)) / 3000,
            "ci_low": 0.47,
            "ci_high": 0.53,
            "elo": 0.0,
            "jass_a": "/work/current/jass",
            "jass_b": "/work/current/jass",
            "pattern_a": "/work/EXACT.pjtw",
            "pattern_b": "/work/EXACT.pjtw",
            "search_params_a": self.q01,
            "search_params_b": self.q00,
            "depth": None if native else 9,
            "movetime": 0.1 if native else None,
        }
        path.write_text(json.dumps(payload), encoding="utf-8")

    def write_conversion(self, arm: str, stratum: str, *, wins: set[int]):
        rows = [
            {"index": index, "result": "win" if index in wins else "loss"}
            for index in range(300)
        ]
        payload = {
            "schema": 2,
            "complete": True,
            "stratum": stratum,
            "expected_records": 300,
            "accounted_records": 300,
            "n_pos": 300,
            "n_win": len(wins),
            "n_draw": 0,
            "n_loss": 300 - len(wins),
            "conversion": round(len(wins) / 300, 6),
            "position_results": rows,
            "pool_sha256": M.EXPECTED_POOL_SHA[stratum],
            "jass": "/work/current/jass",
            "defender_jass": "/work/fixed/jass",
            "pattern": "/work/EXACT.pjtw",
            "defender_pattern": "/work/GEN2.pjtw",
            "search_params": self.q00 if arm == "Q00" else self.q01,
            "defender_search_params": self.defender_q00,
            "depth": 10,
            "movetime": None,
        }
        (self.conv / f"{arm}-{stratum}.json").write_text(
            json.dumps(payload), encoding="utf-8"
        )

    def report(self):
        return M.build_report(
            fixed_gate_path=self.fixed,
            native_gate_path=self.native,
            conversion_dir=self.conv,
            q00=self.q00,
            q01=self.q01,
            defender_q00=self.defender_q00,
            expected_games_per_view=3000,
            min_paired_per_stratum=270,
            bootstrap_samples=2000,
            seed=20260802,
        )

    def test_flat_primary_outcomes_close_the_track(self):
        report = self.report()
        self.assertEqual(report["scientific_verdict"], "QUIESCENCE_CLOSE_CONFIRMED")
        self.assertEqual(report["technical_status"], "complete")
        self.assertEqual(report["conversion"]["pooled_p3_p4"]["n_common"], 600)

    def test_native_movement_reopens_full_0812(self):
        self.write_gate(self.native, wins=1600, losses=1400, native=True)
        report = self.report()
        self.assertEqual(report["scientific_verdict"], "QUIESCENCE_REOPEN_0812")
        self.assertEqual(
            report["force"]["native_movetime_0_1"]["direction"], "positive"
        )

    def test_pooled_conversion_movement_is_the_second_co_primary(self):
        for stratum in M.STRATA:
            self.write_conversion("Q01", stratum, wins=set(range(190)))
        report = self.report()
        self.assertEqual(report["scientific_verdict"], "QUIESCENCE_REOPEN_0812")
        self.assertEqual(report["conversion"]["pooled_p3_p4"]["direction"], "positive")

    def test_short_pairing_is_inconclusive_not_flat(self):
        path = self.conv / "Q01-p3_mince.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        for row in payload["position_results"][:31]:
            row["result"] = "error"
        payload["n_pos"] = 269
        payload["n_win"] = 119
        payload["n_loss"] = 150
        payload["n_errors"] = 31
        payload["conversion"] = round(119 / 269, 6)
        path.write_text(json.dumps(payload), encoding="utf-8")
        report = self.report()
        self.assertEqual(
            report["scientific_verdict"], "QUIESCENCE_REOPEN_INCONCLUSIVE"
        )

    def test_reads_real_aggregate_keys_and_refuses_stale_aliases(self):
        path = self.conv / "Q01-p4_egal.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["conversion_rate"] = payload.pop("conversion")
        payload["records"] = payload.pop("n_pos")
        path.write_text(json.dumps(payload), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "stale aggregate keys"):
            self.report()

    def test_missing_conversion_producer_is_a_hard_error(self):
        (self.conv / "Q01-p4_egal.json").unlink()
        with self.assertRaisesRegex(ValueError, "cannot read"):
            self.report()

    def test_parametrized_assertion_allows_only_the_sacs_button(self):
        contract = M.validate_arm_contract(self.q00, self.q01, self.defender_q00)
        self.assertEqual(contract["attacker_parameter_count"], 65)
        self.assertEqual(contract["defender_parameter_count"], 63)
        wrong = self.q01.replace("qs_threat_ext=0", "qs_threat_ext=1")
        with self.assertRaisesRegex(ValueError, "qs_threat_ext"):
            M.validate_arm_contract(self.q00, wrong, self.defender_q00)
        extra = self.q01 + ",invented=1"
        with self.assertRaisesRegex(ValueError, "expected exactly 65"):
            M.validate_arm_contract(self.q00, extra, self.defender_q00)

    def test_current_fingerprint_tracks_every_engine_parser_key(self):
        source = (ROOT / "src" / "search_params.hpp").read_text(encoding="utf-8")
        parser_keys = re.findall(r'key == "([^"]+)"', source)
        self.assertEqual(len(parser_keys), 65)
        self.assertEqual(set(parser_keys), set(M.CURRENT_SEARCH_KEYS))


if __name__ == "__main__":
    unittest.main()
