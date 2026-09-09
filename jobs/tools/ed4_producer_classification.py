#!/usr/bin/env python3
"""Conservative C0A producer classification from authenticated metadata only."""
from __future__ import annotations
from collections import Counter

READY = 'ED4_C0A_INVENTORY_ADMISSION_READY_V1'
INSUFFICIENT = 'ED4_C0A_INVENTORY_ADMISSION_INSUFFICIENT_V1'

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


def structural_paths(meta):
    paths = [entry.get('path', '') for entry in (meta or {}).get('files', [])]
    return sorted(path for path in paths
                  if any(token in path.lower() for token in STRUCTURAL_TOKENS))


def compact_evidence(job, attempt, basis, paths):
    kinds = Counter()
    for path in paths:
        lower = path.lower()
        for label, token in STRUCTURAL_KINDS:
            if token in lower:
                kinds[label] += 1
    return {
        'job_id': job,
        'attempt_id': attempt,
        'basis': basis,
        'structural_descriptor_count': len(paths),
        'structural_kind_counts': dict(sorted(kinds.items())),
        'example_structural_paths': paths[:3],
    }


def apply(report, metadata):
    if report.get('verdict') not in {READY, INSUFFICIENT}:
        raise ValueError('classification_upstream_verdict')
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
        evidence = row.setdefault('classification_evidence', {})
        evidence['structural_descriptor_paths'] = paths
        if job in COVERED_BY:
            row['classification'] = 'covered_by_authenticated_superset'
            evidence['covering_source'] = COVERED_BY[job]
            evidence['basis'] = 'frozen_protocol_superset_relation_plus_authenticated_inventory'
        elif meta is not None and not paths:
            row['classification'] = 'non_position_producer'
            evidence['basis'] = 'authenticated_inventory_has_no_structural_descriptor'
        else:
            unknown.append(job)
            evidence['basis'] = ('authenticated_inventory_contains_structural_descriptor_without_'
                                 'preregistered_coverage_proof' if meta is not None
                                 else 'no_authenticated_terminal_metadata')
            unknown_evidence.append({
                'job_id': job, 'attempt_id': attempt, 'basis': evidence['basis'],
                'structural_descriptor_paths': paths,
            })
            compact.append(compact_evidence(job, attempt, evidence['basis'], paths))
    report['unknown_or_unclassified_producers'] = sorted(unknown)
    report['unknown_producer_evidence'] = sorted(unknown_evidence, key=lambda item: item['job_id'])
    report['unknown_producer_compact_evidence'] = sorted(compact, key=lambda item: item['job_id'])
    report['classification_counts'] = dict(sorted(Counter(
        row.get('classification', 'unknown') for row in report.get('sources', [])
    ).items()))
    report['verdict'] = (INSUFFICIENT if report.get('missing_paths') or unknown else READY)
    return report
