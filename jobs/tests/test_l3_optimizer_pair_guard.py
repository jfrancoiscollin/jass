import unittest

from jobs.tools.l3_optimizer_pair_guard import decide


def report(*, iterations, gradient, success=True, status=0, gtol=1e-3):
    return {
        "success": success,
        "status": status,
        "message": "CONVERGENCE: NORM_OF_PROJECTED_GRADIENT_<=_PGTOL",
        "iterations": iterations,
        "function_evaluations": iterations + 2,
        "gradient_inf_norm": gradient,
        "gtol": gtol,
    }


class OptimizerPairGuardTest(unittest.TestCase):
    def test_1155_shape_is_blocked_by_iteration_asymmetry(self):
        result = decide(
            report(iterations=141, gradient=0.000548),
            report(iterations=12, gradient=0.000913),
            expected_gtol=1e-3,
        )
        self.assertEqual(result["verdict"], "OPTIMIZER_PAIR_ASYMMETRY_BLOCK")
        self.assertTrue(result["diagnostics"]["iteration_asymmetry"])
        self.assertAlmostEqual(result["diagnostics"]["iteration_ratio"], 141 / 12)
        self.assertTrue(result["diagnostics"]["gradient_to_gtol_is_diagnostic_only"])
        self.assertFalse(result["gate_authorized"])

    def test_balanced_convergence_passes(self):
        result = decide(
            report(iterations=100, gradient=4.0e-5, gtol=1e-4),
            report(iterations=120, gradient=5.0e-5, gtol=1e-4),
            expected_gtol=1e-4,
        )
        self.assertEqual(result["verdict"], "OPTIMIZER_PAIR_VALID")
        self.assertTrue(result["pair_valid"])

    def test_gradient_surface_asymmetry_does_not_decide(self):
        result = decide(
            report(iterations=100, gradient=9.7e-5, gtol=1e-4),
            report(iterations=126, gradient=1.0e-5, gtol=1e-4),
            expected_gtol=1e-4,
        )
        self.assertTrue(result["pair_valid"])

    def test_iteration_limit_is_inclusive(self):
        iteration_boundary = decide(
            report(iterations=10, gradient=4e-5, gtol=1e-4),
            report(iterations=50, gradient=4e-5, gtol=1e-4),
            expected_gtol=1e-4,
        )
        self.assertTrue(iteration_boundary["diagnostics"]["iteration_asymmetry"])
        self.assertFalse(iteration_boundary["pair_valid"])

    def test_individual_success_is_still_required(self):
        result = decide(
            report(iterations=20, gradient=2e-5, success=False, status=1, gtol=1e-4),
            report(iterations=20, gradient=2e-5, gtol=1e-4),
            expected_gtol=1e-4,
        )
        self.assertEqual(result["verdict"], "OPTIMIZER_PAIR_INVALID_ARM")


if __name__ == "__main__":
    unittest.main()
