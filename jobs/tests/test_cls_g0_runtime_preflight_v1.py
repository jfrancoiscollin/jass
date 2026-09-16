from __future__ import annotations

import csv
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from jobs.tools import cls_g0_runtime_preflight_launch_stage as launch
from jobs.tools import cls_g0_runtime_preflight_stage as stage

ROOT = Path(__file__).resolve().parents[2]


class CLSG0RuntimePreflightV1Tests(unittest.TestCase):
    def test_root_selection_is_deterministic_and_balanced(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            deep = root / "deep512.tsv"
            rows = []
            idx = 0
            for phase in stage.gate.PHASES:
                for n in range(stage.gate.ROOTS_PER_PHASE):
                    rows.append({
                        "parent_id": str(idx),
                        "canonical_fingerprint": f"{phase}-fingerprint-{n:03d}",
                        "phase": phase,
                    })
                    idx += 1
            with deep.open("w", newline="", encoding="utf-8") as stream:
                writer = csv.DictWriter(stream, fieldnames=list(rows[0]), delimiter="\t", lineterminator="\n")
                writer.writeheader()
                writer.writerows(rows)
            ids1, subset1 = root / "ids1.txt", root / "subset1.tsv"
            ids2, subset2 = root / "ids2.txt", root / "subset2.tsv"
            first = stage.select_roots(deep, ids1, subset1)
            second = stage.select_roots(deep, ids2, subset2)
            self.assertEqual(first, second)
            self.assertEqual(ids1.read_bytes(), ids2.read_bytes())
            self.assertEqual(subset1.read_bytes(), subset2.read_bytes())
            self.assertEqual(len(first), 32)
            self.assertEqual(len({row["parent_id"] for row in first}), 32)
            self.assertEqual(
                {phase: sum(row["phase"] == phase for row in first) for phase in stage.gate.PHASES},
                {phase: 8 for phase in stage.gate.PHASES},
            )

    def test_launch_profile_freezes_identity_preflight_effects(self) -> None:
        profile = json.loads((ROOT / "jobs/launch_profiles/cls-g0-runtime-tooling-preflight-v1.json").read_text())
        self.assertEqual(profile["campaign"], "cls-v1")
        self.assertEqual(profile["required_phases"], launch.PHASES)
        self.assertEqual(profile["rehearsal_max_effects"], profile["production_max_effects"])
        effects = profile["rehearsal_max_effects"]
        self.assertEqual(effects["new_jass_searches"], 96)
        self.assertEqual(effects["new_scan_searches"], 0)
        self.assertEqual(effects["fits"], 0)
        self.assertEqual(effects["strength_games"], 0)
        self.assertEqual(effects["promotions"], 0)
        self.assertEqual(effects["bakes"], 0)
        self.assertEqual(effects["test_target_reads"], 0)

    def test_preflight_is_byte_identity_not_a_candidate(self) -> None:
        text = (ROOT / "jobs/tools/cls_g0_runtime_preflight_stage.py").read_text(encoding="utf-8")
        self.assertIn("str(curriculum), str(curriculum)", text)
        self.assertIn('"identity_parent_candidate": True', text)
        self.assertIn('"candidate_reads": 0', text)
        self.assertIn('"next_stage": "OPEN_CLS_L_LEARNING_OBJECTIVE_ATTRIBUTION_PREREG"', text)
        self.assertNotIn("train.py", text)

    def test_2016_fetch_workdirs_exist_before_authenticated_fetch_helpers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            work = root / "work"
            artifacts = root / "artifacts"

            def fake_fetch_inputs(path: Path):
                self.assertEqual(path, work / "base-inputs")
                self.assertTrue(path.is_dir())
                placeholder = root / "placeholder"
                return placeholder, placeholder, placeholder, placeholder, placeholder

            def fake_authenticate_sources(path: Path, out: Path):
                self.assertEqual(path, work / "source-auth")
                self.assertTrue(path.is_dir())
                self.assertEqual(out, artifacts)
                raise RuntimeError("stop-after-workdir-proof")

            with mock.patch.object(stage.base, "fetch_inputs", side_effect=fake_fetch_inputs), \
                    mock.patch.object(stage.profile, "authenticate_sources", side_effect=fake_authenticate_sources):
                with self.assertRaisesRegex(RuntimeError, "stop-after-workdir-proof"):
                    stage.run_stage(work, artifacts)


if __name__ == "__main__":
    unittest.main()
