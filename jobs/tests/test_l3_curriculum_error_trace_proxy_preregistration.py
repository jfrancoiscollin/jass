#!/usr/bin/env python3
import copy
import unittest

from jobs.tools import l3_curriculum_error_trace_proxy_preregistration as target
from jobs.tools import l3_curriculum_error_trace_variability_screen as trace


def inputs():
    selected={"name":target.SELECTED_PROXY,"priority":0,"passed":True,"lower_open":52.0,"upper_closed":154.0}
    trace_report={"schema":trace.SCHEMA,"verdict":trace.READY,"passed":True,"preregistration_authorized":True,"selected_proxy":selected,"candidates":[selected,{"name":"other","priority":1,"passed":True}],"coverage_job":"coverage","coverage_attempt":"ca","coverage_code_sha":"cc","pairs_sha256":"pairs"}
    for key in ("exact_action_value_reads","outer_confirm_profile_rows_examined","outer_confirm_action_value_reads","diagnostic_fits","pattern_eval_fits","strength_games","new_selfplay_games","frozen_reads"): trace_report[key]=0
    coverage={"verdict":"JASS_CURRICULUM_ERROR_PAIRED_COVERAGE_SCREEN_NOT_ESTABLISHED","source_job":"action","source_attempt":"aa","source_code_sha":"ac","champion_sha256":"champion"}
    action={"verdict":"JASS_CURRICULUM_ERROR_ACTION_SOURCE_READY","job_id":"action","attempt_id":"aa","source_code_sha":"ac","champion_sha256":"champion","jass_sha256":"jass","search_params_sha256":"search","pattern_bucket_aggregate_reads":0,"pattern_eval_fits":0,"production_model_fits":0,"strength_games":0,"frozen_reads":0}
    return trace_report,coverage,action,("action","aa","ac")


class TraceProxyPreregistrationTests(unittest.TestCase):
    def test_preregisters_one_fixed_proxy_without_targets(self):
        report=target.analyze(*inputs()); self.assertTrue(report["passed"]); self.assertEqual(report["architectures_considered"],1)
        arch=report["fixed_architecture"]; self.assertEqual(arch["risk_gate"]["proxy"],target.SELECTED_PROXY); self.assertEqual(arch["risk_gate"]["lower_open"],52.0); self.assertEqual(arch["alpha"],100.0)
        self.assertEqual(arch["decision"]["abstention"],"unaltered_CURRICULUM_action"); self.assertEqual(report["validation_action_value_reads"],0)

    def test_threshold_drift_fails_closed(self):
        a,b,c,i=inputs(); a=copy.deepcopy(a); a["selected_proxy"]["upper_closed"]=155.0
        with self.assertRaisesRegex(ValueError,"threshold drift"): target.analyze(a,b,c,i)

    def test_nonfirst_proxy_fails_closed(self):
        a,b,c,i=inputs(); a=copy.deepcopy(a); a["candidates"].insert(0,{"name":"earlier","passed":True})
        with self.assertRaisesRegex(ValueError,"first passing"): target.analyze(a,b,c,i)

    def test_any_sealed_read_fails_closed(self):
        a,b,c,i=inputs(); a["outer_confirm_action_value_reads"]=1
        with self.assertRaisesRegex(ValueError,"counter drift"): target.analyze(a,b,c,i)


if __name__ == "__main__": unittest.main()
