import gzip
import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
import numpy as np
from jobs.tools import ed2_value_math as original
from jobs.tools import ed2_value_trust_exact as solver
from jobs.tools import ed2_value_recovery as recovery


def fixture(width=6):
    rng=np.random.default_rng(602)
    x=rng.normal(size=(14,width)); z=rng.normal(size=14)
    edges=(np.array([0,2,4,8]),np.array([1,3,5,9]),np.array([.2,.2,.3,.3]),np.array([1.,-1.,1.,-1.]))
    rx=rng.normal(size=(30,width));rz=rng.normal(size=30);y=rng.uniform(size=30)
    return x,z,edges,rx,rz,y


def write(path,obj):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(obj,sort_keys=True)+'\n')


def bundle(root):
    for i in range(8):(root/f'train-{i}.jsonl').write_text('{}\n')
    (root/'execution-logs').mkdir()
    (root/'execution-logs/pipeline.log').write_text('phase=fit-point\n'+recovery.ERROR+'\n')
    for role in ('replay','wdl_holdout'):(root/(role+'.jnnw')).write_bytes(role.encode())
    selection={'subsets':{r:{'data_sha256':recovery.digest(root/(r+'.jnnw'))} for r in ('replay','wdl_holdout')}}
    write(root/'wdl-selection.json',selection)
    write(root/'wdl-selection.seal.json',{'sha256':recovery.digest(root/'wdl-selection.json')})
    support={'POINT':{'pairs':8},'PARTIAL':{'pairs':4}}
    write(root/'label-support.json',support)
    seal={'source_seal':recovery.P0_SEAL,'recipe':{'frozen':True},'test_teacher_calls':0,
          'support':support,'teacher_files':{f'train-{i}.jsonl':recovery.digest(root/f'train-{i}.jsonl') for i in range(8)}}
    write(root/'train-labels-sealed.json',seal)
    write(root/'train-teacher.json',dict(rows=16,searches=16,requested_nodes=440000,wall_seconds=3))
    (root/'native').mkdir()
    for name in ('train-native.tsv','replay-native.tsv'):
        with gzip.open(root/'native'/(name+'.gz'),'wb') as f:f.write(name.encode())
    return selection,support


class NumericalTests(unittest.TestCase):
    def test_original_objective_and_gradient_are_preserved(self):
        args=fixture(); beta=np.linspace(-.2,.3,6)
        f,g=original.objective(beta,*args)
        ff,gg,_=solver.derivatives(beta,*args)
        self.assertAlmostEqual(f,ff,places=13)
        np.testing.assert_allclose(g,gg,rtol=1e-12,atol=1e-12)

    def test_hessian_matches_gradient_finite_differences(self):
        args=fixture();beta=np.linspace(-.2,.3,6);eps=1e-5
        _,_,h=solver.derivatives(beta,*args)
        for i in range(6):
            d=np.eye(6)[i]*eps
            numerical=(original.objective(beta+d,*args)[1]-original.objective(beta-d,*args)[1])/(2*eps)
            np.testing.assert_allclose(h[:,i],numerical,rtol=1e-7,atol=1e-9)

    def test_hessian_remains_positive_with_rank_deficient_features(self):
        args=list(fixture());args[0][:,2:]=0;args[3][:,2:]=0
        h=solver.derivatives(np.zeros(6),*args)[2]
        self.assertGreaterEqual(float(np.linalg.eigvalsh(h).min()),original.L2-1e-12)

    def test_real_fit_certifies_original_gradient(self):
        args=fixture(240);beta,report=solver.fit(*args)
        self.assertTrue(report['success']);self.assertLessEqual(report['gradient_l2'],1e-6)
        self.assertLessEqual(report['objective_gap_upper_bound'],5.01e-10)
        self.assertLess(original.objective(beta,*args)[0],original.objective(np.zeros(240),*args)[0])
        self.assertEqual(report['restarts'],0)

    def test_nonfinite_fit_fails_closed(self):
        args=list(fixture(240));args[0][0,0]=np.nan
        with self.assertRaises(ValueError):solver.fit(*args)


class RecoveryTests(unittest.TestCase):
    def inventory(self,files=()):
        return dict(job_id=recovery.JOB,attempt_id=recovery.ATTEMPT,code_sha=recovery.CODE,
                    result_state='failed',exit_code=2,files=[{'path':p} for p in files])

    def test_exact_failed_identity_required(self):
        recovery.validate_inventory(self.inventory())
        for key,bad in [('attempt_id','other'),('result_state','completed'),('exit_code',0)]:
            obj=self.inventory();obj[key]=bad
            with self.assertRaises(ValueError):recovery.validate_inventory(obj)

    def test_all_inventory_candidate_and_test_paths_are_forbidden(self):
        for path in ('artefacts/POINT.pjtw','work/PARTIAL-fit.json','work/models-sealed.json','artefacts/test-0.jsonl'):
            with self.assertRaises(ValueError):recovery.validate_inventory(self.inventory([path]))

    def test_sealed_train_bundle_is_accepted(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);bundle(root)
            recovery.validate_bundle(root,{'frozen':True})

    def test_modified_train_or_recipe_refused(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);bundle(root)
            with self.assertRaises(ValueError):recovery.validate_bundle(root,{'frozen':False})
            (root/'train-3.jsonl').write_text('changed')
            with self.assertRaises(ValueError):recovery.validate_bundle(root,{'frozen':True})

    def test_unexpected_failure_or_early_test_refused(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);bundle(root)
            p=root/'train-labels-sealed.json';s=recovery.read(p);s['test_teacher_calls']=1;write(p,s)
            with self.assertRaises(ValueError):recovery.validate_bundle(root,{'frozen':True})
            s['test_teacher_calls']=0;write(p,s)
            (root/'execution-logs/pipeline.log').write_text('different failure')
            with self.assertRaises(ValueError):recovery.validate_bundle(root,{'frozen':True})

    def test_reuse_copies_identical_labels_without_search(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)/'prior';root.mkdir();art=Path(td)/'artefacts';art.mkdir();work=Path(td)/'work';work.mkdir()
            selection,support=bundle(root)
            write(art/'wdl-selection.json',selection)
            for name in ('replay.jnnw','wdl_holdout.jnnw'):(art/name).write_bytes((root/name).read_bytes())
            for name in ('train-native.tsv','replay-native.tsv'):(work/name).write_bytes(name.encode())
            p=SimpleNamespace(groups_for=lambda *x: [],ARMS=('POINT','PARTIAL'),
                load_scores=lambda *x: ({},dict(rows=16,searches=16,requested_nodes=440000)),
                m=SimpleNamespace(pair_edges=lambda gs,v,a:(None,support[a]),write_new=write))
            values,cost=recovery.reuse_train(p,None,root,art,work,{'frozen':True})
            self.assertEqual(cost['new_searches'],0)
            for i in range(8):self.assertEqual((root/f'train-{i}.jsonl').read_bytes(),(art/f'train-{i}.jsonl').read_bytes())
            self.assertTrue(recovery.read(art/'recovery-reuse.json')['native_base_tables_identical'])
            (work/'train-native.tsv').write_text('drift')
            with self.assertRaises(ValueError):recovery.reuse_train(p,None,root,art,work,{'frozen':True})

if __name__=='__main__':unittest.main()
