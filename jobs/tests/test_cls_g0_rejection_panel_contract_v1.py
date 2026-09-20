"""Preregistration/fixture checks only: no engine, transport or remote execution."""
from __future__ import annotations

import copy
import json
import math
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "docs/experiments/CLS_G0_REJECTION_PANEL_V1_20260920.json"
DOC = CONTRACT.with_suffix(".md")
MODELS = {
    "CURRICULUM": "319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1",
    "LOCAL": "197998003db3d221d38e81577cfa381e8227d67705efc1c86b87205ddebbe450",
    "WDL": "eabe71068dbc6aeb519a61c730d18586e75c8b72308ecd340de08fe2e18deed6",
    "HIER": "95bed3ac9fac4368809609fb1a981ee863401a30ca623fb7bfa3caf7eaddf628",
}
CONTRASTS = [["LOCAL", "CURRICULUM"], ["WDL", "CURRICULUM"]]


def validate_contract(c: dict) -> None:
    """Local reference checks for the protocol, not a production launch gate."""
    def need(condition: bool, name: str) -> None:
        if not condition:
            raise ValueError(name)
    need(c["schema"] == "jass.cls_g0_rejection_panel_prereg.v1", "schema")
    need(c["status"] == "PREREGISTRATION_ONLY_NO_EXECUTION", "scope")
    need(c["models"] == MODELS, "models")
    need(c["panel"]["confirmatory_contrasts"] == CONTRASTS, "panel")
    need(c["panel"]["historical_only"] == ["HIER"], "history")
    need(c["panel"]["replay_hier_allowed"] is False, "no_hier_replay")
    need(c["authorization"]["remote_launch_authorized"] is False, "no_launch")
    s = c["statistics"]
    need(s["pairs_per_contrast"] == 288 and s["comparisons"] == 2, "sample")
    need(s["games_per_pair"] == 2 and s["loss_margin_logistic_elo"] == 100, "contrast")
    need(s["family_alpha"] == .05 and s["alpha_per_contrast"] == .025 and
         s["alpha_per_tail"] == .0125, "multiplicity")
    need(math.isclose(s["radius"], math.sqrt(math.log(80)/576), rel_tol=0, abs_tol=1e-15), "radius")
    need(math.isclose(s["score_boundary"], 1/(1+10**.25), rel_tol=0, abs_tol=1e-15), "loss_boundary")
    need(s["capped_game_bounds"] == [0, 1], "censoring")
    for key in ("historical_2069_enters_new_inference", "controls_enter_inference",
                "interim_inference_allowed", "optional_extension_allowed", "pool_across_models_allowed"):
        need(s[key] is False, key)
    b = c["budget"]
    need(b["main_games_total"] == 2 * 288 * 2, "main_games")
    need(b["readiness_games"] == 56 and b["new_games_total_max"] == 1208, "all_games")
    need(b["new_player_searches_total_max"] == 1208 * 162, "search_ceiling")
    need(b["automatic_retries"] == 0, "retry")
    for key in ("new_g0_probes", "new_scan_searches", "fits", "training_selfplay", "promotions", "bakes"):
        need(b[key] == 0, key)
    need(c["runtime"]["nominal_movetime_ms"] == 100 and c["runtime"]["response_ceiling_ms"] == 120, "clock")
    for source in c["sources"].values():
        for key, val in source.items():
            if key.endswith("sha256"):
                need(isinstance(val, str) and re.fullmatch(r"[0-9a-f]{64}", val) is not None, key)
            elif key in ("code_sha", "status_blob_sha", "blob_sha"):
                need(isinstance(val, str) and re.fullmatch(r"[0-9a-f]{40}", val) is not None, key)
    need(c["audit"]["must_precede_any_new_game"] is True, "audit_first")
    need(c["audit"]["raw_2069_roundtrip_required"] is True, "raw_audit")
    need(c["sources"]["historical_match"]["independently_raw_audited_here"] is False, "truthful_audit")
    need(c["audit"]["frozen_g0_redecision_allowed"] is False, "no_g0_redecision")
    need(c["panel_decision"]["needs_two_complete_valid_contrasts"] is True, "both_cells")
    need(all(value is True for value in c["forbidden"].values()), "forbidden")


def fixture_interval(lower: list[float], upper: list[float]) -> tuple[float, float]:
    """Synthetic paired bounds; deliberately independent of historical analyzers."""
    if len(lower) != 288 or len(upper) != 288:
        raise ValueError("complete_pair_sample_required")
    if not all(math.isfinite(a) and math.isfinite(b) and 0 <= a <= b <= 1
               for a, b in zip(lower, upper)):
        raise ValueError("invalid_pair_bounds")
    radius = math.sqrt(math.log(80)/576)
    return max(0, math.fsum(lower)/288-radius), min(1, math.fsum(upper)/288+radius)


