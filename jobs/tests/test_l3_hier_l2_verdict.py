import unittest

from jobs.tools.l3_hier_l2_verdict import decide


def gate(q00, native):
    def view(counts):
        wins, draws, losses = counts
        return {"wins_a": wins, "draws": draws, "wins_b": losses,
                "n": wins + draws + losses}

    q = view(q00)
    n = view(native)
    return {
        "arms": {"a": "HIER", "b": "CONTROL"},
        "per_view": {"q00": q, "native": n},
        "views_summed": {
            "wins_a": q["wins_a"] + n["wins_a"],
            "draws": q["draws"] + n["draws"],
            "wins_b": q["wins_b"] + n["wins_b"],
            "n": q["n"] + n["n"],
        },
    }


class HierL2VerdictTest(unittest.TestCase):
    def test_reopens_only_when_ci_and_both_view_directions_pass(self):
        result = decide(gate((3200, 400, 2400), (3150, 400, 2450)))
        self.assertEqual(result["verdict"], "HIER_L2_REOPEN_FOR_PRIOR_COMBINATION")
        self.assertTrue(result["prior_hier_experiment_authorized"])
        self.assertFalse(result["promotion_authorized"])
        self.assertIsNone(result["automatic_next_job"])

    def test_positive_combined_but_contradictory_view_closes(self):
        result = decide(gate((3600, 300, 2100), (2700, 300, 3000)))
        self.assertEqual(result["verdict"], "HIER_L2_NO_ESTABLISHED_GAIN_CLOSE")
        self.assertFalse(result["same_positive_direction"])

    def test_established_regression_is_distinct(self):
        result = decide(gate((2400, 400, 3200), (2450, 400, 3150)))
        self.assertEqual(result["verdict"], "HIER_L2_REGRESSION_ESTABLISHED")

    def test_wrong_schema_or_sizing_fails_closed(self):
        payload = gate((3200, 400, 2400), (3150, 400, 2450))
        payload["per_view"]["q00"]["n"] -= 1
        with self.assertRaisesRegex(ValueError, "inconsistent raw counts"):
            decide(payload)

        payload = gate((3200, 400, 2400), (3150, 400, 2450))
        payload["views_summed"]["wins_a"] -= 1
        payload["views_summed"]["wins_b"] += 1
        with self.assertRaisesRegex(ValueError, "round-trip"):
            decide(payload)

        payload = gate((3200, 400, 2400), (3150, 400, 2450))
        payload["arms"] = {"a": "CONTROL", "b": "HIER"}
        with self.assertRaisesRegex(ValueError, "A=HIER"):
            decide(payload)


if __name__ == "__main__":
    unittest.main()
