from __future__ import annotations

import copy
import csv
import gzip
import inspect
import json
from pathlib import Path
import tempfile
import shutil
import os
import unittest
from unittest import mock

from jobs.tools import cls_hier_scan_reference_diagnostic as d


def fixture():
    ids = [str(i) for i in range(512)]
    phases, probe, groups = [], [], []
    for i, rid in enumerate(ids):
        phase = f"P{i // 128}"
        phases.append({"parent_id": rid, "phase": phase, "canonical_fingerprint": f"fp{i}"})
        for arm in ("parent", "candidate"):
            probe.append({"root_id": rid, "arm": arm, "bestmove_canonical": "31-27" if arm == "candidate" and i < 168 else "31-26", "completed_nominal_depth": "8" if arm == "candidate" and i >= 482 else "10", "target_depth": "9", "nodes_to_target": "" if arm == "candidate" and i >= 482 else "10000"})
        for move in range(2):
            groups.append({"row_index": str(2*i+move), "parent_id": rid, "parent_phase": phase, "parent_canonical": f"fp{i}", "sibling_identity": f"sid{2*i+move}", "parent_legal_moves": "2", "from": "31", "to": str(26+move), "captured_hex": "0000000000000", "num_captures": "0", "child_rule_terminal": "0", "child_legal_moves": "3", "canonical_from": "20", "canonical_to": str(25-move)})
    report = {"candidate_nodes_to_depth_missing_roots": list(range(482, 512))}
    args = (probe, phases, ids, groups, list(range(1024)), report)
    joined, selected = d.seal_join(*args)
    shards, reports = [], []
    for s in range(16):
        indices = [i for i in selected if i % 16 == s]
        rows = []
        for i in indices:
            for b in d.BUDGETS:
                score = (10 if (i//2)%3 == 0 else -10 if (i//2)%3 == 1 else 0) if i%2 else 0
                rows.append({"row_index": str(i), "budget_nodes": str(b), "sibling_identity": f"sid{i}", "child_score_token": f"{-score/100:.2f}", "parent_score_centi": str(score), "terminal_exact": "0", "requested_nodes": str(b), "last_info_nodes": str(b-16), "snapshot_upper_bound": str(b), "snapshot_above_requested": "0"})
        shards.append(rows)
        reports.append({"schema": "jass.scan_ceiling_scan_ladder.v1", "benchmark_only": True, "source_commit": d.SCAN_COMMIT, "scan_binary_sha256": d.SCAN_BINARY, "groups_sha256": "group-sha", "shard": s, "nshards": 16, "budgets_nodes": list(d.BUDGETS), "processed_rows": len(indices), "output_rows": len(rows), "selected_rows": len(selected), "book_enabled": False, "threads_per_search": 1, "bb_size": 0, "mode": "go analyze", "fresh_state": "new-game before every sibling/budget", "scan_source_algorithms_modified": False, "requested_nodes_exactly_configured": True, "searches": len(rows), "terminal_exact_output_rows": 0})
    return args, joined, selected, shards, reports


class ScanReferenceTests(unittest.TestCase):
    def setUp(self):
        self.args, self.joined, self.selected, self.shards, self.reports = fixture()

    def scores(self):
        return d.parse_scores(self.shards, self.reports, self.selected, "group-sha")

    def test_all_512_168_disagreements_and_30_failures_are_retained(self):
        self.assertEqual(len(self.joined), 512)
        self.assertEqual(sum(r["disagreement"] for r in self.joined), 168)
        self.assertEqual(sum(r["missing_g0_receipt"] for r in self.joined), 30)
        self.assertEqual(len(self.scores()), 2048)

    def test_independent_preference_ties_regret_and_both_budgets(self):
        result, rows = d.evaluate(self.joined, self.scores())
        for b in d.BUDGETS:
            dis = result["budgets"][str(b)]["disagreements"]
            self.assertEqual((dis["hier_preferred"], dis["parent_preferred"], dis["score_ties"]), (56,56,56))
            self.assertEqual(dis["n"], 168)
        self.assertEqual(result["primary_budget_nodes_per_child"], 2000000)
        self.assertEqual(len(rows), 512)
        self.assertEqual(result["disagreement_preference_unstable"], 0)
        self.assertFalse(result["reference_is_ground_truth"])

    def test_raw_coordinates_not_symmetry_coordinates(self):
        self.assertEqual(d.raw_move(self.args[3][0]), "31-26")
        row = dict(self.args[3][0], **{"from":"32", "to":"23", "captured_hex":f"{(1<<26)|(1<<17):013x}", "num_captures":"2"})
        self.assertEqual(d.raw_move(row), "32x23|caps=18,27")

    def test_capture_count_error_is_rejected(self):
        with self.assertRaises(ValueError):
            d.raw_move(dict(self.args[3][0], num_captures="1"))

    def test_probe_or_phase_reordering_is_rejected(self):
        for index in (0,1):
            args = copy.deepcopy(self.args)
            args[index].reverse()
            with self.assertRaises(ValueError):
                d.seal_join(*args)

    def test_missing_sibling_duplicate_and_move_drift_fail(self):
        args = copy.deepcopy(self.args)
        args[4].pop()
        with self.assertRaises(ValueError): d.seal_join(*args)
        args = copy.deepcopy(self.args)
        args[0][0]["bestmove_canonical"] = "1-2"
        with self.assertRaises(ValueError): d.seal_join(*args)
        args = copy.deepcopy(self.args)
        args[3][1]["to"] = "26"
        with self.assertRaises(ValueError): d.seal_join(*args)

    def test_wrong_identity_budget_sign_and_nonfinite_fail(self):
        for field, value in (("sibling_identity","bad"), ("budget_nodes","5"), ("requested_nodes","5"), ("parent_score_centi","99"), ("child_score_token","NaN"), ("child_score_token","0.0001"), ("last_info_nodes","2000001")):
            shards = copy.deepcopy(self.shards)
            shards[0][0][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                d.parse_scores(shards, self.reports, self.selected, "group-sha")

    def test_duplicate_missing_score_and_runtime_provenance_fail(self):
        shards = copy.deepcopy(self.shards)
        shards[0][-1] = dict(shards[0][0])
        with self.assertRaises(ValueError): d.parse_scores(shards,self.reports,self.selected,"group-sha")
        shards[0].pop()
        with self.assertRaises(ValueError): d.parse_scores(shards,self.reports,self.selected,"group-sha")
        for key,value in (("source_commit","bad"),("scan_binary_sha256","bad"),("book_enabled",True),("bb_size",6),("groups_sha256","bad")):
            reports = copy.deepcopy(self.reports)
            reports[0][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError): d.parse_scores(self.shards,reports,self.selected,"group-sha")

    def test_terminal_uses_published_parent_sign_no_fake_search(self):
        selected = copy.deepcopy(self.selected)
        selected[0].update(child_rule_terminal="1",child_legal_moves="0")
        shards, reports = copy.deepcopy(self.shards), copy.deepcopy(self.reports)
        for row in shards[0][:2]:
            row.update(terminal_exact="1", parent_score_centi="10000", child_score_token="-100.00", last_info_nodes="0", snapshot_upper_bound="0")
        reports[0]["searches"] -= 2
        reports[0]["terminal_exact_output_rows"] = 2
        self.assertEqual(d.parse_scores(shards,reports,selected,"group-sha")[(0,2000000)],10000)

    def test_reference_instability_is_reported_not_filtered(self):
        values = self.scores()
        values[(1,2000000)] = -10
        result, rows = d.evaluate(self.joined, values)
        self.assertEqual(len(rows),512)
        self.assertEqual(result["disagreement_preference_unstable"],1)
        self.assertEqual(result["preference_transition_counts"]["1->-1"],1)

    def test_table_json_gzip_roundtrip_deterministic_and_no_clobber(self):
        result, rows = d.evaluate(self.joined, self.scores())
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)
            with (p/"rows.tsv").open("w",newline="") as f:
                w=csv.DictWriter(f,fieldnames=list(rows[0]),delimiter="\t",lineterminator="\n"); w.writeheader(); w.writerows(rows)
            raw=(p/"rows.tsv").read_bytes()
            (p/"rows.tsv.gz").write_bytes(gzip.compress(raw,mtime=0))
            self.assertEqual(d.table(p/"rows.tsv"),d.table(p/"rows.tsv.gz"))
            d.write_json(p/"r.json",result)
            self.assertEqual(d.load(p/"r.json"),result)
            with self.assertRaises(FileExistsError): d.write_json(p/"r.json",result)
            self.assertEqual(d.evaluate(self.joined,self.scores()),(result,rows))

    def test_local_source_has_no_engine_or_gate_execution_path(self):
        text=inspect.getsource(d)
        for forbidden in ("subprocess", "Popen(", "run_candidate_probe(", "gate.decide(", "build_probe(", "train_stream"):
            self.assertNotIn(forbidden,text)
        main=inspect.getsource(d.main)
        self.assertLess(main.index('write_json(art / "scan-blind-join.json"'),main.index('fetch_source(SCAN,'))
        self.assertIn('"historical_scan_score_rows_read": len(values)',main)

    def test_full_main_with_real_phase_evidence_and_synthetic_transport(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            folders = {k: base / str(i) for i,k in enumerate((d.G0,d.SELECTION,d.SCAN))}
            for p in folders.values(): p.mkdir()
            g0,sel,scan = (folders[k] for k in (d.G0,d.SELECTION,d.SCAN))
            def write_table(p, rows):
                p.parent.mkdir(parents=True,exist_ok=True)
                opener = gzip.open if p.suffix == ".gz" else open
                with opener(p,"wt",newline="",encoding="utf-8") as f:
                    w=csv.DictWriter(f,fieldnames=list(rows[0]),delimiter="\t",lineterminator="\n"); w.writeheader(); w.writerows(rows)
            write_table(g0/"probe.tsv",self.args[0]); write_table(g0/"g0-deep512.tsv",self.args[1])
            (g0/"g0-root-ids.txt").write_text("\n".join(self.args[2])+"\n")
            report=dict(self.args[5], roots=512,budget_nodes=200000,threads=1,tt_mb=16,trace_parity_mismatches=0,nodes_to_depth_surrogate_used=False)
            d.write_json(g0/"probe-report.json",report)
            summary={"state":"completed","terminal":"CLS_G0_RUNTIME_CATASTROPHE_GATE_FAIL_V1","scientific_verdict":"FAIL","candidate_arm":"HIER","candidate_sha256":d.CANDIDATE,"direct_parent_sha256":d.PARENT,"fixed_curriculum_anchor_sha256":d.PARENT,"cohort_identity_sha256":d.COHORT,"roots":512,"budget_nodes":200000,"trace_parity_mismatches":0,"strength_games":0,"alpha_spent":0,"gate":{"hard_nodes_to_depth_failure":{"count":30,"parent_missing_roots":[],"candidate_missing_roots":list(range(482,512))}}}
            d.write_json(g0/"scientific-summary.json",summary)
            (g0/"launch-receipt.json").write_text('{}\n')
            write_table(sel/"siblings.tsv",self.args[3]); (sel/"deep512-row-ids.txt").write_text("\n".join(map(str,self.args[4]))+"\n")
            d.write_json(sel/"sibling-manifest.json",{"groups_sha256":d.sha(sel/"siblings.tsv"),"deep_row_ids_sha256":d.sha(sel/"deep512-row-ids.txt")})
            d.write_json(sel/"selection-report.json",{"cohort_identity_sha256":d.COHORT,"deep512":512,"deep512_by_phase":{f"P{i}":128 for i in range(4)}})
            d.write_json(sel/"JASS_CONTROL_SUMMARY.json",{"verdict":"SCAN_COHORT_FROZEN_BENCHMARK_ONLY","passed":True,"cohort_identity_sha256":d.COHORT,"selection_report_sha256":d.sha(sel/"selection-report.json"),"sibling_manifest_sha256":d.sha(sel/"sibling-manifest.json"),**{k:False for k in d.QUARANTINE}})
            for i in range(16):
                write_table(scan/f"scores/scan-deep-shard-{i:02d}-scores.tsv.gz",self.shards[i])
                d.write_json(scan/f"scores/scan-deep-shard-{i:02d}-report.json",dict(self.reports[i],groups_sha256=d.sha(sel/"siblings.tsv")))
            calls=[]
            art=base/"result"/"artefacts"
            def transport(desc,names,out):
                if desc == d.SCAN:
                    self.assertTrue((art/"scan-blind-join.json").is_file())
                calls.append(desc)
                shutil.copytree(folders[desc],out)
                return {"job_id":desc[0],"attempt_id":desc[1],"code_sha":desc[2],"files":list(names)}
            with mock.patch.object(d,"fetch_source",side_effect=transport), mock.patch.object(d,"G0_RECEIPT",d.sha(g0/"launch-receipt.json")), mock.patch.dict(os.environ,{"JASS_RESULT_DIR":str(base/"result"),"JASS_ARTEFACT_DIR":str(art),"LAUNCH_MODE":"rehearsal"}):
                self.assertEqual(d.main(),0)
                with self.assertRaises(FileExistsError): d.main()
            self.assertEqual(calls,[d.G0,d.SELECTION,d.SCAN])
            result=d.load(art/"scientific-summary.json")
            self.assertEqual(result["terminal"],d.TERMINAL)
            self.assertEqual(result["historical_scan_score_rows_read"],2048)
            self.assertIsNone(result["scientific_verdict"])
            evidence=d.load(art/"execution-evidence.json")
            self.assertEqual(evidence["completed_phases"],d.PHASES)
            self.assertEqual(evidence["state"],"completed")
            self.assertTrue(all(v == 0 for v in evidence["actual_side_effects"].values()))
            self.assertEqual(len(d.table(art/"all-512-scan-reference.tsv")),512)

    def test_profile_has_identical_zero_effect_modes(self):
        p=d.ROOT/"jobs/launch_profiles/cls-hier-scan-reference-diagnostic-v1.json"
        profile=d.load(p)
        self.assertEqual(profile["required_phases"],d.PHASES)
        self.assertEqual(profile["rehearsal_max_effects"],profile["production_max_effects"])
        self.assertTrue(all(v == 0 for v in profile["rehearsal_max_effects"].values()))
        self.assertIn("scan-blind-join.json",profile["evidence_outputs"])


if __name__ == "__main__":
    unittest.main()
