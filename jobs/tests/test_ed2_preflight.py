from __future__ import annotations
import importlib.util
import json
import os
from pathlib import Path
import random
import struct
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('ed2',ROOT/'jobs/tools/ed2_preflight.py')
ed2=importlib.util.module_from_spec(spec); spec.loader.exec_module(ed2)

def rec(wm=1,wk=0,bm=1<<49,bk=0,stm=0):
    return struct.pack('<QQQQBib',wm,wk,bm,bk,stm,0,0)

class Helpers(unittest.TestCase):
    def test_symmetry_canonical_and_stm(self):
        a=rec(wm=3,bm=(1<<40)|(1<<45),stm=0)
        b=rec(wm=(1<<9)|(1<<4),bm=(1<<49)|(1<<48),stm=1)
        self.assertEqual(ed2.canonical(a),ed2.canonical(b))
        self.assertNotEqual(ed2.canonical(a),ed2.canonical(a[:32]+b'\1'+a[33:]))
    def test_bad_bitboards_and_labels(self):
        for a in [rec(wm=1,bm=1),rec(wm=1<<50),rec(stm=2),rec()[:-1]+b'\1']:
            with self.assertRaises(ValueError): ed2.values(a)
    def test_counted_format_and_refuse_overwrite(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'r'; p.write_bytes(b'JNNW'+struct.pack('<I',1)+rec())
            self.assertEqual(ed2.records(p),[rec()])
            p.write_bytes(p.read_bytes()+b'x')
            with self.assertRaises(ValueError): ed2.records(p)
            q=Path(td)/'j'; ed2.write_new(q,{'fits':0})
            with self.assertRaises(FileExistsError): ed2.write_new(q,{})
    def test_calibration_filter_cannot_select_train_or_test(self):
        with tempfile.TemporaryDirectory() as td:
            d=Path(td)
            (d/'parents.tsv').write_text('parent_id\tsplit\n'+''.join(f'{i}\tcalibration\n' for i in range(16))+'16\ttrain\n17\ttest\n')
            (d/'groups.tsv').write_text('parent_id\tsplit\trow_index\tchild_rule_terminal\n'+''.join(f'{i}\tcalibration\t{i}\t0\n' for i in range(16))+'16\ttrain\tBAD_UNREAD\t0\n17\ttest\tBAD_UNREAD\t0\n')
            self.assertEqual(ed2.calibration_ids(d),list(range(16)))
    def test_bad_calibration_support_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            d=Path(td); (d/'parents.tsv').write_text('parent_id\tsplit\n0\tcalibration\n'); (d/'groups.tsv').write_text('parent_id\tsplit\trow_index\tchild_rule_terminal\n0\tcalibration\t0\t1\n')
            with self.assertRaises(ValueError): ed2.calibration_ids(d)
    def test_cli(self):
        r=subprocess.run([os.sys.executable,str(ROOT/'jobs/tools/ed2_preflight.py'),'--help'],capture_output=True,text=True)
        self.assertEqual(r.returncode,0,r.stderr)
    def test_frozen_quotas_and_budget(self):
        self.assertEqual(ed2.QUOTAS['production'],{'calibration':2,'train':64,'test':32})
        self.assertEqual(17*sum(ed2.BUDGETS),4335000)
        self.assertEqual(512*16*55000+256*16*200000,1269760000)

@unittest.skipUnless(os.environ.get('ED2_NATIVE_SOURCE'),'native binary supplied by dedicated CI')
class Native(unittest.TestCase):
    def run_source(self,ex,out,mode='smoke'):
        return subprocess.run([os.environ['ED2_NATIVE_SOURCE'],str(ex),str(out),mode],capture_output=True,text=True,timeout=120)
    def test_actual_producer_consumer_replay_and_leakage(self):
        with tempfile.TemporaryDirectory() as td:
            d=Path(td); ex=d/'exclude'; ex.write_text('')
            for name in ('a','b'):
                r=self.run_source(ex,d/name); self.assertEqual(r.returncode,0,r.stderr)
                info=ed2.seal(d/name,ex,d/(name+'.seal'),'smoke')
                self.assertEqual(info['parents'],32); self.assertEqual(info['benchmark_overlap'],0)
                self.assertFalse(info['fit_authorized'])
            for f in ed2.FILES: self.assertEqual((d/'a'/f).read_bytes(),(d/'b'/f).read_bytes())
            self.assertNotEqual(self.run_source(ex,d/'a').returncode,0)
            # Move a complete canonical footprint into the exclusion set.
            # The native selector must skip it before any teacher read.
            ex.write_text(ed2.canonical(ed2.records(d/'a/parents.jnnw')[0])+'\n')
            r=self.run_source(ex,d/'c'); self.assertEqual(r.returncode,0,r.stderr)
            ed2.validate_source(d/'c',ex,'smoke')
            # A source validated against a different exclusion list is invalid.
            with self.assertRaises(ValueError): ed2.validate_source(d/'a',ex,'smoke')
    def test_no_production_without_benchmark_exclusions(self):
        with tempfile.TemporaryDirectory() as td:
            d=Path(td); ex=d/'ex'; ex.write_text('')
            r=self.run_source(ex,d/'out','production')
            self.assertNotEqual(r.returncode,0); self.assertIn('exclusion',r.stderr)
if __name__=='__main__': unittest.main()
