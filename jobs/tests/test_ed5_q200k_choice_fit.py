from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from jobs.tools import ed3_label_pressure as audit
from jobs.tools import ed4_choice_value_fit as ed4fit
from jobs.tools import ed5_q200k_choice as qchoice
from jobs.tools import ed5_q200k_choice_fit as p
from jobs.tools import ed5_q200k_teacher_stage as teacher
from jobs.tools.ed4_choice_fixtures import fixture
from jobs.tools.launch_runtime_v2 import atomic_json


class ED5Q200KChoiceFitTests(unittest.TestCase):
    def test_scientific_recipe_is_exact_ed4_recipe(self):
        self.assertIs(p.RECIPE, ed4fit.RECIPE)
        self.assertEqual(p.recipe_sha(), ed4fit.recipe_sha())
        self.assertEqual(p.MODEL_HASH, ed4fit.MODEL_HASH)
        self.assertEqual(p.MODEL_NAME, "ED5_Q200K_CHOICE.pjtw")

    def test_fit_allowlists_have_no_confirmation_target_or_old_train_teacher(self):
        joined = "\n".join(p.N1_NAMES + p.TEACHER_NAMES)
        self.assertNotIn("test-", joined)
        self.assertNotIn("holdout-native", joined)
        self.assertNotIn("train-labels-sealed", joined)
        self.assertNotIn("train-0.jsonl", joined)
        self.assertNotIn("scientific-summary", joined)
        self.assertEqual(set(p.TEACHER_NAMES[2:]), {f"train-q200k-{i}.jsonl" for i in range(teacher.WORKERS)})

    def _teacher_fixture(self, root: Path):
        groups = [
            {"id": 1, "stm": 1, "rows": [0, 1, 2], "terminals": []},
            {"id": 2, "stm": 0, "rows": [3, 4], "terminals": [4]},
        ]
        scores = {(0, teacher.NODE_BUDGET): 9, (1, teacher.NODE_BUDGET): 9,
                  (2, teacher.NODE_BUDGET): -1, (3, teacher.NODE_BUDGET): 5}
        choices = qchoice.groups_from_q200k(groups, scores)
        payload = [{"parent_id": g["id"], "stm": g["stm"], "V": g["V"], "A": g["A"]} for g in choices]
        atomic_json(root / "choice-sets.json", {"schema": "jass.ed5.q200k_choice_sets.v1", "node_budget": teacher.NODE_BUDGET, "parents": payload})
        teacher_files = {}
        for i in range(teacher.WORKERS):
            name = f"train-q200k-{i}.jsonl"
            (root / name).write_text("", encoding="utf-8")
            teacher_files[name] = audit.sha(root / name)
        seal = {
            "schema": "jass.ed5.q200k_teacher_seal.v1", "role": "train_teacher_only", "mode": "production",
            "source_seal_sha256": audit.SOURCE_SEAL, "scan_sha256": teacher.SCAN_SHA256,
            "node_budget": teacher.NODE_BUDGET, "train_parents": p.TRAIN_PARENTS, "train_rows": p.TRAIN_ROWS,
            "teacher_files": teacher_files, "choice_sets_sha256": audit.sha(root / "choice-sets.json"),
            "confirmation_target_reads": 0, "candidate_reads": 0, "fits": 0, "alpha_spent": 0.0,
            "runtime_authorized": False, "promotion_authorized": False,
        }
        atomic_json(root / "teacher-seal.json", seal)
        return groups, scores, choices

    def test_teacher_seal_and_choice_sets_are_recomputed_before_fit(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            groups, scores, expected = self._teacher_fixture(root)
            with patch.object(teacher, "load_teacher", return_value=(scores, 4972)):
                got, seal, calls = p.validate_teacher_binding(root, groups)
            self.assertEqual(got, expected)
            self.assertEqual(calls, 4972)
            self.assertEqual(seal["confirmation_target_reads"], 0)

    def test_tampered_choice_set_fails_before_fit(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            groups, scores, _ = self._teacher_fixture(root)
            value = json.loads((root / "choice-sets.json").read_text())
            value["parents"][0]["A"] = [2]
            atomic_json(root / "choice-sets.json", value)
            seal = json.loads((root / "teacher-seal.json").read_text())
            seal["choice_sets_sha256"] = audit.sha(root / "choice-sets.json")
            atomic_json(root / "teacher-seal.json", seal)
            with patch.object(teacher, "load_teacher", return_value=(scores, 4972)):
                with self.assertRaisesRegex(ValueError, "choice_sets_not_reproducible"):
                    p.validate_teacher_binding(root, groups)

    def test_one_solve_semantics(self):
        sentinel_beta = np.zeros(240)
        sentinel_report = {"success": True}
        with patch.object(p.math, "fit", return_value=(sentinel_beta, sentinel_report)) as optimizer:
            beta, report = p.solve_once({"fixture": True})
        optimizer.assert_called_once_with({"fixture": True})
        self.assertIs(beta, sentinel_beta)
        self.assertIs(report, sentinel_report)

    def test_rehearsal_production_solver_bytes_are_deterministic(self):
        design, _ = fixture()
        b1, r1 = p.solve_once(design)
        b2, r2 = p.solve_once(design)
        self.assertTrue(np.array_equal(np.asarray(b1, dtype="<f8"), np.asarray(b2, dtype="<f8")))
        self.assertEqual(hashlib.sha256(np.asarray(b1, dtype="<f8").tobytes()).hexdigest(),
                         hashlib.sha256(np.asarray(b2, dtype="<f8").tobytes()).hexdigest())
        self.assertEqual(r1, r2)


if __name__ == "__main__":
    unittest.main()
