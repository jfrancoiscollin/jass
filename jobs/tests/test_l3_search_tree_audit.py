import struct
import unittest

from jobs.tools.l3_search_tree_report import classify
from jobs.tools.l3_search_tree_select import select_stratum
from jobs.tools.l3_search_variants import VARIANT_ORDER, build_manifest


Q00 = (
    "rfp_max_depth=5,rfp_margin=100,nmp_min_depth=4,nmp_min_pieces=6,"
    "nmp_r_base=2,nmp_r_div=4,singular_min_depth=8,singular_margin=2,"
    "lmr_min_depth=3,lmr_first_full_moves=4,lmr_first_full_pv=4,"
    "lmr_first_full_nonpv=2,lmr_base=0,lmr_depth_div=6,lmr_idx_div=8,"
    "lmr_hist_div=0,lmr_formula=0,lmr_log_base=0,lmr_log_mul=40,"
    "lmr_bc_ld=100,lmr_bc_lidx=100,lmp_d1=4,lmp_d2=8,lmp_d3=14,"
    "lmp_max_depth=3,history_max=16384,hist_malus=0,hist_mode=1,"
    "prob_shift=5,hist_pure=1,hist_order_captures=0,"
    "aspiration_initial=50,use_pvs=1,razor_max_depth=4,razor_margin=200,"
    "probcut_min_depth=5,probcut_margin=150,probcut_reduction=4,"
    "ext_promotion=0,ext_forcing=0,forcing_ext_cap=0,ext_single_reply=0,"
    "use_improving=1,use_conthist=1,iid_min_depth=0,iid_reduction=2,"
    "no_reduce_forcing=0,qs_forcing_depth=0,qs_promo_depth=0,"
    "qs_threat_ext=1,qs_sacs=1,qs_sacs_depth0_only=1,"
    "multicut_min_depth=4,multicut_reduction=4,multicut_moves=8,"
    "multicut_cuts=2,tm_next_iter_pct=200,tm_min_depth=5,"
    "drawish_scaling=0,eg_pieces=40,eg_no_nmp=0,eg_no_lmp=0,eg_no_lmr=0"
)


def record(side: str, index: int) -> bytes:
    stm = 0
    wdl = 1 if side == "W" else -1
    wm = 1 << (index % 20)
    bm = 1 << (25 + index % 20)
    return struct.pack("<QQQQBib", wm, 0, bm, 0, stm, 0, wdl)


class SearchTreeAuditTests(unittest.TestCase):
    def test_variant_ladder_is_fully_resolved_and_preregistered(self):
        manifest = build_manifest(Q00)
        self.assertEqual(tuple(manifest["variant_order"]), VARIANT_ORDER)
        self.assertEqual(manifest["base"]["key_count"], 63)
        for arm in manifest["arms"].values():
            self.assertEqual(arm["key_count"], 63)
            self.assertEqual(len(arm["search_params"].split(",")), 63)
        self.assertEqual(
            manifest["arms"]["NO_FORWARD"]["overrides"]["nmp_min_depth"], 99
        )
        self.assertEqual(
            manifest["arms"]["SCAN_EXT_QS"]["overrides"]["ext_single_reply"], 1
        )
        self.assertEqual(
            manifest["arms"]["SCAN_LMR"]["overrides"]["lmr_formula"], 3
        )
        self.assertEqual(
            manifest["arms"]["FULL_WIDTH"]["overrides"]["use_pvs"], 0
        )

    def test_balanced_sentinel_selection(self):
        records = []
        exact = {}
        native = {}
        for side in ("W", "B"):
            for local in range(20):
                index = len(records)
                records.append(record(side, index))
                exact[index] = "loss" if local < 12 else "win"
                native[index] = "win"
        selected = select_stratum(
            stratum="p3_mince",
            records=records,
            exact=exact,
            native=native,
            failures_per_side=8,
            controls_per_side=4,
            seed=958001,
        )
        self.assertEqual(len(selected), 24)
        counts = {}
        for row in selected:
            key = (row["advantaged_side"], row["family"])
            counts[key] = counts.get(key, 0) + 1
        self.assertEqual(counts[("W", "jass_failure")], 8)
        self.assertEqual(counts[("B", "jass_failure")], 8)
        self.assertEqual(counts[("W", "shared_win_control")], 4)
        self.assertEqual(counts[("B", "shared_win_control")], 4)

    def test_classification_localizes_first_robust_arm(self):
        strata = ["p3", "p4"]
        conversion = {
            arm: {
                stratum: {
                    "conversion": 0.55 if arm == "SCAN_EXT_QS" else 0.40,
                    "ci_low": 0.45,
                    "ci_high": 0.65,
                }
                for stratum in strata
            }
            for arm in VARIANT_ORDER
        }
        comparisons = {
            stratum: {
                f"{arm}_vs_Q00": {
                    "delta": 0.15 if arm == "SCAN_EXT_QS" else 0.0,
                    "ci_low": 0.04 if arm == "SCAN_EXT_QS" else -0.05,
                }
                for arm in VARIANT_ORDER
            }
            for stratum in strata
        }
        result = classify(conversion, comparisons, strata)
        self.assertEqual(result["verdict"], "SCAN_EXTENSION_QUIESCENCE_DOMINANT")
        self.assertEqual(result["localized_arm"], "SCAN_EXT_QS")


if __name__ == "__main__":
    unittest.main()
