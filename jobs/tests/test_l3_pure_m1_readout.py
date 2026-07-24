from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "jobs" / "tools" / "l3_pure_m1_readout.py"


def test_readout_writes_status_visible_markers(tmp_path: Path) -> None:
    force = {}
    for i, model in enumerate(("F500", "F2M", "R2M")):
        force[model] = {}
        for key in ("q00_vs_C0", "native_vs_C0", "q00_vs_GEN2"):
            force[model][key] = {
                "n": 400,
                "wins_a": 180,
                "draws": 40,
                "wins_b": 180,
                "rate": 0.5 + i * 0.01,
                "elo": float(i * 7),
                "ci_low": 0.45,
                "ci_high": 0.55,
            }
    conversion = {}
    for i, model in enumerate(("C0", "F500", "F2M", "R2M")):
        conversion[model] = {
            stratum: {
                "n_pos": 100,
                "n_win": 50 + i,
                "n_draw": 10,
                "n_loss": 40 - i,
                "conversion": 0.50 + i * 0.01,
            }
            for stratum in ("p1_net", "p2_moyen", "p3_mince", "p4_egal")
        }
    payload = {
        "schema": 1,
        "verdict": "M1_EVALUATION_READY_HUMAN_REVIEW",
        "force": force,
        "fixed_defender_conversion": conversion,
        "promotion_authorized": False,
        "automatic_next_job": None,
    }
    source = tmp_path / "m1-evaluation.json"
    output = tmp_path / "m1-readout.json"
    markers = tmp_path / "markers"
    source.write_text(json.dumps(payload), encoding="utf-8")

    subprocess.run(
        [
            sys.executable,
            str(TOOL),
            "--input",
            str(source),
            "--out",
            str(output),
            "--marker-dir",
            str(markers),
        ],
        check=True,
    )

    readout = json.loads(output.read_text(encoding="utf-8"))
    assert abs(readout["global_delta_vs_c0"]["R2M"] - 0.03) < 1e-12
    names = {path.name for path in markers.iterdir()}
    assert "PROMOTION_AUTHORIZED__FALSE" in names
    assert "FORCE__F2M__Q00_VS_C0__RATE_BP_5100__ELO_MILLI_P7000" in names
    assert "CONVERSION_GLOBAL__R2M__BP_5300" in names