def fixture_verdict(lo: float, hi: float) -> str:
    boundary = 1/(1+10**.25)
    if not 0 <= lo <= hi <= 1:
        raise ValueError("invalid_interval")
    return ("SUBSTANTIAL_LOSS_SUPPORTED" if hi < boundary else
            "SUBSTANTIAL_LOSS_EXCLUDED" if lo > boundary else "INDETERMINATE")


def fixture_joint(verdicts: dict[str, str], valid: bool = True) -> str:
    if not valid or set(verdicts) != {"LOCAL", "WDL"}:
        return "G0_PANEL_BLOCKED_NO_JOINT_VERDICT_V1"
    if not set(verdicts.values()) <= {"SUBSTANTIAL_LOSS_SUPPORTED", "SUBSTANTIAL_LOSS_EXCLUDED", "INDETERMINATE"}:
        raise ValueError("unknown_verdict")
    if "SUBSTANTIAL_LOSS_EXCLUDED" in verdicts.values():
        return "G0_PANEL_LARGE_LOSS_DISCORDANCE_REPLICATED_V1"
    if set(verdicts.values()) == {"SUBSTANTIAL_LOSS_SUPPORTED"}:
        return "G0_PANEL_LOSS_CONCORDANT_ON_TWO_CASES_V1"
    return "G0_PANEL_INDETERMINATE_V1"


