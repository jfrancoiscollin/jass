from __future__ import annotations
from contextlib import ExitStack
from itertools import combinations
import gzip
import json
import math
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from jobs.tools import cls_g0_strength_main as m


def fens(n=500):
    return ["W:W"+",".join(map(str,p))+":B1,2" for p in list(combinations(range(31,51),3))[:n]]


def seal():
    return m.select_openings(fens(), set())


def pair_rows(score=.5, censored=False):
    return [{"task_id":f"p{i}","arm_a":"HIER","arm_b":"CURRICULUM",
             "games":[{"a_is_white":c,"score_a":score,"reason":"ply cap" if censored else "3-fold repetition"}
                      for c in (True,False)]} for i in range(m.PAIRS)]


def complete_rows(tasks, work, art, evidence):
    out = []
    for s in tasks:
        games=[]
        for c in (True,False):
            games.append({"opening":s["opening"],"a_is_white":c,"outcome":"D","score_a":.5,
                "reason":"3-fold repetition","plies":1,"moves":["31-26"],
                "fens":[s["opening"],s["opening"]],
                "requests":[{"side":"A","nodes":12,"depth":2,"eval_calls":8,"wall_seconds":.07}],
                "warmup_requests":[{"side":"A"},{"side":"B"}],"game_wall_seconds":.1})
        out.append({**{k:s[k] for k in ("task_id","opening","arm_a","arm_b")},"games":games})
    evidence.record_effect("strength_games",len(tasks)*2)
    evidence.record_effect("new_jass_searches",len(tasks)*6)
    m.write(art/"progress.json",{"pairs_completed":len(tasks)})
    return out


