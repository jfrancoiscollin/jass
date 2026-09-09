from __future__ import annotations
import copy
import json
from pathlib import Path
import struct
import tempfile
import unittest
import numpy as np
from jobs.tools import ed3_confirmation_data as d


def sample_records(n):
    rng=np.random.default_rng(91237); rows=[]
    for _ in range(n):
        sq=rng.choice(50,10,replace=False)
        rows.append(struct.pack('<4QB',sum(1<<int(s) for s in sq[:5]),0,sum(1<<int(s) for s in sq[5:]),0,len(rows)%2)+b'\0'*5)
    return rows

class SelectionTests(unittest.TestCase):
    def raw(self):
        rows=sample_records(2400)
        return b'JNNW'+struct.pack('<I',len(rows))+b''.join(rows)

    def test_guard_selects_only_unexposed_openings_without_targets(self):
        raw=self.raw(); old={'subsets':{'replay':{'opening_ids':[0,1]},'wdl_holdout':{'opening_ids':[2,3]}}}
        used={d.canonical(raw[8:46])}
        plan=d.select_guard(raw,lambda i:i%300,old,used,lo=0,hi=2400,sizes=(64,128))
        a,b=plan['subsets'].values()
        self.assertFalse(set(a['opening_ids']) & set(b['opening_ids']))
        self.assertFalse((set(a['opening_ids'])|set(b['opening_ids'])) & {0,1,2,3})
        self.assertFalse((set(a['canonical_identities'])|set(b['canonical_identities'])) & used)
        self.assertEqual(plan['targets_read_at_selection'],0)
        self.assertEqual(plan,d.select_guard(raw,lambda i:i%300,old,used,lo=0,hi=2400,sizes=(64,128)))

    def test_guard_insufficient_support_is_not_silently_extended(self):
        with self.assertRaisesRegex(ValueError,'SUPPORT_INSUFFICIENT'):
            d.select_guard(self.raw(),lambda i:1,{'subsets':{}},set(),lo=0,hi=2400,sizes=(64,128))

    def test_old_wdl_byte_values_cannot_change_selection(self):
        raw=self.raw(); changed=bytearray(raw)
        for i in range(2400):changed[8+i*38+33:8+(i+1)*38]=b'abcde'
        args=(lambda i:i%300,{'subsets':{}},set())
        a=d.select_guard(raw,*args,lo=0,hi=2400,sizes=(64,128))
        b=d.select_guard(bytes(changed),*args,lo=0,hi=2400,sizes=(64,128))
        self.assertEqual(a,b)

    def test_color_rotation_is_an_exact_duplicate(self):
        r=sample_records(1)[0]; bs=struct.unpack_from('<4Q',r)
        rot=lambda b:sum(1<<(49-i) for i in range(50) if b&(1<<i))
        rr=struct.pack('<4QB',rot(bs[2]),rot(bs[3]),rot(bs[0]),rot(bs[1]),1-r[32])+b'\0'*5
        self.assertEqual(d.canonical(r),d.canonical(rr))

    def test_role_mapping_fixed_miniature_and_full_cardinalities(self):
        parents=[];groups=[]
        for role,count in [('calibration',2),('train',64),('test',32)]:
            for ph in range(4):
                for stm in range(2):
                    for _ in range(count):
                        pid=len(parents); parents.append(dict(parent_id=str(pid),split=role,parent_phase=f'P{ph}',parent_stm=str(stm)))
                        for a in range(2):groups.append(dict(parent_id=str(pid),row_index=str(2*pid+a),child_rule_terminal='0'))
        prod=d.selected_groups(parents,groups,'production');dev=d.selected_groups(parents,groups,'rehearsal')
        self.assertEqual(len(prod),512);self.assertEqual(len(dev),16)
        self.assertTrue({g['id'] for g in dev}<={g['id'] for g in prod}) # local ids: actual source disjointness enforced before generation
        bad=[p for p in parents if p['parent_phase']!='P3']
        with self.assertRaisesRegex(ValueError,'fixed_cells_missing'):d.selected_groups(bad,groups,'production')

    def test_invalid_boards_and_counted_layout_fail_closed(self):
        with self.assertRaises(ValueError):d.canonical(struct.pack('<4QB',1,1,2,0,0)+b'\0'*5)
        with self.assertRaises(ValueError):d.select_guard(self.raw()[:-1],lambda i:i,{'subsets':{}},set(),lo=0,hi=2400,sizes=(64,128))

class ReferenceTests(unittest.TestCase):
    def test_complete_reference_and_terminal_no_search(self):
        from jobs.tools.ed3_confirmation import load_scores
        gs=[dict(rows=[0,1],terminals=[1])]
        rows=[dict(row=0,budget=200000,score=12,terminal=False,elapsed_seconds=.1,last_info_nodes=192000),
              dict(row=1,budget=200000,score=10000,terminal=True,elapsed_seconds=0,last_info_nodes=0)]
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'r.jsonl';p.write_text(''.join(json.dumps(r)+'\n' for r in rows))
            scores,n=load_scores([p],gs);self.assertEqual(n,1);self.assertEqual(scores[1,200000],10000)
            with self.assertRaises(ValueError):load_scores([p,p],gs)
            p.write_text(json.dumps(rows[0])+'\n')
            with self.assertRaises(ValueError):load_scores([p],gs)
            rows[0]['budget']=50000;p.write_text(''.join(json.dumps(r)+'\n' for r in rows))
            with self.assertRaises(ValueError):load_scores([p],gs)

    def test_empty_wrong_terminal_and_nonfinite_fail_closed(self):
        from jobs.tools.ed3_confirmation import load_scores
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'r';p.write_text('')
            with self.assertRaises(ValueError):load_scores([p],[dict(rows=[1],terminals=[])])
            r=dict(row=1,budget=200000,score=3,terminal=True,elapsed_seconds=0,last_info_nodes=0)
            p.write_text(json.dumps(r)+'\n')
            with self.assertRaises(ValueError):load_scores([p],[dict(rows=[1],terminals=[1])])
            r.update(terminal=False,elapsed_seconds=float('nan'),last_info_nodes=1)
            p.write_text(json.dumps(r)+'\n')
            with self.assertRaises(ValueError):load_scores([p],[dict(rows=[1],terminals=[])])

    def test_source_mutation_refused_before_worker(self):
        from jobs.tools.ed3_confirmation import verify_sealed_inputs
        with tempfile.TemporaryDirectory() as td:
            p=Path(td);(p/'source').mkdir();(p/'source/a').write_text('fixed');(p/'guard-plan.json').write_text('{}')
            (p/'cohort-seal.json').write_text(json.dumps(dict(source_files={'a':d.sha(p/'source/a')},guard_plan_sha256=d.sha(p/'guard-plan.json'))))
            verify_sealed_inputs(p);(p/'source/a').write_text('changed')
            with self.assertRaisesRegex(ValueError,'source_mutation'):verify_sealed_inputs(p)

    def test_no_training_or_old_test_allowlist(self):
        from jobs.tools import ed3_confirmation as c
        source=Path(c.__file__).read_text()
        self.assertNotIn('.fit(',source);self.assertNotIn('minimize(',source)
        self.assertNotIn('test-parent-readout.json',source)
        self.assertNotIn('native/PARTIAL-test',source)
        self.assertEqual(c.MODEL_SHA['SOFT'],'d8a193de2017a6c156a46d89692245bdc1af00d29d056af3a41e7d6d4f5a486a')

if __name__=='__main__':unittest.main()
