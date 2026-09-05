#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

from jobs.tools.adaptive_sibling_b2_teacher_source import (
    ADAPTER_SCHEMA,
    BASE_SOURCE_NORMALIZED_SHA256,
    BUDGETS,
    MERGED_SCHEMA,
    SHARD_SCHEMA,
    INPUT_AUTH_SCHEMA,
    SELECTION_SCHEMA,
    SHARD_REPORT_KEYS,
    merge_reports,
    render,
    render_file,
    validate_shard_report,
    verify_selection_input,
)


ROOT = Path(__file__).resolve().parents[2]
BASE_SOURCE = ROOT / "src/deep_sibling_teacher.cpp"
TOOL = ROOT / "jobs/tools/adaptive_sibling_b2_teacher_source.py"


def source_text() -> str:
    return BASE_SOURCE.read_text(encoding="utf-8")


def make_report(shard: int, *, nshards: int = 16, parents: int = 4_000) -> dict[str, object]:
    processed = len(range(shard, parents, nshards))
    emitted = 2 * processed
    return {
        "schema": SHARD_SCHEMA,
        "input_parents": parents,
        "shard": shard,
        "nshards": nshards,
        "book_enabled": False,
        "threads_per_search": 1,
        "fresh_tt_each_search": True,
        "fresh_engine_each_search": True,
        "engine_constructions": 3 * emitted,
        "jass_prefixed_environment_count": 0,
        "egdb_configuration_source": "explicit_positional_arguments",
        "egdb_required_available": True,
        "egdb_cache_mb": 256,
        "node_limit_mode": "exact",
        "cheap_budget_nodes": 5_000,
        "screen_budget_nodes": 50_000,
        "teacher_budget_nodes": 200_000,
        "tt_mb": 16,
        "egdb_max_pieces": 6,
        "source_rows": parents,
        "processed_parent_rows": processed,
        "invalid_rows": 0,
        "duplicate_move_entries": 0,
        "emitted_siblings": emitted,
        "rule_terminal_children": 1 if emitted else 0,
        "exact_tb_children": 1 if emitted else 0,
        "cheap_searches": emitted,
        "screen_searches": emitted,
        "teacher_searches": emitted,
        "cheap_nodes": emitted * 5_000,
        "screen_nodes": emitted * 50_000,
        "teacher_nodes": emitted * 200_000,
        "teacher_scores_produced": True,
        "stable_pairs_selected": False,
        "fits": 0,
        "strength_games": 0,
        "promotion_authorized": False,
    }


