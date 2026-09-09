#!/usr/bin/env python3
"""Conservative C0A producer classification from authenticated metadata only."""
from __future__ import annotations
from collections import Counter
from pathlib import Path, PurePosixPath
import hashlib
import re

READY = 'ED4_C0A_INVENTORY_ADMISSION_READY_V1'
INSUFFICIENT = 'ED4_C0A_INVENTORY_ADMISSION_INSUFFICIENT_V1'
CLASSIFICATION_PROTOCOL = 'docs/experiments/L3_ED4_CONFIRMATION_SOURCE_AUDIT_V2_20260909.md'

COVERED_BY = {
    'cpx62-1773-l3-decision-math-b2-historical-preparation-v1': 'cpx62-1835-l3-decision-math-b3-fresh-exclusion-prep-rerun-v1',
    'cpx62-1801-l3-decision-math-b2-full-teacher-publish-empty-artifact-repair-v1': 'cpx62-1778-l3-decision-math-b2-source-selection-v1',
    'cpx62-1841-l3-decision-math-b3-fresh-adaptive-teacher-rerun-v1': 'cpx62-1837-l3-decision-math-b3-fresh-source-selection-v1',
    'cpx62-1842-l3-decision-math-b3-fresh-audit-subset-seal-v1': 'cpx62-1837-l3-decision-math-b3-fresh-source-selection-v1',
    'cpx62-1843-l3-decision-math-b3-fresh-full-ladder-audit-v1': 'cpx62-1837-l3-decision-math-b3-fresh-source-selection-v1',
    'cpx62-1864-l3-scan-oracle-gate0-d3-retrospective-v1': 'cpx62-1862-l3-decision-math-d4-search-utility-offline-cardinality-recovery-requeue-v1',
    'cpx62-1868-l3-d4b-search-utility-micro-screen-v1': 'cpx62-1862-l3-decision-math-d4-search-utility-offline-cardinality-recovery-requeue-v1',
    'cpx62-1873-l3-ed1-partial-order-audit-v1': 'home-1651-l3-scan-ceiling-selection-v1',
    'cpx62-1874-l3-ed1-partial-order-audit-openmp-recovery-v1': 'home-1651-l3-scan-ceiling-selection-v1',
}

STRUCTURAL_KINDS = (
    ('jnnw', '.jnnw'), ('jsm', '.jsm'), ('parent', 'parent'), ('child', 'child'),
    ('sibling', 'sibling'), ('root', 'root'), ('position', 'position'),
    ('opening', 'opening'), ('trajectory', 'trajectory'),
    ('ordered_identity', 'ordered-identit'), ('exclusion_union', 'exclusion-union'),
    ('cohort', 'cohort'), ('source_selection', 'source-selection'),
    ('corpus', 'corpus'), ('dataset', 'dataset'), ('fen', 'fen'),
)
STRUCTURAL_TOKENS = tuple(token for _, token in STRUCTURAL_KINDS)
RAW_SUFFIXES = ('.jnnw', '.jnnw.gz', '.jsm', '.jsm.gz', '.fen', '.fen.gz')
IDENTITY_TERMS = ('parent', 'child', 'sibling', 'root', 'position', 'opening',
                  'identit', 'exclusion')
NON_PAYLOAD_MARKERS = ('/cmakefiles/', '/native-build/', '/build/cmakefiles/',
                       '/documentary-worktree/docs/', '/docs/archives/')
NON_PAYLOAD_SUFFIXES = ('.o', '.o.d', '.cpp', '.hpp', '.cc', '.c', '.cmake', '.md',
                        '.py', '.sh', '.log', '.err')


def structural_paths(meta):
    paths = [entry.get('path', '') for entry in (meta or {}).get('files', [])]
    return sorted(path for path in paths
                  if any(token in path.lower() for token in STRUCTURAL_TOKENS))


def is_position_payload_path(path):
    lower = '/' + str(path).lower().lstrip('/')
    if any(marker in lower for marker in NON_PAYLOAD_MARKERS):
        return False
    if lower.endswith(NON_PAYLOAD_SUFFIXES):
        return False
    if lower.endswith(RAW_SUFFIXES):
        return True
    name = PurePosixPath(lower).name
    if name.endswith(('.tsv', '.tsv.gz', '.txt', '.txt.gz')):
        return any(term in name for term in IDENTITY_TERMS)
    if name.endswith(('.jsonl', '.jsonl.gz')):
        return any(term in lower for term in ('dataset', 'position', '.fen'))
    return False


def position_entries(meta):
    return sorted([entry for entry in (meta or {}).get('files', [])
                   if is_position_payload_path(entry.get('path', ''))],
                  key=lambda entry: entry.get('path', ''))


