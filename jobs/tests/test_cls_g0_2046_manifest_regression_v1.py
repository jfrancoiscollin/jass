from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from jobs.tools import cls_g0_valid_arm_launch_stage as launch
from jobs.tools import cls_g0_valid_arm_stage as stage


class CLSG02046ManifestRegressionV1Tests(unittest.TestCase):
    def test_required_launch_manifest_is_sealed_without_changing_science(self) -> None:
        # Regression boundary: seal transport evidence only; never reinterpret the 2046 readout.
        with tempfile.TemporaryDirectory() as tmp:
            art = Path(tmp)
            for index, name in enumerate(launch.MANIFEST_EVIDENCE, start=1):
                (art / name).write_bytes(f"sealed-{index}\n".encode("ascii"))
            summary = {
                "terminal": "CLS_G0_RUNTIME_CATASTROPHE_GATE_FAIL_V1",
                "scientific_verdict": "FAIL",
                "roots": 512,
                "budget_nodes": 200000,
                "new_jass_searches": 1536,
            }
            launch._write_manifest(art, "LOCAL", "rehearsal", summary)
            manifest = json.loads((art / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["schema"], "jass.cls_g0_valid_arm_runtime_manifest.v1")
            self.assertEqual(manifest["terminal"], summary["terminal"])
            self.assertEqual(manifest["scientific_verdict"], "FAIL")
            self.assertEqual(manifest["candidate_arm"], "LOCAL")
            self.assertEqual(manifest["candidate_sha256"], stage.ARM_MODEL_SHA["LOCAL"])
            self.assertEqual(manifest["direct_parent_sha256"], stage.CURRICULUM_SHA)
            self.assertEqual(manifest["fixed_curriculum_anchor_sha256"], stage.CURRICULUM_SHA)
            self.assertEqual(manifest["roots"], 512)
            self.assertEqual(manifest["budget_nodes"], 200000)
            self.assertEqual(set(manifest["evidence"]), set(launch.MANIFEST_EVIDENCE))
            for name in launch.MANIFEST_EVIDENCE:
                payload = (art / name).read_bytes()
                self.assertEqual(manifest["evidence"][name]["sha256"], hashlib.sha256(payload).hexdigest())
                self.assertEqual(manifest["evidence"][name]["size_bytes"], len(payload))
            effects = manifest["scientific_side_effects"]
            self.assertEqual(effects["new_jass_searches"], 1536)
            for key in (
                "target_reads", "confirmation_target_reads", "fits", "new_scan_searches",
                "strength_games", "selfplay_games", "alpha_spent", "promotions", "bakes",
            ):
                self.assertEqual(effects[key], 0)
            self.assertFalse(manifest["promotion_authorized"])
            self.assertFalse(manifest["bake_authorized"])

    def test_manifest_fails_closed_if_required_stage_evidence_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            art = Path(tmp)
            for name in launch.MANIFEST_EVIDENCE[:-1]:
                (art / name).write_text("sealed\n", encoding="ascii")
            with self.assertRaisesRegex(RuntimeError, "manifest evidence missing/nonempty:RESULTS.md"):
                launch._write_manifest(
                    art,
                    "LOCAL",
                    "rehearsal",
                    {"terminal": "x", "scientific_verdict": "FAIL", "new_jass_searches": 1536},
                )


if __name__ == "__main__":
    unittest.main()
