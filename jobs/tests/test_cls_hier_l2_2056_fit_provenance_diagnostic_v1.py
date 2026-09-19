from __future__ import annotations

import inspect
import json
from pathlib import Path
import unittest

from jobs.tools import cls_hier_l2_2056_fit_provenance_diagnostic as diag

ROOT = Path(__file__).resolve().parents[2]
PROFILE = ROOT / "jobs" / "launch_profiles" / "cls-hier-l2-2056-fit-provenance-diagnostic-v1.json"


class CLSHierL22056FitProvenanceDiagnosticV1Tests(unittest.TestCase):
    def test_sources_and_terminal_are_frozen(self):
        self.assertEqual(diag.FAILED_JOB, "cpx62-2056-l3-cls-hier-l2-control-reproduction-rehearsal-v3")
        self.assertEqual(diag.FAILED_ATTEMPT, "20260919T043639Z-4ed47cc5")
        self.assertEqual(diag.FAILED_CODE, "4ed47cc53d5bd0da708f7ad1324f9da213c4c215")
        self.assertEqual(diag.HIST_JOB, "cpx62-1341-jass-megacorpus-arm-d-fit-v1")
        self.assertEqual(diag.HIST_ATTEMPT, "20260814T191555Z-18c38a33")
        self.assertEqual(diag.HIST_CODE, "18c38a33ae78c9c2e8e2df62fca266da28dacead")
        self.assertEqual(diag.ACTUAL_2056_SHA, "499a213cbc96fdd43956a9b2f757104970b5afe0817979126c1f7eb92b0aa504")
        self.assertEqual(diag.CURRICULUM_SHA, "319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1")

    def test_metadata_allowlists_are_small_and_model_free(self):
        self.assertEqual(
            [remote for remote, _ in diag.FAILED_FILES],
            [
                "artefacts/optimizer.json",
                "artefacts/fit-receipt.json",
                "artefacts/target-consumption.json",
                "artefacts/runtime-authentication.json",
            ],
        )
        self.assertEqual(
            [remote for remote, _ in diag.HIST_FILES],
            [
                "artefacts/D-optimizer.json",
                "artefacts/D-convergence.json",
                "artefacts/D-target-consumption.json",
            ],
        )
        code = inspect.getsource(diag)
        for forbidden in (
            "model.pjtw.gz", "D-c-prior-then-current.pjtw.gz", "logs.tar.gz",
            "current-context30.npy.gz", "turnover1to1.jnnw.gz", "current.feat",
        ):
            self.assertNotIn(forbidden, code)

    def test_comparison_helpers_are_fail_closed_and_bounded(self):
        target = {"source": {"sha256": "a" * 64, "size_bytes": 100}, "records": 10}
        view = diag.target_view(target)
        self.assertEqual(view["source_sha256"], "a" * 64)
        self.assertEqual(diag.differing_top_level_keys({"a": 1}, {"a": 2, "b": 3}), ["a", "b"])
        self.assertEqual(
            diag.without_cosmetic_fields({"label": "D", "arm": "CONTROL", "success": True, "nit": 4}),
            {"success": True, "nit": 4},
        )

    def test_profile_is_zero_effect(self):
        profile = json.loads(PROFILE.read_text(encoding="utf-8"))
        self.assertEqual(profile["required_phases"], [diag.PHASE])
        self.assertEqual(
            profile["command"],
            ["/usr/bin/python3", "jobs/tools/cls_hier_l2_2056_fit_provenance_diagnostic.py"],
        )
        self.assertEqual(profile["rehearsal_max_effects"], profile["production_max_effects"])
        self.assertTrue(all(value == 0 for value in profile["rehearsal_max_effects"].values()))


if __name__ == "__main__":
    unittest.main()