def compact_evidence(job, attempt, basis, paths):
    kinds = Counter()
    for path in paths:
        lower = path.lower()
        for label, token in STRUCTURAL_KINDS:
            if token in lower:
                kinds[label] += 1
    return {'job_id': job, 'attempt_id': attempt, 'basis': basis,
            'structural_descriptor_count': len(paths),
            'structural_kind_counts': dict(sorted(kinds.items())),
            'example_structural_paths': paths[:3]}


def literal_hash_sets(report):
    result = {}
    for row in report.get('sources', []):
        if row.get('classification') != 'included_exact':
            continue
        hashes = {item.get('sha256') for item in row.get('required_paths', [])
                  if item.get('present') is True
                  and re.fullmatch(r'[0-9a-f]{64}', item.get('sha256') or '')}
        if hashes:
            result[row['job_id']] = hashes
    return result


def hash_cover(entries, source_hashes):
    hashes = {entry.get('sha256') for entry in entries}
    if not hashes or any(not re.fullmatch(r'[0-9a-f]{64}', value or '') for value in hashes):
        return None
    covering = [job for job, allowed in source_hashes.items() if hashes <= allowed]
    return sorted(covering)[0] if covering else None


def is_authenticated_nonexecution(row):
    return (row.get('attempt_id') is None and row.get('code_sha') is None
            and row.get('result_state') == 'failed' and row.get('exit_code') == -1)


def bind_protocol(report):
    root = Path(__file__).resolve().parents[2]
    raw = (root / CLASSIFICATION_PROTOCOL).read_bytes()
    report['classification_protocol_path'] = CLASSIFICATION_PROTOCOL
    report['classification_protocol_sha256'] = hashlib.sha256(raw).hexdigest()


def apply(report, metadata):
    if report.get('verdict') not in {READY, INSUFFICIENT}:
        raise ValueError('classification_upstream_verdict')
    bind_protocol(report)
    source_hashes = literal_hash_sets(report)
    unknown = []
    unknown_evidence = []
    compact = []
    for row in report.get('sources', []):
        if row.get('classification') != 'unknown':
            continue
        job = row['job_id']
        attempt = row.get('attempt_id')
        meta = metadata.get((job, attempt)) if attempt else None
        paths = structural_paths(meta)
        payloads = position_entries(meta)
        evidence = row.setdefault('classification_evidence', {})
        evidence['structural_descriptor_paths'] = paths
        evidence['position_payload_descriptor_paths'] = [x.get('path') for x in payloads]
        covering = hash_cover(payloads, source_hashes)
        if job in COVERED_BY:
            row['classification'] = 'covered_by_authenticated_superset'
            evidence['covering_source'] = COVERED_BY[job]
            evidence['basis'] = 'frozen_protocol_superset_relation_plus_authenticated_inventory'
        elif is_authenticated_nonexecution(row):
            row['classification'] = 'non_position_producer'
            evidence['basis'] = 'frozen_status_proves_no_attempt_and_no_code_execution'
        elif meta is not None and not payloads:
            row['classification'] = 'non_position_producer'
            evidence['basis'] = 'authenticated_inventory_has_no_position_payload_descriptor'
        elif covering is not None:
            row['classification'] = 'covered_by_authenticated_superset'
            evidence['covering_source'] = covering
            evidence['basis'] = 'all_position_payload_descriptors_sha256_match_one_frozen_exact_source'
            evidence['covered_payload_sha256'] = sorted({x['sha256'] for x in payloads})
        else:
            unknown.append(job)
            evidence['basis'] = ('authenticated_inventory_contains_uncovered_position_payload_descriptor'
                                 if meta is not None else 'no_authenticated_terminal_metadata')
            unknown_evidence.append({
                'job_id': job, 'attempt_id': attempt, 'basis': evidence['basis'],
                'structural_descriptor_paths': paths,
                'position_payload_descriptor_paths': [x.get('path') for x in payloads]})
            compact.append(compact_evidence(job, attempt, evidence['basis'],
                                             [x.get('path', '') for x in payloads] or paths))
    report['unknown_or_unclassified_producers'] = sorted(unknown)
    report['unknown_producer_evidence'] = sorted(unknown_evidence, key=lambda item: item['job_id'])
    report['unknown_producer_compact_evidence'] = sorted(compact, key=lambda item: item['job_id'])
    report['classification_counts'] = dict(sorted(Counter(
        row.get('classification', 'unknown') for row in report.get('sources', [])).items()))
    report['verdict'] = (INSUFFICIENT if report.get('missing_paths') or unknown else READY)
    return report
