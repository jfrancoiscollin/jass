"""Synthetic regression of native integer JSON IDs versus TSV string IDs.

No R2 access, native search, new game, or change to historical gate decisions.
"""
import copy
import json
import unittest

from jobs.tools import cls_g0_panel_raw_audit as audit


def fixture(arm="LOCAL", native=True):
    roots = [str(i) for i in range(512)]
    phases = [{"parent_id": r, "phase": f"P{i // 128}",
               "canonical_fingerprint": f"fixture-{r}"}
              for i, r in enumerate(roots)]
    rows = []
    for i, root in enumerate(roots):
        for role in ("parent", "candidate"):
            missing = role == "candidate" and i < 56
            rows.append({"root_id": root, "arm": role,
                "completed_nominal_depth": "8" if missing else "10",
                "target_depth": "9", "nodes_observed": "200000",
                "wall_us": "100000", "nps": "2000000", "trace_attempts": "10",
                "bestmove_canonical": "31-26",
                "nodes_to_target": "" if missing else "180000"})
    ids = list(range(56)) if native else roots[:56]
    # JSON roundtrip mirrors the unsigned integer arrays from write_id_array.
    probe = json.loads(json.dumps({"parent_nodes_to_depth_missing_roots": [],
        "candidate_nodes_to_depth_missing_roots": ids, "budget_nodes": 200000,
        "roots": 512, "trace_parity_mismatches": 0,
        "nodes_to_depth_surrogate_used": False}))
    summary = {"candidate_arm": arm, "candidate_sha256": audit.MODELS[arm],
        "direct_parent_sha256": audit.MODELS["CURRICULUM"], "terminal": audit.G0_FAIL}
    return [arm, rows, roots, phases, probe, summary]


class InventoryTypesTests(unittest.TestCase):
    def test_native_integer_arrays_both_arms(self):
        for arm in ("LOCAL", "WDL"):
            with self.subTest(arm=arm):
                args = fixture(arm)
                saved = copy.deepcopy(args)
                rows, report = audit.g0_rows(*args)
                self.assertEqual(args, saved)
                self.assertEqual(len(rows), 512)
                self.assertEqual(report["categories"], {
                    "profondeur_cible_non_atteinte": 56, "recu_exact_present": 456})
                self.assertEqual(report["frozen_g0_verdict"], "FAIL")
                self.assertFalse(report["g0_recomputed"])
                self.assertEqual(report["imputed_receipts"], 0)
                self.assertTrue(all(r["candidate_nodes_to_target"] == "" for r in rows[:56]))

    def test_integer_and_canonical_text_outputs_identical(self):
        self.assertEqual(audit.g0_rows(*fixture(native=True)),
                         audit.g0_rows(*fixture(native=False)))

    def test_mixed_canonical_representations_preserve_identity(self):
        args = fixture()
        args[4]["candidate_nodes_to_depth_missing_roots"][1] = "1"
        self.assertEqual(audit.g0_rows(*args), audit.g0_rows(*fixture()))

    def test_wrong_id_rejected(self):
        args = fixture()
        args[4]["candidate_nodes_to_depth_missing_roots"][-1] = 511
        with self.assertRaisesRegex(audit.AuditError, "G0_MISSING_INVENTORY"):
            audit.g0_rows(*args)

    def test_reordering_rejected(self):
        args = fixture()
        args[4]["candidate_nodes_to_depth_missing_roots"].reverse()
        with self.assertRaisesRegex(audit.AuditError, "G0_MISSING_INVENTORY"):
            audit.g0_rows(*args)

    def test_duplicate_rejected(self):
        args = fixture()
        args[4]["candidate_nodes_to_depth_missing_roots"][1] = 0
        with self.assertRaisesRegex(audit.AuditError, "G0_MISSING_INVENTORY"):
            audit.g0_rows(*args)

    def test_wrong_cardinality_rejected(self):
        args = fixture()
        args[4]["candidate_nodes_to_depth_missing_roots"].pop()
        with self.assertRaisesRegex(audit.AuditError, "G0_MISSING_INVENTORY"):
            audit.g0_rows(*args)

    def test_invalid_array_shapes_rejected(self):
        for bad in (None, {}, "0", (0,), 0):
            with self.subTest(bad=bad):
                args = fixture()
                args[4]["candidate_nodes_to_depth_missing_roots"] = bad
                with self.assertRaisesRegex(audit.AuditError, "G0_MISSING_INVENTORY"):
                    audit.g0_rows(*args)

    def test_noncanonical_or_noninteger_ids_rejected(self):
        for bad in (True, False, 0.0, 1.0, -1, 2**32, None, {}, [],
                    "00", "+0", "-0", " 0", "0 ", "0.0", "٠", "4294967296"):
            with self.subTest(bad=bad):
                args = fixture()
                args[4]["candidate_nodes_to_depth_missing_roots"][0] = bad
                with self.assertRaisesRegex(audit.AuditError, "G0_MISSING_INVENTORY"):
                    audit.g0_rows(*args)

    def test_parent_inventory_also_checked(self):
        args = fixture()
        args[4]["parent_nodes_to_depth_missing_roots"] = [0]
        with self.assertRaisesRegex(audit.AuditError, "G0_MISSING_INVENTORY"):
            audit.g0_rows(*args)

    def test_attained_depth_missing_receipt_remains_distinct(self):
        args = fixture()
        args[1][1]["completed_nominal_depth"] = "9"
        rows, report = audit.g0_rows(*args)
        self.assertEqual(rows[0]["classification"], "profondeur_atteinte_sans_recu_exact")
        self.assertEqual(report["categories"]["profondeur_cible_non_atteinte"], 55)
        self.assertEqual(rows[0]["candidate_nodes_to_target"], "")

    def test_other_probe_guards_unchanged(self):
        args = fixture()
        args[4]["nodes_to_depth_surrogate_used"] = True
        with self.assertRaisesRegex(audit.AuditError, "G0_PROBE_BOUNDARY"):
            audit.g0_rows(*args)


if __name__ == "__main__":
    unittest.main()
