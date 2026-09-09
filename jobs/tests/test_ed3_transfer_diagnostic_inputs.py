"""Archived ownership and integer/native-row contracts, without historical reads."""
from copy import deepcopy
import gzip
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
from jobs.tools import ed3_transfer_diagnostic_inputs as i
from jobs.tools.launch_runtime_v2 import StageEvidence

class InputContracts(unittest.TestCase):
    def table(self,path,a):
        opener=gzip.open if path.suffix=='.gz' else Path.open
        with opener(path,'wt') as f:
            f.write('fixture\n');np.savetxt(f,a,delimiter='\t')

    def test_native_rows_and_gzip_roundtrip_fail_closed(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'native.tsv.gz'; a=np.zeros((3,124));a[:,0]=range(3);a[:,3]=.5
            a[:,4]=[1,2,3];a[:,1]=[.1,.2,.3];a[:,2]=[10,20,30]
            self.table(p,a); t=i.native_table(p,3)
            self.assertTrue(np.array_equal(t['x'][:,0],[.5,1,1.5]))
            for col,value in [(0,7),(2,1.5),(3,2),(1,float('nan'))]:
                bad=a.copy();bad[1,col]=value;self.table(p,bad)
                with self.assertRaises(ValueError):i.native_table(p,3)

    def test_model_reconstruction_and_raw_phase_identity(self):
        x=np.zeros((2,240));x[:,0]=[1,2]
        base=dict(x=x,z=np.array([.1,.2]),cp=np.array([10,20]),raw_features=np.zeros((2,121)))
        tables={a:deepcopy(base) for a in i.ARMS};weights={a:np.zeros(240) for a in i.ARMS}
        weights['SOFT'][0]=.2;tables['SOFT']['z']=base['z']+x@weights['SOFT']
        self.assertLessEqual(i.verify_tables(tables,weights)['SOFT'],1e-9)
        tables['SOFT']['z'][0]+=.01
        with self.assertRaisesRegex(ValueError,'reconstruction'):i.verify_tables(tables,weights)
        tables['SOFT']['z']=base['z']+x@weights['SOFT'];tables['HARD']['raw_features'][0,0]=.25
        with self.assertRaisesRegex(ValueError,'features_changed'):i.verify_tables(tables,weights)

    def test_global_alignment_and_parent_pov(self):
        groups=[dict(id=3,stm=1,rows=[2,5]),dict(id=9,stm=0,rows=[7])]
        t={a:dict(cp=np.array([11,22,33]),z=np.array([.1,.2,.3])) for a in i.ARMS}
        result=i.to_global(groups,[2,5,7],t)
        self.assertTrue(np.array_equal(result['HARD'][[2,5,7]],[11,22,33]))
        self.assertTrue(np.array_equal(result['SOFT_logit'][[2,5,7]],[.1,.2,-.3]))

    def test_seal_mismatch_precedes_teacher_and_wdl_decode(self):
        with tempfile.TemporaryDirectory() as td:
            result=Path(td);art=result/'artefacts';art.mkdir()
            def fetch(**kw):
                key=next(k for k,v in i.SOURCES.items() if v[0] in kw['prefix'])
                job,attempt,code=i.SOURCES[key]
                if key=='p0':
                    p=kw['out_dir']/'artefacts/ed2-source-seal.json';p.parent.mkdir(parents=True);p.write_text('{}')
                return dict(job_id=job,attempt_id=attempt,code_sha=code,result_state='completed',exit_code=0,host='cpx62',
                            files=[dict(path=p) for p in i.ALLOWLIST[key]])
            with patch.object(i,'fetch_files',side_effect=fetch),patch.object(i.np,'load') as targets,\
                 patch.object(i.labels,'groups_and_scores') as labels:
                with self.assertRaisesRegex(ValueError,'source_seal_identity'):i.load_inputs(result,art)
                targets.assert_not_called();labels.assert_not_called()

    def test_only_archived_selected_targets_are_decoded_in_order(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); path=root/'targets.npy';art=root/'artefacts';art.mkdir()
            values=np.full(2000000,.5,dtype=np.float32);values[1900017]=.25;values[1800801]=.75
            # A nonselected invalid value must never enter a scientific target read.
            values[0]=np.nan;np.save(path,values);evidence=StageEvidence(art,'rehearsal')
            y=i.guard_targets(path,[1900017,1800801],evidence)
            self.assertEqual(y.tolist(),[.25,.75]);self.assertEqual(y.dtype,np.float64)
            self.assertEqual(evidence.value['actual_side_effects']['test_target_reads'],2)
            self.assertEqual(evidence.value['existing_heldout_target_reads'],2)

    def test_allowlist_excludes_unrelated_target_copies_and_test_labels(self):
        self.assertEqual([p for names in i.ALLOWLIST.values() for p in names if p.endswith('.npy')],
                         ['inputs/n1/work/current-context30.npy'])
        self.assertFalse(any('test-' in p or 'replay' in p or 'scan' in p for names in i.ALLOWLIST.values() for p in names))

if __name__=='__main__':unittest.main()
