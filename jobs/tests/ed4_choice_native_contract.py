"""Mandatory real C++ fixture producer/consumer contract, with no skip fallback."""
import json,os,tempfile
from pathlib import Path
from jobs.tests.test_ed4_choice_value_fit import fixture_run
probe=Path(os.environ['ED4_NATIVE_PROBE']).resolve(strict=True)
with tempfile.TemporaryDirectory(prefix='ed4-real-native-') as td:
    root=Path(td);first=root/'first';second=root/'second'
    fixture_run(first,first/'artefacts',real_probe=probe)
    result=fixture_run(second,second/'artefacts',mode='production',real_probe=probe,prerequisite=first/'artefacts')
    assert result['verdict']=='ED4_CHOICE_SET_REAL_CANDIDATE_SEALED_V1'
    assert json.loads((second/'artefacts/native-roundtrip.json').read_bytes())['native_reload_mismatches']==0
    assert (first/'artefacts/ED4_CHOICE.pjtw').read_bytes()==(second/'artefacts/ED4_CHOICE.pjtw').read_bytes()
print('ED4_ACTUAL_NATIVE_FIT_AND_REHEARSAL_IDENTITY_PASS synthetic_optimizer_invocations=2 real_fits=0')
