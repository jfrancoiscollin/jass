#!/usr/bin/env python3
"""ED4-C0A descriptor-only admission.  Never fetches a source payload."""
from __future__ import annotations
import argparse, hashlib, json, re, subprocess
from pathlib import Path

SOURCES={
 '1773':('cpx62-1835-l3-decision-math-b3-fresh-exclusion-prep-rerun-v1','20260906T134208Z-c553a572','c553a572ed8ada9c49f8ebbefa3db22a9b6ca739',['artefacts/b3-fresh-exclusion-union.txt','artefacts/b3-fresh-exclusion-manifest.json']),
 'home':('home-1651-l3-scan-ceiling-selection-v1','20260829T133348Z-28e12fba','28e12fba0ead14def244ffc442b15937f65edc0e',['manifest.json','artefacts/parents.jnnw.gz','artefacts/children.jnnw.gz','artefacts/siblings.tsv']),
 'b2':('cpx62-1778-l3-decision-math-b2-source-selection-v1','20260905T102917Z-d3657332','d3657332c3a5609a5501a9ff130f5d5c19488c7f',['artefacts/source-selection-publication.json','artefacts/parents.jnnw','artefacts/parents.tsv','artefacts/ordered-identities.txt']),
 'b3':('cpx62-1837-l3-decision-math-b3-fresh-source-selection-v1','20260906T141235Z-29084b25','29084b25789b1a88c19a86f73c476eedc52acbc6',['artefacts/source-selection-publication.json','artefacts/parents.jnnw','artefacts/parents.tsv','artefacts/ordered-identities.txt']),
 'd4':('cpx62-1862-l3-decision-math-d4-search-utility-offline-cardinality-recovery-requeue-v1','20260907T182914Z-1c779cc8','1c779cc87608a12b26432cad6a23872aeb5eabe8',['artefacts/d4-search-utility-roots.tsv','artefacts/d4-root-pool-provenance.json']),
 'ed2':('cpx62-1875-l3-ed2-data-teacher-preflight-v1','20260908T171140Z-bc30d685','bc30d6858c4d590625f8831c4995f055816b95c2',['artefacts/source/parents.jnnw','artefacts/source/children.jnnw','artefacts/source/parents.tsv','artefacts/source/groups.tsv','artefacts/source/source.json','artefacts/ed2-source-seal.json']),
 'ed3r':('cpx62-1883-l3-ed3-confirmation-rehearsal-v1','20260909T050858Z-0946f57d','0946f57d5443c0507fd9210371396bdf1c49abd2',['artefacts/source/parents.jnnw','artefacts/source/children.jnnw','artefacts/source/parents.tsv','artefacts/source/groups.tsv','artefacts/source/source.json','artefacts/cohort-seal.json','artefacts/guard-plan.json']),
 'ed3p':('cpx62-1884-l3-ed3-confirmation-production-v1','20260909T051901Z-0946f57d','0946f57d5443c0507fd9210371396bdf1c49abd2',['artefacts/source/parents.jnnw','artefacts/source/children.jnnw','artefacts/source/parents.tsv','artefacts/source/groups.tsv','artefacts/source/source.json','artefacts/cohort-seal.json','artefacts/guard-plan.json']),
 'n1':('cpx62-1878-l3-ed2-numerical-recovery-n1','20260908T191343Z-d71679e9','d71679e96d78609b6d32052be80ca78c0deaece0',['artefacts/wdl-selection.json','artefacts/wdl-selection.seal.json','work/current.jnnw','work/current.jsm'])}

from jobs.tools.ed4_metadata_projection import project, IDENTITY, STATUS, INVENTORY
from jobs.tools import fetch_t1bis_inputs as base

CONTROL_SHA = '3ae5a3980ee60816ef078124deafa72b2e2f4662'
PROTOCOL = 'docs/experiments/L3_ED4_CONFIRMATION_SOURCE_AUDIT_V1_20260909.md'
SOURCE_TERMINALS = {value[0]: ('failed', 2) if key == 'd4' else ('completed', 0)
                    for key, value in SOURCES.items()}
MAX_ENVELOPE_BYTES = 32 * 1024 * 1024
EXPECTED_HASHES = {
    'artefacts/b3-fresh-exclusion-union.txt': 'b553939e8ded3ab31d121e40b2be9cfa1012168bf01835f692b59a60815d9ecb',
    'artefacts/b3-fresh-exclusion-manifest.json': 'f734de99761b7a3ee7ddb107de3d678fa29eb7e39a11708b6a8c8bbbe700cc0c',
}
ZERO_READS = {name: 0 for name in ('payload_downloads', 'payload_bytes_read',
    'model_reads', 'target_reads', 'outcome_reads', 'qvalue_reads')}


def need(ok, code):
    if not ok:
        raise ValueError(code)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def project_manifest(raw):
    return project(raw, IDENTITY)


def project_status(raw):
    return project(raw, STATUS)


def project_inventory(raw):
    return project(raw, INVENTORY)


