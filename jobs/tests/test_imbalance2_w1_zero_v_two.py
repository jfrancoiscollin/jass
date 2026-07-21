#!/usr/bin/env python3
from __future__ import annotations

import json
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "jobs/tools/imbalance2_adaptive_reweight.py"
REC = struct.Struct("<QQQQBiB")


def bits(n: int, start: int) -> int:
    value = 0
    for square in range(start, start + n):
        value |= 1 << square
    return value


def rec(low: int, wdl: int) -> bytes:
    return REC.pack(bits(low + 2, 0), 0, bits(low, 24), 0, 0, 0, wdl & 0xFF)


def policy() -> dict:
    rows = []
    for n in range(1, 19):
        alpha = 0.3
        rows.append({
            "stratum": f"{n}v{n+2}",
            "proposed_weights_absolute": {
                "expected_result": 1.0,
                "draw": 1.3,
                "upset_result": 1.9,
            },
        })
    return {
        "decision": "W0_ORACLE_WEIGHT_CALIBRATION_READY",
        "classification": "STRATUM_ORACLE_WEIGHTING_SUPPORTED_DENSITY_ONLY_NOT_SUPPORTED",
        "diagnostics": {"pool_stability_pass": True, "density_only_hypothesis_pass": False},
        "strata": rows,
    }


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        rows = [rec(0, 1), rec(0, 0), rec(0, -1), rec(1, 0), rec(1, 1)]
        inp = root / "in.jnnw"
        inp.write_bytes(b"JNNW" + struct.pack("<I", len(rows)) + b"".join(rows))
        pol = root / "policy.json"; pol.write_text(json.dumps(policy()))
        out = root / "out.jnnw"; report = root / "report.json"
        subprocess.run([
            sys.executable, str(TOOL), "--input", str(inp), "--output", str(out),
            "--policy", str(pol), "--holdout-count", "1", "--seed", "7", "--report", str(report),
        ], check=True)
        payload = json.loads(report.read_text())
        assert payload["schema"] == 2
        assert payload["uncalibrated_fixed_strata"]["0v2"] == {
            "expected_result": 1.0, "draw": 2.0, "upset_result": 4.0
        }
        assert payload["source_by_stratum"]["0v2"]["fixed_v2_expected_result"] == 1
        assert payload["source_by_stratum"]["0v2"]["fixed_v2_draw"] == 1
        assert payload["source_by_stratum"]["0v2"]["fixed_v2_upset_result"] == 1
        assert out.read_bytes()[-38:] == rows[-1]
    print("ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