class MainStudyTests(unittest.TestCase):
    def test_identity_rotation_and_range(self):
        self.assertEqual(m.fen_identity("W:W31,32:B1,2"),m.fen_identity("B:W49,50:B19,20"))
        self.assertEqual(m.fen_identity("W:W31-32:B1-2"),m.fen_identity("W:W31,32:B1,2"))

    def test_bad_fens_fail_closed(self):
        for fen in ("W:W1:B1","W:W51:B2","Q:W31:B2","W:W4-2:B1","W:B1:W32"):
            with self.subTest(fen=fen), self.assertRaises(ValueError):
                m.fen_identity(fen)

    def test_deterministic_score_blind_selection(self):
        a=m.select_openings(fens(),set())
        b=m.select_openings(list(reversed(fens())),set())
        self.assertEqual(a,b)
        m.validate_seal(a)
        self.assertFalse({r['canonical'] for r in a['main']} & {r['canonical'] for r in a['representative']})

    def test_exclusions_are_applied_without_replacement(self):
        forbidden={m.fen_identity(f) for f in fens()[:10]}
        s=m.select_openings(fens(),forbidden)
        self.assertFalse(forbidden & {r['canonical'] for r in s['main']+s['representative']})

    def test_insufficient_pool(self):
        with self.assertRaises(ValueError):m.select_openings(fens(20),set())

    def test_seal_tampering(self):
        s=seal();s['main'][0]['fen']='W:W32:B1'
        with self.assertRaises(ValueError):m.validate_seal(s)

    def test_balanced_result_excludes_only_large_loss(self):
        r=m.analyze_main(pair_rows())
        self.assertEqual(r['statistical_verdict'],'SUBSTANTIAL_LOSS_EXCLUDED')
        self.assertLess(r['score_interval'][0],.5)
        self.assertEqual(r['loss_margin_elo'],100)
        self.assertTrue(r['no_superiority_or_promotion_claim'])

    def test_large_loss_supported(self):
        self.assertEqual(m.analyze_main(pair_rows(0))['statistical_verdict'],'SUBSTANTIAL_LOSS_SUPPORTED')

    def test_inconclusive_is_not_extended(self):
        r=pair_rows()
        for row in r:row['games'][0]['score_a']=.25
        with self.assertRaises(ValueError):m.analyze_main(r)
        r=pair_rows()
        for row in r[:m.PAIRS//2]:row['games'][0]['score_a']=0
        self.assertEqual(m.analyze_main(r)['statistical_verdict'],'INDETERMINATE')

    def test_administrative_draws_do_not_manufacture_noninferiority(self):
        r=m.analyze_main(pair_rows(censored=True))
        self.assertEqual(r['score_interval'],[0,1])
        self.assertEqual(r['statistical_verdict'],'INDETERMINATE')
        self.assertEqual(r['administratively_censored_games'],2*m.PAIRS)

    def test_missing_pairs_and_duplicates_abort(self):
        r=pair_rows()
        with self.assertRaises(ValueError):m.analyze_main(r[:-1])
        r[0]['task_id']=r[1]['task_id']
        with self.assertRaises(ValueError):m.analyze_main(r)

    def test_wrong_colour_or_model_abort(self):
        r=pair_rows();r[0]['games'][0]['a_is_white']=False
        with self.assertRaises(ValueError):m.analyze_main(r)
        r=pair_rows();r[0]['arm_a']='CURRICULUM'
        with self.assertRaises(ValueError):m.analyze_main(r)

    def test_rehearsal_never_schedules_cross_model(self):
        s=seal()
        tasks=m.make_tasks(Path('/w'),Path('/exe'),s,'rehearsal')
        self.assertEqual(len(tasks),16)
        self.assertTrue(all(t['arm_a']==t['arm_b'] for t in tasks))
        main=m.make_tasks(Path('/w'),Path('/exe'),s,'production')
        self.assertEqual(len(main),288)
        self.assertTrue(all((t['arm_a'],t['arm_b'])==('HIER','CURRICULUM') for t in main))

    def test_worker_rejects_unadmitted_contrast_before_model_read(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'spec.json';m.write(p,{'mode':'rehearsal','arm_a':'HIER','arm_b':'CURRICULUM'})
            with self.assertRaisesRegex(ValueError,'WORKER_ARMS'):m.worker(p)

    def test_cold_audit_separates_first_and_later_requests(self):
        pairs=[{'kind':'sanity','games':[]} for _ in range(4)]
        for _ in range(18):
            pairs.append({'kind':'timing','games':[{'requests':[
                {'side':'A','wall_seconds':.5},{'side':'B','wall_seconds':.5},
                {'side':'A','wall_seconds':.07}]} for _ in range(2)]})
        r=m.audit_cold(pairs)
        self.assertEqual(r['over250_first'],72)
        self.assertEqual(r.get('over250_later',0),0)
        self.assertFalse(r['causal_initialization_attribution_proven'])

    def test_profile_and_effect_bounds(self):
        p=Path(m.__file__).resolve().parents[1]/'launch_profiles/cls-g0-strength-main-v1.json'
        profile=json.loads(p.read_text())
        self.assertEqual(profile['required_phases'],m.PHASES)
        self.assertEqual(profile['rehearsal_max_effects']['strength_games'],32)
        self.assertEqual(profile['production_max_effects']['strength_games'],576)
        self.assertEqual(profile['production_max_effects']['new_jass_searches'],576*162)
        self.assertEqual(profile['production_max_effects']['fits'],0)

    def test_confidence_formula_and_budget(self):
        h=math.sqrt(math.log(2/m.ALPHA)/(2*m.PAIRS))
        self.assertAlmostEqual(m.analyze_main(pair_rows())['hoeffding_radius'],h)
        self.assertAlmostEqual(m.SCORE_BOUNDARY,1/(1+10**.25))

    def test_whole_rehearsal_and_production_roundtrip(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);old=root/'old';result=root/'run';art=result/'artefacts'
            art.mkdir(parents=True)
            exe=root/'native';exe.write_text('synthetic native placeholder')
            stub=SimpleNamespace(MODEL_SHA=m.MODELS,BASE_CODE='7b789a0c675ce08868fe4a8fcef0becaa4193286',
                fetch_models=lambda w:{'synthetic_transport':True},build=lambda w:exe,
                validate_game=lambda g:None)
            with ExitStack() as st:
                st.enter_context(patch.object(m,'helpers',return_value=stub))
                st.enter_context(patch.object(m,'fetch_study',return_value=(set(),{},{})))
                st.enter_context(patch.object(m,'generate_openings',return_value=seal()))
                st.enter_context(patch.object(m,'run_tasks',side_effect=complete_rows))
                st.enter_context(patch.object(m.shutil,'disk_usage',return_value=SimpleNamespace(free=4*1024**3)))
                st.enter_context(patch.object(sys,'argv',['stage']))
                st.enter_context(patch.dict(os.environ,JASS_RESULT_DIR=str(result),JASS_ARTEFACT_DIR=str(art),LAUNCH_MODE='rehearsal'))
                self.assertEqual(m.main(),0)
                self.assertEqual(m.read(art/'study-report.json')['terminal'],m.READY)
                self.assertEqual(m.read(art/'scientific-summary.json')['cross_model_games'],0)
                with gzip.open(art/'stage-games.json.gz','rt') as f:self.assertEqual(len(json.load(f)['pairs']),16)
                art.rename(old)
                import shutil
                shutil.copytree(old,result/'launch-prerequisite')
                shutil.rmtree(result/'work')
                art.mkdir()
                m.write(result/'launch-prerequisite.json',{'verdict':'FULL_PIPELINE_REHEARSAL_PASS','published_roundtrip':True})
                os.environ['LAUNCH_MODE']='production'
                self.assertEqual(m.main(),0)
                self.assertEqual(m.read(art/'study-report.json')['terminal'],m.COMPLETE)
                self.assertEqual(m.read(art/'scientific-summary.json')['cross_model_games'],576)
                self.assertFalse(m.read(art/'scientific-summary.json')['promotion_authorized'])


if __name__=='__main__':unittest.main()
