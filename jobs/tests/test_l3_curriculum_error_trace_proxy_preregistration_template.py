#!/usr/bin/env python3
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[2]
TEXT=(ROOT/'jobs/templates/l3-curriculum-error-trace-proxy-preregistration-v1.sh').read_text()

class TraceProxyPreregistrationTemplateTests(unittest.TestCase):
    def test_three_immutable_sources_and_read_only_guards(self):
        for token in ('TRACE_SOURCE_ATTEMPT','COVERAGE_SOURCE_ATTEMPT','ACTION_SOURCE_ATTEMPT','identity/state drift','NO_FIT','NO_SELFPLAY','NO_STRENGTH_GAMES','NO_FROZEN_READ','VALIDATION_ACTION_VALUE_READS__0','OUTER_CONFIRM_ACTION_VALUE_READS__0','PROMOTION_AUTHORIZED__FALSE'): self.assertIn(token,TEXT)
        self.assertNotIn('train_stream_exact.py',TEXT); self.assertNotIn('run_games',TEXT)

    def test_single_fixed_architecture_marker(self):
        self.assertIn('FIXED__MAX_DEPTH_SCORE_SPREAD_GT52_LE154__ALPHA_100__CAP_75__CONSENSUS',TEXT)
        self.assertIn('architectures=1',TEXT)

if __name__ == '__main__': unittest.main()
