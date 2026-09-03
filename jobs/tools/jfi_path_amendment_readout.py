#!/usr/bin/env python3
"""Read-only JFI-A path amendment receipt after terminal P3 autopsy."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

EXPECTED_P3_VERDICT = "JFI_PATH_DEPENDENCE_OBJECTIVE_TOLERANCE_ONLY"
EXPECTED_SELECTED_L2 = 1e-5
EXPECTED_PAIRS = ("A_vs_B_curriculum_center", "C_vs_D_zero_center")
EXPECTED_ARMS = ("A", "B", "C", "D")


def load(path: str) -> dict:
    return json.loads(Path(path).read_text())


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--p3", required=True)
    ap.add_argument("--l2", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)

    p3 = load(args.p3)
    l2 = load(args.l2)

    if p3.get("schema") != "jass.jfi.path_autopsy.p3.v1":
        raise SystemExit("P3 schema drift")
    if p3.get("verdict") != EXPECTED_P3_VERDICT:
        raise SystemExit("P3 verdict does not authorize amendment")
    if p3.get("next_boundary") != "GO_JFI_PATH_AMENDMENT":
        raise SystemExit("P3 next-boundary drift")
    if p3.get("all_four_endpoint_optimizers_satisfy_frozen_convergence_contract") is not True:
        raise SystemExit("endpoint convergence contract not established")
    if p3.get("all_exact_replay_same_center_score_paths_within_original_materiality_limits") is not True:
        raise SystemExit("original score materiality limits not established")
    if p3.get("only_original_jfi_a_trigger_is_frozen_objective_pair_threshold") is not True:
        raise SystemExit("P3 did not isolate the objective-only trigger")

    for name in EXPECTED_PAIRS:
        pair = p3.get("pairs", {}).get(name, {})
        if pair.get("original_score_limits_pass_on_exact_replay") is not True:
            raise SystemExit(f"{name}: exact replay materiality gate failed")
    for arm in EXPECTED_ARMS:
        opt = p3.get("optimizers", {}).get(arm, {})
        if opt.get("frozen_convergence_contract_pass") is not True:
            raise SystemExit(f"{arm}: frozen convergence contract failed")

    markers = p3.get("markers", {})
    expected_markers = {
        "NEW_FITS": 0,
        "REFITS": 0,
        "FRESH_OPENINGS": 0,
        "STRENGTH_GAMES": 0,
        "SCAN_WEIGHT_READS": 0,
        "SCAN_SCORE_READS": 0,
        "SCAN_TARGET_READS": 0,
        "PROMOTION_AUTHORIZED": False,
        "JFI_ACTIVE_AUTHORIZED": False,
    }
    if markers != expected_markers:
        raise SystemExit("P3 guard markers drift")

    selected = float(l2.get("selected_l2"))
    if selected != EXPECTED_SELECTED_L2:
        raise SystemExit(f"selected lambda drift: {selected}")
    if int(l2.get("bootstrap_samples", 0)) != 100000 or int(l2.get("bootstrap_seed", 0)) != 2026120101:
        raise SystemExit("JFI-B one-SE bootstrap contract drift")

    payload = {
        "schema": "jass.jfi.path_amendment.v1",
        "verdict": "JFI_OPTIMIZER_PATH_INDEPENDENCE_ESTABLISHED",
        "basis": {
            "terminal_autopsy_verdict": p3.get("verdict"),
            "same_center_score_materiality_limits_pass": True,
            "all_endpoint_optimizers_converged": True,
            "objective_abs_difference_role": "descriptive_only",
        },
        "amended_path_gate": {
            "holdout_score_rms_limit_cp": 0.5,
            "serialized_score_max_abs_limit_cp": 2.0,
            "endpoint_optimizer_contract": "success=true,status=0,gradient_inf_norm<=gtol",
            "objective_abs_difference_is_gate": False,
        },
        "selected_l2": selected,
        "next_boundary": "GO_JFI_IDENTIFIABILITY",
        "markers": {
            "NEW_FITS": 0,
            "REFITS": 0,
            "FRESH_OPENINGS": 0,
            "STRENGTH_GAMES": 0,
            "SCAN_WEIGHT_READS": 0,
            "SCAN_SCORE_READS": 0,
            "SCAN_TARGET_READS": 0,
            "PROMOTION_AUTHORIZED": False,
            "JFI_ACTIVE_AUTHORIZED": False,
        },
    }
    Path(args.out).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(payload["verdict"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
