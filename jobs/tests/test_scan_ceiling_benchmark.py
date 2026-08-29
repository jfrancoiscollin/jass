from __future__ import annotations

import csv
import re
import struct
import tempfile
import unittest
from pathlib import Path

import numpy as np

from jobs.tools.scan_ceiling_fen_to_jnnw import fen_record
from jobs.tools.scan_ceiling_merge import Parent, sibling_identity
from jobs.tools.scan_ceiling_preflight import symmetry_replay
from jobs.tools.scan_ceiling_scan_score import (
    EngineFailure,
    NodeScanEngine,
    parse_info_fields,
    record_fingerprint,
    record_to_scan_pos,
    scan_snapshot_upper_bound,
    score_token_to_centi,
    terminal_observation,
)
from jobs.tools.scan_ceiling_readout import (
    Groups,
    bootstrap_metrics,
    compute_parent_stats,
    invert_curve,
    kendall_tau_b,
    load_long_scores,
    metric_report,
    pava,
    point_metrics,
    practical_recovery,
    spearman_rho,
)
from jobs.tools.scan_ceiling_preflight import technical_planning_estimates
from jobs.tools.scan_ceiling_shard_timeouts import build_timeout_plan
from jobs.tools.scan_ceiling_select import (
    Candidate,
    FILTER_FIELDS,
    PHASES,
    collect_candidates,
    hash_key,
    select,
    write_outputs,
)
from jobs.tools.tb_frontier_symmetry_dedup import (
    canonical_fingerprint,
    format_fingerprint,
    parse_fingerprint,
    symmetric_fingerprint,
)


ROOT = Path(__file__).resolve().parents[2]
PREREG = ROOT / "docs/experiments/L3_SCAN_CEILING_BENCHMARK_V1_20260829.md"


def record_from_fingerprint(fp: str) -> bytes:
    wm, wk, bm, bk, stm = parse_fingerprint(fp)
    return struct.pack("<QQQQBib", wm, wk, bm, bk, stm, 0, 0)