def write_selection_fixture(root: Path) -> tuple[Path, Path, str]:
    root.mkdir(parents=True, exist_ok=True)
    parents = root / "parents.jnnw"
    raw = b"JNNW" + (4_000).to_bytes(4, "little") + bytes(38 * 4_000)
    parents.write_bytes(raw)
    report = root / "selection-report.json"
    report.write_text(
        json.dumps(
            {
                "schema": SELECTION_SCHEMA,
                "outputs": {
                    "parents_jnnw": {
                        "sha256": hashlib.sha256(raw).hexdigest(),
                        "size_bytes": len(raw),
                        "records": 4_000,
                    }
                },
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return parents, report, hashlib.sha256(report.read_bytes()).hexdigest()


class AdaptiveSiblingB2TeacherSourceTests(unittest.TestCase):
    def test_pinned_historical_source_and_render_are_deterministic(self):
        normalized = BASE_SOURCE.read_bytes().replace(b"\r\n", b"\n")
        self.assertEqual(
            hashlib.sha256(normalized).hexdigest(), BASE_SOURCE_NORMALIZED_SHA256
        )
        first = render(source_text())
        self.assertEqual(first, render(source_text()))
        self.assertTrue(first.endswith("#undef JASS_B2_ENVIRON\n"))

    def test_render_preserves_frozen_budgets_columns_and_search_semantics(self):
        out = render(source_text())
        for token in (
            "constexpr std::uint64_t CHEAP_BUDGET = 5'000;",
            "constexpr std::uint64_t SCREEN_BUDGET = 50'000;",
            "constexpr std::uint64_t TEACHER_BUDGET = 200'000;",
            "q5k_parent",
            "q50_parent",
            "q200_parent",
            "NodeLimitMode::Exact",
            "limits.threads = 1;",
            "engine.use_book(false);",
            "engine.clear_tt();",
            "out.parent_score = -result.score;",
            "std::sort(unique_moves.begin(), unique_moves.end(), semantic_less)",
        ):
            self.assertIn(token, out)
        self.assertNotIn("q1000_parent", out)

    def test_render_constructs_one_local_engine_for_each_search_call(self):
        out = render(source_text())
        self.assertIn("SearchObs run_fresh_search(std::size_t tt_mb,", out)
        self.assertEqual(out.count("Engine engine(tt_mb);"), 1)
        self.assertEqual(out.count("++engine_constructions;"), 1)
        self.assertLess(out.index("Engine engine(tt_mb);"), out.index("++engine_constructions;"))
        self.assertEqual(
            out.count("run_fresh_search(tt_mb, c.engine_constructions, child,"), 3
        )
        self.assertNotIn("run_fresh_search(engine, child,", out)
        self.assertNotIn(
            "    Engine engine(tt_mb);\n    engine.use_book(false);\n    Counters c{};", out
        )
        self.assertIn("fresh_engine_each_search\\\": true", out)
        self.assertIn("engine_constructions\\\": ", out)
        self.assertIn(
            "c.engine_constructions != c.cheap_searches + c.screen_searches + c.teacher_searches",
            out,
        )

    def test_generated_and_python_shard_receipt_schemas_match_exactly(self):
        out = render(source_text())
        block = out[out.index("void write_report("):out.index("}  // namespace")]
        generated_keys = set(re.findall(r'<< "  \\\"([^\\\"]+)\\\"', block))
        self.assertEqual(generated_keys, set(SHARD_REPORT_KEYS))

    def test_all_legal_siblings_including_exact_rows_take_all_searches(self):
        out = render(source_text())
        exact = out.index("const std::optional<int> exact_u = exact_parent_utility(")
        s5 = out.index("const SearchObs s5 =", exact)
        write = out.index("write_zero_target_row(children, child);", s5)
        between = out[exact:write]
        self.assertEqual(between.count("const SearchObs s"), 3)
        self.assertNotIn("continue;", between)
        self.assertNotIn("if (exact_u", between)
        self.assertNotIn("if (rule_terminal", between)
        self.assertNotIn("if (tb_exact", between)

    def test_environment_and_egdb_are_fail_closed_and_explicit(self):
        out = render(source_text())
        for token in (
            "#ifndef JASS_EGDB",
            'std::strncmp(*item, "JASS_", 5) == 0',
            "if (argc != 11)",
            "egdb_cache_mb != 256",
            "egdb::init(egdb_dir, egdb_cache_mb)",
            "!egdb::available()",
            "tb_cap <= 0 || tb_cap > 40",
            "jass_prefixed_environment_count\\\": 0",
            "egdb_configuration_source\\\": \\\"explicit_positional_arguments",
        ):
            self.assertIn(token, out)

    def test_invalid_selected_parent_is_terminal_not_skipped(self):
        out = render(source_text())
        self.assertIn("error: invalid selected-parent row ", out)
        self.assertNotIn("if (!valid_row(row)) { ++c.invalid_rows; continue; }", out)
        self.assertIn("selected-parent target bytes are not zero", out)

    def test_any_base_source_drift_fails_before_rendering(self):
        changed = source_text().replace(
            "No labels are selected here", "No labels are chosen here", 1
        )
        with self.assertRaisesRegex(ValueError, "unexpected normalized base source SHA256"):
            render(changed)

    def test_render_file_publishes_hashes_and_contract(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            output = root / "generated.cpp"
            receipt_path = root / "adapter.json"
            receipt = render_file(BASE_SOURCE, output, receipt_path)
            loaded = json.loads(receipt_path.read_text(encoding="utf-8"))
            self.assertEqual(loaded, receipt)
            self.assertEqual(receipt["schema"], ADAPTER_SCHEMA)
            self.assertEqual(
                receipt["base_source_normalized_sha256"], BASE_SOURCE_NORMALIZED_SHA256
            )
            self.assertEqual(
                receipt["rendered_source_sha256"],
                hashlib.sha256(output.read_bytes()).hexdigest(),
            )
            self.assertEqual(receipt["budgets_nodes"], list(BUDGETS))
            self.assertEqual(receipt["jass_prefixed_environment"], [])
            self.assertTrue(receipt_path.read_bytes().endswith(b"\n"))

    def test_cli_works_from_outside_repository(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            output = root / "generated.cpp"
            receipt = root / "receipt.json"
            subprocess.run(
                [sys.executable, str(TOOL), "render", "--source", str(BASE_SOURCE),
                 "--output", str(output), "--receipt", str(receipt)],
                cwd=root,
                check=True,
                text=True,
                capture_output=True,
            )
            self.assertTrue(output.is_file() and receipt.is_file())

    def test_selection_input_is_authenticated_before_teacher(self):
        with tempfile.TemporaryDirectory() as td:
            parents, report, report_sha = write_selection_fixture(Path(td))
            receipt = verify_selection_input(parents, report, report_sha)
            self.assertEqual(receipt["schema"], INPUT_AUTH_SCHEMA)
            self.assertEqual(receipt["parents_jnnw_records"], 4_000)
            self.assertEqual(receipt["target_bytes_checked"], 20_000)
            self.assertEqual(receipt["target_bytes_nonzero"], 0)
            self.assertTrue(receipt["authenticated_before_teacher"])

    def test_selection_input_authentication_rejects_hash_count_and_target_drift(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            parents, report, report_sha = write_selection_fixture(root)
            with self.assertRaisesRegex(ValueError, "authenticated receipt"):
                verify_selection_input(parents, report, "0" * 64)

            payload = json.loads(report.read_text(encoding="utf-8"))
            payload["outputs"]["parents_jnnw"]["records"] = 3_999
            report.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "exactly 4000"):
                verify_selection_input(
                    parents, report, hashlib.sha256(report.read_bytes()).hexdigest()
                )

            parents, report, report_sha = write_selection_fixture(root)
            damaged = bytearray(parents.read_bytes())
            damaged[8 + 33] = 1
            parents.write_bytes(damaged)
            payload = json.loads(report.read_text(encoding="utf-8"))
            payload["outputs"]["parents_jnnw"]["sha256"] = hashlib.sha256(damaged).hexdigest()
            report.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "target bytes are nonzero"):
                verify_selection_input(
                    parents, report, hashlib.sha256(report.read_bytes()).hexdigest()
                )

    def test_verify_selection_cli_writes_receipt(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            parents, report, report_sha = write_selection_fixture(root)
            receipt = root / "input-auth.json"
            subprocess.run(
                [sys.executable, str(TOOL), "verify-selection",
                 "--parents-jnnw", str(parents), "--selection-report", str(report),
                 "--expected-selection-report-sha256", report_sha,
                 "--receipt", str(receipt)],
                cwd=root,
                check=True,
                text=True,
                capture_output=True,
            )
            self.assertEqual(json.loads(receipt.read_text())["schema"], INPUT_AUTH_SCHEMA)

    def test_generated_source_is_syntax_valid_when_compiler_available(self):
        compiler = os.environ.get("CXX") or shutil.which("c++") or shutil.which("g++")
        if not compiler:
            self.skipTest("no C++ compiler available")
        with tempfile.TemporaryDirectory() as td:
            generated = Path(td) / "adaptive_sibling_b2_teacher.cpp"
            generated.write_text(render(source_text()), encoding="utf-8", newline="\n")
            proc = subprocess.run(
                [compiler, "-std=c++20", "-DJASS_EGDB=1", "-fsyntax-only",
                 "-Isrc", "-Ipattern_jass/src", str(generated)],
                cwd=ROOT,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_shard_receipt_and_merge_happy_path(self):
        merged = merge_reports([make_report(shard) for shard in reversed(range(16))])
        self.assertEqual(merged["schema"], MERGED_SCHEMA)
        self.assertEqual([report["shard"] for report in merged["shards"]], list(range(16)))
        self.assertEqual(merged["processed_parent_rows"], 4_000)
        self.assertEqual(merged["emitted_siblings"], 8_000)
        self.assertEqual(merged["engine_constructions"], 24_000)
        self.assertEqual(merged["cheap_searches"], merged["screen_searches"])
        self.assertEqual(merged["screen_searches"], merged["teacher_searches"])
        self.assertEqual(merged["teacher_searches"], 8_000)

    def test_shard_receipt_rejects_contract_drift(self):
        bad_values = (
            ("fresh_engine_each_search", False),
            ("fresh_tt_each_search", False),
            ("engine_constructions", 11),
            ("cheap_searches", 3),
            ("screen_searches", 3),
            ("teacher_searches", 3),
            ("cheap_budget_nodes", 4_999),
            ("screen_budget_nodes", 49_999),
            ("teacher_budget_nodes", 199_999),
            ("threads_per_search", 2),
            ("book_enabled", True),
            ("node_limit_mode", "soft"),
            ("egdb_cache_mb", 257),
            ("egdb_required_available", False),
            ("jass_prefixed_environment_count", 1),
            ("invalid_rows", 1),
            ("egdb_max_pieces", 41),
            ("cheap_nodes", 2_500_001),
            ("screen_nodes", 25_000_001),
            ("teacher_nodes", 100_000_001),
        )
        for key, bad in bad_values:
            with self.subTest(key=key):
                report = make_report(0)
                report[key] = bad
                with self.assertRaises(ValueError):
                    validate_shard_report(report)

    def test_shard_receipt_rejects_bool_integer_and_unknown_fields(self):
        report = make_report(0)
        report["engine_constructions"] = True
        with self.assertRaises(ValueError):
            validate_shard_report(report)
        report = make_report(0)
        report["unreviewed"] = 1
        with self.assertRaisesRegex(ValueError, "extra"):
            validate_shard_report(report)

    def test_merge_rejects_missing_duplicate_and_inconsistent_shards(self):
        with self.assertRaisesRegex(ValueError, "exactly 16"):
            merge_reports([make_report(shard) for shard in range(15)])
        duplicate = [make_report(shard) for shard in range(15)] + [make_report(0)]
        with self.assertRaisesRegex(ValueError, "unique and exhaustive"):
            merge_reports(duplicate)
        reports = [make_report(shard) for shard in range(16)]
        reports[1]["tt_mb"] = 32
        with self.assertRaisesRegex(ValueError, "tt_mb"):
            merge_reports(reports)

        reports = [make_report(shard) for shard in range(16)]
        reports[0]["duplicate_move_entries"] = (1 << 64) - 1
        reports[1]["duplicate_move_entries"] = 1
        with self.assertRaisesRegex(ValueError, "exceeds uint64"):
            merge_reports(reports)

    def test_merge_cli_round_trips_json(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            inputs = []
            for shard in range(16):
                path = root / f"report-{shard}.json"
                path.write_text(json.dumps(make_report(shard)), encoding="utf-8")
                inputs.append(path)
            output = root / "merged.json"
            argv = [sys.executable, str(TOOL), "merge-reports"]
            for path in inputs:
                argv.extend(("--report", str(path)))
            argv.extend(("--output", str(output)))
            subprocess.run(argv, cwd=root, check=True, text=True, capture_output=True)
            merged = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(merged, merge_reports([make_report(shard) for shard in range(16)]))
            self.assertTrue(output.read_bytes().endswith(b"\n"))

    def test_output_publication_refuses_alias_existing_and_partial_paths(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source_copy = root / "base.cpp"
            source_copy.write_bytes(BASE_SOURCE.read_bytes())
            receipt = root / "receipt.json"
            with self.assertRaisesRegex(ValueError, "pairwise distinct"):
                render_file(source_copy, source_copy, receipt)
            self.assertEqual(source_copy.read_bytes(), BASE_SOURCE.read_bytes())

            output = root / "generated.cpp"
            output.write_text("occupied", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "existing output"):
                render_file(source_copy, output, receipt)
            self.assertEqual(output.read_text(), "occupied")
            self.assertFalse(receipt.exists())

            parents, selection_report, report_sha = write_selection_fixture(root / "selection")
            auth = verify_selection_input(parents, selection_report, report_sha)
            self.assertTrue(auth["authenticated_before_teacher"])
            from jobs.tools.adaptive_sibling_b2_teacher_source import _write_json
            with self.assertRaisesRegex(ValueError, "pairwise distinct"):
                _write_json(parents, auth, protected_inputs=(parents, selection_report))

if __name__ == "__main__":
    unittest.main()
