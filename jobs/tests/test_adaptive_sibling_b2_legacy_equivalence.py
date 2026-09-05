from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from jobs.tools import adaptive_sibling_b2_legacy_equivalence as subject
from jobs.tools import adaptive_sibling_b2_projection as projection
from jobs.tools import adaptive_sibling_teacher_shadow as legacy


def row(
    row_index: int,
    *,
    parent_id: int = 7,
    stm: int = 1,
    pieces: int = 15,
    q5: int = 0,
    q50: int = 0,
    q200: int = 0,
    utility: int = 2,
    terminal: bool = False,
    tb: bool = False,
    n5: int = 5,
    n50: int = 50,
    n200: int = 200,
) -> subject.HistoricalRowV1:
    return subject.HistoricalRowV1(
        row_index=row_index,
        parent_id=parent_id,
        parent_stm=stm,
        parent_pieces=pieces,
        child_rule_terminal=terminal,
        child_tb_exact=tb,
        exact_parent_utility=utility,
        q5k_parent=q5,
        q50_parent=q50,
        q200_parent=q200,
        nodes5k=n5,
        nodes50k=n50,
        nodes200k=n200,
    )


def ordinary_parent() -> list[subject.HistoricalRowV1]:
    return [
        row(0, q5=300, q50=500, q200=10, n200=100),
        row(1, q5=250, q50=450, q200=20, n200=200),
        row(2, q5=0, q50=0, q200=900, n200=300),
    ]


class ParentEquivalenceTests(unittest.TestCase):
    def test_projection_input_and_allocation_hashes_exclude_q200(self):
        original = ordinary_parent()
        changed = [
            subject.HistoricalRowV1(**{
                **{field: getattr(item, field) for field in item.__slots__},
                "q200_parent": -item.q200_parent - 1,
            }) for item in original
        ]
        before_value = subject.projection_parent(original)
        after_value = subject.projection_parent(changed)
        self.assertEqual(before_value, after_value)
        self.assertTrue(all(
            "q200" not in key.lower()
            for projected_row in before_value["rows"] for key in projected_row
        ))

        before = subject.compare_parent(original)
        after = subject.compare_parent(changed)
        self.assertEqual(before.projection_input_sha256, after.projection_input_sha256)
        self.assertEqual(before.decision_input_sha256, after.decision_input_sha256)
        self.assertEqual(before.decision_output_sha256, after.decision_output_sha256)
        self.assertEqual(before.allocation_decision, after.allocation_decision)
        self.assertNotEqual(before.shadow_choice, after.shadow_choice)
        self.assertGreater(before.postseal_q200_selection_reads, 0)
        self.assertGreater(before.postseal_q200_reference_reads, 0)

    def test_nodes200_charged_and_uncharged_perturbations(self):
        base_rows = ordinary_parent()
        base = subject.compare_parent(base_rows)

        charged_rows = copy.deepcopy(base_rows)
        charged_rows[0] = subject.HistoricalRowV1(**{
            **{field: getattr(charged_rows[0], field) for field in charged_rows[0].__slots__},
            "nodes200k": charged_rows[0].nodes200k + 17,
        })
        charged = subject.compare_parent(charged_rows)
        self.assertNotEqual(base.projection_input_sha256, charged.projection_input_sha256)
        self.assertEqual(base.decision_input_sha256, charged.decision_input_sha256)
        self.assertEqual(base.decision_output_sha256, charged.decision_output_sha256)
        self.assertEqual(base.allocation_decision, charged.allocation_decision)
        self.assertEqual(charged.shadow_nodes - base.shadow_nodes, 17)

        uncharged_rows = copy.deepcopy(base_rows)
        uncharged_rows[2] = subject.HistoricalRowV1(**{
            **{field: getattr(uncharged_rows[2], field) for field in uncharged_rows[2].__slots__},
            "nodes200k": uncharged_rows[2].nodes200k + 23,
        })
        uncharged = subject.compare_parent(uncharged_rows)
        self.assertNotEqual(base.projection_input_sha256, uncharged.projection_input_sha256)
        self.assertEqual(base.decision_input_sha256, uncharged.decision_input_sha256)
        self.assertEqual(base.decision_output_sha256, uncharged.decision_output_sha256)
        self.assertEqual(base.allocation_decision, uncharged.allocation_decision)
        self.assertEqual(base.shadow_nodes, uncharged.shadow_nodes)
        self.assertEqual(uncharged.full_nodes - base.full_nodes, 23)

    def test_exact_shortcuts_and_sole_survivor_reconstruct_frozen_b1(self):
        cases = [
            [row(0, terminal=True, utility=1), row(1, q5=50, q50=50, q200=50)],
            [row(0, terminal=True, utility=0), row(1, tb=True, utility=-1)],
            [row(0, terminal=True, utility=0), row(1, q5=50, q50=50, q200=50)],
        ]
        for rows in cases:
            with self.subTest(rows=rows):
                result = subject.compare_parent(rows)
                self.assertTrue(result.decision_match)
                self.assertTrue(result.final_result_match)

    def test_phase_is_derived_and_inconsistent_metadata_fails(self):
        for pieces, expected in ((40, "P0"), (20, "P1"), (12, "P2"), (9, "P3")):
            value = subject.projection_parent([row(0, pieces=pieces), row(1, pieces=pieces)])
            self.assertEqual(value["phase"], expected)
        inconsistent = [row(0, pieces=15), row(1, pieces=16)]
        with self.assertRaisesRegex(subject.EquivalenceError, "inconsistent parent metadata"):
            subject.projection_parent(inconsistent)


