from array import array
import unittest

from jobs.tools.scan_exact_eval_port import (
    BUCKETS,
    E_BK_DENIED,
    E_BK_EXTRA_KING,
    E_BK_HAS_KING,
    E_BK_PST,
    E_BK_SAFE,
    E_BK_SKEW,
    E_BLACK_MEN,
    E_WK_DENIED,
    E_WK_EXTRA_KING,
    E_WK_HAS_KING,
    E_WK_PST,
    E_WK_SAFE,
    E_WK_SKEW,
    E_WHITE_MEN,
    SCAN_PARAMETERS,
    bucket_map,
    decode_scan_int16,
    map_extras,
    pattern_contracts,
)


class ScanExactEvalPortTests(unittest.TestCase):
    def test_scan_payload_is_big_endian_int16(self):
        self.assertEqual(list(decode_scan_int16(b"\x00\x01\xff\xfe")), [1, -2])

    def test_8cf_contracts_cover_four_tables_and_two_halves(self):
        contracts = pattern_contracts()
        self.assertEqual(len(contracts), 8)
        self.assertEqual(
            [contract["scan_table"] for contract in contracts],
            [0, 1, 2, 3, 3, 2, 1, 0],
        )
        self.assertEqual(
            [contract["sign_scan_to_black_pov"] for contract in contracts],
            [-1, -1, -1, -1, 1, 1, 1, 1],
        )
        for contract in contracts:
            self.assertEqual(sorted(contract["exponents"]), list(range(12)))

    def test_bucket_digit_conventions(self):
        identity_exponents = tuple(range(12))
        top = bucket_map(identity_exponents, (1, 2, 0))
        bottom = bucket_map(identity_exponents, (1, 0, 2))
        empty_bucket = 0
        all_black = (BUCKETS - 1) // 2
        all_white = BUCKETS - 1

        self.assertEqual(top[empty_bucket], all_black)
        self.assertEqual(top[all_black], all_white)
        self.assertEqual(top[all_white], 0)
        self.assertEqual(bottom[empty_bucket], all_black)
        self.assertEqual(bottom[all_black], 0)
        self.assertEqual(bottom[all_white], all_white)

    def test_dense_features_are_sign_and_square_mapped(self):
        raw = array("h", [0]) * (SCAN_PARAMETERS * 2)
        for var in range(56):
            raw[var * 2 + 0] = var + 1
            raw[var * 2 + 1] = -(var + 1)

        mg = map_extras(raw, 0, 120)
        eg = map_extras(raw, 1, 120)

        self.assertEqual(mg[E_BLACK_MEN], 1)
        self.assertEqual(mg[E_WHITE_MEN], -1)
        self.assertEqual(mg[E_BK_HAS_KING], 2)
        self.assertEqual(mg[E_WK_HAS_KING], -2)
        self.assertEqual(mg[E_BK_EXTRA_KING], 3)
        self.assertEqual(mg[E_WK_EXTRA_KING], -3)
        self.assertEqual(mg[E_BK_PST + 0], 53)
        self.assertEqual(mg[E_BK_PST + 49], 4)
        self.assertEqual(mg[E_WK_PST + 0], -4)
        self.assertEqual(mg[E_WK_PST + 49], -53)
        self.assertEqual(mg[E_BK_SAFE], 54)
        self.assertEqual(mg[E_WK_SAFE], -54)
        self.assertEqual(mg[E_BK_DENIED], 55)
        self.assertEqual(mg[E_WK_DENIED], -55)
        self.assertEqual(mg[E_BK_SKEW], 56)
        self.assertEqual(mg[E_WK_SKEW], -56)

        self.assertEqual(eg[E_BLACK_MEN], -1)
        self.assertEqual(eg[E_WHITE_MEN], 1)


if __name__ == "__main__":
    unittest.main()
