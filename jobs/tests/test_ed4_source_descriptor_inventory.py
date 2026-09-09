import json
import unittest
from unittest.mock import patch
from types import SimpleNamespace
from jobs.tools import ed4_source_descriptor_inventory as m
from jobs.tools.ed4_metadata_projection import project, STATUS, INVENTORY


def encoded(value):
    return json.dumps(value, indent=2).encode()


def envelope(job, attempt, code, paths, state='completed'):
    prefix = f'r2:jass-data/runs/{job}/{attempt}'
    manifest = encoded(dict(job_id=job, attempt_id=attempt, code_sha=code,
        host=job.split('-')[0], state=state, exit_code=0 if state == 'completed' else 2,
        scientific_summaries={'q200': [987654321.25], 'wdl': 'FORBIDDEN_SENTINEL'}))
    files = [dict(path=p, size_bytes=123, sha256=m.EXPECTED_HASHES.get(p, 'a'*64)) for p in paths]
    if not any(x['path'] == 'manifest.json' for x in files):
        files.append(dict(path='manifest.json', size_bytes=len(manifest), sha256=m.digest(manifest)))
    else:
        item = next(x for x in files if x['path'] == 'manifest.json')
        item.update(size_bytes=len(manifest), sha256=m.digest(manifest))
    inventory = encoded(dict(files=files))
    checks = '\n'.join(f"{x['sha256']}  {x['path']}" for x in files)
    checks += f'\n{m.digest(inventory)}  inventory.json\n'
    return prefix, {'manifest.json': manifest, 'inventory.json': inventory,
        'checksums.sha256': checks.encode(), '_SUCCESS' if state == 'completed' else '_FAILED': b'ok'}


class Projection(unittest.TestCase):
    def test_unknown_values_never_decoded(self):
        raw = b'{"scientific\\u005fsummaries":{"q200":[987654321.25,"FORBIDDEN_SENTINEL"],"x":true},"job_id" : "safe"}'
        decoded = []
        def leaf(token):
            decoded.append(token)
            self.assertNotIn('987654321', token)
            self.assertNotIn('FORBIDDEN_SENTINEL', token)
            return json.loads(token)
        self.assertEqual(project(raw, STATUS, leaf), {'job_id': 'safe'})
        self.assertEqual(decoded, ['"safe"'])

    def test_inventory_escaped_keys_and_path_values(self):
        raw = b'{"fi\\u006ces":[{"sha256":"abc","score":{"a":99},"path" : "model-name-is-metadata","size_bytes":2}],"ignored":[false,null]}'
        self.assertEqual(project(raw, INVENTORY), {'files': [{'sha256': 'abc', 'path': 'model-name-is-metadata', 'size_bytes': 2}]})

    def test_malformed_duplicate_and_wrong_types_fail(self):
        for raw in ['{} garbage', '{"job_id":"a","job\\u005fid":"b"}',
            '{"ignored":[1,]}', '{"ignored":{"a":1,}}', '{"ignored":"\\z"}',
            '{"ignored":01}', '{"ignored":NaN}', '{"exit_code":true}',
            '{"job_id":{"q200":1}}', '{"ignored":{"x":1,"x":2}}']:
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                project(raw, STATUS)