def remote_envelope(rclone, prefix, name):
    need(name in {'_SUCCESS', '_FAILED', 'manifest.json', 'inventory.json', 'checksums.sha256'},
         'remote_name_not_allowlisted')
    result = subprocess.run([rclone, 'cat', f'{prefix}/{name}'], check=True,
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                            timeout=120)
    need(len(result.stdout) <= MAX_ENVELOPE_BYTES, 'metadata_envelope_too_large')
    return result.stdout


def checksum_map(raw):
    result = {}
    for line in raw.decode('ascii').splitlines():
        parts = line.split('  ', 1)
        need(len(parts) == 2 and re.fullmatch('[a-f0-9]{64}', parts[0]), 'checksums_format')
        result[parts[1]] = parts[0]
    return result


def metadata_transport(rclone, prefix, state):
    marker = '_SUCCESS' if state == 'completed' else '_FAILED'
    marker_raw = remote_envelope(rclone, prefix, marker)
    manifest_raw = remote_envelope(rclone, prefix, 'manifest.json')
    inventory_raw = remote_envelope(rclone, prefix, 'inventory.json')
    checksums_raw = remote_envelope(rclone, prefix, 'checksums.sha256')
    checksums = checksum_map(checksums_raw)
    need(checksums.get('manifest.json') == digest(manifest_raw), 'manifest_checksum')
    need(checksums.get('inventory.json') == digest(inventory_raw), 'inventory_checksum')
    manifest = project_manifest(manifest_raw)
    inventory = project_inventory(inventory_raw)
    need(manifest['state'] == state, 'manifest_state')
    need(digest(marker_raw) == checksums.get(marker), 'marker_checksum')
    files = inventory['files']
    return dict(prefix=prefix, job_id=manifest['job_id'], attempt_id=manifest['attempt_id'],
                code_sha=manifest['code_sha'], host=manifest['host'], result_state=manifest['state'],
                exit_code=manifest['exit_code'], files=files,
                authentication=dict(marker=marker, marker_sha256=digest(marker_raw),
                    manifest_sha256=digest(manifest_raw), inventory_sha256=digest(inventory_raw),
                    checksums_sha256=digest(checksums_raw)))


def _git(repo, control_sha, path):
    return subprocess.run(['git', '-C', str(repo), 'show', f'{control_sha}:{path}'],
                          check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          timeout=30).stdout


def control_catalog(repo, control_sha=CONTROL_SHA):
    need(control_sha == CONTROL_SHA, 'control_snapshot_not_frozen')
    raw = _git(repo, control_sha, 'status/catalog.json')
    payload = json.loads(raw)
    rows = payload if isinstance(payload, list) else payload.get('jobs', payload.get('entries', []))
    need(isinstance(rows, list), 'catalog_schema')
    result = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        job = row.get('job_id') or row.get('job')
        match = re.search(r'(?:cpx62|home)-(\d+)', str(job or ''))
        if not match or not 1773 <= int(match.group(1)) <= 1888:
            continue
        status_path = row.get('status_path') or f'status/{job}.json'
        try:
            status_raw = _git(repo, control_sha, status_path)
        except subprocess.CalledProcessError:
            status_raw = json.dumps(row).encode()
        status = project_status(status_raw)
        status['status_path'] = status_path
        status['status_sha256'] = digest(status_raw)
        status['queue_paths'] = row.get('queue_paths', [])
        result.append(status)
    return result


def collect(catalog, rclone='rclone', transport=metadata_transport):
    tasks = {}
    for item in catalog:
        job, attempt = item['job_id'], item.get('attempt_id')
        if not attempt or item.get('state') not in {'completed', 'failed'}:
            continue
        need(re.fullmatch('[a-f0-9]{40}', item.get('code_sha') or ''), 'catalog_code_sha')
        prefix = f'r2:jass-data/runs/{job}/{attempt}'
        need(item.get('result_uri') == prefix, 'catalog_result_uri')
        tasks[job, attempt] = (prefix, item['state'], item['code_sha'], item.get('host'), item['exit_code'])
    for job, attempt, code, _ in SOURCES.values():
        prefix = f'r2:jass-data/runs/{job}/{attempt}'
        expected_state, expected_exit = SOURCE_TERMINALS[job]
        if (job, attempt) in tasks:
            need(tasks[job, attempt][1:3] == (expected_state, code)
                 and tasks[job, attempt][4] == expected_exit, 'literal_catalog_identity')
        else:
            tasks[job, attempt] = (prefix, expected_state, code, None, expected_exit)
    metadata = {}
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {key: pool.submit(transport, rclone, value[0], value[1]) for key, value in tasks.items()}
        try:
            for (job, attempt), future in futures.items():
                item = future.result()
                _, state, code, _host, exit_code = tasks[job, attempt]
                need((item['job_id'], item['attempt_id'], item['code_sha'], item['result_state'],
                      item['exit_code']) == (job, attempt, code, state, exit_code),
                     'authenticated_catalog_identity')
                metadata[job, attempt] = item
        except Exception:
            for future in futures.values():
                future.cancel()
            raise
    return metadata


