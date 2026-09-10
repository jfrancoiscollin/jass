from __future__ import annotations
import hashlib,struct,tempfile,unittest
from pathlib import Path
from unittest import mock
from jobs.tools import ed4_c0c_exclusion_union as v1
from jobs.tools import ed4_c0c_exclusion_union_v3 as v3

class C0CV3Tests(unittest.TestCase):
    def payload(self,target=b'abcde',tail=b'x'*32):
        rec=struct.pack('<QQQQB',1,2,4,8,0)+target
        return b'JNNW'+struct.pack('<I',0)+rec*3023+tail
    def test_two_literal_objects_are_frozen(self):
        self.assertEqual(set(v3.SALVAGE_OBJECTS),{
            'b2-preread-schema-compat/documentary-worktree/jobs/results/ccx33-0206-wdl-loop-mt60/artefacts/sp1-1.jnnw',
            'b2-preread-schema-compat/documentary-worktree/jobs/results/ccx33-0206-wdl-loop-mt60/artefacts/sp1-2.jnnw'})
        self.assertEqual(v3.SALVAGE_OBJECTS[next(iter(v3.SALVAGE_OBJECTS))]['complete_records'],3023)
        self.assertTrue(all(s['tail_bytes']==32 and s['size_bytes']==114914 for s in v3.SALVAGE_OBJECTS.values()))
    def test_exact_shape_recovers_3023_and_skips_targets(self):
        raw=self.payload(); spec={'sha256':hashlib.sha256(raw).hexdigest(),'size_bytes':len(raw),'complete_records':3023,'tail_bytes':32}
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'x'; p.write_bytes(raw)
            real=v1.canonical_from_position_bytes
            with mock.patch.object(v1,'canonical_from_position_bytes',wraps=real) as dec:
                ids,rows,meta=v3._parse_exact_interrupted_jnnw(p,spec)
            self.assertEqual(rows,3023); self.assertEqual(meta['partial_tail_bytes_discarded'],32); self.assertEqual(dec.call_count,3023)
            self.assertTrue(all(len(c.args[0])==33 for c in dec.call_args_list)); self.assertEqual(len(ids),1)
    def test_target_and_tail_values_do_not_change_identities(self):
        out=[]
        for raw in (self.payload(),self.payload(target=b'\xff'*5,tail=b'\0'*32)):
            spec={'sha256':hashlib.sha256(raw).hexdigest(),'size_bytes':len(raw),'complete_records':3023,'tail_bytes':32}
            with tempfile.TemporaryDirectory() as td:
                p=Path(td)/'x'; p.write_bytes(raw); out.append(v3._parse_exact_interrupted_jnnw(p,spec)[0])
        self.assertEqual(out[0],out[1])
    def test_non_exact_object_falls_back_to_v1(self):
        raw=self.payload()
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'x'; p.write_bytes(raw)
            desc={'path':'other.jnnw','kind':'jnnw','sha256':hashlib.sha256(raw).hexdigest(),'size_bytes':len(raw)}
            with self.assertRaisesRegex(v1.C0CError,'jnnw_trailing_bytes'):
                v3._parse_candidate_v3(p,desc,'other','other')
    def test_second_object_hash_is_exact_1911_result(self):
        s=v3.SALVAGE_OBJECTS['b2-preread-schema-compat/documentary-worktree/jobs/results/ccx33-0206-wdl-loop-mt60/artefacts/sp1-2.jnnw']
        self.assertEqual(s['sha256'],'7e1fbd21836db9bb090006b408bb1fb6cecf6ab778baf3c8182a24a18a3fbb4f')
if __name__=='__main__': unittest.main()
