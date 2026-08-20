#!/usr/bin/env python3
import unittest

from jobs.tools.l3_context4_source_contract import (
    pool_certificate_canonical_fingerprint,
    validate_1428_force_readout,
    validate_1428_force_summary,
    validate_1428_pool_certificate,
    validate_equivalent_1428_pool_certificates,
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

    @staticmethod
    def _pool_certificate():
        exclusions = [
            {"label": f"historical-{i}"} for i in range(15)
        ] + [
            {"label": "pool-context3-1419-force-pool1"},
            {"label": "pool-context3-1419-force-pool2"},
        ]
        return {
            "schema": "jass.context3.two_fresh_pools.v1",
            "verdict": "JASS_CONTEXT3_TWO_FRESH_POOLS_READY",
            "pools": [
                {"seed": 2026082001, "openings": 3000},
                {"seed": 2026082002, "openings": 3000},
            ],
            "mutually_disjoint": True,
            "mutual_overlap": 0,
            "historical_exclusions": exclusions,
            "historical_exclusion_count": 17,
            "all_historical_overlaps_zero": True,
            "deterministic_generation_repeated": True,
            "promotion_authorized": False,
        }

    def test_certified_pool_certificate_passes(self):
        validate_1428_pool_certificate(self._pool_certificate())

    def test_pool_certificate_fails_closed_on_contract_drift(self):
        cases = (
            ("historical_exclusion_count", 16, "exclusion count drift"),
            ("mutually_disjoint", False, "disjointness drift"),
            ("deterministic_generation_repeated", False, "deterministic-generation drift"),
            ("promotion_authorized", True, "promotion scope drift"),
        )
        for key, value, message in cases:
            payload = self._pool_certificate()
            payload[key] = value
            with self.subTest(key=key):
                with self.assertRaisesRegex(ValueError, message):
                    validate_1428_pool_certificate(payload)

        payload = self._pool_certificate()
        payload["pools"][1]["seed"] = 2026082003
        with self.assertRaisesRegex(ValueError, "fresh pool seed drift"):
            validate_1428_pool_certificate(payload)

        payload = self._pool_certificate()
        payload["historical_exclusions"][-1] = {"label": "wrong"}
        with self.assertRaisesRegex(ValueError, "missing 1419 pool exclusions"):
            validate_1428_pool_certificate(payload)

    def test_pool_canonical_fingerprint_is_order_independent_only(self):
        direct = self._pool_certificate()
        direct["pools"][0].update({"sha256": "a" * 64, "pool_id": "fresh-1"})
        # Reinsert top-level and pool keys in reverse order: same JSON values,
        # different mapping insertion order. Canonical fingerprint must match.
        embedded = {key: direct[key] for key in reversed(list(direct.keys()))}
        embedded["pools"] = [
            {key: item[key] for key in reversed(list(item.keys()))}
            for item in direct["pools"]
        ]
        self.assertEqual(
            pool_certificate_canonical_fingerprint(direct),
            pool_certificate_canonical_fingerprint(embedded),
        )
        validate_equivalent_1428_pool_certificates(direct, embedded)

    def test_pool_canonical_fingerprint_fails_closed_on_hash_identity_or_metadata_drift(self):
        cases = (
            ("sha256", "a" * 64, "b" * 64),
            ("pool_id", "fresh-1", "fresh-X"),
            ("path", "/tmp/direct.fen", "/tmp/embedded.fen"),
        )
        for key, left, right in cases:
            direct = self._pool_certificate()
            embedded = self._pool_certificate()
            direct["pools"][0][key] = left
            embedded["pools"][0][key] = right
            with self.subTest(key=key):
                with self.assertRaisesRegex(ValueError, "canonical fingerprint drift"):
                    validate_equivalent_1428_pool_certificates(direct, embedded)

    def test_pool_canonical_fingerprint_fails_closed_on_exclusion_receipt_drift(self):
        direct = self._pool_certificate()
        embedded = self._pool_certificate()
        embedded["historical_exclusions"][0] = {"label": "different-history"}
        with self.assertRaisesRegex(ValueError, "canonical fingerprint drift"):
            validate_equivalent_1428_pool_certificates(direct, embedded)

    def test_pool_equivalence_still_rejects_seed_count_and_overlap_drift(self):
        mutations = (
            (lambda p: p["pools"][0].__setitem__("seed", 2026082999), "seed drift"),
            (lambda p: p["pools"][0].__setitem__("openings", 2999), "cardinality drift"),
            (lambda p: p.__setitem__("mutual_overlap", 1), "disjointness drift"),
        )
        for mutate, message in mutations:
            direct = self._pool_certificate()
            embedded = self._pool_certificate()
            mutate(embedded)
            with self.subTest(message=message):
                with self.assertRaisesRegex(ValueError, message):
                    validate_equivalent_1428_pool_certificates(direct, embedded)


if __name__ == "__main__":
    unittest.main()
