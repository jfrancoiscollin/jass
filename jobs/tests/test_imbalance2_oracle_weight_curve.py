#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "jobs/tools/imbalance2_oracle_weight_curve.py"
RUNNER = ROOT / "jobs/templates/l3-imbalance2-w0-oracle-calibration-v1.sh"
WRAPPER = ROOT / "jobs/prepared/l3-imbalance2-w0-20260721/cpx62-l3-imbalance2-w0-oracle-calibration.sh"


def load_tool():
    spec = importlib.util.spec_from_file_location("w0", TOOL)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def make_reference(noisy: bool = False):
    strata = {}
    for n in range(1, 19):
        total = 2 * n + 2
        source = "exact_egdb_wdl" if n <= 2 else "scan_d10_selfplay_reference"
        # Stable monotone fixture unless explicitly made noisy.
        alpha = 0.10 + 0.045 * n
        if noisy and n % 2 == 0:
            alpha = max(0.02, alpha - 0.35)
        loss = 0.05
        win = min(0.90, loss + alpha)
        draw = 1.0 - win - loss
        pools = {}
        for label, offset in (("plateau-a.jnnw", -0.015), ("plateau-b.jnnw", 0.015)):
            pw = max(0.0, min(1.0, win + offset))
            pd = max(0.0, 1.0 - pw - loss)
            pools[label] = {"n":64,"total_pieces":total,"source":source,
                            "rates":{"win":pw,"draw":pd,"loss":loss}}
        strata[f"{n}v{n+2}"] = {
            "n":128,"total_pieces":total,"source":source,
            "rates":{"win":win,"draw":draw,"loss":loss},"pools":pools,
        }
    return {"schema":1,"protocol":"material-stratified-conversion-difficulty-reference",
            "lineage":"L3-IMBALANCE2","perspective":"initial_material_up_side",
            "scan_reference_is_exact":False,"strata":strata}


def main() -> int:
    module = load_tool()
    result = module.calibrate(make_reference(), 32.0)
    assert result["decision"] == "W0_ORACLE_WEIGHT_CALIBRATION_READY"
    assert result["diagnostics"]["pool_stability_pass"] is True
    assert result["diagnostics"]["density_only_hypothesis_pass"] is True
    assert result["classification"] == "DENSITY_ADAPTIVE_WEIGHTING_SUPPORTED"
    assert result["training_authorized"] is False
    assert len(result["strata"]) == 18
    first, last = result["strata"][0], result["strata"][-1]
    assert first["proposed_weights_absolute"]["draw"] < last["proposed_weights_absolute"]["draw"]
    assert last["proposed_weights_dense_normalized"]["upset_result"] <= 4.0

    noisy = module.calibrate(make_reference(noisy=True), 32.0)
    assert noisy["training_authorized"] is False
    assert noisy["automatic_next_job"] is None

    with tempfile.TemporaryDirectory() as tmp:
        ref = Path(tmp) / "ref.json"
        out = Path(tmp) / "out.json"
        ref.write_text(json.dumps(make_reference()), encoding="utf-8")
        subprocess.run(["python3", str(TOOL), "--reference", str(ref), "--out", str(out)], check=True)
        assert json.loads(out.read_text())["weight_policy_authorized"] is False

    for path in (RUNNER, WRAPPER):
        subprocess.run(["bash", "-n", str(path)], check=True)
    runner = RUNNER.read_text(encoding="utf-8")
    assert "JASS_CONTROL_SUMMARY.json" in runner
    assert "TRAINING_AUTHORIZED" in runner
    assert "imbalance2_oracle_weight_curve.py" in runner
    wrapper = WRAPPER.read_text(encoding="utf-8")
    assert "EXPECTED_CODE_SHA" in wrapper
    assert "W0_CALIBRATION_GO=1" in wrapper
    print("ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
