import copy
import importlib.util
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "scan_blind_spot_differential",
    ROOT / "jobs/tools/scan_blind_spot_differential.py",
)
M = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules["scan_blind_spot_differential"] = M
SPEC.loader.exec_module(M)


def protocol(variant: str) -> dict:
    patterns = 8 if variant == "exact" else 32
    return {
        "schema": "l3_scan_blind_spot_atlas_protocol",
        "version": 1,
        "variant": variant,
        "model": {
            "label": variant.upper(),
            "sha256": (M.EXACT_MODEL_SHA256 if variant == "exact"
                       else "b" * 64),
            "gzip_sha256": ("c" * 64 if variant == "exact"
                            else M.GEN2_GZIP_SHA256),
            "source_prefix": f"r2:test/{variant}",
            "source_job": ("cpx62-1117-l3-exact-fold-refit-v1"
                           if variant == "exact" else "frozen-t1bis-gen2"),
            "n_pat": 531441 * patterns,
            "n_ext": 120,
            "num_patterns": patterns,
        },
        "engine": {
            "code_sha": "e" * 40,
            "cmake_flags": ["JASS_ENDGAME_FEATURES=ON", "JASS_KING_MOBILITY=ON",
                            "JASS_SCAN_PARITY=ON", "JASS_TEMPO_STAGE=ON"],
            "egdb": False,
        },
        "scan": {
            "binary_sha256": M.SCAN_BINARY_SHA256,
            "eval_sha256": M.SCAN_EVAL_SHA256,
            "bb_size": 0,
            "book": False,
        },
        "collection": {
            "budget_s_per_shard": 1500,
            "play_depth": 8,
            "judge_depth": 10,
            "max_plies": 160,
            "games_cap": 100000,
            "min_positions": 200,
            "shards": 16,
            "seed_policy": "one_based_shard_index",
            "seeds": list(range(1, 17)),
        },
        "diagnostic_only": True,
        "promotion_authorized": False,
        "automatic_next_job": None,
    }


def atlas(proto: dict, first_cost: float, second_cost: float) -> dict:
    first = {
        "bucket": "ouverture_25+|sans_dame|materiel_egal|calme",
        "positions": 1000,
        "ordinary_positions": 1000,
        "disagreements": 500,
        "disagreement_rate": 0.5,
        "cost_sum": first_cost,
        "cost_per_position": first_cost / 1000,
        "cost_max": 1.0,
        "costs_clipped": 10,
        "ranked": True,
        "worst_fen": "W:W31:B12",
    }
    second = {
        "bucket": "milieu_13_24|dames_des_deux_cotes|en_retard_1_2|capture_forcee",
        "positions": 500,
        "ordinary_positions": 500,
        "disagreements": 200,
        "disagreement_rate": 0.4,
        "cost_sum": second_cost,
        "cost_per_position": second_cost / 500,
        "cost_max": 1.0,
        "costs_clipped": 5,
        "ranked": True,
        "worst_fen": "B:WK40:BK1",
    }
    return {
        "schema": "l3_scan_blind_spot_atlas",
        "version": 2,
        "positions_seen": 1500,
        "moves_agreed": 800,
        "disagreements_judged": 700,
        "min_positions_to_rank": 200,
        "buckets_ranked": [first, second],
        "buckets_below_floor": [],
        "conversion_family": [{
            "bucket": "finale_7_12|une_dame|materiel_egal|calme",
            "positions": 300,
            "disagreements": 250,
            "misses": 30 if proto["variant"] == "exact" else 15,
            "ranked": True,
        }],
        "conversion_positions": 300,
        "conversion_misses": 30 if proto["variant"] == "exact" else 15,
        "costs_clipped": 15,
        "run_protocol": proto,
    }