def build(metadata, catalog, audit_sha, protocol_bytes, control_sha=CONTROL_SHA):
    need(control_sha == CONTROL_SHA and re.fullmatch('[a-f0-9]{64}', audit_sha), 'audit_identity')
    need(catalog and len({x['job_id'] for x in catalog}) == len(catalog), 'catalog_empty_or_duplicate')
    literals = {value[0]: value for value in SOURCES.values()}
    catalog_by_job = {x['job_id']: x for x in catalog}
    need(set(literals) - {'home-1651-l3-scan-ceiling-selection-v1'} <= set(catalog_by_job),
         'literal_source_missing_from_catalog')
    sources, missing, unknown = [], [], []
    total = records = 0
    for job in sorted(set(catalog_by_job) | set(literals)):
        status = catalog_by_job.get(job, {})
        if job in literals:
            _, attempt, code, paths = literals[job]
            need(not status or (status.get('attempt_id'), status.get('code_sha')) == (attempt, code),
                 'literal_snapshot_identity')
        else:
            attempt, code, paths = status.get('attempt_id'), status.get('code_sha'), []
        meta = metadata.get((job, attempt))
        if job in literals or (attempt and status.get('state') in {'completed', 'failed'}):
            need(meta is not None and meta['job_id'] == job and meta['attempt_id'] == attempt
                 and meta['code_sha'] == code, 'missing_authenticated_metadata')
        if job in literals:
            need((meta['result_state'], meta['exit_code']) == SOURCE_TERMINALS[job], 'literal_terminal')
        files = {entry['path']: entry for entry in meta['files']} if meta else {}
        required = []
        for path in paths:
            entry = files.get(path)
            present = entry is not None and entry['size_bytes'] > 0
            if not present:
                missing.append({'job_id': job, 'path': path})
            if present and path in EXPECTED_HASHES:
                need(entry['sha256'] == EXPECTED_HASHES[path], 'frozen_input_descriptor_hash')
            cardinality = entry.get('declared_cardinality') if entry else None
            required.append(dict(path=path, present=present,
                size_bytes=entry['size_bytes'] if entry else None,
                sha256=entry['sha256'] if entry else None, declared_cardinality=cardinality,
                cardinality_source={'path': 'inventory.json',
                    'sha256': meta['authentication']['inventory_sha256']} if cardinality is not None else None))
            if entry:
                total += entry['size_bytes']
                records += cardinality or 0
        classification = 'unknown'
        if job in literals:
            classification = 'included_exact' if all(x['present'] for x in required) else 'structural_payload_unavailable'
        else:
            unknown.append(job)
        sources.append(dict(job_id=job, attempt_id=attempt, code_sha=code,
            prefix=meta['prefix'] if meta else status.get('result_uri'),
            result_state=meta['result_state'] if meta else status.get('state'),
            exit_code=meta['exit_code'] if meta else status.get('exit_code'),
            required_paths=required, classification=classification,
            classification_evidence=dict(status_path=status.get('status_path'),
                status_sha256=status.get('status_sha256'),
                queue_paths=status.get('queue_paths', []),
                authentication=meta['authentication'] if meta else None,
                basis='literal_source_descriptors' if job in literals else 'no_allowlisted_coverage_proof')))
    verdict = 'INSUFFICIENT' if missing or unknown else 'READY'
    return dict(schema='jass.ed4.c0a_source_descriptor_inventory.v1', state='completed',
        verdict=f'ED4_C0A_INVENTORY_ADMISSION_{verdict}_V1', audit_code_sha256=audit_sha,
        protocol_path=PROTOCOL, protocol_sha256=digest(protocol_bytes),
        control_snapshot_commit=control_sha,
        catalogue_cutoff=dict(first_ordinal=1773, last_ordinal=1888, inclusive=True),
        sources=sources, missing_paths=missing, unknown_or_unclassified_producers=unknown,
        declared_input_bytes_total=total, declared_records_total=records, **ZERO_READS)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--control-repo', type=Path, required=True)
    parser.add_argument('--control-sha', default=CONTROL_SHA)
    parser.add_argument('--rclone', default='rclone')
    args = parser.parse_args(argv)
    repository = Path(__file__).resolve().parents[2]
    protocol = (repository / PROTOCOL).read_bytes()
    audit_hash = digest(Path(__file__).read_bytes())
    try:
        catalog = control_catalog(args.control_repo, args.control_sha)
        metadata = collect(catalog, args.rclone)
        report = build(metadata, catalog, audit_hash, protocol, args.control_sha)
    except Exception as exc:
        report = dict(schema='jass.ed4.c0a_source_descriptor_inventory.v1', state='failed',
            verdict='ED4_C0A_INVENTORY_ADMISSION_TECHNICAL_FAILURE_V1',
            audit_code_sha256=audit_hash, protocol_path=PROTOCOL, protocol_sha256=digest(protocol),
            control_snapshot_commit=args.control_sha, failure_type=type(exc).__name__, **ZERO_READS)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with args.out.open('x', encoding='utf-8', newline='\n') as stream:
            stream.write(json.dumps(report, sort_keys=True, indent=2) + '\n')
        return 2
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open('x', encoding='utf-8', newline='\n') as stream:
        stream.write(json.dumps(report, sort_keys=True, indent=2) + '\n')
    print(report['verdict'])
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
