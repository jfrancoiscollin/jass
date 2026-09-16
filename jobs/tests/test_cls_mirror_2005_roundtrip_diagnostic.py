from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from jobs.tools import cls_mirror_2005_roundtrip_diagnostic_stage as stage
from jobs.tools.launch_gate_v2 import published_output_sha
from jobs.tools.launch_runtime_v2 import atomic_json


class ClsMirror2005RoundtripDiagnosticTests(unittest.TestCase):
    def test_frozen_source_and_zero_effect_profile(self):
        self.assertEqual(stage.SOURCE_JOB, "cpx62-2004-l3-cls-mirror-scale-rehearsal-v3")
        self.assertEqual(stage.SOURCE_ATTEMPT, "20260916T124649Z-f769bc39")
        self.assertEqual(stage.SOURCE_CODE_SHA, "f769bc396ab8a9cd9e473908ca62b96fc54f1076")
        self.assertEqual(stage.SOURCE_RECEIPT_SHA256, "1e86eaa354265a09078fe12cd8b1b5c35630e31141fbe7b305008dbd9bc448f4")
        profile_path = Path(__file__).resolve().parents[1] / "launch_profiles" / "cls-mirror-2005-roundtrip-diagnostic-v1.json"
        profile = json.loads(profile_path.read_text())
        self.assertEqual(profile["stage"], "cls-mirror-2005-roundtrip-diagnostic-v1")
        self.assertEqual(profile["command"], ["/usr/bin/python3", "jobs/tools/cls_mirror_2005_roundtrip_diagnostic_stage.py"])
        self.assertEqual(profile["required_phases"], stage.PHASES)
        self.assertEqual(profile["evidence_outputs"], ["roundtrip-diagnostic.json"])
        self.assertTrue(all(v == 0 for v in profile["rehearsal_max_effects"].values()))
        self.assertTrue(all(v == 0 for v in profile["production_max_effects"].values()))

    def test_compare_outputs_reports_only_proven_mismatch(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            for name in stage.ROUNDTRIP_NAMES:
                path = root / name
                if name.endswith(".json"):
                    atomic_json(path, {"name": name, "value": 1})
                else:
                    path.write_text(name + "\n")
            summary = {"schema": "jass.test.v1", "state": "completed", "roots": 512}
            atomic_json(root / "scientific-summary.json", summary)
            expected = {name: published_output_sha(root / name, name) for name in stage.ROUNDTRIP_NAMES}
            decorated = dict(summary)
            decorated["launch"] = {
                "mode": "rehearsal",
                "receipt_sha256": "a" * 64,
                "common_spec_sha256": "b" * 64,
                "production_admitted": False,
                "publisher_roundtrip_verified": False,
            }
            atomic_json(root / "scientific-summary.json", decorated)
            proof = {"output_sha256": expected}
            _, mismatches = stage.compare_outputs(root, proof)
            self.assertEqual(mismatches, [])

            (root / "manifest.json").write_text('{"changed":true}\n')
            _, mismatches = stage.compare_outputs(root, proof)
            self.assertEqual([x["path"] for x in mismatches], ["manifest.json"])
            self.assertNotEqual(mismatches[0]["expected_sha256"], mismatches[0]["actual_published_sha256"])

    def test_compare_outputs_fails_closed_on_receipt_key_drift(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            proof = {"output_sha256": {}}
            with self.assertRaisesRegex(RuntimeError, "receipt_output_hash_contract"):
                stage.compare_outputs(root, proof)


if __name__ == "__main__":
    unittest.main()
