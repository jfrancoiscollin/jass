#!/usr/bin/env python3
from __future__ import annotations

import unittest
import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "jobs/templates/l3-top3-stable-conversion-matrix-v1.sh"
WRAPPER = ROOT / (
    "jobs/prepared/l3-top3-stable-conversion-20260722/"
    "cpx62-0908-l3-top3-stable-conversion-matrix-v1.sh"
)
PURE_WRAPPER = ROOT / (
    "jobs/prepared/l3-pure-top3-conversion-20260723/"
    "cpx62-0921-l3-pure-top3-stable-conversion-matrix-v1.sh"
)
MATRIX_TOOL = ROOT / "jobs/tools/stable_conversion_matrix.py"


class StableConversionJobContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.template = TEMPLATE.read_text(encoding="utf-8")
        cls.wrapper = WRAPPER.read_text(encoding="utf-8")
        cls.pure_wrapper = PURE_WRAPPER.read_text(encoding="utf-8")

    def test_fixed_sizing_and_common_budget(self) -> None:
        for token in (
            'DEPTH="${DEPTH:-10}"',
            'POOL_POSITIONS="${POOL_POSITIONS:-384}"',
            'NSHARDS="${NSHARDS:-16}"',
            'GAME_TIMEOUT="${GAME_TIMEOUT:-120}"',
            'SHARD_TIMEOUT="${SHARD_TIMEOUT:-1200}"',
            'GLOBAL_TIMEOUT="${GLOBAL_TIMEOUT:-2100}"',
            'JASS_BUILD_JOBS="${JASS_BUILD_JOBS:-4}"',
            'ARMS=(scan_scan scan_g4 g4_scan g0_g0 g4_g0 g0_g4 g4_g4)',
            "TOTAL_GAMES=2688",
            "volume=7x384=2688",
            "projected_play=431s",
            "anchor_0862=2048_games/328s=6.24_games_s",
        ):
            self.assertIn(token, self.template)

    def test_provenance_is_immutable_and_fail_closed(self) -> None:
        for token in (
            "cpx62-0842-l3-p1-frozen-v1",
            "337ccbdc4889732af43d3a4a713b8dac06f2a864",
            "ccx33-0890bis-l3-imbalance2-top3-selfplay-2m-p1",
            "952bea08c6d4d657df841eb76627537677141f53",
            'sources.get("standard") != 500000',
            'sources.get("frontier", 0) != 0',
            'selected_source_units") != 384',
            ': "${EXPECTED_SCAN_SHA256:?',
            ': "${EXPECTED_SCAN_RUNTIME_SHA256:?',
        ):
            self.assertIn(token, self.template)

    def test_arch_runtime_and_reporting_guards(self) -> None:
        for token in (
            'find /root -maxdepth 1 -name \'cw-*\'',
            '[ "$NPROC" -eq 16 ]',
            'grep -q "g_emasks" src/scan_eval.cpp',
            'grep -q "has_any_capture" src/search.cpp',
            'grep -q "has_any_capture" src/movegen.cpp',
            'RES="$W/RESULTS.txt"',
            'PROG="$W/PROGRESS.txt"',
            'PHASE_FILE="$W/phase.txt"',
            'set_phase preflight',
            'start_monitor "$JOB_STARTED_EPOCH"',
            'set_phase build_and_native_tests',
            'set_phase pool_build_and_audit',
            'cp "$PROG" "$ART/.PROGRESS.txt.tmp"',
            'mv "$ART/.PROGRESS.txt.tmp" "$ART/PROGRESS.txt"',
            'run_pids "$arm" "${pids[@]}"',
            '--target jass jass_tests',
            'ctest --test-dir "$W/build" --output-on-failure',
            'jobs/tools/scan_runtime_fingerprint.py',
            '--scan-dir "$SCAN_RUNTIME_DIR"',
            'chmod 0444 "$SCAN_RUNTIME_DIR/scan.ini" "$SCAN_RUNTIME_DIR/data/eval"',
        ):
            self.assertIn(token, self.template)
        self.assertNotIn("\n    wait\n", self.template)

    def test_strict_floor_and_no_continuation(self) -> None:
        for token in (
            'build.get("selected_positions") != 384',
            'contract.get("positions") != 384',
            'get("global", {}).get("n") != 384',
            'p.get("technical_failures") or p.get("technical_rows")',
            'training_continuation_authorized=false',
            'promotion_authorized=false',
            'automatic_next_job=null',
        ):
            self.assertIn(token, self.template)

    def test_wrapper_is_prepared_not_queued(self) -> None:
        self.assertTrue(WRAPPER.is_file())
        self.assertNotIn("jobs/queue", str(WRAPPER).replace("\\", "/"))
        for token in (
            "cpx62-0908-l3-top3-stable-conversion-matrix-v1",
            'export NSHARDS=16 PAR=16 GAME_TIMEOUT=120 SHARD_TIMEOUT=1200 GLOBAL_TIMEOUT=2100',
            ': "${EXPECTED_SCAN_RUNTIME_SHA256:?',
            "export JASS_BUILD_JOBS=4",
        ):
            self.assertIn(token, self.wrapper)
        self.assertIn('exec timeout -k 60s "${GLOBAL_TIMEOUT}s"', self.wrapper)
        self.assertIn(
            "bash jobs/templates/l3-top3-stable-conversion-matrix-v1.sh",
            self.wrapper,
        )

    def test_template_wiring_matches_real_matrix_cli(self) -> None:
        spec = importlib.util.spec_from_file_location("stable_matrix_job_contract", MATRIX_TOOL)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        parser = module.build_parser()
        run = parser.parse_args([
            "run", "--pool", "pool.fen", "--proof", "proof.jsonl",
            "--arm", "g4_g0", "--shard-index", "0", "--jass", "jass",
            "--scan", "scan", "--g0", "g0.pjtw", "--g4", "g4.pjtw",
            "--scan-runtime-sha256", "4" * 64,
            "--search-params", "rfp_max_depth=5", "--output", "s0.jsonl",
            "--progress-file", "s0.progress.json", "--depth", "10",
            "--max-plies", "400", "--game-timeout", "120", "--nshards", "16",
        ])
        self.assertEqual(run.arm, "g4_g0")
        aggregate = parser.parse_args([
            "aggregate", "--pool", "pool.fen", "--proof", "proof.jsonl",
            "--result", "g4_g0=s0.jsonl", "--bootstrap-samples", "10",
            "--bootstrap-seed", "271828", "--run-config", "run.json",
            "--expected-per-arm", "384", "--output", "matrix.json",
        ])
        self.assertEqual(aggregate.bootstrap_samples, 10)
        for token in (
            '--g0 "$W/g0.pjtw" --g4 "$W/g4.pjtw"',
            '--scan-runtime-sha256 "$SCAN_RUNTIME_SHA256"',
            '--search-params "$SEARCH_PARAMS"',
            '--depth "$DEPTH" --max-plies "$MAXPLIES" --game-timeout "$GAME_TIMEOUT"',
            '--shard-index "$shard"',
            '--nshards "$NSHARDS"',
            '--output "$MATRIX/$arm/s${shard}.jsonl"',
            'RESULT_ARGS+=(--result "$arm=$result")',
            '--run-config "$OUT/run-config.json" --expected-per-arm "$POOL_POSITIONS"',
            '--bootstrap-samples "$BOOTSTRAP"',
            '--output "$OUT/stable-top3-causal-matrix.json"',
            '"move_identity": "exact_capture_set"',
            '"name": "equal_weight_12_cell_standardized"',
        ):
            self.assertIn(token, self.template)
        for stale in (
            "--g0-pattern", "--g4-pattern", "--inputs",
        ):
            self.assertNotIn(stale, self.template)

    def test_0921_pure_mirror_is_same_matrix_with_pinned_pure_g4(self) -> None:
        for token in (
            'EVAL_SOURCE_MODE="${EVAL_SOURCE_MODE:-imbalance2-0890bis}"',
            "pure-0842",
            "artefacts/g0-material.pjtw.gz=pure-g0.pjtw.gz",
            "artefacts/g4.pjtw.gz=pure-g4.pjtw.gz",
            "e7eb9cd359d3418720e5e39484187d9d224ac9febd2b26e6302190454dd4e8e6",
            "93c76031be3a039aa08eec4a1d3166321d93d602ca78a139509f8c6e90de5e86",
            'manifest.get("training_sources") != ["selfplay_terminal_wdl"]',
            "observed_0908=2688_games/320s_total",
            'SHARD_TIMEOUT" -eq 900',
            'GLOBAL_TIMEOUT" -eq 1200',
        ):
            self.assertIn(token, self.template)
        for token in (
            "cpx62-0921-l3-pure-top3-stable-conversion-matrix-v1",
            'export EVAL_SOURCE_MODE="pure-0842"',
            "NSHARDS=16 PAR=16 GAME_TIMEOUT=120 SHARD_TIMEOUT=900 GLOBAL_TIMEOUT=1200",
            "JASS_BUILD_JOBS=4",
            "BOOTSTRAP=10000",
        ):
            self.assertIn(token, self.pure_wrapper)


if __name__ == "__main__":
    unittest.main()
