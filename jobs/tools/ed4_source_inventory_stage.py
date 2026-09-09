#!/usr/bin/env python3
"""V2 evidence wrapper for C0A descriptor admission; no source payload access."""
from __future__ import annotations
import json
import os
import re
import shutil
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from jobs.tools import ed4_source_descriptor_inventory as inventory
from jobs.tools import ed4_producer_classification as producer_classification
from jobs.tools import ed4_structural_candidate_manifest as structural_candidates
from jobs.tools.launch_runtime_v2 import StageEvidence, atomic_json

OUTPUT = 'ed4-c0a-source-descriptor-inventory.json'
CANDIDATE_OUTPUT = 'ed4-c0b-structural-candidate-manifest.json'
PHASES = ['control-catalog', 'authenticate-envelopes', 'classify-descriptors', 'publish-readback']
VERDICTS = {'ED4_C0A_INVENTORY_ADMISSION_READY_V1',
            'ED4_C0A_INVENTORY_ADMISSION_INSUFFICIENT_V1'}
FAILURE = 'ED4_C0A_INVENTORY_ADMISSION_TECHNICAL_FAILURE_V1'


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def terminal(report, mode):
    return dict(schema='jass.ed4.c0a_inventory_terminal.v1', state=report['state'],
                verdict=report['verdict'], mode=mode, classification='METADATA_ONLY',
                scientific_verdict=None, scientific_success_established=False,
                inventory_only=True, source_audit_completed=False,
                confirmation_authorized=False, runtime_authorized=False,
                automatic_continuation=False, fits=0, teacher_calls=0,
                search_calls=0, games=0, alpha_spent=0, promotions=0, bakes=0,
                control_snapshot_commit=inventory.CONTROL_SHA,
                **{key: report[key] for key in inventory.ZERO_READS})


def collect_metadata(catalog, rclone='rclone', transport=inventory.metadata_transport):
    tasks = {}
    for item in catalog:
        job, attempt = item['job_id'], item.get('attempt_id')
        if not attempt or item.get('state') not in {'completed', 'failed'}:
            continue
        inventory.need(re.fullmatch('[a-f0-9]{40}', item.get('code_sha') or ''),
                       'catalog_code_sha')
        prefix = f'r2:jass-data/runs/{job}/{attempt}'
        inventory.need(item.get('result_uri') == prefix, 'catalog_result_uri')
        tasks[job, attempt] = (prefix, item['state'], item['code_sha'], item['exit_code'])
    for job, attempt, code, _ in inventory.SOURCES.values():
        prefix = f'r2:jass-data/runs/{job}/{attempt}'
        expected_state, expected_exit = inventory.SOURCE_TERMINALS[job]
        if (job, attempt) in tasks:
            inventory.need(tasks[job, attempt][1:3] == (expected_state, code)
                           and tasks[job, attempt][3] == expected_exit,
                           'literal_catalog_identity')
        else:
            tasks[job, attempt] = (prefix, expected_state, code, expected_exit)
    metadata = {}
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {key: pool.submit(transport, rclone, value[0], value[1])
                   for key, value in tasks.items()}
        try:
            for (job, attempt), future in futures.items():
                item = future.result()
                _, state, code, exit_code = tasks[job, attempt]
                inventory.need(item['job_id'] == job, 'authenticated_job_id')
                inventory.need(item['attempt_id'] == attempt, 'authenticated_attempt_id')
                inventory.need(item['code_sha'] == code, 'authenticated_code_sha')
                inventory.need(item['result_state'] == state, 'authenticated_result_state')
                inventory.need(item['exit_code'] == exit_code, 'authenticated_exit_code')
                metadata[job, attempt] = item
        except Exception:
            for future in futures.values():
                future.cancel()
            raise
    return metadata


