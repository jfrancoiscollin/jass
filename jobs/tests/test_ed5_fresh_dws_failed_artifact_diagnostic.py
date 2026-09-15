from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from jobs.tools import ed5_fresh_dws_failed_artifact_diagnostic_stage as stage


class Ed5FreshDwsFailedArtifactDiagnosticTests(unittest.TestCase):
    def source_report(self) -> dict:
        return {
            "schema": "jass.ed5.fresh_dws_historical_disjointness.v1",
            "state": "failed",
            "terminal": "ED5_FRESH_DWS_HISTORICAL_COLLISION_TECHNICAL_FAILURE_V1",
            "mode": "rehearsal",
            "sources": {"D": {}, "W": {}, "S": {}},
            "counts": {"D": 1, "W": 1, "S": 1},
            "pairwise_overlaps": {"D_W": {"count": 0, "digest": "a"}, "D_S": {"count": 0, "digest": "a"}, "W_S": {"count": 0, "digest": "a"}},
            "historical_overlaps": {"D": {}, "W": {}, "S": {}},
            "historical_sources": {},
            "pairwise_and_historical_disjoint": False,
            "target_reads": 0,
            "candidate_reads": 0,
            "control_evaluations": 0,
            "scan_searches": 0,
            "jass_searches": 0,
            "fits": 0,
            "alpha_spent": 0,
            "confirmation_target_consumed": False,
            "next_stage": "PRE_TARGET_COLLISION_RECOVERY_ONLY",
        }

    def run_fixture(self, report: dict):
        td = tempfile.TemporaryDirectory()
        root = Path(td.name)
        result = root / "result"
        artifact = result / "artefacts"
        result.mkdir()
        artifact.mkdir()
        raw = (json.dumps(report, indent=2, sort_keys=True) + "\n").encode()

        def fake_fetch_files(**kwargs):
            self.assertEqual(kwargs["expected_state"], "failed")
            self.assertEqual(kwargs["prefix"], stage.SOURCE_PREFIX)
            self.assertEqual(kwargs["selections"], [(stage.SOURCE_REMOTE_PATH, stage.LOCAL_NAME)])
            out = kwargs["out_dir"]
            out.mkdir(parents=True, exist_ok=True)
            (out / stage.LOCAL_NAME).write_bytes(raw)
            import hashlib
            return {
                "job_id": stage.SOURCE_JOB,
                "attempt_id": stage.SOURCE_ATTEMPT,
                "code_sha": stage.SOURCE_CODE_SHA,
                "result_state": "failed",
                "exit_code": 2,
                "files": [{
                    "path": stage.SOURCE_REMOTE_PATH,
                    "local_name": stage.LOCAL_NAME,
                    "sha256": hashlib.sha256(raw).hexdigest(),
                    "size_bytes": len(raw),
                }],
            }

        env = {
            "JASS_RESULT_DIR": str(result),
            "JASS_ARTEFACT_DIR": str(artifact),
            "LAUNCH_MODE": "rehearsal",
        }
        return td, artifact, raw, fake_fetch_files, env

    def test_republishes_exact_failed_overlap_artifact_with_zero_reads(self):
        report = self.source_report()
        td, artifact, raw, fake_fetch_files, env = self.run_fixture(report)
        with td, mock.patch.dict(os.environ, env, clear=False), mock.patch.object(stage, "fetch_files", side_effect=fake_fetch_files):
            self.assertEqual(stage.main(), 0)
            self.assertEqual((artifact / stage.LOCAL_NAME).read_bytes(), raw)
            summary = json.loads((artifact / "scientific-summary.json").read_text())
            self.assertEqual(summary["classification"], "TECHNICAL_DIAGNOSTIC_ONLY")
            self.assertEqual(summary["recovered"], report)
            for key, expected in stage.ZERO_FIELDS.items():
                self.assertEqual(summary[key], expected)
            self.assertIsNone(summary["scientific_verdict"])
            self.assertFalse(summary["confirmation_authorized"])

    def test_fails_closed_if_failed_artifact_claims_target_consumption(self):
        report = self.source_report()
        report["target_reads"] = 1
        td, artifact, _raw, fake_fetch_files, env = self.run_fixture(report)
        with td, mock.patch.dict(os.environ, env, clear=False), mock.patch.object(stage, "fetch_files", side_effect=fake_fetch_files):
            self.assertEqual(stage.main(), 2)
            summary = json.loads((artifact / "scientific-summary.json").read_text())
            self.assertEqual(summary["classification"], "TECHNICAL")
            self.assertEqual(summary["target_reads"], 0)
            self.assertIsNone(summary["scientific_verdict"])

    def test_profile_is_read_only_and_binds_this_stage(self):
        profile = json.loads((Path(__file__).resolve().parents[1] / "launch_profiles" / "ed5-fresh-dws-failed-artifact-diagnostic-v1.json").read_text())
        self.assertEqual(profile["command"], ["/usr/bin/python3", "jobs/tools/ed5_fresh_dws_failed_artifact_diagnostic_stage.py"])
        self.assertEqual(profile["required_phases"], stage.PHASES)
        for effects in (profile["rehearsal_max_effects"], profile["production_max_effects"]):
            self.assertTrue(all(value == 0 for value in effects.values()))


if __name__ == "__main__":
    unittest.main()
