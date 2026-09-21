from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from jobs.tools import cls_g0_panel_readiness as ready
from jobs.tools import cls_g0_panel_stage as stage


def synthetic_worker(task):
    import os,time
    if os.name != "nt":os.setsid()
    counts={"strength_games":2,"new_jass_searches":9}
    stage.durable_counts(Path(task["count_file"]),counts)
    if task.get("slow"):time.sleep(20)
    stage.atomic_json(Path(task["result_file"]),{"state":"completed","row":{"task_id":task["task_id"]},"counts":counts})


class PanelStageTests(unittest.TestCase):
    def context(self, root: Path, phase="local"):
        from jobs.tools import cls_g0_panel_gate_v1 as gate
        profile_path=root/"profile.json";profile_path.write_bytes((gate.ROOT/"jobs/launch_profiles/cls-g0-panel-v1.json").read_bytes())
        profile=json.loads(profile_path.read_text());plan=gate.build_plan("a"*40,stage.sha(profile_path))
        typed={"job_id":"cpx62-r","attempt_id":"attempt-1","launch_receipt_sha256":"1"*64,"publisher_manifest_sha256":"2"*64,"opening_selection_sha256":"b"*64}
        dep={"authenticated_readiness":typed} if phase!="readiness" else {}
        material=gate.materialize(plan,phase,dep)
        plan_path=root/"plan.json";plan_path.write_bytes(gate.canonical(plan))
        spec_path=root/"spec.json";spec_path.write_bytes(gate.canonical(material))
        return {"schema":stage.CONTEXT_SCHEMA,"phase":phase,"common_plan":plan,"common_plan_sha256":gate.digest(plan),
                "materialized_spec":material,"materialized_spec_sha256":gate.digest(material),"profile_sha256":stage.sha(profile_path),
                "code_sha":"a"*40,"command":profile["command"],"runtime_identity":plan["runtime_identity"],
                "opening_selection_sha256":typed["opening_selection_sha256"] if phase!="readiness" else None,
                "authenticated_dependencies":dep if phase!="readiness" else {"authenticated_readiness":plan["audit_2072"]},
                "paths":{"common_plan":str(plan_path),"spec":str(spec_path),"profile":str(profile_path)}}

    def test_context_rehashes_files_and_rejects_tamper(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); ctx = self.context(root)
            (root / "panel-admission-context.json").write_text(json.dumps(ctx))
            self.assertEqual(stage.load_context(root)["phase"], "local")
            (root / "spec.json").write_text("{}")
            with self.assertRaisesRegex(ValueError, "SPEC_PATH_DRIFT"):
                stage.load_context(root)

    def test_wdl_requires_technical_local_dependency_without_outcome(self):
        with tempfile.TemporaryDirectory() as tmp:
            ctx = self.context(Path(tmp), "wdl")
            with self.assertRaisesRegex(ValueError, "WDL_LOCAL_TECHNICAL_DEPENDENCY"):
                stage.authenticate_dependencies(ctx)
            ctx["authenticated_dependencies"]["local_technical_completion"] = {
                "prebound_local_job_id": "local", "prebound_local_admission_sha256": "c" * 64,
                "job_id": "local", "attempt_id": "attempt", "launch_receipt_sha256": "d" * 64,
                "scientific_verdict": None}
            stage.authenticate_dependencies(ctx)
            ctx["authenticated_dependencies"]["local_technical_completion"]["scientific_verdict"] = "WIN"
            with self.assertRaisesRegex(ValueError, "WDL_LOCAL_TECHNICAL_ONLY"):
                stage.authenticate_dependencies(ctx)

    def test_stage_finalizes_its_own_evidence_and_refuses_foreign_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); result, art = root / "result", root / "art"; result.mkdir(); ctx = self.context(root)
            seal = {"selection_sha256": "b" * 64}
            report = {"pairs": 288, "games": 576}
            runtime=root/"runtime.json";runtime.write_text("{}");ctx["paths"]["readiness_runtime"]=str(runtime)
            with mock.patch.object(stage, "authenticated_sources", return_value=({}, {"historical", "warmup"}, {})), \
                 mock.patch.object(stage, "verify_native", return_value=(root / "jass", {})), \
                 mock.patch.object(stage, "generate_and_seal", return_value=seal), \
                 mock.patch.object(stage, "model_paths", return_value={}), \
                 mock.patch.object(stage, "_forbidden", return_value={"historical"}), \
                 mock.patch.object(stage, "tasks_for", return_value=[]), \
                 mock.patch.object(stage, "execute", return_value=[]), \
                 mock.patch.object(stage, "validate", return_value=report):
                summary = stage.run(result, art, context=ctx)
            self.assertEqual(summary["state"], "completed")
            evidence = json.loads((art / "execution-evidence.json").read_text())
            self.assertEqual(evidence["completed_phases"], list(stage.PHASES))
            self.assertEqual(evidence["state"], "completed")
            self.assertTrue((art / "stage-games.json.gz").read_bytes().startswith(b"\x1f\x8b"))

    def test_readiness_stage_checkpoints_seal_and_serializes_real_report(self):
        from jobs.tests.test_cls_g0_panel_readiness import fens,raw,ReadinessContractTests
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);result=root/"result";result.mkdir();art=root/"art";ctx=self.context(root,"readiness")
            forbidden={ready.canonical_identity(ready.WARM_FEN),ready.canonical_identity("W:WK40:B11")}
            pool=raw(fens(ready.POOL_SIZE));seal=ready.seal_openings(pool,pool,forbidden)
            def execute(tasks,phase,art,evidence):
                evidence.value["actual_side_effects"].update(strength_games=56,new_jass_searches=168)
                evidence.value["timed_block_wall_seconds"]=6.0
                return [{**{k:task[k] for k in ("task_id","opening","arm_a","arm_b","kind")},"pair_wall_seconds":1.,
                         "games":[ReadinessContractTests._game(task,True),ReadinessContractTests._game(task,False)]} for task in tasks]
            with mock.patch.object(stage,"authenticated_sources",return_value=({},forbidden,{arm:root/arm for arm in ready.MODELS})),mock.patch.object(stage,"verify_native",return_value=(root/"jass",{})),mock.patch.object(stage,"generate_and_seal",return_value=seal),mock.patch.object(stage,"execute",side_effect=execute):
                summary=stage.run(result,art,context=ctx)
            self.assertEqual(summary["state"],"completed")
            self.assertEqual(json.loads((result/"panel-admission-context.json").read_text())["opening_selection_sha256"],seal["selection_sha256"])
            self.assertEqual(json.loads((art/"study-report.json").read_text())["games"],56)
            manifest=json.loads((art/"manifest.json").read_text())
            self.assertEqual(manifest["output_sha256"],{n:stage.sha(art/n) for n in stage.OUTPUTS if n!="manifest.json"})

    def test_summary_replacement_requires_stage_owned_publish_placeholder(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); art = root / "art"; art.mkdir()
            evidence = stage.StageEvidence(art, "production"); evidence.begin("publish")
            (art / "scientific-summary.json").write_text('{"schema":"foreign"}')
            with self.assertRaisesRegex(ValueError, "SUMMARY_OWNERSHIP"):
                stage.put_final_summary(art / "scientific-summary.json", {}, evidence)

    def test_scheduler_sums_two_concurrent_worker_snapshots(self):
        with tempfile.TemporaryDirectory() as tmp:
            art=Path(tmp); evidence=stage.StageEvidence(art,"rehearsal");evidence.begin("execute")
            tasks=[{"task_id":str(i),"kind":"timed"} for i in range(2)]
            rows=stage.execute(tasks,"readiness",art,evidence,worker=synthetic_worker)
            self.assertEqual([r["task_id"] for r in rows],["0","1"])
            self.assertEqual(evidence.value["actual_side_effects"]["strength_games"],4)
            self.assertEqual(evidence.value["actual_side_effects"]["new_jass_searches"],18)

    def test_scheduler_preserves_partial_work_on_timeout(self):
        with tempfile.TemporaryDirectory() as tmp:
            art=Path(tmp);evidence=stage.StageEvidence(art,"rehearsal");evidence.begin("execute")
            with self.assertRaisesRegex(ValueError,"PAIR_TIMEOUT"):
                stage.execute([{"task_id":"slow","kind":"timed","slow":True}],"readiness",art,evidence,
                              worker=synthetic_worker,pair_timeout=2)
            self.assertEqual(evidence.value["actual_side_effects"]["strength_games"],2)
            self.assertEqual(evidence.value["actual_side_effects"]["new_jass_searches"],9)

    def test_frozen_intervals_censoring_and_joint_mapping(self):
        import copy,gzip,math
        def rows(arm,score,cap=False):
            return [{"task_id":str(i),"arm_a":arm,"arm_b":"CURRICULUM","games":[
                {"a_is_white":white,"score_a":score,"reason":"ply cap" if cap else "3-fold repetition"} for white in (True,False)]} for i in range(288)]
        low=stage.contrast_report(rows("WDL",0),"WDL")
        high=stage.contrast_report(rows("WDL",1),"WDL")
        censored=stage.contrast_report(rows("WDL",.5,True),"WDL")
        self.assertAlmostEqual(low["hoeffding_radius"],.08722204497512172)
        self.assertEqual(low["contrast_verdict"],"SUBSTANTIAL_LOSS_SUPPORTED")
        self.assertEqual(high["contrast_verdict"],"SUBSTANTIAL_LOSS_EXCLUDED")
        self.assertEqual(censored["interval"],[0.,1.])
        self.assertEqual(censored["contrast_verdict"],"INDETERMINATE")
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/"local.json.gz"
            with gzip.open(p,"wb") as f:f.write(stage.canonical({"pairs":rows("LOCAL",0)}))
            ctx={"paths":{"local_stage_games":str(p)},"authenticated_dependencies":{"local_technical_completion":{"stage_games_sha256":stage.sha(p)}}}
            for report,terminal in ((low,"G0_PANEL_LOSS_CONCORDANT_ON_TWO_CASES_V1"),(high,"G0_PANEL_LARGE_LOSS_DISCORDANCE_REPLICATED_V1"),(censored,"G0_PANEL_INDETERMINATE_V1")):
                result=stage.joint_readout(ctx,report);self.assertEqual(result["terminal"],terminal)
                json.dumps(result,allow_nan=False)  # no circular report reference

    def test_historical_exclusions_use_exact_sources_not_score_fields(self):
        import csv,gzip,hashlib,copy
        from jobs.tools import cls_g0_panel_gate_v1 as gate
        from jobs.tools import cls_g0_panel_audit_stage as historical
        contract=gate.frozen_contract()
        with tempfile.TemporaryDirectory() as tmp:
            work=Path(tmp);audited=work/"audited";audited.mkdir();dirs={}
            game={"opening":"W:W32:B27","plies":1,"fens":["W:W32:B27","B:W21:B"]}
            forbidden_score="W:W40:B10"
            for label,n in (("calibration2066",44),("rehearsal2067",32),("rehearsal2068",32),("historical_match",576)):
                directory=audited/label;directory.mkdir();dirs[label]=directory
                payload={"pairs":[{"games":[game,game]} for _ in range(n//2)],"score":forbidden_score}
                name="stage-games.json.gz" if label=="historical_match" else contract["sources"][label]["artifact"]
                if name.endswith(".gz"):
                    with gzip.open(directory/name,"wb") as f:f.write(stage.canonical(payload))
                else:(directory/name).write_bytes(stage.canonical(payload))
            (dirs["historical_match"]/"opening-freeze.json").write_bytes(stage.canonical({"main":[{"fen":game["opening"]}]*288,"representative":[{"fen":"W:W41:B9"}]*8}))
            selection=audited/"selection1651";selection.mkdir();dirs["selection1651"]=selection
            with (selection/"parents.tsv").open("w",newline="") as out:
                writer=csv.DictWriter(out,fieldnames=["parent_id","canonical_fingerprint"],delimiter="\t");writer.writeheader()
                writer.writerows({"parent_id":str(i),"canonical_fingerprint":ready.canonical_identity("W:W39:B11")} for i in range(2000))
            (selection/"selection-report.json").write_bytes(stage.canonical({"passed":True,"cohort_identity_sha256":contract["sources"]["selection1651"]["cohort_identity_sha256"],"parents_tsv_sha256":stage.sha(selection/"parents.tsv")}))
            for arm in ready.MODELS:(audited/(arm+".pjtw")).write_bytes(b"synthetic model")
            original_sha=stage.sha
            def fixture_sha(path):return ready.MODELS[path.stem] if path.suffix==".pjtw" else original_sha(path)
            def extra(work,label,source,names):
                if label=="selection1651":self.assertIn("selection-report.json",names)
                return dirs[label],{"authenticated":True}
            with mock.patch.object(stage,"_fetch_2072",return_value={"synthetic":True}),mock.patch.object(historical,"get_contract",return_value=contract),mock.patch.object(historical,"authenticate",return_value=({"historical_match":dirs["historical_match"]},{})),mock.patch.object(historical,"fetch_source",side_effect=extra),mock.patch.object(stage,"sha",side_effect=fixture_sha):
                source,excluded,models=stage.authenticated_sources(work,{})
                self.assertEqual(source["parent_count"],2000);self.assertEqual(source["historical_start_count"],296)
                self.assertNotIn(ready.canonical_identity(forbidden_score),excluded)
                self.assertIn(ready.canonical_identity("W:W41:B9"),excluded)
                (dirs["calibration2066"]/"calibration-games.json").write_bytes(stage.canonical({"pairs":[]}))
                with self.assertRaisesRegex(ValueError,"HISTORICAL_GAME_COVERAGE"):
                    stage.authenticated_sources(work,{})

    def test_2072_fetch_rejects_missing_required_r2_artifact(self):
        from jobs.tools import fetch_result_files as transport
        inventory = {"job_id": stage.ready.AUDIT_2072_JOB, "attempt_id": stage.ready.AUDIT_2072_ATTEMPT,
                     "code_sha": stage.ready.AUDIT_2072_CODE, "result_state": "completed", "exit_code": 0,
                     "files": []}
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(transport, "inspect_result_inventory", return_value=inventory):
            with self.assertRaisesRegex(ValueError, "AUDIT_2072_ARTIFACT_MISSING"):
                stage._fetch_2072(Path(tmp))


if __name__ == "__main__":
    unittest.main()