def run(artifact, mode, control_repo, *, catalog_reader=inventory.control_catalog,
        collector=None, builder=inventory.build):
    evidence = StageEvidence(artifact, mode)
    audit_hash = protocol_hash = None
    read_counts = dict(inventory.ZERO_READS)
    if collector is None:
        collector = collect_metadata
    try:
        evidence.begin(PHASES[0])
        inventory.need(shutil.disk_usage(artifact).free >= 3 * 1024**3, 'disk_floor')
        protocol = (ROOT / inventory.PROTOCOL).read_bytes()
        protocol_hash = inventory.digest(protocol)
        audit_hash = inventory.digest(Path(inventory.__file__).read_bytes())
        catalog = catalog_reader(control_repo, inventory.CONTROL_SHA)
        evidence.complete()
        evidence.begin(PHASES[1])
        metadata = collector(catalog)
        evidence.complete()
        evidence.begin(PHASES[2])
        report = builder(metadata, catalog, audit_hash, protocol, inventory.CONTROL_SHA)
        report = producer_classification.apply(report, metadata)
        candidates = structural_candidates.build(metadata, report, inventory.CONTROL_SHA)
        for key in read_counts:
            count = report.get(key)
            if type(count) is int and count >= 0:
                read_counts[key] = count
        inventory.need(report.get('state') == 'completed'
                       and report.get('verdict') in VERDICTS, 'inventory_terminal')
        inventory.need(report.get('control_snapshot_commit') == inventory.CONTROL_SHA,
                       'inventory_snapshot')
        inventory.need(all(type(report.get(k)) is int and report[k] == 0
                           for k in inventory.ZERO_READS), 'inventory_read_barrier')
        inventory.need(all(candidates.get(k) == 0 for k in
                           ('payload_downloads','payload_bytes_read','model_reads','target_reads',
                            'outcome_reads','qvalue_reads')), 'candidate_read_barrier')
        evidence.complete()
        evidence.begin(PHASES[3])
        atomic_json(artifact / OUTPUT, report)
        atomic_json(artifact / CANDIDATE_OUTPUT, candidates)
        inventory.need(read_json(artifact / OUTPUT) == report, 'inventory_readback')
        inventory.need(read_json(artifact / CANDIDATE_OUTPUT) == candidates,
                       'candidate_manifest_readback')
        summary = terminal(report, mode)
        summary.update(inventory_sha256=inventory.digest((artifact / OUTPUT).read_bytes()),
                       c0b_candidate_manifest_sha256=inventory.digest((artifact / CANDIDATE_OUTPUT).read_bytes()),
                       c0b_candidate_jobs_count=candidates['candidate_jobs_count'],
                       c0b_candidate_files_count=candidates['candidate_files_count'],
                       c0b_candidate_declared_bytes_total=candidates['candidate_declared_bytes_total'],
                       c0b_candidate_kind_counts=candidates['candidate_kind_counts'],
                       c0b_jobs_without_parseable_position_candidate_count=len(candidates['jobs_without_parseable_position_candidate']),
                       missing_paths_count=len(report['missing_paths']),
                       unclassified_producers_count=len(report['unknown_or_unclassified_producers']),
                       classification_counts=report.get('classification_counts', {}),
                       missing_paths=report['missing_paths'],
                       unknown_or_unclassified_producers=report['unknown_or_unclassified_producers'],
                       unknown_producer_compact_evidence=report.get('unknown_producer_compact_evidence', []))
        atomic_json(artifact / 'scientific-summary.json', summary)
        inventory.need(read_json(artifact / 'scientific-summary.json') == summary,
                       'summary_readback')
        evidence.complete()
        evidence.finish()
        return summary
    except Exception as exc:
        failure = dict(schema='jass.ed4.c0a_source_descriptor_inventory.v1',
                       state='failed', verdict=FAILURE, audit_code_sha256=audit_hash,
                       protocol_path=inventory.PROTOCOL, protocol_sha256=protocol_hash,
                       control_snapshot_commit=inventory.CONTROL_SHA,
                       failure_type=type(exc).__name__, **read_counts)
        atomic_json(artifact / OUTPUT, failure)
        atomic_json(artifact / 'scientific-summary.json', terminal(failure, mode))
        evidence.fail(exc)
        raise


def main():
    try:
        run(Path(os.environ['JASS_ARTEFACT_DIR']), os.environ['LAUNCH_MODE'],
            Path(os.environ['ED4_CONTROL_REPO']))
        return 0
    except Exception as exc:
        print('ED4 inventory stage failed: ' + type(exc).__name__, file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
