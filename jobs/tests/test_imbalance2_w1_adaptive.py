#!/usr/bin/env python3
from __future__ import annotations

import json
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REWEIGHT = ROOT / "jobs/tools/imbalance2_adaptive_reweight.py"
REPORT = ROOT / "jobs/tools/imbalance2_w1_screen_report.py"
RUNNER = ROOT / "jobs/templates/l3-imbalance2-w1-screen-v1.sh"
PREPARED = ROOT / "jobs/prepared/l3-imbalance2-w1-20260721/ccx33-l3-imbalance2-w1-screen.sh"
REC = struct.Struct("<QQQQBiB")


def bits(n: int, start: int) -> int:
    value = 0
    for square in range(start, start + n):
        value |= 1 << square
    return value


def record(low: int, *, white_up: bool, stm: int, wdl: int) -> bytes:
    high = low + 2
    if white_up:
        wm, bm = bits(high, 0), bits(low, 24)
    else:
        wm, bm = bits(low, 0), bits(high, 24)
    return REC.pack(wm, 0, bm, 0, stm, 0, wdl & 0xFF)


def write_jnnw(path: Path, rows: list[bytes]) -> None:
    path.write_bytes(b"JNNW" + struct.pack("<I", len(rows)) + b"".join(rows))


def policy_payload(*, stable: bool = True, density: bool = False) -> dict:
    rows = []
    for n in range(1, 19):
        alpha = 0.25 + n / 100.0
        rows.append({
            "stratum": f"{n}v{n+2}",
            "proposed_weights_absolute": {
                "expected_result": 1.0,
                "draw": round(1.0 + alpha, 6),
                "upset_result": round(1.0 + 3.0 * alpha, 6),
            },
        })
    return {
        "decision": "W0_ORACLE_WEIGHT_CALIBRATION_READY",
        "classification": "STRATUM_ORACLE_WEIGHTING_SUPPORTED_DENSITY_ONLY_NOT_SUPPORTED",
        "diagnostics": {"pool_stability_pass": stable, "density_only_hypothesis_pass": density},
        "strata": rows,
    }


def gate_report(path: Path, pool: str, outcome: str) -> None:
    rows = []
    for n in range(1, 19):
        for index in range(64):
            rows.append({"index": (n - 1) * 64 + index, "stratum": f"{n}v{n+2}", "outcome": outcome})
    path.write_text(json.dumps({"engine": "candidate", "pool": str(path.parent / f"plateau-{pool}.jnnw"), "rows": rows}), encoding="utf-8")


