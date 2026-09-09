"""Synthetic-only V2 wiring tests; no live control repository or R2 calls."""
from __future__ import annotations
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace
from jobs.tools import ed4_source_inventory_stage as stage
from jobs.tools import ed4_source_descriptor_inventory as inventory
from jobs.tools.launch_runtime_v2 import EFFECTS
from jobs.tests import test_ed4_source_descriptor_inventory as fixtures


def fixture_inputs(*, missing=False, unknown=False, host_drift=False):
    case = fixtures.Inventory()
    catalog, store = case.fixtures()
    if missing:
        job, attempt, code, paths = inventory.SOURCES['n1']
        prefix, raw = fixtures.envelope(job, attempt, code, paths[:-1])
        store[prefix] = raw
    if unknown:
        catalog.append(dict(job_id='cpx62-1780-unclaimed-v1', attempt_id=None,
                            code_sha=None, state=None, host=None, exit_code=None))
    if host_drift:
        catalog[0]['host'] = 'legacy-status-alias'
    calls = []
    transport = case.transport(store, calls)
    def catalog_reader(repo, sha):
        case.assertEqual(sha, inventory.CONTROL_SHA)
        return catalog
    def collector(items):
        return stage.collect_metadata(items, transport=transport)
    return catalog_reader, collector, calls, store


def fixture_run(result, artifact, mode='rehearsal', **options):
    reader, collector, calls, _ = fixture_inputs(**options)
    summary = stage.run(artifact, mode, result / 'synthetic-control',
                        catalog_reader=reader, collector=collector)
    if not calls or any(name not in {'_SUCCESS', '_FAILED', 'manifest.json',
                                    'inventory.json', 'checksums.sha256'}
                        for _, name in calls):
        raise AssertionError('fixture_transport_scope')
    return summary


