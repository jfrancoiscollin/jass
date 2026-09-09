#!/usr/bin/env python3
"""Conservative C0A producer classification from authenticated metadata only.

This module never opens a source payload. It consumes the authenticated envelope
inventory already fetched by C0A admission and applies only preregistered
superset relations plus a conservative structural-descriptor screen.
"""
from __future__ import annotations
from collections import Counter

READY = 'ED4_C0A_INVENTORY_ADMISSION_READY_V1'
INSUFFICIENT = 'ED4_C0A_INVENTORY_ADMISSION_INSUFFICIENT_V1'

# Relations stated prospectively in L3_ED4_CONFIRMATION_SOURCE_AUDIT_V1_20260909.md.
# The keys are exact frozen control-snapshot jobs, not name-pattern heuristics.
COVERED_BY = {
    'cpx62-1773-l3-decision-math-b2-historical-preparation-v1':
        'cpx62-1835-l3-decision-math-b3-fresh-exclusion-prep-rerun-v1',
    'cpx62-1801-l3-decision-math-b2-full-teacher-publish-empty-artifact-repair-v1':
        'cpx62-1778-l3-decision-math-b2-source-selection-v1',
    'cpx62-1841-l3-decision-math-b3-fresh-adaptive-teacher-rerun-v1':
        'cpx62-1837-l3-decision-math-b3-fresh-source-selection-v1',
    'cpx62-1842-l3-decision-math-b3-fresh-audit-subset-seal-v1':
        'cpx62-1837-l3-decision-math-b3-fresh-source-selection-v1',
    'cpx62-1843-l3-decision-math-b3-fresh-full-ladder-audit-v1':
        'cpx62-1837-l3-decision-math-b3-fresh-source-selection-v1',
    'cpx62-1864-l3-scan-oracle-gate0-d3-retrospective-v1':
        'cpx62-1862-l3-decision-math-d4-search-utility-offline-cardinality-recovery-requeue-v1',
    'cpx62-1868-l3-d4b-search-utility-micro-screen-v1':
        'cpx62-1862-l3-decision-math-d4-search-utility-offline-cardinality-recovery-requeue-v1',
    'cpx62-1873-l3-ed1-partial-order-audit-v1':
        'home-1651-l3-scan-ceiling-selection-v1',
    'cpx62-1874-l3-ed1-partial-order-audit-openmp-recovery-v1':
        'home-1651-l3-scan-ceiling-selection-v1',
}

# If any authenticated descriptor has one of these shapes we refuse to call the
# producer "non-position" without an explicit superset relation. False positives
# are intentional: they leave a blocker instead of incorrectly admitting data.
STRUCTURAL_TOKENS = (
    '.jnnw', '.jsm', 'parent', 'child', 'sibling', 'root', 'position',
    'opening', 'trajectory', 'ordered-identit', 'exclusion-union', 'cohort',
    'source-selection', 'corpus', 'dataset', 'fen',
)


def structural_paths(meta):
    paths = [entry.get('path', '') for entry in (meta or {}).get('files', [])]
    return sorted(path for path in paths
                  if any(token in path.lower() for token in STRUCTURAL_TOKENS))


def apply(report, metadata):
    """Return report with evidence-based classifications, still fail-closed."""
    if report.get('verdict') not in {READY, INSUFFICIENT}:
        raise ValueError('classification_upstream_verdict')
    unknown = []
    unknown_evidence = []
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
                'job_id': job,
                'attempt_id': attempt,
                'basis': evidence['basis'],
                'structural_descriptor_paths': paths,
            })
    report['unknown_or_unclassified_producers'] = sorted(unknown)
    report['unknown_producer_evidence'] = sorted(unknown_evidence, key=lambda item: item['job_id'])
    report['classification_counts'] = dict(sorted(Counter(
        row.get('classification', 'unknown') for row in report.get('sources', [])
    ).items()))
    report['verdict'] = (INSUFFICIENT if report.get('missing_paths') or unknown else READY)
    return report