class DifferentialContract(unittest.TestCase):
    def setUp(self):
        self.ep = protocol("exact")
        self.gp = protocol("gen2")
        self.ea = atlas(self.ep, 100.0, 50.0)
        self.ga = atlas(self.gp, 150.0, 25.0)

    def test_reports_exact_minus_gen2_globally_by_axis_and_bucket(self):
        result = M.compare(self.ea, self.ep, self.ga, self.gp)
        self.assertEqual(result["verdict"],
                         "L3_SCAN_BLIND_SPOT_DIFFERENTIAL_MEASURED")
        delta = result["global_differential_exact_minus_gen2"]
        self.assertAlmostEqual(delta["ordinary_cost_per_position"], -0.016667)
        self.assertEqual(result["common_ranked_bucket_count"], 2)
        self.assertEqual(len(result["axis_differentials"]["phase"]), 2)
        top = {r["bucket"]: r for r in result["bucket_differentials"]}
        self.assertAlmostEqual(
            top["ouverture_25+|sans_dame|materiel_egal|calme"]
               ["delta_cost_per_position_exact_minus_gen2"],
            -0.05,
        )
        self.assertEqual(result["common_ranked_conversion_bucket_count"], 1)
        self.assertAlmostEqual(
            result["conversion_bucket_differentials"][0]
                  ["delta_miss_rate_over_positions_exact_minus_gen2"],
            0.05,
        )
        self.assertTrue(result["interpretation"]
                        ["geometry_profile_comparison_authorized"])
        self.assertFalse(result["interpretation"]
                         ["linear_vs_nonlinear_class_attribution_authorized"])

    def test_rejects_n_ext_drift(self):
        self.gp["model"]["n_ext"] = 124
        self.ga["run_protocol"] = self.gp
        with self.assertRaisesRegex(M.DifferentialError, "n_ext"):
            M.compare(self.ea, self.ep, self.ga, self.gp)

    def test_rejects_scan_drift(self):
        self.gp["scan"]["eval_sha256"] = "2" * 64
        self.ga["run_protocol"] = self.gp
        with self.assertRaisesRegex(M.DifferentialError, "Scan eval"):
            M.compare(self.ea, self.ep, self.ga, self.gp)

    def test_rejects_budget_or_seed_drift(self):
        self.gp["collection"]["seeds"] = [2, 3]
        self.ga["run_protocol"] = self.gp
        with self.assertRaisesRegex(M.DifferentialError, "collection setting seeds"):
            M.compare(self.ea, self.ep, self.ga, self.gp)

    def test_rejects_atlas_protocol_mismatch(self):
        self.ga["run_protocol"] = copy.deepcopy(self.gp)
        self.ga["run_protocol"]["collection"]["play_depth"] = 9
        with self.assertRaisesRegex(M.DifferentialError, "embedded protocol"):
            M.compare(self.ea, self.ep, self.ga, self.gp)

    def test_allows_sparse_bucket_sets_and_reports_coverage(self):
        self.ga["buckets_below_floor"].append({
            "bucket": "finale_7_12|sans_dame|en_avance_3+|calme",
            "positions": 1,
            "ordinary_positions": 1,
            "disagreements": 0,
            "cost_sum": 0.0,
            "ranked": False,
        })
        result = M.compare(self.ea, self.ep, self.ga, self.gp)
        self.assertEqual(result["common_ranked_bucket_count"], 2)
        self.assertEqual(
            result["axis_values_only_one_arm"]["phase"]["gen2"],
            ["finale_7_12"],
        )

    def test_cli_fails_closed_and_writes_only_a_valid_readout(self):
        root = Path(tempfile.mkdtemp())
        paths = {}
        for name, value in (("ea", self.ea), ("ep", self.ep),
                            ("ga", self.ga), ("gp", self.gp)):
            paths[name] = root / f"{name}.json"
            paths[name].write_text(json.dumps(value), encoding="utf-8")
        out = root / "diff.json"
        rc = M.main([
            "--exact-atlas", str(paths["ea"]),
            "--exact-protocol", str(paths["ep"]),
            "--gen2-atlas", str(paths["ga"]),
            "--gen2-protocol", str(paths["gp"]),
            "--out", str(out),
        ])
        self.assertEqual(rc, 0)
        self.assertTrue(out.exists())
        self.gp["scan"]["binary_sha256"] = "3" * 64
        paths["gp"].write_text(json.dumps(self.gp), encoding="utf-8")
        bad = root / "bad.json"
        rc = M.main([
            "--exact-atlas", str(paths["ea"]),
            "--exact-protocol", str(paths["ep"]),
            "--gen2-atlas", str(paths["ga"]),
            "--gen2-protocol", str(paths["gp"]),
            "--out", str(bad),
        ])
        self.assertEqual(rc, 2)
        self.assertFalse(bad.exists())


class TemplateVariantContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = (ROOT / "jobs/templates/l3-scan-blind-spot-atlas-v1.sh").read_text(
            encoding="utf-8"
        )

    def test_requires_explicit_exact_or_gen2_variant(self):
        self.assertIn("--variant {exact|gen2}", self.text)
        self.assertIn("PATTERN_VARIANT=8cf", self.text)
        self.assertIn("PATTERN_VARIANT=v4", self.text)
        self.assertIn("EXPECTED_NUM_PATTERNS=8", self.text)
        self.assertIn("EXPECTED_NUM_PATTERNS=32", self.text)

    def test_asserts_geometry_and_constant_extras(self):
        self.assertIn("n_ext != 120", self.text)
        self.assertIn("n_pat != want", self.text)
        self.assertIn("fetch_t1bis_inputs.py", self.text)
        self.assertIn("artefacts/exact.pjtw.gz=MODEL.pjtw.gz", self.text)

    def test_publishes_a_machine_readable_protocol(self):
        self.assertIn('"l3_scan_blind_spot_atlas_protocol"', self.text)
        self.assertIn('"seed_policy": "one_based_shard_index"', self.text)
        self.assertIn('"egdb": False', self.text)
        self.assertIn('atlas["run_protocol"] = protocol', self.text)

    def test_embedded_python_is_syntax_valid(self):
        blocks = re.findall(r"<<'PY'[^\n]*\n(.*?)\nPY(?=\n|$)",
                            self.text, flags=re.DOTALL)
        self.assertGreaterEqual(len(blocks), 5)
        for block in blocks:
            compile(block, "l3-scan-blind-spot-atlas-v1.sh:<heredoc>", "exec")


class PreparedJobsContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        prepared = (ROOT / "jobs/prepared" /
                    "l3-scan-blind-spot-differential-20260801")
        cls.exact = (prepared /
                     "cpx62-1142-l3-scan-blind-spot-atlas-exact-v1.sh").read_text(
                         encoding="utf-8"
                     )
        cls.gen2 = (prepared /
                    "cpx62-1143-l3-scan-blind-spot-atlas-gen2-v1.sh").read_text(
                        encoding="utf-8"
                    )
        cls.readout = (prepared /
                       "cpx62-1144-l3-scan-blind-spot-differential-v1.sh").read_text(
                           encoding="utf-8"
                       )
        cls.readout_template = (
            ROOT / "jobs/templates/l3-scan-blind-spot-differential-v1.sh"
        ).read_text(encoding="utf-8")

    def test_arms_select_the_intended_variant(self):
        self.assertIn("--variant exact", self.exact)
        self.assertNotIn("--variant gen2", self.exact)
        self.assertIn("--variant gen2", self.gen2)
        self.assertNotIn("--variant exact", self.gen2)

    def test_scan_and_collection_protocol_are_identical(self):
        constant_lines = (
            'export SCAN_BIN="/root/jass-scan/scan_linux"',
            'export EXPECTED_SCAN_SHA256="a634cbb44c9528eab277cdf6cdf8d29d506318ce5fba3f9bc69c2025b5941864"',
            'export EXPECTED_SCAN_EVAL_SHA256="0e7161c38af605f5e367f3f8fe17525d1c40db722714c68921971b386e58abba"',
            "export BUDGET_S=1500 PLAY_DEPTH=8 JUDGE_DEPTH=10 MAX_PLIES=160",
            "export GAMES_CAP=100000 MIN_POSITIONS=200 SHARDS=16",
        )
        for line in constant_lines:
            self.assertEqual(self.exact.count(line), 1)
            self.assertEqual(self.gen2.count(line), 1)

    def test_readout_is_wired_to_both_completed_arms(self):
        self.assertIn(
            'EXPECTED_EXACT_ATLAS_JOB="cpx62-1142-l3-scan-blind-spot-atlas-exact-v1"',
            self.readout,
        )
        self.assertIn(
            'EXPECTED_GEN2_ATLAS_JOB="cpx62-1143-l3-scan-blind-spot-atlas-gen2-v1"',
            self.readout,
        )
        self.assertIn("EXACT_ATLAS_PREFIX", self.readout)
        self.assertIn("GEN2_ATLAS_PREFIX", self.readout)

    def test_prepared_jobs_cannot_continue_automatically(self):
        for text in (self.exact, self.gen2, self.readout):
            self.assertIn("NO_AUTOMATIC_CONTINUATION=1", text)
            self.assertNotIn("queue/pending", text)

    def test_readout_embedded_python_is_syntax_valid(self):
        blocks = re.findall(r"<<'PY'[^\n]*\n(.*?)\nPY(?=\n|$)",
                            self.readout_template, flags=re.DOTALL)
        self.assertEqual(len(blocks), 2)
        for block in blocks:
            compile(block,
                    "l3-scan-blind-spot-differential-v1.sh:<heredoc>",
                    "exec")


if __name__ == "__main__":
    unittest.main()
