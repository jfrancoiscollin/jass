#!/usr/bin/env python3
from __future__ import annotations

import gzip
import importlib.util
import json
from pathlib import Path
import struct
import subprocess
import sys
import tarfile
import tempfile
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "jobs/tools/imbalance2_d1x_autopsy.py"
RUNNER = ROOT / "jobs/templates/l3-imbalance2-d1x-autopsy-v1.sh"
PREPARED = ROOT / "jobs/prepared/l3-imbalance2-d1x-20260720"

spec = importlib.util.spec_from_file_location("d1x", TOOL)
d1x = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(d1x)


def write_pjtw(path: Path, n_ext: int, extra_tail=(0, 0, 0, 0)) -> None:
    n_pat = 2
    weights = np.zeros(2 * (n_pat + n_ext), dtype="<i4")
    weights[0] = 10
    weights[n_pat] = -5
    ext_mg = 2 * n_pat
    ext_eg = 2 * n_pat + n_ext
    if n_ext == 124:
        weights[ext_mg + 120:ext_mg + 124] = np.array(extra_tail, dtype="<i4")
        weights[ext_eg + 120:ext_eg + 124] = np.array(extra_tail, dtype="<i4") * 2
    raw = b"PJTW" + struct.pack("<IIII", 3, 1000, n_pat, n_ext) + weights.tobytes()
    path.write_bytes(gzip.compress(raw, mtime=0))


def write_jnnw(path: Path, count: int) -> None:
    rows = bytearray()
    for i in range(count):
        # White one man, Black three men, equal king counts: exact RC4 domain.
        wm = 1 << (i % 10)
        bm = (1 << 20) | (1 << 21) | (1 << 22)
        rows += struct.pack("<QQQQBib", wm, 0, bm, 0, i % 2, 0, 0)
    path.write_bytes(b"JNNW" + struct.pack("<I", count) + bytes(rows))


def write_feat(path: Path, count: int) -> None:
    x = np.zeros((count, 124), dtype="<f4")
    x[:, -4:] = np.array([1, 2, 3, 4], dtype="<f4")
    path.write_bytes(b"FEAT" + struct.pack("<II", count, 124) + x.tobytes())


def write_reports_tar(path: Path) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for arm in ("control", "rc4"):
            for pool in ("plateau-c.jnnw", "plateau-d.jnnw"):
                rows = []
                for i in range(1152):
                    n = i % 18 + 1
                    outcome = "draw"
                    if arm == "rc4" and i == 0:
                        outcome = "loss"
                    rows.append({"index": i, "stratum": f"{n}v{n+2}", "outcome": outcome})
                payload = {"engine": "candidate", "pool": pool, "rows": rows}
                out = root / arm / pool.replace(".jnnw", ".json")
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_text(json.dumps(payload))
        with tarfile.open(path, "w:gz") as tar:
            tar.add(root, arcname=".")


def write_sentinel_tar(path: Path) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        rows = []
        for i in range(30):
            for engine in ("control", "rc4"):
                rows.append({
                    "sentinel_id": f"S{i:02d}", "engine": engine,
                    "analysis": {"best_move": "1-6", "score": i, "nodes": 100 + i},
                })
        (root / "s0.json").write_text(json.dumps({
            "protocol": "imbalance2-d1-rc4-sentinel-replay", "rows": rows,
        }))
        with tarfile.open(path, "w:gz") as tar:
            tar.add(root, arcname=".")


