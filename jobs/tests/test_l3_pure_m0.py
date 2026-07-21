#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VERDICT = ROOT / "jobs/tools/l3_pure_m0_verdict.py"
COVERAGE = ROOT / "jobs/tools/l3_pure_m0_coverage.py"
SOURCES = ROOT / "jobs/tools/l3_pure_m0_sources.py"
TRIANGLE = ROOT / "jobs/templates/l3-pure-m0-triangle-v1.sh"
COVERAGE_RUNNER = ROOT / "jobs/templates/l3-pure-m0-coverage-v1.sh"
PREPARED = ROOT / "jobs/prepared/l3-pure-maturity-m0-20260721"


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


VERDICT_MOD = load_module(VERDICT, "l3_pure_m0_verdict_tested")
COVERAGE_MOD = load_module(COVERAGE, "l3_pure_m0_coverage_tested")
SOURCES_MOD = load_module(SOURCES, "l3_pure_m0_sources_tested")


def gate(rate: float, low: float, high: float, elo: float, *, n: int = 600) -> dict:
    wins = int(round(rate * n))
    return {
        "wins_a": wins,
        "draws": 0,
        "wins_b": n - wins,
        "n": n,
        "rate": rate,
        "ci_low": low,
        "ci_high": high,
        "elo": elo,
        "complete": True,
        "depth": 9,
        "movetime": None,
    }


def coverage_report(records: int, cov: float, ge10: int, ge100: int, gini: float) -> dict:
    total = 2_125_768
    visited = int(round(total * cov))
    fraction = visited / total
    return {
        "schema": 1,
        "stage": "l3_bucket_visits",
        "geometry": {
            "num_patterns": 8,
            "buckets_per_pattern_colorfold": 265_721,
            "trained_buckets_total": total,
        },
        "corpus": {
            "files": ["synthetic.jnnw"],
            "total_records": records,
            "total_bucket_visits": records * 8,
            "visits_per_record": 8.0,
        },
        "coverage": {
            "visited_buckets": visited,
            "coverage_fraction": fraction,
            "buckets_with_at_least": {
                "ge_1": visited,
                "ge_10": ge10,
                "ge_100": ge100,
                "ge_1000": 0,
            },
            "frac_buckets_ge_100": ge100 / total,
        },
        "concentration": {
            "gini": gini,
            "top_100_visit_mass_fraction": 0.1,
            "mean_visits_per_visited_bucket": 10.0,
        },
        "per_pattern": [],
        "capacity_heuristic": "data_limited_more_capacity_not_justified",
    }


def q00_search() -> str:
    required = {
        "qs_threat_ext": 0,
        "qs_sacs": 0,
        "qs_sacs_depth0_only": 1,
        "qs_forcing_depth": 0,
        "qs_promo_depth": 0,
    }
    values = {f"k{i:02d}": i for i in range(58)}
    values.update(required)
    assert len(values) == 63
    return ",".join(f"{key}={value}" for key, value in values.items())