class RejectionPanelContractTests(unittest.TestCase):
    def setUp(self):
        self.c = json.loads(CONTRACT.read_text(encoding="utf-8"))

    def test_contract_valid(self):
        validate_contract(self.c)

    def test_all_model_hashes_complete_and_in_document(self):
        text = DOC.read_text(encoding="utf-8")
        for sha in MODELS.values():
            self.assertRegex(sha, r"^[a-f0-9]{64}$")
            self.assertIn(sha, text)

    def test_closed_panel_cannot_substitute_hier(self):
        self.c["panel"]["confirmatory_contrasts"][0][0] = "HIER"
        with self.assertRaisesRegex(ValueError, "panel"):
            validate_contract(self.c)

    def test_model_mutation_rejected(self):
        self.c["models"]["LOCAL"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "models"):
            validate_contract(self.c)

    def test_launch_not_authorized_by_document(self):
        self.c["authorization"]["remote_launch_authorized"] = True
        with self.assertRaisesRegex(ValueError, "no_launch"):
            validate_contract(self.c)

    def test_history_and_controls_not_pooled(self):
        for key in ("historical_2069_enters_new_inference", "controls_enter_inference", "pool_across_models_allowed"):
            with self.subTest(key=key):
                c = copy.deepcopy(self.c)
                c["statistics"][key] = True
                with self.assertRaises(ValueError):
                    validate_contract(c)

    def test_alpha_not_reallocated(self):
        self.c["statistics"]["alpha_per_contrast"] = .05
        with self.assertRaisesRegex(ValueError, "multiplicity"):
            validate_contract(self.c)

    def test_loss_boundary_cannot_be_relaxed(self):
        self.c["statistics"]["score_boundary"] = .40
        with self.assertRaisesRegex(ValueError, "loss_boundary"):
            validate_contract(self.c)

    def test_sample_and_margin_fixed(self):
        self.c["statistics"]["pairs_per_contrast"] = 576
        with self.assertRaisesRegex(ValueError, "sample"):
            validate_contract(self.c)

    def test_no_automatic_retry_or_extra_compute(self):
        for key in ("automatic_retries", "new_g0_probes", "new_scan_searches", "fits", "promotions", "bakes"):
            with self.subTest(key=key):
                c = copy.deepcopy(self.c)
                c["budget"][key] = 1
                with self.assertRaises(ValueError):
                    validate_contract(c)

    def test_resource_arithmetic(self):
        b = self.c["budget"]
        self.assertEqual(b["main_games_total"] + b["readiness_games"], b["new_games_total_max"])
        self.assertEqual(b["main_player_searches_max"] + b["readiness_player_searches_max"], b["new_player_searches_total_max"])
        self.assertEqual(b["read_only_audit_stage_seconds"] + b["readiness_stage_seconds"] + 2*b["main_stage_seconds_per_contrast"], b["total_stage_seconds_max"])
        self.assertEqual(b["total_stage_seconds_max"]+4*b["dispatcher_overhead_seconds_per_stage"], b["total_dispatcher_seconds_max"])
        self.assertEqual(self.c["readiness"]["deterministic_games"] + self.c["readiness"]["timed_games"], 56)

    def test_opening_rule_and_exclusions_are_explicit(self):
        o = self.c["openings"]
        self.assertEqual((o["pool_seed"], o["order_seed"]), (2026092011, 2026092012))
        self.assertEqual((o["main_count"], o["representative_count"]), (288, 8))
        self.assertIn("2069_all_trajectories", o["exclusion_sources"])
        self.assertIn("2067_all_trajectories", o["exclusion_sources"])
        self.assertIn("all_2069_main_and_representative_starts", o["exclusion_sources"])
        for k in ("score_based_selection_allowed", "seed_retry_allowed", "replacement_allowed", "main_representative_trajectory_overlap_allowed", "all_training_disjointness_claimed"):
            self.assertIs(o[k], False)

    def test_raw_audit_mandatory_not_claimed_done(self):
        self.c["sources"]["historical_match"]["independently_raw_audited_here"] = True
        with self.assertRaisesRegex(ValueError, "truthful_audit"):
            validate_contract(self.c)

    def test_frozen_g0_never_redecided(self):
        self.c["audit"]["frozen_g0_redecision_allowed"] = True
        with self.assertRaisesRegex(ValueError, "no_g0_redecision"):
            validate_contract(self.c)

    def test_half_score_excludes_only_large_loss(self):
        lo, hi = fixture_interval([.5]*288, [.5]*288)
        self.assertAlmostEqual(lo, .4127779550248783)
        self.assertGreater(hi, .5)
        self.assertEqual(fixture_verdict(lo, hi), "SUBSTANTIAL_LOSS_EXCLUDED")

    def test_large_loss_fixture(self):
        self.assertEqual(fixture_verdict(*fixture_interval([.1]*288, [.1]*288)), "SUBSTANTIAL_LOSS_SUPPORTED")

    def test_equal_boundary_not_supported_or_excluded(self):
        b = 1/(1+10**.25)
        self.assertEqual(fixture_verdict(b, b), "INDETERMINATE")
        self.assertEqual(fixture_verdict(0, b), "INDETERMINATE")
        self.assertEqual(fixture_verdict(b, 1), "INDETERMINATE")

    def test_censoring_is_not_a_draw(self):
        lo, hi = fixture_interval([0]*288, [1]*288)
        self.assertEqual((lo, hi), (0, 1))
        self.assertEqual(fixture_verdict(lo, hi), "INDETERMINATE")

    def test_incomplete_or_invalid_pairs_rejected(self):
        for low, high in (([.5]*287, [.5]*287), ([.5]*288, [.4]*288), ([float("nan")]*288, [.5]*288)):
            with self.assertRaises(ValueError):
                fixture_interval(low, high)

    def test_joint_requires_both_cells(self):
        self.assertEqual(fixture_joint({"LOCAL": "SUBSTANTIAL_LOSS_EXCLUDED"}), "G0_PANEL_BLOCKED_NO_JOINT_VERDICT_V1")

    def test_joint_complete_outcomes(self):
        self.assertEqual(fixture_joint({"LOCAL": "SUBSTANTIAL_LOSS_EXCLUDED", "WDL": "INDETERMINATE"}), self.c["panel_decision"]["any_new_excluded"])
        self.assertEqual(fixture_joint({"LOCAL": "SUBSTANTIAL_LOSS_SUPPORTED", "WDL": "SUBSTANTIAL_LOSS_SUPPORTED"}), self.c["panel_decision"]["both_supported"])
        self.assertEqual(fixture_joint({"LOCAL": "SUBSTANTIAL_LOSS_SUPPORTED", "WDL": "INDETERMINATE"}), self.c["panel_decision"]["otherwise"])
        self.assertEqual(fixture_joint({"LOCAL": "INDETERMINATE", "WDL": "INDETERMINATE"}, valid=False), self.c["panel_decision"]["technical_or_incomplete"])

    def test_source_pin_typo_rejected(self):
        self.c["sources"]["valid_arms"]["receipt_sha256"] = "deadbeef"
        with self.assertRaisesRegex(ValueError, "receipt_sha256"):
            validate_contract(self.c)

    def test_no_general_accuracy_claim_or_v2_activation(self):
        self.assertIs(self.c["panel"]["general_gate_accuracy_estimable"], False)
        self.assertIs(self.c["forbidden"]["g0_v2_activation"], True)
        self.assertEqual(self.c["panel_decision"]["after_terminal"], "STOP_INTERPRET_NO_AUTO_G0_V2_NO_PROMOTION")


if __name__ == "__main__":
    unittest.main()
