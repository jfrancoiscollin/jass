from __future__ import annotations

import copy
from pathlib import Path
import struct
import tempfile
import unittest

import numpy as np

from jobs.tools import jfi_boundary_b
from jobs.tools import jfi_candidate_prefix
from jobs.tools.jfi_candidate_universe import JNNW_DTYPE


def valid_input():
    return {
        "schema": "jass.jfi.boundary_b_input.v1",
        "code_sha": "a" * 40,
        "machine": {
            "host": "cpx62", "nproc": 16, "avx2": True, "bmi2": True,
            "native_build": True,
        },
        "numeric_env": {"OMP_NUM_THREADS": "1"},
        "disk": {"scratch_path": "/scratch", "scratch_free_bytes": 100 * 1024**3},
        "jfi_a_b": {
            "job_id": "cpx62-1749-l3-jfi-factorial-l2-fit-v1",
            "attempt_id": "20260901T225526Z-25bb488e",
            "code_sha": "b" * 40, "full_fits": 7,
            "path_verdict": "JFI_OPTIMIZER_PATH_INDEPENDENCE_ESTABLISHED",
            "selected_l2": 1e-5,
            "identifiability": {
                "selected_l2": 1e-5, "coordinates": 34_000_240,
                "effective_df": 1000.0,
                "class_counts": {"UNSEEN": 1, "PRIOR_DOMINATED": 2,
                                 "MIXED": 3, "DATA_DOMINATED": 4},
            },
        },
        "source_40m": {
            "records": 40_000_000, "external_teacher_inputs": 0,
            "data_sha256": "c" * 64, "meta_sha256": "d" * 64,
        },
        "candidate_universe": {
            "records": 10_000_000, "train_candidates": 9_000_000,
            "dev_eval": 1_000_000, "target_reads": 0, "scan_reads": 0,
            "manifest_sha256": "e" * 64,
        },
        "selector_sizer": {
            "rows": 20_000, "seconds": 5.0, "rows_per_second": 4000.0,
            "full_train_candidates": 9_000_000,
            "guards": {"TARGET_READS": 0, "ARM_SELECTIONS": 0},
        },
        "fit_projection": {"two_arm_seconds": 2000.0, "per_arm_timeout_seconds": 86400},
        "markers": dict(jfi_boundary_b.ZERO_MARKERS),
    }


