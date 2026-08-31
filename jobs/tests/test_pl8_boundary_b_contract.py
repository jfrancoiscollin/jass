import importlib.util
import pathlib
import struct
import sys
import unittest

ROOT=pathlib.Path(__file__).resolve().parents[2]

def load(name,path):
    spec=importlib.util.spec_from_file_location(name,ROOT/path)
    m=importlib.util.module_from_spec(spec)
    sys.modules[name]=m
    spec.loader.exec_module(m)
    return m

class PL8BoundaryBContract(unittest.TestCase):
    def test_deep_readout_frozen_gates(self):
        m=load('pl8_deep_readout_contract','jobs/tools/pl8_deep_readout.py')
        self.assertEqual(m.BOOTSTRAP_SAMPLES,200000);self.assertEqual(m.BOOTSTRAP_SEED,2026103121)
        self.assertEqual(m.MIN_ACCEPTED,6000);self.assertEqual(m.MIN_ACCEPTED_PHASE,1200);self.assertEqual(m.MIN_ACCEPTED_COLOUR,2400)
        s=(ROOT/'jobs/tools/pl8_deep_readout.py').read_text()
        for x in ('nonnegative_top_hit_delta_every_phase','positive_pairwise_delta_every_phase','positive_pairwise_delta_both_colours','forbidden_runtime_inputs_absent','PL8_FRESH_SUPPORT_NOT_ESTABLISHED'):
            self.assertIn(x,s)
    def test_anchor_exact_30_and_offset_only(self):
        m=load('pl8_anchor_shrink_contract','jobs/tools/pl8_anchor_shrink.py')
        self.assertEqual((m.SEED,m.STATES,m.ITER),(2026103102,500000,30));self.assertEqual((m.RMS_MAX,m.P99_MAX),(12.0,35.0))
        raw=bytearray(200);raw[:4]=b'PL8P';before=bytes(raw);out=m.with_shrink(before,.25)
        self.assertEqual(struct.unpack_from('<d',out,m.SHRINK_OFFSET)[0],.25)
        self.assertEqual(out[:m.SHRINK_OFFSET],before[:m.SHRINK_OFFSET]);self.assertEqual(out[m.SHRINK_OFFSET+8:],before[m.SHRINK_OFFSET+8:])
    def test_selection_seeds_and_sizes(self):
        m=load('pl8_catalog_select_contract','jobs/tools/pl8_catalog_select.py')
        self.assertEqual(m.ANCHOR_SEED,2026103102);self.assertEqual(m.FRESH_SEED,2026103120)
        self.assertEqual(m.PHASES,(('P0',30,40),('P1',20,29),('P2',12,19),('P3',9,11)))

if __name__=='__main__':unittest.main()
