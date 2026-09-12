"""Authenticated transport for the frozen, target-blind linkage diagnostic."""
from __future__ import annotations
import collections
import hashlib
import json
from pathlib import Path

from jobs.tools import ed4_c0c_exclusion_union as c0c
from jobs.tools import fetch_result_files as fetch
from jobs.tools.ed4_c0c_exact_linkage_diagnostic import (
    OUTPUT_NAME, _canonical, _deadline, _need, _schema_from_manifest,
    build_synthetic_diagnostic, descriptor_key, expected_descriptors,
)
from jobs.tools.launch_runtime_v2 import atomic_json

POLICY_NAME = 'ed4-c0c-exact-linkage-read-policy-v1.json'
SUMMARY_FIELDS = ('schema','state','classification','terminal','descriptor_count',
    'resolved_descriptor_count','unresolved_descriptor_count','recovery_evidence_sha256',
    'manifest_sha256','parent_diagnostic_sha256','parent_failure_rows_sha256',
    'read_ledger','target_reads','score_reads','wdl_reads','qvalue_reads','model_reads',
    'teacher_calls','search_calls','fits','games','alpha_spent','scientific_verdict',
    'confirmation_authorized','automatic_continuation')


def validate_metadata(manifest: dict, c0a: dict, c0b: dict, diagnostic: dict) -> dict:
    """Validate the entire prospective map before source payload transport."""
    parent = manifest['parent']
    _need(manifest['c0a_sha256'] == c0c.C0A_SHA and manifest['c0b_sha256'] == c0c.C0B_SHA,
          'metadata_parent_pins')
    _need(diagnostic['schema'] == 'jass.ed4.c0c_full_format_diagnostic.v2' and
          diagnostic['state'] == 'completed', 'diagnostic_parent_schema')
    rows = diagnostic['rows']
    _need(hashlib.sha256(_canonical(rows)).hexdigest() == parent['classification_sha256'] ==
          diagnostic['classification_sha256'], 'parent_classification_digest')
    failures = [r for r in rows if not r['outcome'].endswith('pass') and r['outcome'] != 'zero-byte']
    _need(failures == manifest['failure_rows'] and hashlib.sha256(_canonical(failures)).hexdigest() ==
          parent['failure_rows_sha256'] == diagnostic['failure_rows_sha256'], 'exact_21_failure_parent')
    partition = dict(collections.Counter(r['outcome'] for r in rows))
    _need({'descriptor_count':len(rows), **partition} == manifest['frozen_partition'], 'frozen_partition')
    _need(len(rows) == 726 and len(failures) == 21 and len({descriptor_key(r) for r in rows}) == 726,
          'parent_descriptor_cardinality')
    for name in ('target_fields_decoded','target_reads','score_reads','wdl_reads','qvalue_reads',
                 'model_reads','teacher_calls','search_calls','fits','games','alpha_spent'):
        _need(type(diagnostic[name]) is int and diagnostic[name] == 0, 'parent_forbidden_effect')
    _need(diagnostic['scientific_verdict'] is None and diagnostic['confirmation_authorized'] is False and
          diagnostic['automatic_continuation'] is False, 'parent_science_boundary')
    universe = {descriptor_key(dict(job_id=j['job_id'],attempt_id=j['attempt_id'],**d)):d
                for j in c0b['candidate_jobs'] for d in j['candidate_files']}
    _need(len(universe) == 726, 'c0b_cardinality')
    for row in rows:
        desc = universe.get(descriptor_key(row))
        _need(desc is not None and all(row[k] == desc[k] for k in ('path','kind','sha256','size_bytes')),
              'parent_c0b_descriptor_drift')
    source_index = {s['job_id']:s for s in c0a['sources']}
    mapped = expected_descriptors(manifest)
    _need(len(manifest['tsv_cases']) == 4 and len(mapped) == 29, 'companion_map_cardinality')
    _need(len(manifest['sources']) == len({s['job_id'] for s in manifest['sources']}) == 14,
          'source_map_cardinality')
    _need({s['job_id'] for s in manifest['sources']} == {k[0] for k in mapped}, 'source_map_membership')
    for source in manifest['sources']:
        frozen = source_index.get(source['job_id'])
        _need(frozen is not None and all(source[k] == frozen[k] for k in
              ('job_id','attempt_id','prefix','code_sha','result_state','exit_code')), 'source_identity_drift')
        _need(source['authentication'] == frozen['classification_evidence']['authentication'], 'source_auth_pins')
    for key, desc in mapped.items():
        if desc.get('metadata_parent','c0b') == 'c0b':
            frozen = universe.get(key)
        else:
            _need(desc['metadata_parent'] == 'c0a', 'companion_metadata_parent')
            source = source_index.get(desc['job_id'])
            _need(source is not None and source['attempt_id'] == desc['attempt_id'] and
                  source['classification'] == 'included_exact', 'companion_source_identity')
            frozen = next((d for d in source['required_paths'] if d['path'] == desc['path']), None)
        _need(frozen is not None and all(desc[k] == frozen[k] for k in ('path','sha256','size_bytes')),
              'companion_descriptor_drift')
    _need(manifest['runtime'] == {'mode':'rehearsal','stage_seconds':2100,'publication_seconds':2700},
          'manifest_runtime')
    policy = manifest['read_policy']
    _need(policy['jnnw_source_record_offsets'] == [0,33] and policy['forbidden_source_record_offsets'] == [33,38]
          and policy['alternate_framing_authorized'] is False, 'manifest_read_policy')
    _need(manifest['invalid_stm']['complete_coverage_proof'] is None and
          manifest['invalid_stm']['artifact_causality_proven'] is False and
          manifest['invalid_stm']['recovery_authorized'] is False, 'invalid_coverage_boundary')
    declared_aliases = [r for case in manifest['tsv_cases'] for r in case['aliases']]
    _need(sorted(declared_aliases,key=descriptor_key) == [r for r in failures if r['outcome']=='tsv_no_position_field'] and
          manifest['comment_only']['aliases'] == [r for r in failures if r['outcome']=='fen_empty'] and
          manifest['invalid_stm']['aliases'] == [r for r in failures if r['outcome']=='position_stm_invalid'],
          'class_alias_membership')
    for case in manifest['tsv_cases']:
        schema = _schema_from_manifest(manifest,case)
        schema_map = manifest['schemas'][case['schema_id']]
        _need(hashlib.sha256(_canonical(list(schema.columns))).hexdigest() == schema_map['header_canonical_sha256'],
              'header_preregistration_digest')
        _need(case['expected_child_count'] == case['expected_data_rows'] and
              case['expected_child_uncompressed_bytes'] == 8+38*case['expected_child_count'] and
              case['expected_parent_uncompressed_bytes'] == 8+38*case['expected_parent_count'], 'companion_geometry_map')
    return mapped


