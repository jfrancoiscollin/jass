"""Required CI native source/evaluation path: missing binaries fail, never skip."""
import os
from pathlib import Path
import tempfile
from jobs.tests.test_ed3_confirmation_publication import fixture_run
for name in ('ED3_CONFIRM_SOURCE','ED3_CONFIRM_NATIVE_PROBE'):
    assert name in os.environ and Path(os.environ[name]).is_file(), name
with tempfile.TemporaryDirectory() as td:
    root=Path(td);out=fixture_run(root,root/'artefacts',actual_native=True)
    assert out['parents']==16 and out['fits']==0
    assert out['scientific_verdict'] is None
print('ED3 confirmation full native source/readout path PASS')
