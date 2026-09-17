from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from jobs.tools.launch_runtime_v2 import StageEvidence

ROOT = Path(__file__).resolve().parents[2]
PHASE = "execute-cls-l-source-normalization-preflight"


class CLSL2034ExecutionEvidenceRepairV1Tests(unittest.TestCase):
    def test_2034_failure_shape_is_missing_execution_evidence_only(self):
        profile = json.loads(
            (ROOT / "jobs/launch_profiles/cls-l-source-normalization-preflight-v1.json").read_text()
        )
        self.assertEqual(profile["required_phases"], [PHASE])
        self.assertEqual(profile["rehearsal_max_effects"], profile["production_max_effects"])
        self.assertTrue(all(value == 0 for value in profile["rehearsal_max_effects"].values()))

    def test_shell_emits_completed_required_phase_after_scientific_receipts(self):
        shell = (ROOT / "jobs/templates/l3-cls-l-source-normalization-preflight-v1.sh").read_text()
        evidence_marker = "evidence = StageEvidence(Path(sys.argv[1]), sys.argv[2])"
        self.assertIn(evidence_marker, shell)
        self.assertIn(f"evidence.begin('{PHASE}')", shell)
        self.assertIn("evidence.complete()", shell)
        self.assertIn("evidence.finish()", shell)
        self.assertLess(shell.index("open(f'{art}/manifest.json'"), shell.index(evidence_marker))
        self.assertLess(shell.index("open(f'{art}/scientific-summary.json'"), shell.index(evidence_marker))
        self.assertNotIn("train_stream.py --", shell)
        self.assertNotIn("--max-iter", shell)

    def test_stage_evidence_preserves_final_scientific_summary_and_zero_effects(self):
        with tempfile.TemporaryDirectory() as d:
            art = Path(d)
            frozen_summary = {
                "schema": "jass.cls_l_source_normalization_preflight.v1",
                "terminal": "CLS_L_SOURCE_NORMALIZATION_PREFLIGHT_READY_V1",
                "scientific_verdict": None,
                "fits": 0,
                "strength_games": 0,
            }
            (art / "scientific-summary.json").write_text(
                json.dumps(frozen_summary, sort_keys=True) + "\n", encoding="utf-8"
            )
            evidence = StageEvidence(art, "rehearsal")
            evidence.begin(PHASE)
            evidence.complete()
            evidence.finish()

            published = json.loads((art / "execution-evidence.json").read_text())
            summary = json.loads((art / "scientific-summary.json").read_text())

        self.assertEqual(published["state"], "completed")
        self.assertEqual(published["completed_phases"], [PHASE])
        self.assertTrue(all(value == 0 for value in published["actual_side_effects"].values()))
        self.assertEqual(summary, frozen_summary)


if __name__ == "__main__":
    unittest.main()
