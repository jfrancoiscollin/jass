from __future__ import annotations
import functools
import gzip
import hashlib
import io
import json
from pathlib import Path
import shutil
import struct
import tempfile
import unittest
import numpy as np
from jobs.tools import ed3_label_pressure as e
from jobs.tools.launch_runtime_v2 import atomic_json


def fixture(root):
    for name in ('p0/source','n1/native','base','target','work','art'):(root/name).mkdir(parents=True)
    groups='row_index\tsibling_identity\tchild_fingerprint\tchild_rule_terminal\tchild_legal_moves\tparent_id\tparent_phase\tparent_stm\tsplit\n'
    for i in range(4):groups+=f'{i}\t{i//2}:{i%2}\tboard\t0\t2\t{i//2}\tP0\t{i//2}\ttrain\n'
    (root/'p0/source/groups.tsv').write_text(groups)
    hashes={}
    for i,name in enumerate(e.TRAIN_NAMES):
        payload=[]
        if i<4:
            for budget in (5000,50000):payload.append(json.dumps(dict(row=i,budget=budget,score=20 if i%2==0 else 0,terminal=False)))
        path=root/'n1'/name;path.write_text('\n'.join(payload)+'\n' if payload else '')
        hashes[name]=e.sha(path)
    atomic_json(root/'n1/train-labels-sealed.json',dict(source_seal=e.SOURCE_SEAL,test_teacher_calls=0,teacher_files=hashes))
    rng=np.random.default_rng(98)
    ext=rng.normal(size=(4,120));phase=np.array([.1,.2,.8,.9])
    rx=rng.normal(size=(8,120));rphase=np.linspace(.1,.9,8)
    model_weights={'BASE':np.zeros(240),'POINT':rng.normal(size=240)*.02,'PARTIAL':rng.normal(size=240)*.01}
    models={}
    for arm,w in model_weights.items():
        q=np.rint(w*1000).astype('<i4');model_weights[arm]=q/1000
        raw=struct.pack('<5I',0x57544a50,3,1000,2,120)+np.zeros(4,dtype='<i4').tobytes()+q.tobytes()
        models[arm]=hashlib.sha256(raw).hexdigest()
        if arm=='BASE':(root/'base/WDL_CONTROL.pjtw.gz').write_bytes(gzip.compress(raw))
        else:(root/'n1'/(arm+'.pjtw')).write_bytes(raw)
    def table(name,x,ph,w):
        z=np.hstack([x*ph[:,None],x*(1-ph[:,None])])@w
        a=np.column_stack([np.arange(len(x)),z,np.trunc(z*100),ph,x])
        with gzip.open(root/'n1/native'/name,'wt') as f:
            f.write('header\n');np.savetxt(f,a,delimiter='\t',fmt='%.17g')
    table('train-native.tsv.gz',ext,phase,model_weights['BASE'])
    table('replay-native.tsv.gz',rx,rphase,model_weights['BASE'])
    for arm in ('POINT','PARTIAL'):table(arm+'-train-native.tsv.gz',ext,phase,model_weights[arm])
    atomic_json(root/'n1/wdl-selection.json',dict(subsets={'replay':{'indices':list(range(8))}}))
    atomic_json(root/'n1/wdl-selection.seal.json',dict(sha256=e.sha(root/'n1/wdl-selection.json')))
    y=np.full(16,np.nan,dtype=np.float32);y[:8]=np.linspace(.2,.8,8)
    data=io.BytesIO();np.save(data,y,allow_pickle=False)
    (root/'target/current_2m-context30.npy.gz').write_bytes(gzip.compress(data.getvalue()))
    return models


def analyze(root,models):
    return e.analyze_inputs(root/'p0',root/'n1',root/'base',root/'target',root/'work',
                            expected_parents=2,replay_n=8,total_targets=16,model_hashes=models)


