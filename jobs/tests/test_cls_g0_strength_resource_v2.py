from __future__ import annotations
from contextlib import ExitStack
import inspect
import os
import sys
import tempfile
from types import SimpleNamespace
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from jobs.tools import cls_g0_strength_main as base
from jobs.tools import cls_g0_strength_main_resource_v2 as v2


class ResourceOnlyTests(unittest.TestCase):
    def test_old_admission_default_is_unchanged(self):
        sig = inspect.signature(base.main)
        self.assertEqual(sig.parameters['projected_work_ceiling'].default, 2700)
        self.assertEqual(base.MAIN_WORK_CAP, 2700)

    def test_new_entrypoint_pins_original_openings_and_resource_only(self):
        with patch.object(base, 'main', return_value=0) as run:
            self.assertEqual(v2.main(),0)
            run.assert_called_once_with(projected_work_ceiling=3000,
                expected_selection_sha='0a9497f68387b1e0b65a36a9d0da538e9cfd7932167c0d2b0f664e15b81c53c1')
        self.assertEqual(base.PAIRS,288)
        self.assertEqual(base.LOSS_ELO,100)
        self.assertEqual(base.RESPONSE_LIMIT,.120)
        self.assertEqual(base.MOVETIME,.1)
        self.assertEqual(base.MAIN_WORK_CAP,2700)

    def test_profile_scientific_effects_and_phase_identity(self):
        root=Path(base.__file__).resolve().parents[1]/'launch_profiles'
        old=json.loads((root/'cls-g0-strength-main-v1.json').read_text())
        new=json.loads((root/'cls-g0-strength-main-resource-v2.json').read_text())
        for key in ('campaign','required_phases','evidence_outputs','rehearsal_max_effects','production_max_effects'):
            self.assertEqual(old[key],new[key])
        self.assertEqual(new['regressions'][:-1],old['regressions'])
        self.assertIn('ORIGINAL_2067_SELECTION_DRIFT',inspect.getsource(base))


    def run_preparation_fixture(self, use_resource_v2: bool) -> dict:
        from jobs.tests.test_cls_g0_strength_main import seal, complete_rows
        selected=seal()
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); result=root/'result';art=result/'artefacts';art.mkdir(parents=True)
            exe=root/'exe';exe.write_text('synthetic')
            stub=SimpleNamespace(MODEL_SHA=base.MODELS,BASE_CODE='native-unchanged',
                fetch_models=lambda w:{},build=lambda w:exe,validate_game=lambda g:None)
            with ExitStack() as stack:
                stack.enter_context(patch.object(base,'helpers',return_value=stub))
                stack.enter_context(patch.object(base,'fetch_study',return_value=(set(),{},{})))
                stack.enter_context(patch.object(base,'generate_openings',return_value=selected))
                stack.enter_context(patch.object(base,'run_tasks',side_effect=complete_rows))
                stack.enter_context(patch.object(base.shutil,'disk_usage',return_value=SimpleNamespace(free=4*1024**3)))
                stack.enter_context(patch.object(base.time,'monotonic',side_effect=[0,153.23255123593844]))
                stack.enter_context(patch.object(sys,'argv',['stage']))
                stack.enter_context(patch.dict(os.environ,JASS_RESULT_DIR=str(result),JASS_ARTEFACT_DIR=str(art),LAUNCH_MODE='rehearsal'))
                # The synthetic selection is deliberately not the real immutable cohort.
                stack.enter_context(patch.object(v2,'ORIGINAL_SELECTION_SHA',selected['selection_sha256']))
                self.assertEqual(v2.main() if use_resource_v2 else base.main(),0)
                return base.read(art/'study-report.json')

    def test_original_2067_resource_block_is_preserved(self):
        r=self.run_preparation_fixture(False)
        self.assertEqual(r['terminal'],'CLS_G0_STRENGTH_MAIN_PREPARATION_BLOCKED_V1')
        self.assertFalse(r['production_ready'])
        self.assertEqual(r['main_work_ceiling_seconds'],2700)

    def test_new_resource_admission_only_changes_planning_allowance(self):
        r=self.run_preparation_fixture(True)
        self.assertEqual(r['terminal'],base.READY)
        self.assertTrue(r['production_ready'])
        self.assertEqual(r['main_work_ceiling_seconds'],3000)
        self.assertEqual(r['cross_model_games'],0)
        self.assertAlmostEqual(r['projected_main_work_seconds'],2758.185922246892)


if __name__=='__main__':unittest.main()