class AdaptiveReweightTests(unittest.TestCase):
    def test_resamples_by_stratum_and_preserves_holdout_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rows = []
            for n in range(1, 19):
                rows.extend([
                    record(n, white_up=True, stm=0, wdl=1),
                    record(n, white_up=True, stm=0, wdl=0),
                    record(n, white_up=True, stm=0, wdl=-1),
                    record(n, white_up=False, stm=0, wdl=1),
                ])
            holdout = rows[-8:]
            inp, out = root / "in.jnnw", root / "out.jnnw"
            write_jnnw(inp, rows)
            policy = root / "policy.json"
            policy.write_text(json.dumps(policy_payload()), encoding="utf-8")
            report = root / "report.json"
            subprocess.run([
                sys.executable, str(REWEIGHT), "--input", str(inp), "--output", str(out),
                "--policy", str(policy), "--holdout-count", "8", "--seed", "17", "--report", str(report),
            ], check=True, capture_output=True, text=True)
            raw = out.read_bytes()
            self.assertEqual(struct.unpack_from("<I", raw, 4)[0], len(rows))
            self.assertEqual(raw[-8 * 38:], b"".join(holdout))
            payload = json.loads(report.read_text())
            self.assertEqual(payload["domain_records"], len(rows) - 8)
            self.assertFalse(payload["wdl_labels_changed"])
            self.assertEqual(set(payload["weights_by_stratum"]), {f"{n}v{n+2}" for n in range(1, 19)})

    def test_zero_v_two_retains_historical_fixed_v2_weights(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rows = [
                record(0, white_up=True, stm=0, wdl=1),
                record(0, white_up=True, stm=0, wdl=0),
                record(0, white_up=True, stm=0, wdl=-1),
                record(1, white_up=True, stm=0, wdl=1),
            ]
            inp, out = root / "in.jnnw", root / "out.jnnw"
            write_jnnw(inp, rows)
            policy = root / "policy.json"; policy.write_text(json.dumps(policy_payload()), encoding="utf-8")
            report = root / "report.json"
            subprocess.run([
                sys.executable, str(REWEIGHT), "--input", str(inp), "--output", str(out),
                "--policy", str(policy), "--holdout-count", "1", "--seed", "17", "--report", str(report),
            ], check=True, capture_output=True, text=True)
            payload = json.loads(report.read_text())
            self.assertEqual(payload["uncalibrated_fixed_strata"]["0v2"], {
                "expected_result": 1.0, "draw": 2.0, "upset_result": 4.0,
            })
            self.assertEqual(payload["source_by_stratum"]["0v2"]["fixed_v2_expected_result"], 1)
            self.assertEqual(payload["source_by_stratum"]["0v2"]["fixed_v2_draw"], 1)
            self.assertEqual(payload["source_by_stratum"]["0v2"]["fixed_v2_upset_result"], 1)

    def test_rejects_density_only_or_unstable_policy(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            inp = root / "in.jnnw"
            write_jnnw(inp, [record(1, white_up=True, stm=0, wdl=0)] * 4)
            for name, payload in (("density", policy_payload(density=True)), ("unstable", policy_payload(stable=False))):
                policy = root / f"{name}.json"; policy.write_text(json.dumps(payload), encoding="utf-8")
                proc = subprocess.run([
                    sys.executable, str(REWEIGHT), "--input", str(inp), "--output", str(root / f"{name}.out"),
                    "--policy", str(policy), "--holdout-count", "1", "--seed", "1", "--report", str(root / f"{name}.report"),
                ], capture_output=True, text=True)
                self.assertNotEqual(proc.returncode, 0)


class W1ReportTests(unittest.TestCase):
    def run_report(self, adaptive_outcome: str) -> dict:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        sets = {"control": [], "adaptive": []}
        for arm, outcome in (("control", "draw"), ("adaptive", adaptive_outcome)):
            for pool in ("e", "f"):
                path = root / f"{arm}-{pool}.json"
                gate_report(path, pool, outcome)
                sets[arm].append(str(path))
        manifest = root / "manifest.json"
        manifest.write_text(json.dumps({"same_pools": True, "same_search_budget": True, "report_sets": sets}), encoding="utf-8")
        generalist = root / "generalist.json"
        generalist.write_text(json.dumps({
            "protocol": "l3-imbalance2-w1-paired-generalist-guard",
            "adaptive_score_rate": 0.5,
            "paired_bootstrap_95": [0.45, 0.55],
            "pass": True,
        }), encoding="utf-8")
        policy = root / "policy-report.json"
        policy.write_text(json.dumps({"protocol": "l3-imbalance2-w1-stratum-adaptive-resample"}), encoding="utf-8")
        out, summary = root / "out.json", root / "summary.json"
        subprocess.run([
            sys.executable, str(REPORT), "--manifest", str(manifest), "--generalist", str(generalist),
            "--policy-report", str(policy), "--out", str(out), "--summary-out", str(summary),
            "--bootstrap", "10000", "--seed", "141421",
        ], check=True, capture_output=True, text=True)
        return json.loads(out.read_text())

    def test_large_paired_improvement_passes_screen_only(self):
        payload = self.run_report("win")
        self.assertEqual(payload["decision"], "W1_ADAPTIVE_SCREEN_PASS_REVIEW_CONFIRMATION")
        self.assertTrue(payload["confirmation_requires_fresh_c512_crossfit"])
        self.assertFalse(payload["training_continuation_authorized"])
        self.assertFalse(payload["promotion_authorized"])
        self.assertIsNone(payload["automatic_next_job"])

    def test_flat_result_is_no_go(self):
        payload = self.run_report("draw")
        self.assertEqual(payload["decision"], "W1_ADAPTIVE_NO_GO")


class PreparedContractTests(unittest.TestCase):
    def test_shell_contract(self):
        for path in (RUNNER, PREPARED):
            self.assertTrue(path.is_file(), path)
            subprocess.run(["bash", "-n", str(path)], check=True)
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("jobs/queue", text)
        runner = RUNNER.read_text(encoding="utf-8")
        for token in (
            "g4-source.jnnw.gz", "g3.pjtw.gz", "w0-oracle-weight-calibration.json",
            "POOL_SEED:-141421", "PLATEAU_PER_STRATUM:-64", "DEPTH:-10",
            "same_warm_start_both_arms", "TRAINING_CONTINUATION_AUTHORIZED__FALSE",
            "PROMOTION_AUTHORIZED__FALSE", "JASS_CONTROL_SUMMARY.json",
        ):
            self.assertIn(token, runner)
        wrapper = PREPARED.read_text(encoding="utf-8")
        self.assertIn("ccx33-0852-l3-imbalance2-role-v2-p1", wrapper)
        self.assertIn("cpx62-0877-l3-imbalance2-w0-oracle-calibration", wrapper)
        self.assertIn('${EXPECTED_CODE_SHA:?', wrapper)
        self.assertIn("W1_ADAPTIVE_GO=1", wrapper)


if __name__ == "__main__":
    unittest.main()
