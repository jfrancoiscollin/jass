#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "jobs/tools/jfi_path_amendment_readout.py"


def p3_payload():
    return {
        "schema": "jass.jfi.path_autopsy.p3.v1",
        "verdict": "JFI_PATH_DEPENDENCE_OBJECTIVE_TOLERANCE_ONLY",
        "next_boundary": "GO_JFI_PATH_AMENDMENT",
        "all_four_endpoint_optimizers_satisfy_frozen_convergence_contract": True,
        "all_exact_replay_same_center_score_paths_within_original_materiality_limits": True,
        "only_original_jfi_a_trigger_is_frozen_objective_pair_threshold": True,
        "pairs": {
            "A_vs_B_curriculum_center": {"original_score_limits_pass_on_exact_replay": True},
            "C_vs_D_zero_center": {"original_score_limits_pass_on_exact_replay": True},
        },
        "optimizers": {arm: {"frozen_convergence_contract_pass": True} for arm in "ABCD"},
        "markers": {
            "NEW_FITS": 0, "REFITS": 0, "FRESH_OPENINGS": 0,
            "STRENGTH_GAMES": 0, "SCAN_WEIGHT_READS": 0,
            "SCAN_SCORE_READS": 0, "SCAN_TARGET_READS": 0,
            "PROMOTION_AUTHORIZED": False, "JFI_ACTIVE_AUTHORIZED": False,
        },
    }


def l2_payload():
    return {"selected_l2": 1e-5, "bootstrap_samples": 100000, "bootstrap_seed": 2026120101}


def run(p3, l2):
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        p3p, l2p, out = td/"p3.json", td/"l2.json", td/"out.json"
        p3p.write_text(json.dumps(p3)); l2p.write_text(json.dumps(l2))
        proc = subprocess.run([sys.executable, str(TOOL), "--p3", str(p3p), "--l2", str(l2p), "--out", str(out)], text=True, capture_output=True)
        payload = json.loads(out.read_text()) if out.exists() else None
        return proc, payload


def test_pass():
    proc, payload = run(p3_payload(), l2_payload())
    assert proc.returncode == 0, proc.stderr
    assert payload["verdict"] == "JFI_OPTIMIZER_PATH_INDEPENDENCE_ESTABLISHED"
    assert payload["selected_l2"] == 1e-5
    assert payload["next_boundary"] == "GO_JFI_IDENTIFIABILITY"
    assert payload["amended_path_gate"]["objective_abs_difference_is_gate"] is False


def test_fail_closed_on_material_score_effect():
    p3 = p3_payload(); p3["pairs"]["A_vs_B_curriculum_center"]["original_score_limits_pass_on_exact_replay"] = False
    proc, payload = run(p3, l2_payload())
    assert proc.returncode != 0
    assert payload is None


def test_fail_closed_on_lambda_drift():
    l2 = l2_payload(); l2["selected_l2"] = 1e-4
    proc, payload = run(p3_payload(), l2)
    assert proc.returncode != 0
    assert payload is None


if __name__ == "__main__":
    test_pass(); test_fail_closed_on_material_score_effect(); test_fail_closed_on_lambda_drift()
    print("PASS")
