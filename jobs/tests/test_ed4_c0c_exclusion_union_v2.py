from __future__ import annotations
import hashlib, struct, tempfile, unittest
from pathlib import Path
from unittest import mock

from jobs.tools import ed4_c0c_exclusion_union_v2 as v2
from jobs.tools import ed4_c0c_exclusion_union as v1

class C0CV2Tests(unittest.TestCase):
    def _payload(self):
        header=b'JNNW'+struct.pack('<I',0)
        rec=struct.pack('<QQQQB',1,2,4,8,0)+b'abcde'
        body=rec*v2.SALVAGE_COMPLETE_RECORDS+b'x'*v2.SALVAGE_PARTIAL_TAIL_BYTES
        return header+body

    def test_shape_is_exact_3023_plus_32(self):
        raw=self._payload()
        self.assertEqual(len(raw), 8 + 3023*38 + 32)

    def test_exact_salvage_recovers_only_complete_records(self):
        raw=self._payload()
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'x.jnnw'; p.write_bytes(raw)
            with mock.patch.object(v2,'SALVAGE_SHA256',hashlib.sha256(raw).hexdigest()), \
                 mock.patch.object(v2,'SALVAGE_SIZE',len(raw)):
                ids,rows,meta=v2._parse_exact_interrupted_jnnw(p)
        self.assertEqual(rows,3023)
        self.assertEqual(meta['complete_records_recovered'],3023)
        self.assertEqual(meta['partial_tail_bytes_discarded'],32)
        self.assertEqual(len(ids),1)

    def test_v1_remains_fail_closed_on_same_shape(self):
        raw=self._payload()
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'x.jnnw'; p.write_bytes(raw)
            with self.assertRaisesRegex(v1.C0CError,'jnnw_trailing_bytes'):
                v1.parse_jnnw(p)

    def test_non_exact_candidate_still_uses_v1(self):
        desc={'path':'other.jnnw','kind':'jnnw','sha256':'a'*64,'size_bytes':99}
        with mock.patch.object(v1,'parse_candidate',side_effect=v1.C0CError('jnnw_trailing_bytes')):
            with self.assertRaisesRegex(v1.C0CError,'jnnw_trailing_bytes'):
                v2._parse_candidate_v2(Path('/tmp/none'),desc,'job','attempt')

if __name__=='__main__': unittest.main()
