import unittest

from jobs.tools.scan_static_parity import compare_scores, parse_scan_output


class ScanStaticParityTests(unittest.TestCase):
    def test_probe_output_ignores_init_noise_and_is_ordered(self):
        output = "init eval\nEVAL\t0\t17\nEVAL\t1\t-3\n"
        self.assertEqual(parse_scan_output(output, 2), [17, -3])

    def test_comparison_reports_exact_and_mismatch_rows(self):
        result = compare_scores(
            ["W:W1:B50", "B:W1:B50"],
            [10, -4],
            [10, -3],
        )
        self.assertEqual(result["exact_matches"], 1)
        self.assertEqual(result["mismatches"], 1)
        self.assertEqual(result["max_abs_delta"], 1)
        self.assertEqual(
            result["mismatch_examples"][0]["delta_jass_minus_scan"], 1
        )


if __name__ == "__main__":
    unittest.main()