class BoundaryBTests(unittest.TestCase):
    def test_valid_facts_stop_at_active_boundary(self):
        facts = jfi_boundary_b.build_facts(valid_input())
        self.assertEqual(facts["verdict"], "JFI_BOUNDARY_B_READY")
        self.assertEqual(facts["next_boundary"], "GO JFI ACTIVE")
        self.assertEqual(facts["markers"], jfi_boundary_b.ZERO_MARKERS)

    def test_scientific_or_target_read_marker_fails_closed(self):
        for field, value in (("SCIENTIFIC_DECISION", True),
                             ("TARGET_READS_BEFORE_SELECTION_FREEZE", 1)):
            source = valid_input(); source["markers"][field] = value
            with self.assertRaisesRegex(ValueError, "zero-marker"):
                jfi_boundary_b.build_facts(source)

    def test_path_failure_or_zero_lambda_fails_closed(self):
        for field, value in (("path_verdict", "JFI_OPTIMIZER_PATH_DEPENDENCE_DETECTED"),
                             ("selected_l2", 0.0)):
            source = copy.deepcopy(valid_input()); source["jfi_a_b"][field] = value
            with self.assertRaisesRegex(ValueError, "prerequisite"):
                jfi_boundary_b.build_facts(source)

    def test_candidate_prefix_is_bounded_and_zero_label(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            rows = np.zeros(6, dtype=JNNW_DTYPE); rows["wm"] = np.arange(1, 7)
            data = root / "candidate.jnnw"
            data.write_bytes(b"JNNW" + struct.pack("<I", len(rows)) + rows.tobytes())
            origin = root / "origin.npy"; np.save(origin, np.arange(6, dtype=np.uint32))
            out_data, out_origin = root / "prefix.jnnw", root / "prefix-origin.npy"
            report = jfi_candidate_prefix.materialize_prefix(
                data, origin, 4, out_data, out_origin,
            )
            self.assertEqual(report["records"], 4)
            self.assertEqual(out_data.stat().st_size, 8 + 4 * JNNW_DTYPE.itemsize)
            np.testing.assert_array_equal(np.load(out_origin), np.arange(4, dtype=np.uint32))
            self.assertEqual(report["guards"]["TARGET_READS"], 0)

    def test_candidate_prefix_rejects_embedded_target(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            rows = np.zeros(2, dtype=JNNW_DTYPE); rows[0]["score"] = 1
            data = root / "candidate.jnnw"
            data.write_bytes(b"JNNW" + struct.pack("<I", len(rows)) + rows.tobytes())
            origin = root / "origin.npy"; np.save(origin, np.arange(2, dtype=np.uint32))
            with self.assertRaisesRegex(ValueError, "not target blind"):
                jfi_candidate_prefix.materialize_prefix(
                    data, origin, 2, root / "out.jnnw", root / "out.npy",
                )

    def test_boundary_template_freezes_universe_but_never_selects_or_fits(self):
        template = (
            Path(__file__).resolve().parents[1]
            / "templates" / "l3-jfi-boundary-b-v1.sh"
        ).read_text()
        self.assertIn("jfi_candidate_universe.py", template)
        self.assertIn("CANDIDATE_RECORDS=10000000", template)
        self.assertIn("SIZER_RECORDS=20000", template)
        self.assertIn("TARGET_READS_BEFORE_SELECTION_FREEZE__0", template)
        self.assertIn("NEXT_BOUNDARY__GO_JFI_ACTIVE", template)
        self.assertNotIn("jfi_active_select_stream.py", template)
        self.assertNotIn("train_stream.py", template)
        self.assertNotIn("run_jass_gate_bounded.py", template)
        self.assertIn(': "${JFI_AB_ROOT:?}"', template)
        self.assertIn('AB_ROOT="$JFI_AB_ROOT"', template)
        self.assertIn("JFI-A/B root identity mismatch", template)
        self.assertNotIn(
            "r2:jass-data/runs/cpx62-1749-l3-jfi-factorial-l2-fit-v1/"
            "20260901T225526Z-25bb488e",
            template,
        )

    def test_downstream_templates_pin_authorized_jfi_ab_identity(self):
        template_dir = Path(__file__).resolve().parents[1] / "templates"
        for name in (
            "l3-jfi-active-select-v1.sh",
            "l3-jfi-active-fit-v1.sh",
            "l3-jfi-d-active4-select-v1.sh",
            "l3-jfi-d-active4-fit-v1.sh",
        ):
            with self.subTest(template=name):
                template = (template_dir / name).read_text()
                self.assertIn(': "${JFI_AB_ROOT:?}"', template)
                self.assertIn('AB_ROOT="$JFI_AB_ROOT"', template)
                self.assertIn("JFI-A/B root identity mismatch", template)
                self.assertIn("JFI-A/B scientific code drift", template)
                self.assertNotIn(
                    "r2:jass-data/runs/cpx62-1749-l3-jfi-factorial-l2-fit-v1/"
                    "20260901T225526Z-25bb488e",
                    template,
                )

    def test_selector_template_publishes_before_any_target_access(self):
        template = (
            Path(__file__).resolve().parents[1]
            / "templates" / "l3-jfi-active-select-v1.sh"
        ).read_text()
        self.assertIn("jfi_active_select_stream.py", template)
        self.assertIn("JFI_C_SELECTION_MANIFEST.json", template)
        self.assertIn("TARGET_READS_TOTAL__0", template)
        self.assertIn("SELECTION_FROZEN", template)
        self.assertNotIn("jfi_active_materialize.py", template)
        self.assertNotIn("train_stream.py", template)
        self.assertNotIn("l3_conditional_targets.py", template)
        self.assertNotIn("--target-values", template)
        self.assertNotIn("run_jass_gate_bounded.py", template)

    def test_active_fit_template_consumes_completed_selection_and_has_two_fits(self):
        template = (
            Path(__file__).resolve().parents[1]
            / "templates" / "l3-jfi-active-fit-v1.sh"
        ).read_text()
        self.assertIn("SELECTION_FROZEN", template)
        self.assertIn("jfi_active_materialize.py", template)
        self.assertIn("jfi_active_targets.py", template)
        self.assertIn("--bootstrap-seed 2026120104", template)
        self.assertIn("JFI_ACTIVE_INFORMATION_GAIN_NOT_ESTABLISHED", template)
        self.assertEqual(template.count("fit_arm active"), 1)
        self.assertEqual(template.count("fit_arm uniform"), 1)
        self.assertNotIn("run_jass_gate_bounded.py", template)
        self.assertNotIn("--prior-mean", template)


if __name__ == "__main__":
    unittest.main()
