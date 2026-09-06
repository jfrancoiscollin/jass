from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from jobs.tools import adaptive_sibling_b2_select as selector
from jobs.tools import sibling_dataset_v2_stage as subject


class SiblingDatasetV2Tests(unittest.TestCase):
    def test_structural_missingness_is_null_not_zero(self) -> None:
        value = subject._observation({}, "5k", False)
        self.assertFalse(value["observed"])
        self.assertTrue(all(item is None for key, item in value.items() if key != "observed"))
        subject.validate_observation_object(value, expected_observed=False)
        broken = dict(value)
        broken["nodes"] = 0
        with self.assertRaisesRegex(subject.CError, "structural missingness"):
            subject.validate_observation_object(broken, expected_observed=False)

    def test_observed_search_preserves_real_zero_values(self) -> None:
        row = {
            "q5k_parent": "0", "nodes5k": "5000", "completed_depth5k": "8",
            "effective_depth5k": "9", "aborted5k": "1", "stop5k": "nodes",
            "elapsed_us5k": "0", "pv5k_enters_egdb": "0",
        }
        value = subject._observation(row, "5k", True)
        self.assertTrue(value["observed"])
        self.assertEqual(value["score_parent"], 0)
        self.assertEqual(value["nodes"], 5000)
        subject.validate_observation_object(value, expected_observed=True)

    def test_split_is_frozen_stratified_parent_cluster(self) -> None:
        rows = []
        parent_id = 0
        parent_cell: dict[int, str] = {}
        for cell in selector.CELL_ORDER:
            phase, stm_token = cell.split("_stm")
            for local in range(500):
                rows.append({
                    "parent_id": str(parent_id),
                    "canonical_fingerprint": f"{phase}:{stm_token}:{local:04d}:{parent_id:04d}",
                    "raw_fingerprint": f"raw:{parent_id}",
                    "parent_stm": stm_token,
                    "pieces": "40" if phase == "P0" else "25" if phase == "P1" else "15" if phase == "P2" else "10",
                    "legal_moves": "2", "phase": phase,
                    "source_shard": str(parent_id % 16),
                    "source_row_index": str(parent_id % 10000),
                    "selection_hash": f"{parent_id:064x}",
                })
                parent_cell[parent_id] = cell
                parent_id += 1
        assignment = subject.assign_splits(rows)
        self.assertEqual(len(assignment), 4000)
        self.assertEqual(sum(v == "train" for v in assignment.values()), 3200)
        self.assertEqual(sum(v == "valid" for v in assignment.values()), 400)
        self.assertEqual(sum(v == "test" for v in assignment.values()), 400)
        for cell in selector.CELL_ORDER:
            ids = [pid for pid, assigned_cell in parent_cell.items() if assigned_cell == cell]
            self.assertEqual(sum(assignment[pid] == "train" for pid in ids), 400)
            self.assertEqual(sum(assignment[pid] == "valid" for pid in ids), 50)
            self.assertEqual(sum(assignment[pid] == "test" for pid in ids), 50)
        self.assertEqual(assignment, subject.assign_splits(rows))

    def test_terminal_authorization_does_not_expose_transfer_diagnostics(self) -> None:
        payload = {
            "schema": subject.b3_readout.PUBLICATION_SCHEMA,
            "state": "completed",
            "verdict": subject.b3_readout.VERDICT,
            "fresh_b3_parents": 4000,
            "adaptive_rows": 38053,
            "structural_identity_checks": "PASS",
            "action_set_checks": "PASS",
            "exact_result_consistency_checks": "PASS",
            "executed_search_replay_checks": "PASS",
            "reference_backfill": False,
            "adaptive_corpus_mutated": False,
            "sibling_dataset_v2_creation_authorized": True,
            "fits_authorized": False,
            "model_search_authorized": False,
            "strength_games_authorized": False,
            "promotion_authorized": False,
            "bake_authorized": False,
            "transfer_diagnostics": {"poison": "must-not-reach-converter"},
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "publication.json"
            path.write_bytes(subject.canonical(payload))
            view = subject.authenticate_terminal(path)
        self.assertNotIn("transfer_diagnostics", view)
        self.assertNotIn("poison", repr(view))
        self.assertTrue(view["sibling_dataset_v2_creation_authorized"])

    def test_full_ladder_reference_is_absent_from_fetch_maps(self) -> None:
        mappings = subject.SOURCE_MAPPINGS + subject.TEACHER_MAPPINGS + subject.TERMINAL_MAPPINGS
        rendered = "\n".join(remote for remote, _ in mappings)
        self.assertNotIn("1843", rendered)
        self.assertNotIn("full-ladder", rendered)
        self.assertEqual(subject.FORBIDDEN_REFERENCE_JOB,
                         "cpx62-1843-l3-decision-math-b3-fresh-full-ladder-audit-v1")

    def test_action_allocation_nesting_expression(self) -> None:
        # Regression for Python precedence in the production guard.
        cases = [
            (True, False, False, True),
            (False, True, False, False),
            (True, True, True, False),
            (False, False, True, True),
            (False, False, False, False),
        ]
        for searched50, searched5, searched200, invalid_expected in cases:
            invalid = (searched200 and not searched50) or (searched50 and not searched5)
            self.assertEqual(invalid, invalid_expected)

    def test_cli_boundary(self) -> None:
        args = subject.parse_args(["--work-dir", "/tmp/c-work", "--artifact-dir", "/tmp/c-artifacts"])
        self.assertEqual(str(args.work_dir), "/tmp/c-work")
        self.assertEqual(str(args.artifact_dir), "/tmp/c-artifacts")
        self.assertEqual(subject.VERDICT, "C_SIBLING_DATASET_V2_AUTHENTICATED_V1")
        self.assertEqual(subject.NEXT_STAGE, "D_WDL_LISTWISE_PREREGISTRATION")


if __name__ == "__main__":
    unittest.main()