class ED3DiagnosticTests(unittest.TestCase):
    def test_full_synthetic_producer_consumer_model_replay_and_report(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);models=fixture(root);report=analyze(root,models)
            self.assertEqual(report['train_pairs'],2);self.assertTrue(report['diagnostic_only'])
            self.assertAlmostEqual(report['prospective_tau'],20/np.log(3))
            self.assertEqual(set(report['arms']),{'BASE','POINT','PARTIAL'})
            # Non-selected targets are NaN: touching them as an evaluated fold fails.
            self.assertTrue(np.isfinite(report['arms']['BASE']['replay_logloss']))
            atomic_json(root/'art/report.json',report)
            self.assertEqual(json.loads((root/'art/report.json').read_text()),report)

    def test_forbidden_test_budget_rejected_even_with_consistent_file_hash(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);fixture(root);path=root/'n1/train-0.jsonl'
            path.write_text(path.read_text().replace('5000','200000'))
            seal=e.load_json(root/'n1/train-labels-sealed.json');seal['teacher_files']['train-0.jsonl']=e.sha(path)
            atomic_json(root/'n1/train-labels-sealed.json',seal)
            with self.assertRaisesRegex(ValueError,'forbidden_target_role'):e.groups_and_scores(root/'p0',root/'n1',2)

    def test_corrupted_teacher_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);fixture(root);(root/'n1/train-0.jsonl').write_text('{}')
            with self.assertRaisesRegex(ValueError,'teacher_hash'):e.groups_and_scores(root/'p0',root/'n1',2)

    def test_missing_teacher_coverage_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);fixture(root);path=root/'n1/train-0.jsonl';path.write_text('')
            seal=e.load_json(root/'n1/train-labels-sealed.json');seal['teacher_files']['train-0.jsonl']=e.sha(path)
            atomic_json(root/'n1/train-labels-sealed.json',seal)
            with self.assertRaisesRegex(ValueError,'teacher_coverage'):e.groups_and_scores(root/'p0',root/'n1',2)

    def test_replaced_model_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);models=fixture(root);(root/'n1/POINT.pjtw').write_bytes(b'wrong')
            with self.assertRaisesRegex(ValueError,'model_identity'):analyze(root,models)

    def test_full_entrypoint_fetch_validate_measure_publish(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);models=fixture(root);result=root/'run';art=result/'artefacts';art.mkdir(parents=True)
            calls=[]
            def downloader(identity,names,out,report):
                key={e.P0:'p0',e.N1:'n1',e.BASE:'base',e.TARGET:'target'}[identity]
                calls.extend(names)
                # Synthetic fixture does not need unused descriptive support.
                for name in names:
                    path=root/key/name
                    if not path.exists():continue
                    dest=out/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,dest)
                atomic_json(report,dict(fixture=True))
            analyzer=functools.partial(e.analyze_inputs,expected_parents=2,replay_n=8,total_targets=16,model_hashes=models)
            result_doc=e.run(art,result,'rehearsal',downloader,analyzer)
            self.assertEqual(result_doc['fits'],0)
            evidence=e.load_json(art/'execution-evidence.json')
            self.assertEqual(evidence['completed_phases'],e.PHASES);self.assertEqual(evidence['state'],'completed')
            self.assertFalse(any('holdout-native' in x or x.startswith('test-') for x in calls))
            self.assertEqual(e.load_json(art/'scientific-summary.json')['verdict'],result_doc['verdict'])

    def test_failure_is_structured_at_original_phase(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'art').mkdir()
            def broken(*args):raise ValueError('transport credentials must not be copied')
            with self.assertRaises(ValueError):e.run(root/'art',root,'rehearsal',broken)
            v=e.load_json(root/'art/execution-evidence.json')
            self.assertEqual(v['phase'],'authenticate');self.assertEqual(v['state'],'failed')
            self.assertNotIn('credentials',json.dumps(v))

if __name__=='__main__':unittest.main()

# Used by the real generic-stage integration rehearsal; not an ED3 production CLI.
def fixture_run(result, art):
    root=result/'fixture';root.mkdir()
    models=fixture(root)
    def downloader(identity,names,out,report):
        key={e.P0:'p0',e.N1:'n1',e.BASE:'base',e.TARGET:'target'}[identity]
        for name in names:
            src=root/key/name
            if not src.exists():continue
            dest=out/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dest)
        atomic_json(report,dict(fixture=True))
    analyzer=functools.partial(e.analyze_inputs,expected_parents=2,replay_n=8,total_targets=16,model_hashes=models)
    return e.run(art,result,'rehearsal',downloader,analyzer)
