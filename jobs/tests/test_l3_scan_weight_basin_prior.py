import json
import struct
import tempfile
import unittest
from pathlib import Path

import numpy as np

from jobs.tools.sb1_fit_contract import (
    ARMS,
    RECIPE,
    build_train_command,
    only_prior_basin_diff,
)
from jobs.tools.sb1_scope_guard import ALLOWED_PATHS, validate_changed_paths
from jobs.tools.sb1_subset import main as subset_main
from jobs.tools.sb1_weight_audit import correlation, variance_decomposition


class Sb1FrozenContractTest(unittest.TestCase):
    def _command(self, prior, out="out.pjtw"):
        return build_train_command(
            python="python", train_stream="pattern_jass/tools/train_stream.py",
            data="current.jnnw", feat="shared.feat", target_values="context30.npy",
            prior=prior, out=out, targets_report=out + ".targets.json",
            optimizer_report=out + ".optimizer.json", holdout_count=200000,
        )

    def test_recipe_is_exact_preregistered_recipe(self):
        self.assertEqual(ARMS, {"SELF_BASIN": "C", "SCAN_BASIN": "SCAN_EXACT"})
        self.assertEqual(RECIPE, {
            "target": "external", "loss": "logistic", "fold": "exact",
            "phase": "tempo-stage", "prior_decay": 0.0, "l2": 1e-5,
            "max_iter": 2000, "lbfgs_maxcor": 20, "lbfgs_gtol": 1e-4,
            "chunk": 20000, "prune": True,
        })

    def test_ab_commands_differ_only_by_registered_prior_and_output_paths(self):
        a = self._command("C.pjtw", "SELF_BASIN.pjtw")
        b = self._command("SCAN_EXACT.pjtw", "SCAN_BASIN.pjtw")
        self.assertTrue(only_prior_basin_diff(a, b))
        flags = [token for token in a if token.startswith("--")]
        self.assertEqual(flags, [
            "--data", "--feat", "--out", "--target", "--target-values",
            "--targets-report", "--loss", "--exact-fold", "--tempo-stage",
            "--prior-mean", "--prior-decay", "--holdout-count", "--l2",
            "--max-iter", "--chunk", "--lbfgs-maxcor", "--lbfgs-gtol",
            "--prune", "--optimizer-report",
        ])
        joined = " ".join(a).lower()
        for forbidden in (
            "--sample-weights", "--trainable-region", "--warm-start",
            "--king-patterns", "pl8", "f6", "rich-d", "nnue",
            "micro-search", "search-label", "--prior-alpha-cap",
            "--prior-decay-ext", "--prior-visit-scale",
        ):
            self.assertNotIn(forbidden, joined)

    def test_scope_guard_blocks_engine_or_unregistered_changes(self):
        report = validate_changed_paths(sorted(ALLOWED_PATHS))
        self.assertFalse(report["engine_semantics_mutated"])
        with self.assertRaisesRegex(ValueError, "scope violation"):
            validate_changed_paths(["src/search.cpp"])
        with self.assertRaisesRegex(ValueError, "scope violation"):
            validate_changed_paths(["pattern_jass/tools/train_stream.py"])
        with self.assertRaisesRegex(ValueError, "scope violation"):
            validate_changed_paths(["src/movegen.cpp"])
        with self.assertRaisesRegex(ValueError, "scope violation"):
            validate_changed_paths(["src/egdb.cpp"])

    def test_bounded_subset_preserves_consumed_prefix_alignment(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            count, width, subset = 12, 3, 8
            data = root / "current.jnnw"
            rows = bytes((i % 251 for i in range(count * 38)))
            data.write_bytes(b"JNNW" + struct.pack("<I", count) + rows)
            feat = root / "current.feat"
            values = np.arange(count * width, dtype="<f4")
            feat.write_bytes(b"FEAT" + struct.pack("<II", count, width) + values.tobytes())
            targets = root / "context.npy"
            target_values = np.linspace(0.1, 0.9, count, dtype=np.float32)
            np.save(targets, target_values, allow_pickle=False)
            manifest = root / "manifest.json"
            out_data, out_feat, out_target = root / "sub.jnnw", root / "sub.feat", root / "sub.npy"
            self.assertEqual(subset_main([
                "--data", str(data), "--feat", str(feat), "--target-values", str(targets),
                "--records", str(subset), "--holdout-count", "2",
                "--out-data", str(out_data), "--out-feat", str(out_feat),
                "--out-target-values", str(out_target), "--manifest", str(manifest),
            ]), 0)
            self.assertEqual(out_data.read_bytes()[8:], rows[:subset * 38])
            self.assertEqual(out_feat.read_bytes()[12:], values[:subset * width].tobytes())
            np.testing.assert_array_equal(np.load(out_target), target_values[:subset])
            doc = json.loads(manifest.read_text())
            self.assertEqual(doc["markers"], {
                "FRESH_FORCE": 0, "FULL_FITS": 0,
                "SCIENTIFIC_DECISION": False, "STRENGTH_GAMES": 0,
            })

    def test_audit_math_is_read_only_and_variance_identity_closes(self):
        a = np.array([1.0, 2.0, 3.0, 4.0])
        b = 2.0 * a + 3.0
        self.assertAlmostEqual(correlation(a, b), 1.0)
        report = variance_decomposition(
            np.array([1.0, -1.0, 2.0, -2.0]),
            np.array([0.5, -0.5, -1.0, 1.0]),
        )
        self.assertAlmostEqual(report["identity_residual"], 0.0, places=12)

    def test_templates_stop_before_any_force_and_fit_uses_one_shared_dump(self):
        root = Path(__file__).resolve().parents[2]
        boundary = (root / "jobs/templates/l3-sb1-scan-basin-boundary-a-v1.sh").read_text()
        fit = (root / "jobs/templates/l3-sb1-scan-basin-fit-v1.sh").read_text()
        for marker in (
            "FULL_FITS=0", "FRESH_FORCE=0", "STRENGTH_GAMES=0",
            "SCIENTIFIC_DECISION=FALSE", "GO SB1 FIT",
        ):
            self.assertIn(marker, boundary)
        self.assertIn("GO_SB1_FIT", fit)
        self.assertIn("for arm in SELF_BASIN SCAN_BASIN", fit)
        self.assertEqual(fit.count("--dump-eval-features"), 1)
        for text in (boundary, fit):
            self.assertIn("NO_FRESH_FORCE", text)
            self.assertNotIn("run_jass_gate_bounded.py", text)
            self.assertNotIn("fresh-openings", text)
            self.assertNotIn("GO_SB1_FORCE", text)


if __name__ == "__main__":
    unittest.main()
