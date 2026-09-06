from __future__ import annotations

import unittest

from jobs.tools import adaptive_sibling_b3_fresh_transfer_readout as subject


def row(*, q200: int = 0, rule: bool = False, tb: bool = False,
        utility: int = 2, selected: bool = False) -> dict[str, str]:
    value = {field: "0" for field in subject.ADAPTIVE_FIELDS}
    value.update({
        "parent_id": "0", "row_index": "0", "parent_fingerprint": "fp",
        "parent_stm": "0", "parent_pieces": "20", "from": "1", "to": "2",
        "num_captures": "0", "promotes": "0", "moving_king": "0",
        "captured_kings": "0", "material_count_delta_parent": "0",
        "child_pieces": "20", "child_legal_moves": "2", "child_forced_capture": "0",
        "child_rule_terminal": "1" if rule else "0",
        "child_tb_exact": "1" if tb else "0",
        "exact_parent_utility": str(utility), "t_baseline_parent": "0",
        "q5k_parent": str(q200), "q50_parent": str(q200), "q200_parent": str(q200),
        "nodes5k": "0", "nodes50k": "0", "nodes200k": "0",
        "completed_depth5k": "0", "completed_depth50k": "0", "completed_depth200k": "0",
        "effective_depth5k": "0", "effective_depth50k": "0", "effective_depth200k": "0",
        "aborted5k": "0", "aborted50k": "0", "aborted200k": "0",
        "stop5k": "none", "stop50k": "none", "stop200k": "none",
        "elapsed_us5k": "0", "elapsed_us50k": "0", "elapsed_us200k": "0",
        "pv5k_enters_egdb": "0", "pv50k_enters_egdb": "0", "pv200k_enters_egdb": "0",
        "searched5": "0", "searched50": "0", "searched200": "0",
        "survived5": "0", "survived50": "0", "selected": "1" if selected else "0",
        "exact_shortcut_reason": "NONE", "sole_survivor_reason": "NONE", "uncertified": "0",
    })
    return value


class B3FreshTransferReadoutTests(unittest.TestCase):
    def test_field_contract_extends_b2_without_mutating_it(self) -> None:
        self.assertEqual(subject.ADAPTIVE_FIELDS[:len(subject.b2_readout.GROUP_FIELDS)],
                         list(subject.b2_readout.GROUP_FIELDS))
        self.assertEqual(subject.ADAPTIVE_FIELDS[-9:], [
            "searched5", "searched50", "searched200", "survived5", "survived50",
            "selected", "exact_shortcut_reason", "sole_survivor_reason", "uncertified",
        ])

    def test_reference_prefers_exact_win_then_best_nonexact(self) -> None:
        rows = [row(q200=100), row(q200=200), row(rule=True, utility=1)]
        self.assertEqual(subject._reference_index(rows), 2)
        rows = [row(q200=100), row(q200=200), row(q200=150)]
        self.assertEqual(subject._reference_index(rows), 1)

    def test_value_equivalence_uses_exact_utility_or_full_q200(self) -> None:
        self.assertTrue(subject._value_equivalent(row(q200=42), row(q200=42)))
        self.assertFalse(subject._value_equivalent(row(q200=42), row(q200=41)))
        self.assertTrue(subject._value_equivalent(
            row(tb=True, utility=0), row(tb=True, utility=0)))
        self.assertFalse(subject._value_equivalent(
            row(tb=True, utility=0), row(tb=True, utility=-1)))
        self.assertFalse(subject._value_equivalent(row(tb=True, utility=1), row(q200=30000)))

    def test_executed_search_must_replay_exactly_except_elapsed_time(self) -> None:
        adaptive = row(q200=10)
        full = row(q200=10)
        adaptive.update({
            "searched5": "1", "q5k_parent": "7", "nodes5k": "5000",
            "completed_depth5k": "9", "effective_depth5k": "10",
            "aborted5k": "1", "stop5k": "nodes", "pv5k_enters_egdb": "0",
            "elapsed_us5k": "123",
        })
        full.update({
            "q5k_parent": "7", "nodes5k": "5000", "completed_depth5k": "9",
            "effective_depth5k": "10", "aborted5k": "1", "stop5k": "nodes",
            "pv5k_enters_egdb": "0", "elapsed_us5k": "999",
        })
        subject._validate_observation_match(adaptive, full)
        full["q5k_parent"] = "8"
        with self.assertRaisesRegex(subject.ReadoutError, "observation differs"):
            subject._validate_observation_match(adaptive, full)

    def test_unsearched_horizon_cannot_carry_nodes(self) -> None:
        adaptive = row()
        full = row()
        adaptive["nodes50k"] = "1"
        with self.assertRaisesRegex(subject.ReadoutError, "unsearched q50"):
            subject._validate_observation_match(adaptive, full)

    def test_readout_authorization_boundary_is_dataset_only(self) -> None:
        self.assertEqual(subject.VERDICT,
                         "B3_FRESH_CORPUS_AUTHENTICATED_TRANSFER_DIAGNOSTICS_COMPLETE_V1")
        self.assertEqual(subject.FULL_VERDICT, "B3_FRESH_FULL_LADDER_AUDIT_COMPLETE_V1")


if __name__ == "__main__":
    unittest.main()
