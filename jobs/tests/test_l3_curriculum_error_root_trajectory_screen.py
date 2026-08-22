from __future__ import annotations

import unittest

from jobs.tools import l3_curriculum_error_root_trajectory_screen as screen


A = "1-2"
B = "3-4"
IA = "50-49"
IB = "48-47"


def profile(pair_id: int, *, margin_large: bool = False) -> dict:
    a9 = 100.0 if margin_large else 10.0
    b9 = 0.0 if margin_large else 9.0
    return {
        "source": {
            "opening_id": f"opening-{pair_id}",
            "exact_state_key": f"state-{pair_id}",
        },
        "trace": {
            "original": {"depths": {
                "8": {"moves": [{"action": A, "score": a9}, {"action": B, "score": 0.0}]},
                "9": {"moves": [{"action": A, "score": a9}, {"action": B, "score": b9}]},
            }},
            "exact_image": {"depths": {
                "8": {"moves": [{"action": IA, "score": a9}, {"action": IB, "score": 0.0}]},
                "9": {"moves": [{"action": IA, "score": a9}, {"action": IB, "score": b9}]},
            }},
        },
    }


def judged(teacher: str) -> dict:
    return {
        "exact_teacher_action": teacher,
        "action_values": {
            A: {"root_cp": 0.0},
            B: {"root_cp": 100.0},
        },
    }


def pair(pair_id: int) -> dict:
    return {
        "pair_id": pair_id,
        "error": {"profile": profile(pair_id), "judged": judged(B)},
        "control": {"profile": profile(1000 + pair_id, margin_large=True), "judged": judged(A)},
    }


class CurriculumErrorRootTrajectoryScreenTests(unittest.TestCase):
    def test_extrapolation_can_promote_rising_action(self) -> None:
        choice = screen._choice(profile(0), beta=1.0, margin_cp=20.0, image=False)
        self.assertEqual(choice["baseline"], A)
        self.assertEqual(choice["proposed"], B)
        self.assertEqual(choice["chosen"], B)
        self.assertTrue(choice["changed"])

    def test_uncertainty_band_abstains_on_large_margin(self) -> None:
        choice = screen._choice(profile(0, margin_large=True), beta=1.0, margin_cp=20.0, image=False)
        self.assertEqual(choice["baseline"], A)
        self.assertEqual(choice["chosen"], A)
        self.assertFalse(choice["changed"])

    def test_exact_image_action_mapping_is_equivariant(self) -> None:
        original = screen._choice(profile(0), beta=1.0, margin_cp=20.0, image=False)
        image = screen._choice(profile(0), beta=1.0, margin_cp=20.0, image=True)
        self.assertEqual(original["chosen"], image["chosen"])
        self.assertEqual(image["chosen"], B)

    def test_decision_improves_teacher_margin_without_new_search(self) -> None:
        result = screen._decision(pair(0)["error"], beta=1.0, margin_cp=20.0)
        self.assertEqual(result["improvement_cp"], 100.0)
        self.assertEqual(result["candidate_teacher_hit"], 1.0)
        self.assertTrue(result["candidate_exact_image_agreement"])

    def test_paired_evaluation_rewards_errors_and_abstains_on_controls(self) -> None:
        result = screen._evaluate(
            [pair(index) for index in range(32)], beta=1.0, margin_cp=20.0,
            bootstrap_samples=1000, bootstrap_seed=7,
        )
        self.assertEqual(result["error_improvement"]["mean"], 100.0)
        self.assertEqual(result["control_improvement"]["mean"], 0.0)
        self.assertEqual(result["paired_error_minus_control"]["mean"], 100.0)
        self.assertEqual(result["error_changed_pairs"], 32)
        self.assertEqual(result["control_changed_pairs"], 0)
        self.assertEqual(result["depth8_missing_action_fraction"], 0.0)

    def test_component_split_keeps_shared_exact_state_atomic(self) -> None:
        rows = [pair(index) for index in range(160)]
        rows[1]["error"]["profile"]["source"]["exact_state_key"] = rows[0]["control"]["profile"]["source"]["exact_state_key"]
        fit, validation, audit = screen._inner_split(rows, seed=2026082228)
        side = {row["pair_id"]: "fit" for row in fit} | {
            row["pair_id"]: "validation" for row in validation
        }
        self.assertEqual(side[0], side[1])
        self.assertEqual(audit["overlap"], 0)
        self.assertGreaterEqual(len(validation), 24)

    def test_fixed_candidate_family_is_small_and_preregistered(self) -> None:
        self.assertEqual(screen.BETAS, (0.25, 0.5, 1.0))
        self.assertEqual(screen.MARGINS_CP, (20.0, 50.0, 100.0, 1_000_000.0))
        self.assertEqual(len(screen.BETAS) * len(screen.MARGINS_CP), 12)


if __name__ == "__main__":
    unittest.main()
