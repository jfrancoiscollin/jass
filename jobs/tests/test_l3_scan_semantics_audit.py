import unittest

from jobs.tests.test_l3_search_tree_audit import Q00
from jobs.tools.l3_scan_semantics_report import classify
from jobs.tools.l3_scan_semantics_variants import VARIANT_ORDER, build_manifest


class ScanSemanticsAuditTests(unittest.TestCase):
    def test_ladder_appends_only_diagnostic_switches(self):
        manifest = build_manifest(Q00)
        self.assertEqual(tuple(manifest["variant_order"]), VARIANT_ORDER)
        self.assertEqual(manifest["base"]["source_key_count"], 63)
        self.assertEqual(manifest["base"]["resolved_key_count"], 65)
        for arm in manifest["arms"].values():
            self.assertEqual(arm["key_count"], 65)
            self.assertEqual(len(arm["search_params"].split(",")), 65)
        self.assertEqual(
            manifest["arms"]["SCAN_CORE"]["overrides"]["scan_verify_pruning"], 0
        )
        self.assertEqual(
            manifest["arms"]["SCAN_VERIFY"]["overrides"]["scan_verify_pruning"], 1
        )
        threat = manifest["arms"]["SCAN_VERIFY_THREAT"]["overrides"]
        self.assertEqual(threat["scan_threat_reentry"], 1)
        self.assertEqual(threat["qs_threat_ext"], 0)

    def test_classification_localizes_verification(self):
        strata = ["p3", "p4"]
        conversion = {}
        paired = {}
        for depth in ("10", "12"):
            conversion[depth] = {
                arm: {
                    stratum: {
                        "conversion": 0.55 if arm == "SCAN_VERIFY" else 0.40,
                        "ci_low": 0.45,
                        "ci_high": 0.65,
                    }
                    for stratum in strata
                }
                for arm in VARIANT_ORDER
            }
            paired[depth] = {
                stratum: {
                    "SCAN_VERIFY_vs_SCAN_CORE": {
                        "delta": 0.15,
                        "ci_low": 0.04,
                    },
                    "SCAN_VERIFY_THREAT_vs_SCAN_CORE": {
                        "delta": 0.01,
                        "ci_low": -0.05,
                    },
                }
                for stratum in strata
            }
        result = classify(conversion, paired, strata)
        self.assertEqual(result["verdict"], "SCAN_VERIFICATION_PRUNING_DOMINANT")
        self.assertEqual(result["localized_arm"], "SCAN_VERIFY")
        self.assertEqual(result["localized_depth"], 10)

    def test_classification_requires_internal_instrumentation_when_flat(self):
        strata = ["p3", "p4"]
        conversion = {
            depth: {
                arm: {
                    stratum: {
                        "conversion": 0.40,
                        "ci_low": 0.34,
                        "ci_high": 0.46,
                    }
                    for stratum in strata
                }
                for arm in VARIANT_ORDER
            }
            for depth in ("10", "12")
        }
        paired = {
            depth: {
                stratum: {
                    f"{arm}_vs_SCAN_CORE": {
                        "delta": 0.0,
                        "ci_low": -0.06,
                    }
                    for arm in ("SCAN_VERIFY", "SCAN_VERIFY_THREAT")
                }
                for stratum in strata
            }
            for depth in ("10", "12")
        }
        result = classify(conversion, paired, strata)
        self.assertEqual(result["verdict"], "SCAN_INTERNAL_NODE_SEMANTICS_REQUIRED")
        self.assertIsNone(result["localized_arm"])


if __name__ == "__main__":
    unittest.main()