class Inventory(unittest.TestCase):
    def fixtures(self):
        catalog, store = [], {}
        for job, attempt, code, paths in m.SOURCES.values():
            self.assertEqual(len(code), 40)
            state, exit_code = m.SOURCE_TERMINALS[job]
            prefix, raw = envelope(job, attempt, code, paths, state)
            store[prefix] = raw
            if not job.startswith('home-1651'):
                catalog.append(dict(job_id=job, attempt_id=attempt, code_sha=code,
                    state=state, exit_code=exit_code, host='cpx62', result_uri=prefix))
        return catalog, store

    def transport(self, store, calls):
        def reader(_, prefix, name):
            calls.append((prefix, name))
            self.assertIn(name, {'_SUCCESS', '_FAILED', 'manifest.json', 'inventory.json', 'checksums.sha256'})
            return store[prefix][name]
        return lambda rclone, prefix, state='completed': m.metadata_transport(rclone, prefix, state, reader)

    def test_home_scan_uses_result_manifest_not_nonexistent_artifact_manifest(self):
        paths = m.SOURCES['home'][3]
        self.assertIn('manifest.json', paths)
        self.assertNotIn('artefacts/manifest.json', paths)

    def test_full_synthetic_admission_roundtrip_only_envelopes(self):
        catalog, store = self.fixtures()
        calls = []
        meta = m.collect(catalog, transport=self.transport(store, calls))
        report = m.build(meta, catalog, 'b'*64, b'protocol')
        self.assertEqual(report['verdict'], 'ED4_C0A_INVENTORY_ADMISSION_READY_V1')
        self.assertEqual(len(report['sources']), 9)
        self.assertEqual(len(calls), 36)
        self.assertTrue(all(report[key] == 0 for key in m.ZERO_READS))
        self.assertEqual(json.loads(json.dumps(report)), report)
        home = next(x for x in report['sources'] if x['job_id'] == m.SOURCES['home'][0])
        self.assertTrue(all(x['present'] for x in home['required_paths']))
        d4 = next(x for x in report['sources'] if x['job_id'] == m.SOURCES['d4'][0])
        self.assertEqual((d4['result_state'], d4['exit_code'], d4['classification']),
                         ('failed', 2, 'included_exact'))

    def test_literal_d4_state_cannot_be_replaced(self):
        catalog, store = self.fixtures()
        row = next(x for x in catalog if x['job_id'] == m.SOURCES['d4'][0])
        row.update(state='completed', exit_code=0)
        calls = []
        with self.assertRaises(ValueError):
            m.collect(catalog, transport=self.transport(store, calls))
        self.assertEqual(calls, [])

    def test_failed_job_authenticated_then_unknown(self):
        catalog, store = self.fixtures()
        job, attempt, code = 'cpx62-1774-synthetic-v1', '20260901T000000Z-aaaaaaaa', 'a'*40
        prefix, raw = envelope(job, attempt, code, ['artefacts/report.json'], 'failed')
        store[prefix] = raw
        catalog.append(dict(job_id=job, attempt_id=attempt, code_sha=code, host='cpx62',
            state='failed', exit_code=2, result_uri=prefix))
        calls = []
        meta = m.collect(catalog, transport=self.transport(store, calls))
        report = m.build(meta, catalog, 'b'*64, b'p')
        self.assertIn((prefix, '_FAILED'), calls)
        self.assertEqual(report['unknown_or_unclassified_producers'], [job])
        self.assertEqual(len(report['sources']), 10)
        self.assertTrue(report['verdict'].endswith('INSUFFICIENT_V1'))

    def test_nonexecuted_null_host_is_skipped_and_unknown_at_base_inventory(self):
        catalog, store = self.fixtures()
        job = 'cpx62-1820-l3-decision-math-b2-terminal-classified-failure-zero-placeholder-repair-v1'
        raw = json.dumps(dict(job_id=job, attempt_id=None, code_sha=None,
            state='failed', exit_code=-1, host=None)).encode()
        self.assertEqual(m.project_status(raw)['host'], None)
        with self.assertRaises(ValueError):
            m.project_manifest(raw)
        catalog.append(dict(job_id=job, attempt_id=None, code_sha=None,
            state='failed', exit_code=-1, host=None))
        calls = []
        meta = m.collect(catalog, transport=self.transport(store, calls))
        self.assertNotIn(job, {key[0] for key in meta})
        report = m.build(meta, catalog, 'b'*64, b'p')
        self.assertIn(job, report['unknown_or_unclassified_producers'])

    def test_missing_path_is_insufficient(self):
        catalog, store = self.fixtures()
        job, attempt, code, paths = m.SOURCES['n1']
        prefix, raw = envelope(job, attempt, code, paths[:-1])
        store[prefix] = raw
        meta = m.collect(catalog, transport=self.transport(store, []))
        report = m.build(meta, catalog, 'b'*64, b'p')
        self.assertEqual(report['missing_paths'], [{'job_id': job, 'path': 'work/current.jsm'}])
        self.assertTrue(report['verdict'].endswith('INSUFFICIENT_V1'))

    def test_corruption_and_identity_rejected(self):
        for variant in ['manifest', 'inventory', 'checksums', 'size', 'duplicate', 'identity']:
            with self.subTest(variant=variant):
                catalog, store = self.fixtures()
                raw = store[catalog[0]['result_uri']]
                if variant in {'manifest', 'inventory', 'checksums'}:
                    name = {'manifest': 'manifest.json', 'inventory': 'inventory.json', 'checksums': 'checksums.sha256'}[variant]
                    raw[name] += b' '
                elif variant == 'identity':
                    catalog[0]['code_sha'] = '0'*40
                else:
                    inv = json.loads(raw['inventory.json'])
                    if variant == 'size':
                        next(x for x in inv['files'] if x['path'] == 'manifest.json')['size_bytes'] += 1
                    else:
                        inv['files'].append(inv['files'][0])
                    raw['inventory.json'] = encoded(inv)
                    lines = raw['checksums.sha256'].decode().splitlines()
                    raw['checksums.sha256'] = ('\n'.join(x for x in lines if not x.endswith('  inventory.json')) +
                        '\n' + m.digest(raw['inventory.json']) + '  inventory.json\n').encode()
                with self.assertRaises((ValueError, RuntimeError)):
                    m.collect(catalog, transport=self.transport(store, []))

    def test_catalog_omission_duplicate_and_snapshot_rejected(self):
        catalog, store = self.fixtures()
        meta = m.collect(catalog, transport=self.transport(store, []))
        for bad in [[], catalog[:-1], catalog + [catalog[0]]]:
            with self.assertRaises(ValueError):
                m.build(meta, bad, 'b'*64, b'p')
        with self.assertRaises(ValueError):
            m.control_catalog('unused', '0'*40)

    def test_git_catalog_projection(self):
        job = 'cpx62-1773-synthetic-v1'
        unclaimed = 'cpx62-1780-unclaimed-v1'
        def git(_, args):
            if args[0] == 'rev-parse':
                return m.CONTROL_SHA.encode()
            if args[0] == 'ls-tree':
                return f'status/{job}.json\nqueue/done/{job}.sh\nqueue/pending/{unclaimed}.sh\nstatus/cpx62-1889-later-v1.json\n'.encode()
            return encoded(dict(job_id=job, state='failed', scientific_summaries={'q200': 999}))
        rows = m.control_catalog('fixture', m.CONTROL_SHA, git)
        self.assertEqual([x['job_id'] for x in rows], [job, unclaimed])
        self.assertNotIn('scientific_summaries', rows[0])
        self.assertEqual(rows[0]['queue_paths'], [f'queue/done/{job}.sh'])
        self.assertIsNone(rows[1]['state'])

    def test_payload_request_rejected_before_subprocess(self):
        with patch.object(m.subprocess, 'run') as run, self.assertRaises(ValueError):
            m.remote_envelope('rclone', 'unused', 'artefacts/ED4_CHOICE.pjtw')
        run.assert_not_called()

    def test_measured_inventory_size_fits_bounded_transport(self):
        largest_observed_inventory = b' ' * 18121658
        with patch.object(m.subprocess, 'run', return_value=SimpleNamespace(returncode=0, stdout=largest_observed_inventory)):
            self.assertEqual(len(m.remote_envelope('rclone', 'fixture', 'inventory.json')), 18121658)
        with patch.object(m.subprocess, 'run', return_value=SimpleNamespace(returncode=0, stdout=b' ' * (32*1024*1024+1))):
            with self.assertRaises(ValueError):
                m.remote_envelope('rclone', 'fixture', 'inventory.json')


if __name__ == '__main__':
    unittest.main()