class ScanCeilingBenchmarkTest(unittest.TestCase):
    def test_fen_record_scan_mapping_and_score_precision(self):
        record = fen_record("B:W31,K32:BK7,8")
        self.assertEqual(len(record), 38)
        self.assertEqual(record_fingerprint(record), format_fingerprint(
            1 << 30, 1 << 31, 1 << 7, 1 << 6, 1,
        ))
        scan = record_to_scan_pos(record)
        self.assertEqual(len(scan), 51)
        self.assertEqual(scan[0], "B")
        self.assertEqual((scan[31], scan[32], scan[7], scan[8]), ("w", "W", "B", "b"))
        self.assertEqual(score_token_to_centi("-12.34"), -1234)
        with self.assertRaisesRegex(ValueError, "sub-cent"):
            score_token_to_centi("0.001")

    def test_scan_node_rpc_fixes_commands_and_parent_pov(self):
        engine = object.__new__(NodeScanEngine)
        engine.label = "fake"
        commands: list[str] = []
        engine._drain = lambda: None
        engine._send = commands.append
        lines = [
            'info depth=1 mean-depth=1.0 score=0.25 nodes=41 pv="32-28"',
            'info depth=3 mean-depth=2.4 score=-0.17 nodes=1004 pv="32-28 17-22"',
            "done move=32-28",
        ]
        engine._read_until = lambda predicate, timeout_s: lines
        observation = engine.search_nodes("W" + "e" * 50, 1000, 5.0)
        self.assertEqual(commands, [
            "new-game", "pos pos=" + "W" + "e" * 50,
            "level nodes=1000", "go analyze",
        ])
        self.assertEqual(observation["child_score_centi"], -17)
        self.assertEqual(observation["parent_score_centi"], 17)
        self.assertEqual(observation["last_info_nodes"], 1004)
        self.assertEqual(observation["snapshot_upper_bound"], 1008)
        self.assertTrue(observation["snapshot_above_requested"])
        self.assertEqual(scan_snapshot_upper_bound(5_000), 5_008)
        self.assertEqual(scan_snapshot_upper_bound(50_000), 50_000)
        self.assertEqual(observation["done_move"], "32-28")
        self.assertEqual(parse_info_fields(lines[1])["pv"], "32-28 17-22")
        self.assertEqual(terminal_observation()["parent_score_centi"], 10_000)
        engine._read_until = lambda predicate, timeout_s: [
            'info depth=3 score=-0.17 nodes=1009 pv="32-28"',
            "done move=32-28",
        ]
        with self.assertRaisesRegex(EngineFailure, "invalid progressive node snapshot"):
            engine.search_nodes("W" + "e" * 50, 1000, 5.0)

    def test_collect_reports_exact_and_symmetry_duplicates_separately(self):
        raw = format_fingerprint(
            sum(1 << bit for bit in range(5)), 0,
            sum(1 << bit for bit in range(20, 24)), 0, 0,
        )
        sym = symmetric_fingerprint(raw)
        records = [record_from_fingerprint(raw), record_from_fingerprint(raw), record_from_fingerprint(sym)]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            states = root / "filtered.jnnw"
            meta = root / "filtered.tsv"
            states.write_bytes(b"JNNW" + struct.pack("<I", len(records)) + b"".join(records))
            with meta.open("w", newline="", encoding="utf-8") as stream:
                writer = csv.DictWriter(stream, fieldnames=FILTER_FIELDS, delimiter="\t", lineterminator="\n")
                writer.writeheader()
                for index, fp in enumerate((raw, raw, sym)):
                    writer.writerow({
                        "row_index": index, "source_row_index": 100 + index,
                        "parent_fingerprint": fp, "parent_stm": parse_fingerprint(fp)[4],
                        "pieces": 9, "legal_moves": 3,
                    })
            unique, receipt = collect_candidates([states], [meta], set(), 2026091301, 2026091302)
        self.assertEqual(len(unique), 1)
        self.assertEqual(receipt["exact_duplicate_occurrences_removed"], 1)
        self.assertEqual(receipt["rotate180_colour_swap_duplicate_occurrences_removed"], 1)

    def test_nested_subsets_have_fixed_phase_quotas_and_hash_order(self):
        candidates: dict[str, Candidate] = {}
        for phase_index, (phase, (lo, _)) in enumerate(PHASES.items()):
            for index in range(510):
                identity = f"phase-{phase_index}-{index:04d}"
                candidate = Candidate(
                    canonical=identity, raw_fingerprint=identity,
                    record=b"\0" * 38, stm=index % 2, pieces=lo,
                    legal_moves=2 + index % 15, phase=phase,
                    source_shard=index % 16, source_row_index=index,
                    selection_hash=hash_key(2026091301, identity),
                    subset_hash=hash_key(2026091302, identity),
                )
                candidates[identity] = candidate
        selected, deep, ultra, available = select(candidates)
        self.assertEqual(available, {phase: 510 for phase in PHASES})
        self.assertEqual(len(selected), 2000)
        for phase in PHASES:
            self.assertEqual(sum(c.phase == phase and c.canonical in deep for c in selected), 128)
            self.assertEqual(sum(c.phase == phase and c.canonical in ultra for c in selected), 64)
        self.assertLess(ultra, deep)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = [root / name for name in ("parents.jnnw", "parents.tsv", "deep.tsv", "ultra.tsv")]
            write_outputs(selected, deep, ultra, *paths)
            with paths[2].open(newline="", encoding="utf-8") as stream:
                rows = list(csv.DictReader(stream, delimiter="\t"))
        for phase in PHASES:
            hashes = [row["subset_hash"] for row in rows if row["phase"] == phase]
            self.assertEqual(hashes, sorted(hashes))

    def test_canonical_sibling_identity_is_symmetry_invariant(self):
        raw = format_fingerprint(1 << 30, 0, 1 << 19, 0, 0)
        sym = symmetric_fingerprint(raw)
        canonical = canonical_fingerprint(raw)
        child = format_fingerprint(1 << 26, 0, 1 << 19, 0, 1)
        child_sym = symmetric_fingerprint(child)
        parent_a = Parent(0, canonical, raw, 0, 2, 2, "P3")
        parent_b = Parent(0, canonical, sym, 1, 2, 2, "P3")
        row_a = {"from": "31", "to": "27", "captured_hex": "0000000000000",
                 "promotes": "0", "child_fingerprint": child}
        row_b = {"from": "20", "to": "24", "captured_hex": "0000000000000",
                 "promotes": "0", "child_fingerprint": child_sym}
        self.assertEqual(sibling_identity(parent_a, row_a)[0], sibling_identity(parent_b, row_b)[0])

    def test_pairwise_ties_and_strict_canonical_diagnostic(self):
        groups = Groups(
            rows=[{}, {}, {}],
            sibling_id=np.asarray(["b", "a", "c"], dtype=object),
            parent_id=np.asarray([0, 0, 0], dtype=np.int32),
            phase=np.asarray(["P0"] * 3, dtype=object),
            stm=np.asarray([0, 0, 0], dtype=np.int8),
            pieces=np.asarray([30, 30, 30], dtype=np.int16),
            branching=np.asarray([3, 3, 3], dtype=np.int8),
            rows_by_parent={0: np.asarray([0, 1, 2], dtype=np.int64)},
        )
        reference = np.asarray([2.0, 2.0, 0.0])
        signals = {
            "correct_but_strict_top_wrong": np.asarray([3.0, 1.0, 0.0]),
            "comparable_ties": np.asarray([1.0, 1.0, 1.0]),
        }
        stats = compute_parent_stats(groups, [0], reference, signals)
        points = point_metrics(stats)
        self.assertEqual(stats.pairs_total[0], 3)
        self.assertEqual(stats.pair_den[0], 2)
        self.assertEqual(stats.pairs_tied[0], 1)
        self.assertEqual(points["pairwise_primary"].tolist(), [1.0, 0.5])
        self.assertAlmostEqual(points["pairwise_strict"][0], 2 / 3)
        self.assertEqual(points["top_hit_primary"][0], 1.0)
        self.assertEqual(points["top_hit_strict"][0], 0.0)
        boot = bootstrap_metrics(stats, np.random.Generator(np.random.PCG64(7)), 20)
        self.assertTrue(np.all(boot["pairwise_primary"][:, 0] == 1.0))
        report = metric_report(stats, points, boot)
        self.assertEqual(report["correct_but_strict_top_wrong"]["pairwise_primary"]["raw_numerator"], 2.0)
        self.assertEqual(report["correct_but_strict_top_wrong"]["pairwise_primary"]["raw_denominator"], 2)
        self.assertEqual(report["correct_but_strict_top_wrong"]["top_hit_primary"]["raw_numerator"], 1)

    def test_practical_recovery_is_na_when_practical_ceiling_denominator_is_nonpositive(self):
        names = ["T0", "D1", "RF1", "T3-A", "Jass1k", "Jass50k", "Jass200k", "Jass1M", "Scan2M"]
        point = np.asarray([0.75, 0.76, 0.77, 0.78, 0.76, 0.79, 0.80, 0.81, 0.75])
        boot = np.tile(point, (12, 1))
        result = practical_recovery(names, {"pairwise_primary": point}, boot)
        self.assertEqual(result["point_denominator"], 0.0)
        for metric in result["signals"].values():
            self.assertIsNone(metric["point"])
            self.assertEqual(metric["bootstrap_valid"], 0)
            self.assertEqual(metric["bootstrap_na"], 12)

    def test_rank_correlations_and_isotonic_inversion(self):
        increasing = np.asarray([1.0, 2.0, 2.0, 4.0])
        self.assertAlmostEqual(kendall_tau_b(increasing, increasing), 1.0)
        self.assertAlmostEqual(spearman_rho(increasing, increasing), 1.0)
        fitted = pava(np.asarray([0.55, 0.70, 0.65, 0.80]), np.ones(4))
        self.assertEqual(fitted.tolist(), [0.55, 0.675, 0.675, 0.8])
        category, value, lo, hi = invert_curve(
            np.asarray([1_000.0, 5_000.0, 50_000.0, 200_000.0]), fitted, 0.675,
        )
        self.assertEqual(category, "plateau")
        self.assertAlmostEqual(value, np.sqrt(5_000 * 50_000))
        self.assertEqual((lo, hi), (5_000.0, 50_000.0))

    def test_node_receipts_and_preflight_planning_are_explicit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            jass = root / "jass.tsv"
            jass.write_text(
                "row_index\tbudget_nodes\tparent_score\tchild_score\tnodes\tcompleted_depth\t"
                "effective_depth\taborted_iteration\tstop_reason\telapsed_us\t"
                "budget_status\tterminal_exact\ttb_exact\n"
                "0\t1000\t12\t-12\t1000\t5\t6\t1\tnodes\t10000\trequested_nodes_reached\t0\t0\n"
                "1\t1000\t30000\t-30000\t0\t0\t0\t0\tterminal_exact\t0\tterminal_exact\t1\t0\n"
                "2\t1000\t29900\t-29900\t64\t64\t64\t0\tnone\t1000\tmax_depth_exhausted\t0\t0\n",
                encoding="utf-8",
            )
            scores, receipt = load_long_scores([jass], 3, {0, 1, 2}, (1000,), "jass")
            scan = root / "scan.tsv"
            scan.write_text(
                "row_index\tbudget_nodes\tparent_score_centi\tchild_score_token\trequested_nodes\t"
                "last_info_nodes\tterminal_exact\tsnapshot_upper_bound\t"
                "snapshot_above_requested\n"
                "0\t1000\t17\t-0.17\t1000\t1004\t0\t1008\t1\n",
                encoding="utf-8",
            )
            _, scan_receipt = load_long_scores([scan], 1, {0}, (1000,), "scan")
        self.assertEqual(scores[1000].tolist(), [12.0, 30000.0, 29900.0])
        self.assertEqual(receipt["by_budget"]["1000"]["searched_rows"], 2)
        self.assertEqual(receipt["by_budget"]["1000"]["requested_nodes_reached_rows"], 1)
        self.assertEqual(receipt["by_budget"]["1000"]["max_depth_exhausted_rows"], 1)
        self.assertEqual(receipt["by_budget"]["1000"]["reported_or_snapshot_nodes_sum"], 1064)
        self.assertEqual(scan_receipt["by_budget"]["1000"]["snapshot_above_requested_rows"], 1)
        self.assertEqual(scan_receipt["by_budget"]["1000"]["scan_snapshot_upper_bound"], 1008)
        planning = technical_planning_estimates(
            [{"nodes": "1000", "elapsed_us": "10000", "budget_nodes": "1000"}],
            [{"terminal_exact": "0", "elapsed_seconds": "0.02", "requested_nodes": "1000"}],
        )
        self.assertEqual(planning["worker_cap"], 15)
        self.assertEqual(planning["logical_cpu_margin"], 1)
        self.assertIn("Scan_ULTRA256", planning["stage_eta_ranges"])

    def test_pov_guard_uses_static_symmetry_not_finite_node_score_equality(self):
        records = [
            fen_record("B:W26,32-50:B1-20"),
            fen_record("W:W31-50:B1-19,25"),
        ]
        groups = [
            {"parent_id": "0", "t0_parent": "-7"},
            {"parent_id": "1", "t0_parent": "-7"},
        ]
        jass = [
            {"parent_score": "-1", "child_score": "1"},
            {"parent_score": "0", "child_score": "0"},
        ]
        scan = [
            {"parent_score_centi": "-3", "child_score_token": "0.03"},
            {"parent_score_centi": "1", "child_score_token": "-0.01"},
        ]
        receipt = symmetry_replay(records, groups, jass, scan)
        self.assertEqual(receipt["colour_swap_child_pairs"], 1)
        self.assertTrue(receipt["static_t0_parent_scores_equal"])
        self.assertFalse(receipt["finite_node_cross_symmetry_score_equality_required"])
        bad_groups = [dict(row) for row in groups]
        bad_groups[1]["t0_parent"] = "-8"
        with self.assertRaisesRegex(ValueError, "static T0"):
            symmetry_replay(records, bad_groups, jass, scan)
        bad_jass = [dict(row) for row in jass]
        bad_jass[1]["child_score"] = "1"
        with self.assertRaisesRegex(ValueError, "Jass child-to-parent"):
            symmetry_replay(records, groups, bad_jass, scan)
        bad_scan = [dict(row) for row in scan]
        bad_scan[1]["child_score_token"] = "0.01"
        with self.assertRaisesRegex(ValueError, "Scan child-to-parent"):
            symmetry_replay(records, groups, jass, bad_scan)

    def test_frozen_rf1_wrapper_is_decoded_without_refit(self):
        try:
            from jobs.tools.scan_ceiling_static_score import rf1_artifact_from_frozen_payload
        except ModuleNotFoundError as exc:
            if exc.name == "scipy":
                self.skipTest("SciPy numeric runtime unavailable")
            raise
        payload = {
            "schema": "jass.l3_residual_feature_rf1.v1",
            "family": "F6_ALL_NEW",
            "feature_width": 66,
            "feature_names": [f"frozen_feature_{index:02d}" for index in range(66)],
            "d1_coefficient": 1.0,
            "intercept": 0.0,
            "d1_sha256": "e91a55500713154f50be74db5d699b64d7684e1c078725d09e1d15e713549b49",
            "extractor_code_sha": "e5c4a0d6e88e99c06819100c4b5dbc697bbe3a53",
            "replay_exact": True,
            "q1_label_reads": 0,
            "q1_score_reads": 0,
            "t2_fresh_label_reads": 0,
            "t2_fresh_score_reads": 0,
            "probe_artifact_sha256": "0" * 64,
            "normalization": {"mean": [0.0] * 66, "std": [1.0] * 66},
            "residual_coefficients": [0.0] * 66,
            "optimizer": {"success": True},
        }
        artifact = rf1_artifact_from_frozen_payload(payload)
        prediction = artifact.predict(np.ones((1, 66)), np.asarray([7.0]))
        self.assertEqual(prediction.tolist(), [7.0])
        bad = dict(payload)
        bad["q1_score_reads"] = 1
        with self.assertRaisesRegex(ValueError, "wrapper contract"):
            rf1_artifact_from_frozen_payload(bad)

    def test_frozen_cohort_and_stage_code_provenance_are_explicit(self):
        stage_templates = (
            "l3-scan-ceiling-static-v1.sh",
            "l3-scan-ceiling-jass-score-v1.sh",
            "l3-scan-ceiling-scan-score-v1.sh",
        )
        for template in stage_templates:
            text = (ROOT / "jobs/templates" / template).read_text(encoding="utf-8")
            self.assertIn('${FROZEN_COHORT_CODE_SHA:?}', text)
            self.assertIn("'frozen_cohort_code_sha'", text)
        for template in (
            "l3-scan-ceiling-jass-score-v1.sh",
            "l3-scan-ceiling-scan-score-v1.sh",
        ):
            text = (ROOT / "jobs/templates" / template).read_text(encoding="utf-8")
            self.assertIn('${SCORE_RESUME_CODE_SHA:?required with SCORE_RESUME_PREFIX}', text)
            self.assertIn('${SCORE_RUNTIME_TIMEOUT_MULTIPLIER:-3}', text)
            self.assertIn("jass.scan_ceiling_runtime_timeout_policy.v1", text)
        readout = (ROOT / "jobs/templates/l3-scan-ceiling-readout-v1.sh").read_text(
            encoding="utf-8",
        )
        for variable in (
            "FROZEN_COHORT_CODE_SHA", "STATIC_CODE_SHA", "JASS_BASE_CODE_SHA",
            "JASS_DEEP_CODE_SHA", "SCAN_BASE_CODE_SHA", "SCAN_DEEP_CODE_SHA",
            "SCAN_ULTRA_CODE_SHA",
        ):
            self.assertIn('${' + variable + ':?}', readout)
        self.assertIn("jass.scan_ceiling_code_provenance.v1", readout)

    def test_scan_ceiling_template_python_heredocs_compile(self):
        for template in (
            "l3-scan-ceiling-static-v1.sh", "l3-scan-ceiling-jass-score-v1.sh",
            "l3-scan-ceiling-scan-score-v1.sh", "l3-scan-ceiling-readout-v1.sh",
        ):
            text = (ROOT / "jobs/templates" / template).read_text(encoding="utf-8")
            blocks = re.findall(r"<<'(?P<tag>PY[A-Z0-9_]*)'\n(?P<body>.*?)\n(?P=tag)", text, re.S)
            self.assertTrue(blocks, template)
            for tag, body in blocks:
                compile(body, f"{template}:{tag}", "exec")

    def test_shard_timeouts_are_rate_derived_and_exact_rows_are_excluded(self):
        preflight = {
            "throughput_and_eta": {
                "planning_only_not_scientific_metric": True,
                "worker_cap": 15,
                "observed_1k_smoke": {
                    "Jass": {"requested_nodes_per_second": 1000.0},
                    "Scan": {"requested_nodes_per_second": 500.0},
                },
            },
        }
        with tempfile.TemporaryDirectory() as directory:
            groups = Path(directory) / "groups.tsv"
            groups.write_text(
                "row_index\tchild_rule_terminal\tchild_tb_exact\n"
                "0\t0\t0\n1\t1\t0\n2\t0\t1\n3\t0\t0\n",
                encoding="utf-8",
            )
            jass = build_timeout_plan(
                preflight, groups, "-", "Jass", (1000,), 2,
                grace_seconds=0, minimum_timeout_seconds=1,
            )
            scan = build_timeout_plan(
                preflight, groups, "-", "Scan", (1000,), 2,
                grace_seconds=0, minimum_timeout_seconds=1,
            )
        self.assertEqual([x["searched_rows"] for x in jass["shards"]], [1, 1])
        self.assertEqual([x["requested_nodes"] for x in jass["shards"]], [1000, 1000])
        self.assertEqual([x["searched_rows"] for x in scan["shards"]], [2, 1])
        self.assertEqual(scan["shards"][0]["timeout_seconds"], 6)
        self.assertEqual(jass["groups_sha256"], scan["groups_sha256"])
        self.assertEqual(jass["row_ids_sha256"], None)
        self.assertFalse(scan["scientific_budgets_changed"])

    def test_frozen_source_contract_has_no_short_search_or_fit_path(self):
        prereg = PREREG.read_text(encoding="utf-8")
        ladder = (ROOT / "src/scan_ceiling_jass_ladder.cpp").read_text(encoding="utf-8")
        scan = (ROOT / "jobs/tools/scan_ceiling_scan_score.py").read_text(encoding="utf-8")
        cmake = (ROOT / "CMakeLists.txt").read_text(encoding="utf-8")
        for token in ("2026091301", "2026091302", "2026091303", "200000"):
            self.assertIn(token, prereg)
        self.assertIn("jass::Engine engine(tt_mb)", ladder)
        self.assertIn("exact Jass node budget mismatch", ladder)
        self.assertIn("max_depth_exhausted", ladder)
        self.assertNotIn("short_rows", ladder)
        self.assertIn('self._send("new-game")', scan)
        self.assertIn('self._send("go analyze")', scan)
        self.assertIn("SCAN_NODE_POLL_QUANTUM = 16", scan)
        self.assertIn("scan_node_poll_quantum = 16", prereg)
        self.assertIn('("book", "false")', (ROOT / "jobs/tools/calibrate_vs_scan.py").read_text(encoding="utf-8"))
        for target in (
            "jass_scan_ceiling_parent_filter", "jass_scan_ceiling_source_generator",
            "jass_scan_ceiling_sibling_export",
            "jass_scan_ceiling_jass_ladder",
        ):
            self.assertIn(target, cmake)
        source_generator = (ROOT / "src/scan_ceiling_source_generator.cpp").read_text(encoding="utf-8")
        self.assertIn('\\"scores_generated\\": 0', source_generator)
        self.assertIn('\\"wdl_generated\\": 0', source_generator)
        selection_job = (ROOT / "jobs/templates/l3-scan-ceiling-selection-v1.sh").read_text(encoding="utf-8")
        self.assertNotIn("--gen-data-wdl", selection_job)
        self.assertIn("sibling-export-stage-manifest.json", selection_job)
        self.assertIn("--inventory-only", selection_job)
        for template in (
            "l3-scan-ceiling-selection-v1.sh", "l3-scan-ceiling-jass-score-v1.sh",
            "l3-scan-ceiling-scan-score-v1.sh",
        ):
            text = (ROOT / "jobs/templates" / template).read_text(encoding="utf-8")
            self.assertIn("MAX_WORKERS=15", text)
            self.assertIn("timeout -k 120s", text)
        for template in (
            "l3-scan-ceiling-preflight-v1.sh", "l3-scan-ceiling-selection-v1.sh",
            "l3-scan-ceiling-static-v1.sh", "l3-scan-ceiling-jass-score-v1.sh",
            "l3-scan-ceiling-scan-score-v1.sh", "l3-scan-ceiling-readout-v1.sh",
        ):
            text = (ROOT / "jobs/templates" / template).read_text(encoding="utf-8")
            self.assertIn("DFA=$(df -Pm /root", text)
        for template in (
            "l3-scan-ceiling-preflight-v1.sh", "l3-scan-ceiling-selection-v1.sh",
            "l3-scan-ceiling-static-v1.sh",
        ):
            self.assertIn(
                "arch_assert", (ROOT / "jobs/templates" / template).read_text(encoding="utf-8"),
            )
        for policy in (
            "training_allowed", "tuning_allowed", "calibration_allowed",
            "model_selection_allowed", "runtime_scale_selection_allowed",
        ):
            self.assertIn(policy, prereg)


if __name__ == "__main__":
    unittest.main()
