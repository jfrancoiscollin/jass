#!/usr/bin/env python3
"""JFI path-dependence autopsy P3: stopping-tolerance terminal diagnosis."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

PAIR_LIMIT = 1e-6
EXPECTED_PAIRS = ("A_vs_B_curriculum_center", "C_vs_D_zero_center")
EXPECTED_ARMS = ("A", "B", "C", "D")


def load(path: str) -> dict:
    return json.loads(Path(path).read_text())


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--p1", required=True)
    ap.add_argument("--p2", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)

    p1 = load(args.p1)
    p2 = load(args.p2)
    technical = False

    if p1.get("schema") != "jass.jfi.path_autopsy.p1.v1":
        technical = True
    if p2.get("schema") != "jass.jfi.path_autopsy.p2.v1":
        technical = True

    p1_objective_only = p1.get("verdict") == "JFI_PATH_AUTOPSY_OBJECTIVE_ONLY_TRIGGER"
    p2_ready = (
        p2.get("verdict") == "JFI_PATH_AUTOPSY_P2_READY_FOR_P3"
        and p2.get("p3_authorized") is True
        and p2.get("endpoint_reproduction") is True
    )

    p2_markers_ok = p2.get("markers") == {
        "NEW_FITS": 0,
        "REFITS": 0,
        "FRESH_OPENINGS": 0,
        "STRENGTH_GAMES": 0,
        "SCAN_WEIGHT_READS": 0,
        "SCAN_SCORE_READS": 0,
        "SCAN_TARGET_READS": 0,
        "PROMOTION_AUTHORIZED": False,
    }

    pair_reports = {}
    all_score_limits_pass = True
    only_objective_trigger = p1_objective_only
    for name in EXPECTED_PAIRS:
        one = p1.get("pairs", {}).get(name, {})
        two = p2.get("pairs", {}).get(name, {})
        checks = one.get("checks", {})
        score_pass = bool(
            checks.get("score_rms_pass") is True
            and checks.get("score_max_abs_pass") is True
            and two.get("original_score_limits_pass") is True
        )
        objective_failed = checks.get("objective_pass") is False
        all_score_limits_pass = all_score_limits_pass and score_pass
        only_objective_trigger = only_objective_trigger and score_pass and objective_failed
        objective_delta = float(one.get("objective_abs_difference", float("nan")))
        left, right = (("A", "B") if name.startswith("A_vs_B") else ("C", "D"))
        gtols = [float(p1.get("optimizers", {}).get(arm, {}).get("gtol", float("nan"))) for arm in (left, right)]
        pair_gtol = max(gtols) if all(value > 0 for value in gtols) else float("nan")
        pair_reports[name] = {
            "objective_abs_difference": objective_delta,
            "frozen_pair_objective_limit": PAIR_LIMIT,
            "objective_difference_over_pair_limit": objective_delta / PAIR_LIMIT,
            "endpoint_gtol": {left: gtols[0], right: gtols[1]},
            "objective_difference_over_max_endpoint_gtol_descriptive_only": objective_delta / pair_gtol,
            "original_score_limits_pass_on_exact_replay": bool(two.get("original_score_limits_pass")),
            "original_trigger_checks": checks,
        }

    optimizer_reports = {}
    all_converged = True
    for arm in EXPECTED_ARMS:
        opt = p1.get("optimizers", {}).get(arm, {})
        success = opt.get("success") is True
        status_zero = opt.get("status") == 0
        grad = float(opt.get("gradient_inf_norm", float("nan")))
        gtol = float(opt.get("gtol", float("nan")))
        gradient_pass = gtol > 0 and grad <= gtol
        contract_pass = success and status_zero and gradient_pass
        all_converged = all_converged and contract_pass
        optimizer_reports[arm] = {
            "success": success,
            "status": opt.get("status"),
            "iterations": opt.get("iterations"),
            "max_iterations": opt.get("max_iterations"),
            "maxcor": opt.get("maxcor"),
            "final_objective": opt.get("final_objective"),
            "gradient_inf_norm": grad,
            "gtol": gtol,
            "gradient_over_gtol": grad / gtol if gtol > 0 else None,
            "frozen_convergence_contract_pass": contract_pass,
        }

    if technical or not p2_markers_ok:
        verdict = "JFI_PATH_DEPENDENCE_AUTOPSY_TECHNICAL_INCONCLUSIVE"
    elif not all_score_limits_pass:
        verdict = "JFI_PATH_DEPENDENCE_MATERIAL_SCORE_EFFECT_CONFIRMED"
    elif p2_ready and only_objective_trigger and all_converged:
        verdict = "JFI_PATH_DEPENDENCE_OBJECTIVE_TOLERANCE_ONLY"
    else:
        verdict = "JFI_PATH_DEPENDENCE_AUTOPSY_MIXED"

    payload = {
        "schema": "jass.jfi.path_autopsy.p3.v1",
        "verdict": verdict,
        "source": {
            "p1_verdict": p1.get("verdict"),
            "p2_verdict": p2.get("verdict"),
            "p2_endpoint_reproduction": p2.get("endpoint_reproduction"),
        },
        "pairs": pair_reports,
        "optimizers": optimizer_reports,
        "all_four_endpoint_optimizers_satisfy_frozen_convergence_contract": all_converged,
        "all_exact_replay_same_center_score_paths_within_original_materiality_limits": all_score_limits_pass,
        "only_original_jfi_a_trigger_is_frozen_objective_pair_threshold": only_objective_trigger,
        "stopping_semantics": {
            "gtol": "gradient infinity-norm stopping criterion",
            "objective_pair_threshold": "independent preregistered cross-endpoint objective-difference gate",
            "implication": "gtol=1e-4 does not mathematically imply objective_abs_difference<=1e-6 between separately converged endpoints",
        },
        "next_boundary": (
            "GO_JFI_PATH_AMENDMENT"
            if verdict == "JFI_PATH_DEPENDENCE_OBJECTIVE_TOLERANCE_ONLY"
            else None
        ),
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
    print(verdict)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
