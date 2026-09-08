"""CI-only actual C++ producer/consumer check. Missing native binary fails."""
from pathlib import Path
import os
import tempfile
from jobs.tests.test_ed3_soft_value_fit import fixture_run

if __name__=='__main__':
    binary=Path(os.environ['ED3_NATIVE_PROBE']).resolve(strict=True)
    with tempfile.TemporaryDirectory() as td:
        root=Path(td)
        result=fixture_run(root,root/'artefacts',real_probe=binary)
        assert result['fits']==1 and result['native_reload_mismatches']==0
        assert result['test_target_reads']==0 and not result['heldout_evaluation_performed']
    print('ED3 actual-native complete candidate path PASS')
