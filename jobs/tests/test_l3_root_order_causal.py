import unittest

from jobs.tools.l3_root_order_causal_report import classify, paired_boolean
from jobs.tools.l3_root_order_oracle import schedule_from_events


class RootOrderCausalTests(unittest.TestCase):
    def test_schedule_uses_final_attempt_at_each_depth(self):
        events = []
        for depth in range(1, 4):
            for attempt, move in ((1, "31-26"), (2, "31-27")):
                events.extend(
                    [
                        {
                            "event": "begin",
                            "depth": depth,
                            "attempt": attempt,
                        },
                        {
                            "event": "move",
                            "depth": depth,
                            "attempt": attempt,
                            "move": move,
                        },
                        {
                            "event": "end",
                            "depth": depth,
                            "attempt": attempt,
                        },
                    ]
                )
        self.assertEqual(
            schedule_from_events(events, 3),
            "1:31-27;2:31-27;3:31-27",
        )

    def test_paired_boolean_detects_improvement(self):
        result = paired_boolean(
            [True] * 20,
            [False] * 10 + [True] * 10,
            seed=1,
            samples=10000,
        )
        self.assertEqual(result["delta"], 0.5)
        self.assertGreater(result["ci_low"], 0)

    def test_classification_prefers_conversion_recovery(self):
        conversion = {
            "p3": {
                "root_order": {"ci_low": 0.82},
                "paired": {"delta": 0.3, "ci_low": 0.2},
            },
            "p4": {
                "root_order": {"ci_low": 0.81},
                "paired": {"delta": 0.3, "ci_low": 0.2},
            },
        }
        verdict = classify(
            order_contract=True,
            root_paired={"delta": 0.2, "ci_low": 0.1},
            conversion=conversion,
        )
        self.assertEqual(verdict, "ROOT_ORDER_REPLAY_RECOVERS_CONVERSION")

    def test_root_only_gain_does_not_claim_conversion(self):
        conversion = {
            key: {
                "root_order": {"ci_low": 0.3},
                "paired": {"delta": 0.02, "ci_low": -0.03},
            }
            for key in ("p3", "p4")
        }
        verdict = classify(
            order_contract=True,
            root_paired={"delta": 0.2, "ci_low": 0.05},
            conversion=conversion,
        )
        self.assertEqual(
            verdict, "ROOT_ORDER_EXPLAINS_ROOT_CHOICE_NOT_CONVERSION"
        )


if __name__ == "__main__":
    unittest.main()