class ReportAndBoundaryTests(unittest.TestCase):
    def test_report_limits_historical_semantic_claims(self):
        rows = ordinary_parent()
        old_report, _ = legacy.build_report(subject._legacy_rows(rows))
        aggregate = {key: old_report[key] for key in subject.EXPECTED_B1_AGGREGATE}
        report_sha = hashlib.sha256(subject._legacy_report_bytes(old_report)).hexdigest()
        with mock.patch.object(subject, "EXPECTED_ROWS", len(rows)), \
             mock.patch.object(subject, "EXPECTED_PARENTS", 1), \
             mock.patch.object(subject, "EXPECTED_B1_AGGREGATE", aggregate), \
             mock.patch.object(subject, "EXPECTED_B1_REPORT_SHA256", report_sha):
            report = subject.build_equivalence_report(rows, "a" * 64)
        self.assertEqual(report["equivalence"]["allocation_decision_matches"], 1)
        self.assertEqual(report["equivalence"]["final_b1_result_matches"], 1)
        self.assertEqual(report["information_barrier"]["q200_value_reads"], 0)
        self.assertEqual(report["information_barrier"]["q200_label_reads"], 0)
        self.assertEqual(report["information_barrier"]["q200_policy_reads"], 0)
        self.assertEqual(report["information_barrier"]["q200_policy_branches"], 0)
        self.assertEqual(report["information_barrier"]["q200_fields_in_projection_decision"], 0)
        scope = report["historical_semantic_scope"]
        self.assertTrue(scope["allocation_sets_choices_costs_and_b1_aggregate_compared"])
        self.assertFalse(scope["complete_move_identity_compared"])
        self.assertFalse(scope["captured_square_bitboard_compared"])
        self.assertFalse(scope["score_provenance_or_signal_family_compared"])
        self.assertFalse(scope["fresh_confirmation_claimed"])
        self.assertFalse(scope["b2_gate_claimed"])

    def test_frozen_cardinality_and_aggregate_fail_closed(self):
        rows = ordinary_parent()
        with self.assertRaisesRegex(subject.EquivalenceError, "cardinality"):
            subject.build_equivalence_report(rows, "a" * 64)

        old_report, _ = legacy.build_report(subject._legacy_rows(rows))
        wrong = {key: old_report[key] for key in subject.EXPECTED_B1_AGGREGATE}
        wrong["shadow_nodes"] += 1
        with mock.patch.object(subject, "EXPECTED_ROWS", len(rows)), \
             mock.patch.object(subject, "EXPECTED_PARENTS", 1), \
             mock.patch.object(subject, "EXPECTED_B1_AGGREGATE", wrong):
            with self.assertRaisesRegex(subject.EquivalenceError, "shadow_nodes mismatch"):
                subject.build_equivalence_report(rows, "a" * 64)

    def test_source_identity_and_output_alias_fail_before_write(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "groups.tsv.gz"
            source.write_bytes(b"not-the-teacher")
            with self.assertRaisesRegex(subject.EquivalenceError, "frozen teacher-1574"):
                subject.load_historical_groups(source, "0" * 64)
            with self.assertRaisesRegex(subject.EquivalenceError, "distinct"):
                subject.run(source, subject.EXPECTED_GROUPS_SHA256, source)
            self.assertEqual(source.read_bytes(), b"not-the-teacher")

    def test_standalone_cli_imports_outside_repository_cwd(self):
        tool = Path(subject.__file__).resolve()
        with tempfile.TemporaryDirectory() as temporary:
            completed = subprocess.run(
                [sys.executable, str(tool), "--help"], cwd=temporary,
                capture_output=True, text=True, check=False,
            )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("--expected-groups-sha256", completed.stdout)

    def test_published_companions_are_exact_hashed_and_roundtrip(self):
        rows = ordinary_parent()
        old_report, old_results = legacy.build_report(subject._legacy_rows(rows))
        aggregate = {key: old_report[key] for key in subject.EXPECTED_B1_AGGREGATE}
        report_sha = hashlib.sha256(subject._legacy_report_bytes(old_report)).hexdigest()
        with tempfile.TemporaryDirectory() as temporary, \
             mock.patch.object(subject, "EXPECTED_ROWS", len(rows)), \
             mock.patch.object(subject, "EXPECTED_PARENTS", 1), \
             mock.patch.object(subject, "EXPECTED_B1_AGGREGATE", aggregate), \
             mock.patch.object(subject, "EXPECTED_B1_REPORT_SHA256", report_sha), \
             mock.patch.object(subject, "load_historical_groups", return_value=rows):
            root = Path(temporary)
            source = root / "groups.tsv.gz"
            source.write_bytes(b"fixture")
            out_report = root / "equivalence-report.json"
            report = subject.run(source, subject.EXPECTED_GROUPS_SHA256, out_report)
            self.assertEqual(json.loads(out_report.read_bytes()), report)
            for name, filename in subject.COMPANION_FILENAMES.items():
                path = root / filename
                raw = path.read_bytes()
                receipt = report["published_artifacts"][name]
                self.assertEqual(receipt["filename"], filename)
                self.assertEqual(receipt["size_bytes"], len(raw))
                self.assertEqual(receipt["sha256"], hashlib.sha256(raw).hexdigest())
            reference = root / "reference-decisions.tsv"
            legacy.write_decisions(reference, old_results)
            self.assertEqual(
                (root / subject.COMPANION_FILENAMES["legacy_decisions"]).read_bytes(),
                reference.read_bytes(),
            )
            diff = json.loads((root / subject.COMPANION_FILENAMES["empty_diff"]).read_bytes())
            self.assertEqual(diff["differences"], [])

    def test_companion_alias_and_nonzero_policy_counter_fail_closed(self):
        rows = ordinary_parent()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "groups.tsv.gz"
            source.write_bytes(b"fixture")
            colliding = root / subject.COMPANION_FILENAMES["projection_receipts"]
            with self.assertRaisesRegex(subject.EquivalenceError, "pairwise distinct"):
                subject.run(source, subject.EXPECTED_GROUPS_SHA256, colliding)
            self.assertFalse(colliding.exists())

            case_variant = root / subject.COMPANION_FILENAMES["projection_receipts"].upper()
            with self.assertRaisesRegex(subject.EquivalenceError, "pairwise distinct"):
                subject.run(source, subject.EXPECTED_GROUPS_SHA256, case_variant)
            self.assertFalse(case_variant.exists())

        original = projection.project_parent

        def contaminated(parent):
            receipt, _ = original(parent)
            receipt["q200_value_reads"] = 1
            return receipt, projection.canonical_json_line(receipt)

        with mock.patch.object(projection, "project_parent", side_effect=contaminated):
            with self.assertRaisesRegex(subject.EquivalenceError, "nonzero pre-seal"):
                subject.compare_parent(rows)

    def test_canonical_report_is_separate_from_legacy_pretty_report(self):
        rows = ordinary_parent()
        old_report, _ = legacy.build_report(subject._legacy_rows(rows))
        aggregate = {key: old_report[key] for key in subject.EXPECTED_B1_AGGREGATE}
        report_sha = hashlib.sha256(subject._legacy_report_bytes(old_report)).hexdigest()
        with mock.patch.object(subject, "EXPECTED_ROWS", len(rows)), \
             mock.patch.object(subject, "EXPECTED_PARENTS", 1), \
             mock.patch.object(subject, "EXPECTED_B1_AGGREGATE", aggregate), \
             mock.patch.object(subject, "EXPECTED_B1_REPORT_SHA256", report_sha):
            report = subject.build_equivalence_report(rows, "b" * 64)
        raw = projection.canonical_json_line(report)
        self.assertEqual(raw, projection.canonical_json_line(__import__("json").loads(raw)))
        self.assertNotEqual(raw, subject._legacy_report_bytes(old_report))


if __name__ == "__main__":
    unittest.main()
