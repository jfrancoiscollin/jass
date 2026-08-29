import unittest

from jobs.tools.search_semantics_attribution_variants import (
    ARM_ORDER,
    OVERRIDES,
    build_manifest,
)


class SearchSemanticsAttributionTests(unittest.TestCase):
    def test_preregistered_arms_are_single_and_disjoint(self):
        manifest = build_manifest("a" * 40, "b" * 64)
        self.assertEqual(tuple(manifest["arm_order"]), ARM_ORDER)
        self.assertEqual(manifest["axis_count"], 6)
        self.assertEqual(manifest["arms"]["J0"]["changed_keys"], [])
        changed = []
        for arm in ARM_ORDER[1:]:
            keys = set(OVERRIDES[arm])
            self.assertTrue(keys)
            self.assertTrue(keys.isdisjoint(set().union(*changed)) if changed else True)
            changed.append(keys)

    def test_exact_axis_contract(self):
        self.assertEqual(OVERRIDES["J1_SCAN_VERIFY"], {"scan_verify_pruning": 1})
        self.assertEqual(OVERRIDES["J2_SCAN_THREAT_REENTRY"], {
            "qs_threat_ext": 0, "scan_threat_reentry": 1,
        })
        self.assertEqual(OVERRIDES["J3_SCAN_SINGLE_REPLY"], {"ext_single_reply": 1})
        self.assertEqual(OVERRIDES["J4_SCAN_LMR"], {"scan_lmr_semantics": 1})
        self.assertEqual(OVERRIDES["J5_SCAN_ORDERING"], {
            "scan_probabilistic_ordering": 1,
        })
        self.assertEqual(OVERRIDES["J6_NO_NULL_MOVE"], {"disable_null_move": 1})

    def test_no_training_or_promotion_authority(self):
        manifest = build_manifest("c" * 40, "d" * 64)
        self.assertFalse(manifest["training_allowed"])
        self.assertFalse(manifest["tuning_allowed"])
        self.assertEqual(manifest["strength_games"], 0)
        self.assertFalse(manifest["bake"])
        self.assertFalse(manifest["promotion"])


if __name__ == "__main__":
    unittest.main()