class M0VerdictTests(unittest.TestCase):
    def test_recommends_clean_p1_when_native_and_q00_align(self):
        native = {
            "c0_a_vs_gen2": gate(0.50, 0.46, 0.54, 0.0),
            "p1_g4_vs_gen2": gate(0.52, 0.48, 0.56, 13.9),
            "p1_g4_vs_c0_a": gate(0.56, 0.515, 0.605, 41.9),
        }
        q00 = {
            "c0_a_vs_gen2": gate(0.49, 0.45, 0.53, -7.0),
            "p1_g4_vs_gen2": gate(0.51, 0.47, 0.55, 7.0),
            "p1_g4_vs_c0_a": gate(0.53, 0.49, 0.57, 20.9),
        }
        decision, _ = VERDICT_MOD.choose_parent(native, q00)
        self.assertEqual(decision, "M0_RECOMMEND_0842_G4")

    def test_unresolved_when_views_do_not_clear_rules(self):
        native = {
            "c0_a_vs_gen2": gate(0.50, 0.46, 0.54, 0.0),
            "p1_g4_vs_gen2": gate(0.505, 0.465, 0.545, 3.5),
            "p1_g4_vs_c0_a": gate(0.51, 0.47, 0.55, 7.0),
        }
        q00 = {
            "c0_a_vs_gen2": gate(0.50, 0.46, 0.54, 0.0),
            "p1_g4_vs_gen2": gate(0.50, 0.46, 0.54, 0.0),
            "p1_g4_vs_c0_a": gate(0.49, 0.45, 0.53, -7.0),
        }
        decision, _ = VERDICT_MOD.choose_parent(native, q00)
        self.assertEqual(decision, "M0_PARENT_UNRESOLVED_MORE_N_OR_REVIEW")

    def test_cli_outputs_summary_and_never_authorizes_m1(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths: dict[str, Path] = {}
            for view in ("historical", "q00", "native"):
                for name, payload in (
                    ("a-gen2", gate(0.50, 0.46, 0.54, 0.0)),
                    ("p1-gen2", gate(0.52, 0.48, 0.56, 13.9)),
                    ("p1-a", gate(0.56, 0.515, 0.605, 41.9)),
                ):
                    path = root / f"{view}-{name}.json"
                    path.write_text(json.dumps(payload), encoding="utf-8")
                    paths[f"{view}-{name}"] = path
            out = root / "verdict.json"
            summary = root / "summary.json"
            cmd = [sys.executable, str(VERDICT)]
            for view in ("historical", "q00", "native"):
                cmd += [f"--{view}-a-gen2", str(paths[f"{view}-a-gen2"])]
                cmd += [f"--{view}-p1-gen2", str(paths[f"{view}-p1-gen2"])]
                cmd += [f"--{view}-p1-a", str(paths[f"{view}-p1-a"])]
            cmd += ["--out", str(out), "--summary-out", str(summary)]
            subprocess.run(cmd, check=True, capture_output=True, text=True)
            payload = json.loads(out.read_text())
            status = json.loads(summary.read_text())
            self.assertFalse(payload["m1_authorized"])
            self.assertFalse(payload["promotion_authorized"])
            self.assertIsNone(payload["automatic_next_job"])
            self.assertFalse(status["m1_authorized"])


class M0CoverageTests(unittest.TestCase):
    def test_cli_aggregates_exact_generation_counts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            c0_paths = []
            p1_paths = []
            for idx, cov in enumerate((0.04, 0.05, 0.06), 1):
                path = root / f"c0-g{idx}.json"
                path.write_text(json.dumps(coverage_report(500_000, cov, 1000 * idx, 100 * idx, 0.86)), encoding="utf-8")
                c0_paths.append(path)
            for idx, cov in enumerate((0.04, 0.055, 0.065, 0.075), 1):
                path = root / f"p1-g{idx}.json"
                path.write_text(json.dumps(coverage_report(500_000, cov, 1200 * idx, 120 * idx, 0.84)), encoding="utf-8")
                p1_paths.append(path)
            c0_cum = root / "c0-cum.json"
            p1_cum = root / "p1-cum.json"
            c0_cum.write_text(json.dumps(coverage_report(1_500_000, 0.09, 9000, 900, 0.85)), encoding="utf-8")
            p1_cum.write_text(json.dumps(coverage_report(2_000_000, 0.11, 12000, 1200, 0.83)), encoding="utf-8")
            out = root / "coverage.json"
            summary = root / "summary.json"
            cmd = [sys.executable, str(COVERAGE)]
            for path in c0_paths:
                cmd += ["--c0-generation", str(path)]
            for path in p1_paths:
                cmd += ["--p1-generation", str(path)]
            cmd += ["--c0-cumulative", str(c0_cum), "--p1-cumulative", str(p1_cum), "--out", str(out), "--summary-out", str(summary)]
            subprocess.run(cmd, check=True, capture_output=True, text=True)
            payload = json.loads(out.read_text())
            self.assertEqual(payload["decision"], "M0_COVERAGE_AUDIT_READY")
            self.assertEqual(payload["coverage_space"]["trained_buckets_total"], 2_125_768)
            self.assertEqual(len(payload["c0_a"]["per_generation"]), 3)
            self.assertEqual(len(payload["p1_0842"]["per_generation"]), 4)
            self.assertEqual(payload["coverage_leader_diagnostic_only"], "P1_0842_G4")
            self.assertFalse(payload["m1_authorized"])

    def test_rejects_raw_runtime_bucket_count_as_training_space(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.json"
            payload = coverage_report(500_000, 0.05, 100, 10, 0.8)
            payload["geometry"]["trained_buckets_total"] = 4_251_528
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "colour-fold geometry"):
                COVERAGE_MOD.load_report(path)


class M0SourceContractTests(unittest.TestCase):
    def test_accepts_reviewed_0790_schema1_without_embedded_search_params(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            c0 = root / "c0"; p1 = root / "p1"; c0.mkdir(); p1.mkdir()
            (c0 / "g3.pjtw.gz").write_bytes(b"c0-model")
            (p1 / "g4.pjtw.gz").write_bytes(b"p1-model")
            c0_manifest = {
                "schema": 1,
                "lineage": "L3-PURE",
                "arm": "A",
                "generations": 3,
                "scientific_status": "complete_generation_chain",
                "champion_sha256": {"g3.pjtw.gz": hashlib.sha256(b"c0-model").hexdigest()},
            }
            search = q00_search()
            p1_manifest = {
                "schema": 4,
                "experiment": "L3-PURE-P1",
                "variant": "FROZEN_BASELINE",
                "scientific_status": "complete_p1_training",
                "recipe": {
                    "lineage": "L3-PURE", "variant": "FROZEN_BASELINE",
                    "geometry": "8cf", "generations": 4, "search_params": search,
                },
                "search_params_sha256": hashlib.sha256(search.encode()).hexdigest(),
                "student_sha256": {"g4.pjtw.gz": hashlib.sha256(b"p1-model").hexdigest()},
            }
            (c0 / "manifest.json").write_text(json.dumps(c0_manifest), encoding="utf-8")
            (p1 / "manifest.json").write_text(json.dumps(p1_manifest), encoding="utf-8")
            vc0 = root / "verified-c0.json"; vp1 = root / "verified-p1.json"
            vc0.write_text(json.dumps({"job_id": SOURCES_MOD.C0_LEGACY_JOB, "code_sha": SOURCES_MOD.C0_LEGACY_CODE_SHA, "result_state": "completed"}), encoding="utf-8")
            vp1.write_text(json.dumps({"job_id": "cpx62-0842-l3-p1-frozen-v1", "code_sha": "337ccbdc", "result_state": "completed"}), encoding="utf-8")
            args = argparse.Namespace(
                c0_dir=str(c0), p1_dir=str(p1), verified_c0=str(vc0), verified_p1=str(vp1),
                expected_c0_job=SOURCES_MOD.C0_LEGACY_JOB,
                expected_p1_job="cpx62-0842-l3-p1-frozen-v1",
            )
            payload = SOURCES_MOD.validate(args)
            self.assertEqual(payload["c0_search_params_source"], "reviewed_0790_schema1_compatibility")
            self.assertEqual(payload["c0_search_params"], SOURCES_MOD.C0_REVIEWED_SEARCH)
            self.assertEqual(len(payload["p1_q00_search_params"].split(",")), 63)

    def test_rejects_missing_c0_fingerprint_for_any_unreviewed_source(self):
        with self.assertRaisesRegex(ValueError, "lacks search_params"):
            SOURCES_MOD.resolve_c0_search(
                {"schema": 1, "lineage": "L3-PURE", "arm": "A", "generations": 3},
                {"job_id": "other", "code_sha": "other"},
                "other",
            )


class M0PreparedContractTests(unittest.TestCase):
    def test_shell_files_are_valid_and_not_self_queued(self):
        scripts = [TRIANGLE, COVERAGE_RUNNER, *sorted(PREPARED.glob("*.sh"))]
        self.assertEqual(len(scripts), 4)
        for script in scripts:
            subprocess.run(["bash", "-n", str(script)], check=True)
            text = script.read_text(encoding="utf-8")
            self.assertNotIn("jobs/queue", text)

    def test_wrappers_pin_exact_sources_and_require_merged_sha(self):
        for script in sorted(PREPARED.glob("*.sh")):
            text = script.read_text(encoding="utf-8")
            self.assertIn('${EXPECTED_CODE_SHA:?', text)
            self.assertIn("ccx33-0790-l3-pure-c0-a-v1", text)
            self.assertIn("cpx62-0842-l3-p1-frozen-v1", text)
            self.assertIn("FULL_RUN_APPROVED=1", text)
            self.assertIn("SCIENTIFIC_GO=1", text)

    def test_runners_publish_gitops_summary_and_fail_closed(self):
        triangle = TRIANGLE.read_text(encoding="utf-8")
        coverage = COVERAGE_RUNNER.read_text(encoding="utf-8")
        for text in (triangle, coverage):
            self.assertIn("JASS_CONTROL_SUMMARY.json", text)
            self.assertIn("M1_AUTHORIZED__FALSE", text)
            self.assertIn("automatic_next_job", (VERDICT.read_text() + COVERAGE.read_text()))
        self.assertIn("l3_pure_m0_sources.py", triangle)
        self.assertIn("VERDICT__", triangle)
        self.assertIn("RECOMMENDED_PARENT__", triangle)
        self.assertIn("VERDICT__M0_COVERAGE_AUDIT_READY", coverage)


if __name__ == "__main__":
    unittest.main()