class D1XTests(unittest.TestCase):
    def test_model_and_feature_activity(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            control = root / "control.pjtw.gz"
            rc4 = root / "rc4.pjtw.gz"
            data = root / "data.jnnw"
            feat = root / "data.feat"
            write_pjtw(control, 120)
            write_pjtw(rc4, 124, (1, -2, 3, -4))
            write_jnnw(data, 4)
            write_feat(feat, 4)
            models = d1x.compare_models(control, rc4)
            activity = d1x.inspect_features(feat, data)
            self.assertEqual(models["max_abs_rc4_weight_raw"], 8)
            self.assertEqual(activity["role_domain_rate"], 1.0)
            self.assertEqual(activity["any_rc4_nonzero_rate"], 1.0)

    def test_end_to_end_synthetic_autopsy(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            control = root / "control.pjtw.gz"; write_pjtw(control, 120)
            rc4 = root / "rc4.pjtw.gz"; write_pjtw(rc4, 124, (1, 2, 3, 4))
            files = {}
            for name in ("train", "c", "d"):
                data = root / f"{name}.jnnw"; feat = root / f"{name}.feat"
                write_jnnw(data, 4); write_feat(feat, 4); files[name] = (data, feat)
            raw_tar = root / "raw.tar.gz"; write_reports_tar(raw_tar)
            sent_tar = root / "sent.tar.gz"; write_sentinel_tar(sent_tar)
            decision = root / "decision.json"
            decision.write_text(json.dumps({
                "decision": "D1_RC4_NO_GO",
                "paired": {"macro_equal_stratum": {
                    "rc4_minus_control_failure_cost": 0.003038,
                    "stratified_bootstrap_95": [-0.043403, 0.049913],
                    "nonworse_strata": 9,
                }},
                "sentinel_gate": {
                    "corrected_representation_cases": 0,
                    "new_divergences_non_target": 0,
                    "throughput": {"rc4_over_control": 0.935302},
                },
            }))
            general = root / "general.json"
            game_rows = []
            for pair in range(64):
                game_rows.extend([
                    {"pair": pair, "rc4_colour": "white", "outcome_white_pov": "D", "rc4_points": 0.5, "plies": 20, "reason": "draw"},
                    {"pair": pair, "rc4_colour": "black", "outcome_white_pov": "D", "rc4_points": 0.5, "plies": 20, "reason": "draw"},
                ])
            general.write_text(json.dumps({
                "protocol": "d1-rc4-paired-generalist-guard", "pairs": 64,
                "seed": 314159, "rc4_score_rate": 0.5,
                "paired_bootstrap_95": [0.4, 0.6], "pass": True,
                "game_rows": game_rows,
            }))
            out = root / "out.json"
            cmd = [sys.executable, str(TOOL),
                "--decision", str(decision), "--generalist", str(general),
                "--control-model", str(control), "--rc4-model", str(rc4),
                "--raw-reports", str(raw_tar), "--sentinel-replays", str(sent_tar),
                "--train-feat", str(files["train"][1]), "--train-data", str(files["train"][0]),
                "--pool-c-feat", str(files["c"][1]), "--pool-c-data", str(files["c"][0]),
                "--pool-d-feat", str(files["d"][1]), "--pool-d-data", str(files["d"][0]),
                "--openings", str(ROOT / "data/dilf_combinations.fen"), "--out", str(out)]
            subprocess.run(cmd, check=True, capture_output=True, text=True)
            payload = json.loads(out.read_text())
            self.assertEqual(payload["decision"], "D1X_RC4_AUTOPSY_READY")
            self.assertFalse(payload["search_pilot_authorized"])
            self.assertEqual(payload["conversion_transition_analysis"]["paired_positions"], 2304)

    def test_runner_and_prepared_contracts(self):
        scripts = [RUNNER, *sorted(PREPARED.glob("*.sh"))]
        self.assertEqual(len(scripts), 3)
        for script in scripts:
            subprocess.run(["bash", "-n", str(script)], check=True)
        text = RUNNER.read_text()
        for forbidden in ("train_stream.py", "--tournament", "--gen-data-wdl", "SCAN_BIN", "automatic_next_job="):
            self.assertNotIn(forbidden, text)
        self.assertIn("D1X_AUTOPSY_GO", text)
        self.assertIn("search_pilot_authorized=false", text)


if __name__ == "__main__":
    unittest.main()