class InventoryStageTests(unittest.TestCase):
    def test_ready_complete_phases_and_no_scientific_authorization(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); art = root / 'artefacts'
            summary = fixture_run(root, art)
            report = stage.read_json(art / stage.OUTPUT)
            evidence = stage.read_json(art / 'execution-evidence.json')
            self.assertEqual(report['verdict'], 'ED4_C0A_INVENTORY_ADMISSION_READY_V1')
            self.assertEqual(evidence['completed_phases'], stage.PHASES)
            self.assertEqual(evidence['state'], 'completed')
            self.assertEqual(evidence['actual_side_effects'], {k: 0 for k in EFFECTS})
            self.assertEqual(summary['inventory_sha256'], inventory.digest((art / stage.OUTPUT).read_bytes()))
            self.assertIsNone(summary['scientific_verdict'])
            for key in ('scientific_success_established', 'source_audit_completed',
                        'confirmation_authorized', 'runtime_authorized', 'automatic_continuation'):
                self.assertIs(summary[key], False)
            self.assertTrue(all(report[k] == summary[k] == 0 for k in inventory.ZERO_READS))

    def test_status_host_drift_does_not_change_authenticated_source_identity(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); art = root / 'artefacts'
            summary = fixture_run(root, art, host_drift=True)
            self.assertEqual(summary['verdict'], 'ED4_C0A_INVENTORY_ADMISSION_READY_V1')
            self.assertEqual(stage.read_json(art / 'execution-evidence.json')['state'], 'completed')

    def test_missing_and_unknown_are_completed_insufficient(self):
        for option in ('missing', 'unknown'):
            with self.subTest(option=option), tempfile.TemporaryDirectory() as td:
                root = Path(td); art = root / 'artefacts'
                summary = fixture_run(root, art, **{option: True})
                self.assertEqual(summary['verdict'], 'ED4_C0A_INVENTORY_ADMISSION_INSUFFICIENT_V1')
                self.assertEqual(summary['state'], 'completed')
                self.assertEqual(stage.read_json(art / 'execution-evidence.json')['state'], 'completed')
                self.assertEqual(summary['missing_paths_count'] + summary['unclassified_producers_count'], 1)

    def test_rehearsal_and_production_have_identical_inventory(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            for mode in ('rehearsal', 'production'):
                fixture_run(root, root / mode, mode=mode, unknown=True)
            self.assertEqual((root / 'rehearsal' / stage.OUTPUT).read_bytes(),
                             (root / 'production' / stage.OUTPUT).read_bytes())

    def test_corrupt_envelope_fails_at_authentication(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); art = root / 'artefacts'
            reader, collector, _, store = fixture_inputs()
            next(iter(store.values()))['inventory.json'] += b' '
            with self.assertRaises((ValueError, RuntimeError)):
                stage.run(art, 'rehearsal', root, catalog_reader=reader, collector=collector)
            evidence = stage.read_json(art / 'execution-evidence.json')
            self.assertEqual(evidence['state'], 'failed')
            self.assertEqual(evidence['completed_phases'], [stage.PHASES[0]])
            self.assertEqual(evidence['phase'], stage.PHASES[1])
            self.assertEqual(stage.read_json(art / stage.OUTPUT)['verdict'], stage.FAILURE)

    def test_exception_text_is_not_published(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); art = root / 'artefacts'
            def fail(*args):
                raise RuntimeError('FORBIDDEN_TARGET_SENTINEL credential-placeholder')
            with self.assertRaises(RuntimeError):
                stage.run(art, 'rehearsal', root, catalog_reader=fail)
            for path in art.glob('*.json'):
                text = path.read_text()
                self.assertNotIn('FORBIDDEN_TARGET_SENTINEL', text)
                self.assertNotIn('credential-placeholder', text)
            self.assertEqual(stage.read_json(art / stage.OUTPUT)['failure_type'], 'RuntimeError')

    def test_inconsistent_builder_report_fails_closed(self):
        for field, value in [('state', 'running'), ('verdict', 'unknown'),
                             ('control_snapshot_commit', 'a' * 40), ('model_reads', 1)]:
            with self.subTest(field=field), tempfile.TemporaryDirectory() as td:
                root = Path(td); art = root / 'artefacts'
                reader, collector, _, _ = fixture_inputs()
                def builder(*args):
                    report = inventory.build(*args)
                    report[field] = value
                    return report
                with self.assertRaises(ValueError):
                    stage.run(art, 'rehearsal', root, catalog_reader=reader,
                              collector=collector, builder=builder)
                self.assertEqual(stage.read_json(art / 'execution-evidence.json')['state'], 'failed')
                if field == 'model_reads':
                    self.assertEqual(stage.read_json(art / stage.OUTPUT)['model_reads'], 1)
                    self.assertEqual(stage.read_json(art / 'scientific-summary.json')['model_reads'], 1)

    def test_readback_disagreement_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); art = root / 'artefacts'
            with patch.object(stage, 'read_json', return_value={}), self.assertRaises(ValueError):
                fixture_run(root, art)
            self.assertEqual(json.loads((art / stage.OUTPUT).read_text())['verdict'], stage.FAILURE)
            self.assertEqual(json.loads((art / 'execution-evidence.json').read_text())['completed_phases'],
                             stage.PHASES[:-1])

    def test_disk_floor_rejects_before_any_catalog_read(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); art = root / 'artefacts'
            with patch.object(stage.shutil, 'disk_usage', return_value=SimpleNamespace(free=0)), \
                 patch.object(inventory, '_git') as git, self.assertRaises(ValueError):
                stage.run(art, 'rehearsal', root)
            git.assert_not_called()
            self.assertEqual(stage.read_json(art / 'execution-evidence.json')['completed_phases'], [])

    def test_profile_matches_entrypoint_evidence_and_zero_effects(self):
        profile = json.loads((stage.ROOT / 'jobs/launch_profiles/ed4-source-inventory-v1.json').read_text())
        self.assertEqual(profile['schema'], 'jass.launch_profile.v2')
        self.assertEqual(profile['required_phases'], stage.PHASES)
        self.assertEqual(profile['evidence_outputs'], [stage.OUTPUT])
        self.assertEqual(profile['command'][1:], ['jobs/tools/ed4_source_inventory_stage.py'])
        for mode in ('rehearsal', 'production'):
            self.assertEqual(profile[mode + '_max_effects'], {k: 0 for k in EFFECTS})
        for suite in ('jobs.tests.test_launch_gate_v2', 'jobs.tests.test_launch_gate_pipeline_v2',
                      'jobs.tests.test_ed4_source_descriptor_inventory',
                      'jobs.tests.test_ed4_source_inventory_stage',
                      'jobs.tests.test_ed4_source_inventory_pipeline'):
            self.assertIn(suite, profile['regressions'])


if __name__ == '__main__':
    unittest.main()
