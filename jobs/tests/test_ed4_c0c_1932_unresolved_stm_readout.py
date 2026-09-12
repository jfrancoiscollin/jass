from __future__ import annotations
import os, tempfile, unittest
from pathlib import Path
from unittest import mock
from jobs.tools import ed4_c0c_1932_unresolved_stm_readout_stage as stage

class ReadoutBoundaryTests(unittest.TestCase):
    def test_production_fails_before_transport(self):
        with tempfile.TemporaryDirectory() as td, \
             mock.patch.object(stage.fetch_result_files,'inspect_result_inventory',side_effect=AssertionError('transport forbidden')) as inspect, \
             mock.patch.object(stage.fetch_result_files,'fetch_files',side_effect=AssertionError('transport forbidden')) as fetch, \
             mock.patch.dict(os.environ,{'JASS_ARTEFACT_DIR':str(Path(td)/'a'),'JASS_RESULT_DIR':str(Path(td)/'r'),'LAUNCH_MODE':'production'},clear=False):
            self.assertEqual(stage.main(),2)
        inspect.assert_not_called(); fetch.assert_not_called()

if __name__=='__main__': unittest.main()
