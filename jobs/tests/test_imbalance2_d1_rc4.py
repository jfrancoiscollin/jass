#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "jobs/tools"
RUNNER = ROOT / "jobs/templates/l3-imbalance2-d1-rc4-v1.sh"
PREPARED = ROOT / "jobs/prepared/l3-imbalance2-d1-rc4-20260720"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class D1Rc4Tests(unittest.TestCase):
    def test_python_and_shell_syntax(self):
        python_files = [
            TOOLS / "apply_imbalance2_rc4_patch.py",
            TOOLS / "imbalance2_d1_rc4_sentinel.py",
            TOOLS / "imbalance2_d1_rc4_generalist.py",
            TOOLS / "imbalance2_d1_rc4_report.py",
        ]
        subprocess.run([sys.executable, "-m", "py_compile", *map(str, python_files)], check=True)
        wrappers = sorted(PREPARED.glob("*.sh"))
        self.assertEqual(len(wrappers), 2)
        for script in [RUNNER, *wrappers]:
            subprocess.run(["bash", "-n", str(script)], check=True)

    def test_wrappers_are_scientifically_identical_and_not_queued(self):
        wrappers = sorted(PREPARED.glob("*.sh"))
        normalized = []
        for script in wrappers:
            text = script.read_text(encoding="utf-8")
            self.assertNotIn("/jobs/queue/", str(script))
            self.assertIn("do not queue without explicit go", text)
            self.assertIn('POOL_SEED=314159', text)
            self.assertIn('PLATEAU_PER_STRATUM=64 DEPTH=10 MAXPLIES=400', text)
            self.assertIn('D1_RC4_GO=1', text)
            self.assertIn('GENERALIST_PAIRS=64', text)
            body = "\n".join(
                line for line in text.splitlines()
                if not line.startswith("# id:") and not line.startswith("# description:")
            )
            normalized.append(body)
        self.assertEqual(normalized[0], normalized[1])

    def test_runner_is_same_corpus_single_factor_and_non_promotable(self):
        text = RUNNER.read_text(encoding="utf-8")
        for required in (
            "g4-source.jnnw.gz",
            "same_weighted_jnnw",
            "same_source_bytes_both_arms",
            "JASS_ROLE_CONVERSION=1",
            "control-refit.pjtw.gz",
            "rc4.pjtw.gz",
            "plateau-c.jnnw",
            "plateau-d.jnnw",
            "d1b_authorized=false",
            "automatic_next_job=null",
        ):
            self.assertIn(required, text)
        for forbidden in ("--gen-data-wdl", "PARENT_MODEL_URI", "SCAN_BIN"):
            self.assertNotIn(forbidden, text)

    def test_generalist_loader_removes_inline_comments(self):
        module = load_module("d1_generalist", TOOLS / "imbalance2_d1_rc4_generalist.py")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "fens.txt"
            path.write_text(
                "# heading\nW:W31,32:B1,2  # diagram\nB:W27:B3 # another\n",
                encoding="utf-8",
            )
            self.assertEqual(module.load_fens(path), ["W:W31,32:B1,2", "B:W27:B3"])

    def test_paired_metric_and_sentinel_gate(self):
        report = load_module("d1_report", TOOLS / "imbalance2_d1_rc4_report.py")
        control = {}
        rc4 = {}
        keys = []
        for pool in ("plateau-c.jnnw", "plateau-d.jnnw"):
            for n in range(1, 19):
                key = (pool, n)
                keys.append(key)
                control[key] = {"stratum": f"{n}v{n+2}", "outcome": "draw"}
                rc4[key] = {"stratum": f"{n}v{n+2}", "outcome": "win"}
        paired = report.paired_view(control, rc4, keys, reps=1000, seed=314159)
        macro = paired["macro_equal_stratum"]
        self.assertEqual(macro["rc4_minus_control_failure_cost"], -1.0)
        self.assertEqual(macro["nonworse_strata"], 18)
        self.assertEqual(macro["stratified_bootstrap_95"], [-1.0, -1.0])

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cases = []
            for i in range(30):
                cases.append({
                    "sentinel_id": f"s{i:02d}",
                    "causal_hypothesis": (
                        "REPRESENTATION_OR_OBJECTIVE_CANDIDATE" if i < 7 else "SEARCH_AND_EVAL_MIXED"
                    ),
                    "scan_d14_anchor_move": "31-26",
                })
            d0 = root / "d0.json"
            d0.write_text(json.dumps({
                "protocol": "imbalance2-d0-causal-diagnostic",
                "cases": cases,
            }), encoding="utf-8")
            rows = []
            for i, case in enumerate(cases):
                for engine in ("control", "rc4"):
                    move = "31-26"
                    if i < 7 and engine == "control":
                        move = "32-27"
                    rows.append({
                        "sentinel_id": case["sentinel_id"],
                        "engine": engine,
                        "analysis": {
                            "best_move": move,
                            "nodes": 1000,
                            "elapsed_seconds": 1.0,
                        },
                    })
            replay = root / "replay.json"
            replay.write_text(json.dumps({
                "protocol": "imbalance2-d1-rc4-sentinel-replay",
                "rows": rows,
            }), encoding="utf-8")
            gate = report.sentinel_gate(str(d0), [str(replay)])
            self.assertEqual(gate["corrected_representation_cases"], 7)
            self.assertEqual(gate["new_divergences_non_target"], 0)
            self.assertTrue(gate["mechanism_pass"])
            self.assertTrue(gate["throughput"]["pass"])

    def test_isolated_patch_applies_without_touching_repository(self):
        patcher = TOOLS / "apply_imbalance2_rc4_patch.py"
        original_h = (ROOT / "src/scan_eval.hpp").read_bytes()
        original_c = (ROOT / "src/scan_eval.cpp").read_bytes()
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source"
            (source / "src").mkdir(parents=True)
            shutil.copy2(ROOT / "src/scan_eval.hpp", source / "src/scan_eval.hpp")
            shutil.copy2(ROOT / "src/scan_eval.cpp", source / "src/scan_eval.cpp")
            report = Path(tmp) / "patch.json"
            subprocess.run([
                sys.executable, str(patcher), "--source-root", str(source), "--report", str(report)
            ], check=True)
            payload = json.loads(report.read_text(encoding="utf-8"))
            self.assertEqual(payload["extra_count_delta"], 4)
            self.assertFalse(payload["production_source_modified"])
            self.assertIn("EXTRA_RC_SAFE_MOB_DELTA", (source / "src/scan_eval.hpp").read_text())
        self.assertEqual(original_h, (ROOT / "src/scan_eval.hpp").read_bytes())
        self.assertEqual(original_c, (ROOT / "src/scan_eval.cpp").read_bytes())

    @unittest.skipUnless(shutil.which("cmake") and shutil.which("c++"), "C++ toolchain unavailable")
    def test_rc4_isolated_source_compiles(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source"
            build = Path(tmp) / "build"
            shutil.copytree(
                ROOT,
                source,
                ignore=shutil.ignore_patterns(".git", "build", "__pycache__", "*.pyc"),
            )
            subprocess.run([
                sys.executable,
                str(source / "jobs/tools/apply_imbalance2_rc4_patch.py"),
                "--source-root", str(source),
                "--report", str(Path(tmp) / "patch.json"),
            ], check=True)
            subprocess.run([
                "cmake", "-S", str(source), "-B", str(build),
                "-DCMAKE_BUILD_TYPE=Release",
                "-DJASS_NATIVE=OFF",
                "-DJASS_ENABLE_SIMD=OFF",
                "-DJASS_ENDGAME_FEATURES=ON",
                "-DJASS_KING_MOBILITY=ON",
                "-DJASS_SCAN_PARITY=ON",
                "-DJASS_TEMPO_STAGE=ON",
                "-DCMAKE_CXX_FLAGS=-DJASS_ROLE_CONVERSION=1",
            ], check=True, stdout=subprocess.DEVNULL)
            subprocess.run([
                "cmake", "--build", str(build), "--target", "jass", "-j2"
            ], check=True, stdout=subprocess.DEVNULL)
            self.assertTrue((build / "jass").is_file())


if __name__ == "__main__":
    unittest.main()