def _verify_inventory_identity(report, source):
    _need(all(report.get(k) == source[k] for k in
          ('job_id','attempt_id','code_sha','result_state','exit_code')), 'source_published_identity')


def build_diagnostic(manifest: dict, manifest_sha256: str, work: Path, artifact: Path,
                     deadline: float, checkpoint=None) -> dict:
    """No source object is fetched until all metadata and the policy are fixed."""
    def phase(name,event):
        _deadline(deadline)
        if checkpoint: checkpoint(name,event)
    _need(not work.exists() and not work.is_symlink(), 'work_dir_must_not_exist')
    work.mkdir(parents=True)
    artifact.mkdir(parents=True,exist_ok=True)
    phase('authenticate-1931-parent-and-source-metadata','begin')
    c0a,c0b = c0c.fetch_parent(work/'catalogue')
    _deadline(deadline)
    parent = manifest['parent']
    parent_dir = work/'diagnostic-parent'
    report = fetch.fetch_files(rclone='rclone', prefix=f"r2:jass-data/runs/{parent['job_id']}/{parent['attempt_id']}",
        expected_state='completed', selections=[(parent['path'],'diagnostic.json')], out_dir=parent_dir)
    _verify_inventory_identity(report,parent)
    raw = (parent_dir/'diagnostic.json').read_bytes()
    _need(len(raw) == parent['size_bytes'] and hashlib.sha256(raw).hexdigest() == parent['sha256'],
          'diagnostic_parent_payload_pin')
    mapped = validate_metadata(manifest,c0a,c0b,json.loads(raw))
    for source in manifest['sources']:
        _deadline(deadline)
        # Bind metadata to the already authenticated C0A snapshot, not only to a
        # mutually consistent newly fetched result envelope.
        for filename,key in (('manifest.json','manifest_sha256'),('inventory.json','inventory_sha256'),
                             ('checksums.sha256','checksums_sha256')):
            raw = fetch.base.remote_bytes('rclone',source['prefix']+'/'+filename)
            _need(hashlib.sha256(raw).hexdigest() == source['authentication'][key], 'source_metadata_hash_drift')
        report = fetch.inspect_result_inventory(rclone='rclone',prefix=source['prefix'],expected_state=source['result_state'])
        _verify_inventory_identity(report,source)
        inventory = {d['path']:d for d in report['files']}
        for key,desc in mapped.items():
            if key[:2] != (source['job_id'],source['attempt_id']): continue
            actual = inventory.get(desc['path'])
            _need(actual is not None and all(actual[k] == desc[k] for k in ('sha256','size_bytes')),
                  'source_inventory_descriptor_drift')
    phase('authenticate-1931-parent-and-source-metadata','complete')
    phase('validate-explicit-tsv-schemas','begin')
    policy = {'schema':'jass.ed4.c0c_exact_linkage_read_policy.v1','manifest_sha256':manifest_sha256,
              'manifest':manifest,'semantic_payload_reads_started':False}
    policy_path = artifact/POLICY_NAME
    _need(not policy_path.exists(), 'read_policy_already_exists')
    policy_path.write_bytes(_canonical(policy))
    phase('validate-explicit-tsv-schemas','complete')
    phase('validate-exact-companion-linkage','begin')
    payloads = {}
    transport_hash_bytes = 0
    for index,source in enumerate(manifest['sources']):
        _deadline(deadline)
        selected = [(key,d) for key,d in mapped.items() if key[:2] == (source['job_id'],source['attempt_id'])]
        local = work/f'source-{index:02d}'
        selections = [(d['path'],f'{i:03d}.opaque') for i,(_key,d) in enumerate(selected)]
        report = fetch.fetch_files(rclone='rclone',prefix=source['prefix'],expected_state=source['result_state'],
                                  selections=selections,out_dir=local)
        _verify_inventory_identity(report,source)
        _need(len(report['files']) == len(selected), 'fetch_descriptor_count')
        actual = {d['path']:d for d in report['files']}
        _need(set(actual) == {d['path'] for _,d in selected}, 'fetch_descriptor_set')
        for i,(key,desc) in enumerate(selected):
            _need(all(actual[desc['path']][k] == desc[k] for k in ('sha256','size_bytes')), 'fetch_descriptor_drift')
            payloads[key] = (local/f'{i:03d}.opaque').read_bytes()
            transport_hash_bytes += desc['size_bytes'] # download_verified hashes once.
    result = build_synthetic_diagnostic(manifest,payloads,deadline,transport_hash_bytes)
    phase('validate-exact-companion-linkage','complete')
    result.update(manifest_sha256=manifest_sha256,parent_diagnostic_sha256=parent['sha256'],
        parent_failure_rows_sha256=parent['failure_rows_sha256'],frozen_partition=manifest['frozen_partition'],
        read_policy_sha256=hashlib.sha256(policy_path.read_bytes()).hexdigest(),
        read_ledger_scope='Source payload hashing passes; decoded headers/structural fields and prefixes. Metadata hashing excluded. Alias byte analysis deduplicated by SHA; transport authenticates every descriptor.',
        metadata_sources_authenticated=len(manifest['sources']),payload_descriptors_authenticated=len(mapped))
    phase('publish-recovery-evidence','begin')
    atomic_json(artifact/(OUTPUT_NAME+'.json'), result)
    phase('publish-recovery-evidence','complete')
    return result
