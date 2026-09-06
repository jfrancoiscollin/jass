from __future__ import annotations

import unittest

from jobs.tools import adaptive_sibling_b2_exact_zero_cost_compat as compat
from jobs.tools import adaptive_sibling_b2_readout as readout
from jobs.tools import adaptive_sibling_b2_statistics as statistics


def mapping(parent_id: int = 0, *, full_nodes: int = 0, shadow_nodes: int = 0,
            cell: str = "P0_stm0") -> dict[str, object]:
    return {
        "schema": statistics.INPUT_SCHEMA,
        "parent_id": parent_id,
        "cell": cell,
        "full_nodes": full_nodes,
        "shadow_nodes": shadow_nodes,
        "fully_nonexact": False,
        "same_row": True,
        "value_equivalent": True,
        "exact_mismatch": False,
        "signal_event": False,
        "signal_direction_code": 0,
        "numeric_eligible": False,
        "numeric_component": 0,
    }


class ExactZeroCostCompatTests(unittest.TestCase):
    def tearDown(self) -> None:
        compat.uninstall()

    def test_exact_x_rejects_zero_full_parent_before_compat(self):
        with self.assertRaises(statistics.StatisticsContractError):
            statistics.ParentStatsSufficientV1.from_mapping(mapping())
        with self.assertRaises(readout.ReadoutError):
            readout._checked_sum((0, 0, 0), "full total", require_positive=True)

    def test_compat_accepts_only_zero_full_with_zero_shadow(self):
        receipt = compat.install()
        self.assertTrue(receipt.frozen_paths_unchanged)
        row = statistics.ParentStatsSufficientV1.from_mapping(mapping())
        self.assertEqual(row.full_nodes, 0)
        self.assertEqual(row.shadow_nodes, 0)
        self.assertEqual(
            readout._checked_sum((0, 0, 0), "full total", require_positive=True), 0)
        with self.assertRaisesRegex(
                statistics.StatisticsContractError,
                "zero full_nodes requires zero shadow_nodes"):
            statistics.ParentStatsSufficientV1.from_mapping(
                mapping(full_nodes=0, shadow_nodes=1))

    def test_compat_does_not_relax_other_positive_sums(self):
        compat.install()
        with self.assertRaises(readout.ReadoutError):
            readout._checked_sum((0, 0), "some other denominator", require_positive=True)
        self.assertEqual(
            readout._checked_sum((10, 20), "full total", require_positive=True), 30)

    def test_cell_support_remains_aggregate_nonzero(self):
        compat.install()
        rows = []
        parent = 0
        cells = {cell: [] for cell in statistics.CELL_ORDER}
        for cell in statistics.CELL_ORDER:
            for index in range(statistics.CELL_SIZE):
                row = statistics.ParentStatsSufficientV1.from_mapping(mapping(
                    parent_id=parent,
                    cell=cell,
                    full_nodes=0 if index == 0 else 100,
                    shadow_nodes=0 if index == 0 else 50,
                ))
                rows.append(row)
                cells[cell].append(row)
                parent += 1
        statistics.validate_parent_population(rows)
        global_counts = statistics._aggregate_rows(rows)
        cell_counts = {cell: statistics._aggregate_rows(cells[cell])
                       for cell in statistics.CELL_ORDER}
        report = statistics._support_report(global_counts, cell_counts)
        # Other frozen support dimensions are intentionally absent in this
        # fixture; the node-support rule itself must not report zero.
        self.assertFalse(any("node support is zero" in reason
                             for reason in report["reasons"]))
        cell_counts[statistics.CELL_ORDER[0]]["full_nodes"] = 0
        report = statistics._support_report(global_counts, cell_counts)
        self.assertTrue(any("node support is zero" in reason
                            for reason in report["reasons"]))


if __name__ == "__main__":
    unittest.main()
