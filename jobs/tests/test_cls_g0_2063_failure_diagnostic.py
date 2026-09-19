from __future__ import annotations

import copy
import csv
import inspect
import json
import math
from pathlib import Path
import tempfile
import unittest

from jobs.tools import cls_g0_2063_failure_diagnostic as d


def fixture(q=128):
    ids, phases, deep, probe = [], [], [], []
    for i in range(4 * q):
        rid = str(i)
        ids.append(rid)
        phases.append({"parent_id": rid, "phase": f"P{i // q}"})
        deep.append({"root_id": rid, "budget": "1000000", "bestmove_canonical": "1-6"})
        for arm in ("parent", "candidate"):
            probe.append({"root_id": rid, "arm": arm, "completed_nominal_depth": "10",
                          "target_depth": "9", "nodes_observed": "200000", "wall_us": "100000",
                          "nps": "2000000", "trace_attempts": "11", "nodes_to_target": "100000",
                          "bestmove_canonical": "1-6"})
    report = {"parent_nodes_to_depth_missing_roots": [], "candidate_nodes_to_depth_missing_roots": [],
              "hard_nodes_to_depth_failure_roots": [], "hard_nodes_to_depth_failure_count": 0,
              "nodes_to_depth_surrogate_used": False}
    return probe, phases, deep, ids, report


class DiagnosticTests(unittest.TestCase):
    def test_frozen_source_and_read_boundary(self):
        self.assertEqual(d.JOB, "cpx62-2063-l3-cls-g0-hier-runtime-rehearsal-v1")
        self.assertEqual(d.ATTEMPT, "20260919T155826Z-a6f9fa6f")
        self.assertEqual(d.CODE, "a6f9fa6fbdc66f8d89dd7a5e8c196422cf98a28a")
        self.assertEqual(d.RECEIPT_SHA, "a5b9a83a6a7932920ca23cf1cd7d15f67855c12835ddecb18c4f67bc9b0d6e59")
        self.assertEqual(len(d.FILES), 7)
        self.assertIn("probe.tsv", d.FILES)
        for forbidden in ("model.pjtw.gz", "parents.jnnw", "current-context30.npy", "logs.tar.gz"):
            self.assertNotIn(forbidden, d.FILES)
        code = inspect.getsource(d)
        for forbidden in ("gate.decide(", "gate.bootstrap(", "run_candidate_probe(", "subprocess.run("):
            self.assertNotIn(forbidden, code)
        self.assertIn('"scientific_verdict": None', code)
        self.assertIn('"gate_reevaluated": False', code)

    def test_all_512_identity_control(self):
        audit, rows = d.analyze(*fixture())
        self.assertEqual(len(rows), 512)
        self.assertEqual(audit["all_roots"]["categories"]["RECEIPT_PRESENT"], 512)
        self.assertEqual(audit["all_roots"]["equal_depth"], 512)
        self.assertEqual(audit["all_roots"]["nps_ratio"]["mean"], 1.0)
        self.assertEqual(audit["all_roots"]["moves_same_as_parent"], 512)
        self.assertEqual(audit["missing_receipt_subset"]["n"], 0)
        self.assertEqual(audit["missing_receipt_subset"]["depth_delta"], {"n": 0, "not_estimable": True})

    def test_distinguish_depth_shortfall_from_receipt_filter(self):
        args = fixture()
        probe, _, _, _, report = args
        for i in range(30):
            row = probe[2 * i + 1]
            row["nodes_to_target"] = ""
            row["completed_nominal_depth"] = "8" if i < 20 else "10"
            row["bestmove_canonical"] = "2-7"
        report.update({"candidate_nodes_to_depth_missing_roots": list(range(30)),
                       "hard_nodes_to_depth_failure_roots": list(range(30)),
                       "hard_nodes_to_depth_failure_count": 30})
        audit, rows = d.analyze(*args)
        self.assertEqual(audit["all_roots"]["categories"], {"RECEIPT_PRESENT": 482,
                         "DEPTH_BELOW_TARGET": 20, "TARGET_REACHED_NO_QUALIFYING_RECEIPT": 10})
        self.assertEqual(audit["all_roots"]["nodes_ratio_observed_subset"]["n"], 482)
        self.assertIsNone(audit["all_roots"]["nodes_ratio_population_estimate"])
        self.assertEqual(audit["all_roots"]["reference_matches_lost"], 30)
        self.assertEqual(len(audit["missing_rows"]), 30)
        self.assertFalse(audit["full_attempt_trace_available"])
        self.assertTrue(all(r["nodes_ratio_observed"] is None for r in rows[:30]))

    def test_no_missing_root_may_be_silently_dropped(self):
        args = fixture()
        args[0].pop()
        with self.assertRaises(ValueError):
            d.analyze(*args)

    def test_duplicate_and_order_drift_rejected(self):
        for change in (lambda a: a[3].__setitem__(1, "0"),
                       lambda a: a[0].reverse(), lambda a: a[2].reverse()):
            args = fixture()
            change(args)
            with self.assertRaises(ValueError):
                d.analyze(*args)

    def test_phase_quota_and_target_drift_rejected(self):
        for table_idx, row_idx, key, value in ((1, 0, "phase", "P1"),
                                               (0, 1, "target_depth", "8")):
            args = fixture()
            args[table_idx][row_idx][key] = value
            with self.assertRaises(ValueError):
                d.analyze(*args)

    def test_invalid_runtime_and_receipt_rejected(self):
        for key, value in (("nps", "nan"), ("nps", "0"), ("nodes_observed", "200001"),
                           ("nodes_to_target", "0"), ("nodes_to_target", "200001")):
            args = fixture()
            args[0][1][key] = value
            with self.assertRaises(ValueError):
                d.analyze(*args)

    def test_missing_inventory_crosscheck(self):
        args = fixture()
        args[0][1]["nodes_to_target"] = ""
        with self.assertRaises(ValueError):
            d.analyze(*args)

    def test_wrong_reference_or_surrogate_rejected(self):
        for mutate in (lambda a: a[2][0].__setitem__("budget", "200000"),
                       lambda a: a[4].__setitem__("nodes_to_depth_surrogate_used", True)):
            args = fixture()
            mutate(args)
            with self.assertRaises(ValueError):
                d.analyze(*args)

    def test_roundtrip_and_determinism(self):
        args = fixture()
        first, rows = d.analyze(*args)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = []
            for name, table in zip(("probe", "phases", "deep"), args[:3]):
                path = root / f"{name}.tsv"
                with path.open("w", newline="") as h:
                    writer = csv.DictWriter(h, fieldnames=list(table[0]), delimiter="\t")
                    writer.writeheader()
                    writer.writerows(table)
                paths.append(path)
            second, rows2 = d.analyze(*(d.table(p) for p in paths), args[3], args[4])
            self.assertEqual(first, second)
            self.assertEqual(rows, rows2)
            out = root / "audit.json"
            d.write_json(out, first)
            self.assertEqual(d.load(out)["all_roots"]["n"], 512)
            with self.assertRaises(FileExistsError):
                d.write_json(out, first)


if __name__ == "__main__":
    unittest.main()
