import unittest
from jobs.tools import l3_curriculum_error_loss_first_sibling_rank_preregistration as p


def source():
    return {
        "schema": p.SOURCE_SCHEMA, "code_sha": p.SOURCE_CODE,
        "verdict": p.SOURCE_VERDICT, "passed": True,
        "scientific_status": "raw_cp_endpoint_tail_dominated__loss_first_rank_supervision_required",
        "next_stage": "preregister_loss_first_sibling_rank_corpus",
        "loss_tail": {"score_scale_tail_dominated": True, "sentinel_scale_loss_count": 2, "sentinel_scale_loss_share": .741258},
        "loss_first_acquisition_contract": {"name": "loss_first_sibling_rank_corpus_v1"},
        "anchored_local_refit_authorized": False, "production_model_authorized": False,
        "strength_gate_authorized": False, "promotion_authorized": False,
        "automatic_continuation": False,
    }


class PreregistrationTest(unittest.TestCase):
    def test_fixed_protocol(self):
        r=p.preregister(source())
        self.assertEqual(r["source_campaign"]["total_games"],1536)
        self.assertEqual(r["teacher"]["budgets"],["depth10","depth12"])
        self.assertFalse(r["teacher"]["raw_cp_sentinels_used_as_loss_magnitude"])
        self.assertEqual(r["labels"]["per_opening_total_loss_mass"],1.0)
        self.assertTrue(r["source_campaign_authorized"])
        self.assertFalse(r["anchored_local_refit_authorized"])

    def test_rejects_non_tail_source(self):
        s=source(); s["loss_tail"]["score_scale_tail_dominated"]=False
        with self.assertRaisesRegex(ValueError,"exact certified 1541"):
            p.preregister(s)


if __name__=="__main__": unittest.main()
