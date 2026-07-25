import unittest

from jobs.tools.l3_scan_gap_causal import classify


def row(rate, low, high):
    return {"conversion": rate, "ci_low": low, "ci_high": high}


class ScanGapCausalTests(unittest.TestCase):
    def test_eval_dominant_when_exact_d10_is_supported(self):
        conversion = {
            "SCAN_EXACT_D10": {
                "p3": row(0.92, 0.88, 0.95),
                "p4": row(0.91, 0.87, 0.94),
            },
            "SCAN_EXACT_D12": {
                "p3": row(0.94, 0.90, 0.96),
                "p4": row(0.93, 0.89, 0.95),
            },
        }
        comparisons = {
            "p3": {"SCAN_EXACT_D12_vs_D10": {"ci_low": -0.01}},
            "p4": {"SCAN_EXACT_D12_vs_D10": {"ci_low": -0.01}},
        }
        result = classify(conversion, comparisons, ["p3", "p4"])
        self.assertEqual(result["verdict"], "EVAL_WEIGHTS_DOMINANT")

    def test_search_implementation_when_exact_d12_stays_below_floor(self):
        conversion = {
            "SCAN_EXACT_D10": {
                "p3": row(0.40, 0.35, 0.46),
                "p4": row(0.38, 0.33, 0.44),
            },
            "SCAN_EXACT_D12": {
                "p3": row(0.46, 0.40, 0.52),
                "p4": row(0.44, 0.38, 0.50),
            },
        }
        comparisons = {
            "p3": {"SCAN_EXACT_D12_vs_D10": {"ci_low": 0.01}},
            "p4": {"SCAN_EXACT_D12_vs_D10": {"ci_low": 0.00}},
        }
        result = classify(conversion, comparisons, ["p3", "p4"])
        self.assertEqual(result["verdict"], "SEARCH_IMPLEMENTATION_DOMINANT")


if __name__ == "__main__":
    unittest.main()
