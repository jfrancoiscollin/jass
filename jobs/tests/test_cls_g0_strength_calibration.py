from __future__ import annotations
import json
import math
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

from jobs.tools import cls_g0_strength_calibration as c


def game(index=0, colour=True):
    opening=c.openings()[index]
    return {"opening":opening,"a_is_white":colour,"outcome":"D","score_a":.5,
        "plies":1,"reason":"3-fold repetition","moves":["20-25"],"fens":[opening,opening],
        "requests":[{"side":"A","wall_seconds":.1,"nodes":100,"depth":3,"eval_calls":20}],
        "game_wall_seconds":.2}


def pairs():
    result=[]
    for kind in ("sanity","timing"):
        for arm in c.MODEL_SHA:
            for i in range(2 if kind=="sanity" else 9):
                result.append({"task_id":f"{kind}-{arm}-{i}","kind":kind,"arm":arm,
                    "model_sha256":c.MODEL_SHA[arm],"games":[game(i,True),game(i,False)]})
    return result


class CalibrationTests(unittest.TestCase):
    def test_frozen_scope(self):
        self.assertEqual(c.MAX_GAMES,44)
        self.assertEqual(c.MAX_SEARCHES,7040)
        self.assertEqual(c.MOVETIME,.1)
        self.assertEqual(c.MAX_PLIES,160)
        self.assertEqual(c.WORKERS,4)
        for value in c.MODEL_SHA.values():
            self.assertEqual(len(value),64)
        self.assertEqual(c.HIER_JOB,"cpx62-2062-l3-cls-hier-l2-hier-candidate-rehearsal-v1")

    def test_openings_are_all_nine_known_first_moves(self):
        seen=c.openings()
        self.assertEqual(len(seen),9)
        self.assertEqual(len(set(seen)),9)
        for fen,(origin,dest) in zip(seen,c.FIRST_MOVES):
            men=set(map(int,fen.split(":")[1][1:].split(",")))
            self.assertEqual(len(men),20)
            self.assertNotIn(origin,men)
            self.assertIn(dest,men)
            self.assertTrue(fen.startswith("B:W") and fen.endswith(":B1-20"))

    def test_tasks_are_same_model_only_and_balanced(self):
        work=Path("/synthetic"); exe=Path("/synthetic/jass")
        tasks=c.tasks(work,exe,"sanity")+c.tasks(work,exe,"timing")
        self.assertEqual(len(tasks),22)
        self.assertEqual(len({t["task_id"] for t in tasks}),22)
        for t in tasks:
            self.assertEqual(Path(t["model"]).name,t["arm"]+".pjtw")
        self.assertNotIn("pattern_b",str(tasks))

    def test_invalid_worker_mode_is_rejected_before_model_read(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"spec.json"
            c.write(p,{"arm":"HIER","kind":"main"})
            with self.assertRaises(ValueError):c.worker(p)

    def test_worker_rejects_wrong_model_bytes(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); model=root/"bad.pjtw";model.write_bytes(b"wrong")
            p=root/"spec.json"
            c.write(p,{"arm":"HIER","kind":"timing","opening":c.openings()[0],"model":str(model)})
            with self.assertRaisesRegex(ValueError,"WORKER_MODEL_SHA"):c.worker(p)

    def test_bad_technical_results_are_never_draws(self):
        for reason in ("game time cap","illegal move 1-2 from A","unknown termination"):
            row=game();row["reason"]=reason
            with self.assertRaises(ValueError):c.validate_game(row)

    def test_bad_numeric_or_incomplete_trajectory_is_rejected(self):
        row=game();row["requests"][0]["wall_seconds"]=math.nan
        with self.assertRaises(ValueError):c.validate_game(row)
        row=game();row["fens"].pop()
        with self.assertRaises(ValueError):c.validate_game(row)
        row=game();row["score_a"]=0
        with self.assertRaises(ValueError):c.validate_game(row)

    def test_complete_all_pair_summary(self):
        report=c.summarize(pairs())
        self.assertEqual(set(report),{"sanity_CURRICULUM","sanity_HIER","timing_CURRICULUM","timing_HIER"})
        self.assertEqual(sum(r["games"] for r in report.values()),44)
        self.assertEqual(report["timing_HIER"]["games"],18)
        self.assertEqual(report["timing_HIER"]["moves_above_250ms"],0)
        self.assertNotIn("elo",str(report))

    def test_missing_duplicate_and_wrong_identity_pairs_fail_closed(self):
        for value in (pairs()[:-1],pairs()[:-1]+[pairs()[0]]):
            with self.assertRaises(ValueError):c.summarize(value)
        value=pairs();value[0]["model_sha256"]="0"*64
        with self.assertRaises(ValueError):c.summarize(value)
        value=pairs();value[0]["games"][0]["opening"]=c.openings()[1]
        with self.assertRaises(ValueError):c.summarize(value)

    def test_wrong_pair_colour_fails(self):
        value=pairs();value[0]["games"][1]["a_is_white"]=True
        with self.assertRaises(ValueError):c.summarize(value)

    def test_no_clobber_and_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"r.json"; obj={"pairs":pairs()}
            c.write(p,obj);self.assertEqual(c.read(p),obj)
            with self.assertRaises(ValueError):c.write(p,obj)
            c.write(p,{"update":1},replace=True);self.assertEqual(c.read(p),{"update":1})

    def test_worker_environment_excludes_policy_and_credentials(self):
        with mock.patch.dict(os.environ,{"JASS_SEARCH_PARAMS":"forbidden","RCLONE_CONFIG_R2_SECRET_ACCESS_KEY":"secret"}):
            env=c.worker_env()
        self.assertNotIn("JASS_SEARCH_PARAMS",env)
        self.assertNotIn("RCLONE_CONFIG_R2_SECRET_ACCESS_KEY",env)
        self.assertEqual(env["JASS_EGDB_CACHE_MB"],"256")

    def test_command_timeout_is_bounded(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(__import__("subprocess").TimeoutExpired):
                c.command([sys.executable,"-c","import time;time.sleep(10)"],Path(d)/"log",.1)

    def test_worker_complete_path_with_synthetic_games(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);spec=c.tasks(root,root/"jass","sanity")[0]
            sp=root/"spec.json";c.write(sp,spec)
            with mock.patch.object(c,"sha",return_value=c.PARENT_SHA),mock.patch.object(c,"native_game",side_effect=[game(),game(colour=False)]):
                c.worker(sp)
            self.assertEqual(c.read(Path(spec["output"]))["games"],[game(),game(colour=False)])

    def test_complete_stage_with_real_evidence_and_synthetic_transport(self):
        from jobs.tools.launch_runtime_v2 import StageEvidence
        with tempfile.TemporaryDirectory() as d:
            result=Path(d);art=result/"artefacts";art.mkdir()
            def fake_build(work):
                exe=work/"fake-jass";exe.write_bytes(b"synthetic binary")
                (work/"egdb-selfcheck.log").write_text("synthetic selfcheck")
                return exe
            def fake_tasks(items,work,artifact,evidence):
                kind=items[0]["kind"]
                selected=[r for r in pairs() if r["kind"]==kind]
                evidence.record_effect("strength_games",2*len(selected))
                evidence.record_effect("new_jass_searches",2*len(selected))
                c.write(artifact/"calibration-progress.json",{"synthetic":True},replace=True)
                return selected
            with mock.patch.dict(os.environ,{"JASS_RESULT_DIR":str(result),"JASS_ARTEFACT_DIR":str(art),"LAUNCH_MODE":"rehearsal"}), \
                 mock.patch.object(sys,"argv",["calibration"]), \
                 mock.patch.object(c,"fetch_models",return_value={"synthetic":True}), \
                 mock.patch.object(c,"build",side_effect=fake_build), \
                 mock.patch.object(c,"run_tasks",side_effect=fake_tasks), \
                 mock.patch.object(c.shutil,"disk_usage",return_value=type("Disk",(),{"free":4*1024**3})()):
                self.assertEqual(c.main(),0)
            evidence=c.read(art/"execution-evidence.json")
            self.assertEqual(evidence["state"],"completed")
            self.assertEqual(evidence["completed_phases"],c.PHASES)
            self.assertEqual(evidence["actual_side_effects"]["strength_games"],44)
            summary=c.read(art/"scientific-summary.json")
            self.assertFalse(summary["main_match_admitted"])
            self.assertIsNone(summary["scientific_verdict"])
            profile=c.read(Path(__file__).resolve().parents[2]/"jobs/launch_profiles/cls-g0-strength-calibration-v1.json")
            for name in profile["evidence_outputs"]:
                self.assertGreater((art/name).stat().st_size,0,name)

    def test_profile_enforces_calibration_and_no_main_match(self):
        root=Path(__file__).resolve().parents[2]
        p=json.loads((root/"jobs/launch_profiles/cls-g0-strength-calibration-v1.json").read_text())
        self.assertEqual(p["required_phases"],c.PHASES)
        for key in ("rehearsal_max_effects","production_max_effects"):
            self.assertEqual(p[key]["strength_games"],44)
            self.assertEqual(p[key]["new_jass_searches"],7040)
            self.assertTrue(all(p[key][x]==0 for x in ("fits","promotions","bakes","test_target_reads","new_scan_searches","selfplay_games")))
        text=(root/"docs/experiments/L3_CLS_G0_STRENGTH_VALIDATION_V1_20260920.md").read_text()
        self.assertIn("MAIN MATCH NOT YET ADMITTED",text)
        self.assertIn("explicitly grants a limited study-only exception",text)

if __name__=="__main__":unittest.main()
