#!/usr/bin/env python3
import unittest

from jobs.tools.l3_context4_source_contract import (
    validate_1428_force_readout,
    validate_1428_force_summary,
)


class Context4SourceContractTests(unittest.TestCase):
    def test_certified_nested_runner_protocol_scope_passes(self):
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

    def test_obsolete_top_level_runner_scope_is_rejected(self):
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

    def test_nested_runner_scope_fails_closed_on_guard_drift(self):
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

    @staticmethod
    def _scientific_readout():
        return {
            "schema": "jass.l3_context3_two_pool_force_readout.v1",
            "verdict": "JASS_CONTEXT3_ALIGNED_VS_SHUFFLED_NOT_ESTABLISHED",
            "protocol": {
                "models_reused": True,
                "refits": 0,
                "new_selfplay": 0,
                "frozen_cohorts_read": 0,
            },
            "promotion_authorized": False,
            "automatic_next_job": None,
        }

    def test_certified_scientific_readout_promotion_scope_passes(self):
        validate_1428_force_readout(self._scientific_readout())

    def test_runner_wrapper_is_not_accepted_as_scientific_readout(self):
        runner = {
            "verdict": "JASS_CONTEXT3_ALIGNED_VS_SHUFFLED_NOT_ESTABLISHED",
            "protocol": {
                "fits": {"count": 0},
                "new_selfplay": {"generated": 0},
                "frozen_cohorts": {"read": 0},
                "models_reused": True,
            },
        }
        with self.assertRaisesRegex(ValueError, "scientific readout schema drift"):
            validate_1428_force_readout(runner)

    def test_scientific_readout_fails_closed_on_scope_drift(self):
        cases = (
            ("promotion_authorized", True, "promotion scope drift"),
            ("automatic_next_job", "forbidden", "continuation scope drift"),
        )
        for key, value, message in cases:
            payload = self._scientific_readout()
            payload[key] = value
            with self.subTest(key=key):
                with self.assertRaisesRegex(ValueError, message):
                    validate_1428_force_readout(payload)

        protocol_cases = (
            ("models_reused", False, "model-reuse contract"),
            ("refits", 1, "unexpectedly refit"),
            ("new_selfplay", 1, "unexpectedly self-played"),
            ("frozen_cohorts_read", 1, "frozen-read contract"),
        )
        for key, value, message in protocol_cases:
            payload = self._scientific_readout()
            payload["protocol"][key] = value
            with self.subTest(key=key):
                with self.assertRaisesRegex(ValueError, message):
                    validate_1428_force_readout(payload)


if __name__ == "__main__":
    unittest.main()
