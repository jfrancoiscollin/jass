from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from jobs.tools import adaptive_sibling_b2_legacy_contract_compat as compat
from jobs.tools import adaptive_sibling_b2_teacher_merge as merge_v1


class PrereadLegacyCompatibilityTests(unittest.TestCase):
    def test_omitted_v1_recovery_flags_are_supplied_as_false_only_in_memory(self):
        with tempfile.TemporaryDirectory() as temp:
            report = Path(temp) / "selection-report.json"
            report.write_text(json.dumps({"top_up": False}) + "\n", encoding="ascii")
            original_receipt = {"schema": "frozen-v1"}
            seen = {}

            def validator(receipt, **kwargs):
                seen["receipt"] = dict(receipt)
                seen["kwargs"] = kwargs

            compat.preread_validate_f_compat(
                original_receipt,
                selection_report=report,
                original_validator=validator,
                x="x",
            )
            self.assertEqual(original_receipt, {"schema": "frozen-v1"})
            self.assertEqual(
                {key: seen["receipt"][key]
                 for key in ("top_up", "regeneration", "new_seed")},
                {"top_up": False, "regeneration": False, "new_seed": False},
            )
            self.assertEqual(seen["kwargs"]["x"], "x")

    def test_omitted_flags_require_selection_report_top_up_false(self):
        with tempfile.TemporaryDirectory() as temp:
            report = Path(temp) / "selection-report.json"
            report.write_text(json.dumps({"top_up": True}) + "\n", encoding="ascii")
            with self.assertRaises(compat.LegacyCompatError):
                compat.preread_validate_f_compat(
                    {"schema": "frozen-v1"},
                    selection_report=report,
                    original_validator=lambda *_args, **_kwargs: None,
                )

    def test_present_native_flags_are_not_rewritten(self):
        with tempfile.TemporaryDirectory() as temp:
            report = Path(temp) / "selection-report.json"
            report.write_text(json.dumps({"top_up": False}) + "\n", encoding="ascii")
            receipt = {"top_up": False, "regeneration": False, "new_seed": False}
            seen = {}

            def validator(value, **_kwargs):
                seen.update(value)

            compat.preread_validate_f_compat(
                receipt, selection_report=report, original_validator=validator,
            )
            self.assertEqual(seen, receipt)


class MergeLegacyCompatibilityTests(unittest.TestCase):
    @staticmethod
    def fixture():
        parent = (0, 1 << 1, 1 << 10, 0, 0)
        child = (0, 1 << 45, 1 << 10, 0, 1)
        fingerprint = merge_v1.format_fingerprint(*parent)
        group = {
            "from": "2",
            "to": "46",
            "moving_king": "1",
            "promotes": "1",
            "num_captures": "0",
            "captured_kings": "0",
            "parent_pieces": "2",
            "child_pieces": "2",
            "material_count_delta_parent": "0",
            "parent_fingerprint": fingerprint,
        }
        parent_meta = {
            "raw_fingerprint": fingerprint,
            "parent_id_int": 7,
            "legal_moves_int": 2,
        }
        return parent, child, group, parent_meta

    def test_v1_rejects_raw_king_promotion_flag_shape(self):
        parent, child, group, meta = self.fixture()
        with self.assertRaisesRegex(merge_v1.MergeError, "king move cannot be marked"):
            merge_v1.structural_action(parent, child, group, meta, 7, 0, 0)

    def test_compat_accepts_same_valid_board_transition_and_restores_raw_flag(self):
        parent, child, group, meta = self.fixture()
        row = compat.structural_action_compat(
            parent, child, group, meta, 7, 0, 0,
            original=merge_v1.structural_action,
        )
        self.assertTrue(row["promotes"])
        self.assertEqual(row["from"], 2)
        self.assertEqual(row["to"], 46)
        self.assertEqual(row["captured_square_bitboard"], 0)
        self.assertEqual(row["parent_id"], 7)

    def test_non_target_shape_delegates_unchanged(self):
        parent, child, group, meta = self.fixture()
        group = dict(group)
        group["promotes"] = "0"
        expected = merge_v1.structural_action(parent, child, group, meta, 7, 0, 0)
        actual = compat.structural_action_compat(
            parent, child, group, meta, 7, 0, 0,
            original=merge_v1.structural_action,
        )
        self.assertEqual(actual, expected)


if __name__ == "__main__":
    unittest.main()
