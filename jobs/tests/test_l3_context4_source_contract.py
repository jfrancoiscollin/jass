#!/usr/bin/env python3
import unittest

from jobs.tools.l3_context4_source_contract import validate_1428_force_summary


class Context4SourceContractTests(unittest.TestCase):
    def test_certified_nested_protocol_scope_passes(self):
        validate_1428_force_summary(
            {
                "verdict": "JASS_CONTEXT3_ALIGNED_VS_SHUFFLED_NOT_ESTABLISHED",
                "protocol": {
                    "fits": {"count": 0},
                    "new_selfplay": {"generated": 0},
                    "frozen_cohorts": {"read": 0},
                    "models_reused": True,
                },
            }
        )

    def test_obsolete_top_level_scope_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "protocol scope missing"):
            validate_1428_force_summary(
                {
                    "verdict": "JASS_CONTEXT3_ALIGNED_VS_SHUFFLED_NOT_ESTABLISHED",
                    "refits": 0,
                    "new_selfplay": 0,
                    "frozen_cohorts_read": 0,
                    "models_reused": True,
                }
            )

    def test_nested_scope_fails_closed_on_guard_drift(self):
        base = {
            "verdict": "JASS_CONTEXT3_ALIGNED_VS_SHUFFLED_NOT_ESTABLISHED",
            "protocol": {
                "fits": {"count": 0},
                "new_selfplay": {"generated": 0},
                "frozen_cohorts": {"read": 0},
                "models_reused": True,
            },
        }
        cases = (
            ("fits", {"count": 1}, "unexpectedly refit"),
            ("new_selfplay", {"generated": 1}, "unexpectedly self-played"),
            ("frozen_cohorts", {"read": 1}, "frozen-read contract"),
            ("models_reused", False, "model-reuse contract"),
        )
        for key, value, message in cases:
            payload = {**base, "protocol": dict(base["protocol"])}
            payload["protocol"][key] = value
            with self.subTest(key=key):
                with self.assertRaisesRegex(ValueError, message):
                    validate_1428_force_summary(payload)


if __name__ == "__main__":
    unittest.main()
