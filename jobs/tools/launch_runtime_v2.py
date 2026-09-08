#!/usr/bin/env python3
"""Structured, bounded diagnostics; never copy exception messages or environments."""
from __future__ import annotations
import datetime as dt
import json
import os
from pathlib import Path
import re
import subprocess
import traceback

SAFE = re.compile(r'^[A-Za-z0-9_.:-]{1,120}$')
EFFECTS = ('fits', 'new_scan_searches', 'new_jass_searches', 'strength_games',
           'selfplay_games', 'promotions', 'bakes', 'test_target_reads')


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def atomic_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise ValueError('symlink output')
    tmp = path.with_name(path.name + '.tmp')
    with tmp.open('x', encoding='utf-8') as f:
        json.dump(value, f, sort_keys=True, indent=2, allow_nan=False)
        f.write('\n')
    os.replace(tmp, path)


def available_cpus():
    env = dict(os.environ)
    for key in ('OMP_NUM_THREADS', 'OMP_THREAD_LIMIT'):
        env.pop(key, None)
    return int(subprocess.check_output(['nproc'], env=env, text=True, timeout=5).strip())


class StageEvidence:
    """Checkpoint each completed phase. An exception never marks the phase complete."""
    def __init__(self, artifact: Path, mode: str):
        if mode not in ('rehearsal', 'production'):
            raise ValueError('invalid mode')
        self.path = artifact / 'execution-evidence.json'
        if self.path.exists():
            raise ValueError('existing evidence')
        self.value = dict(schema='jass.execution_evidence.v2', mode=mode,
                          state='running', phase='initialize', completed_phases=[],
                          actual_side_effects={k: 0 for k in EFFECTS})
        self.save()

    def save(self):
        self.value['snapshot_at'] = now()
        atomic_json(self.path, self.value)
        summary = self.path.parent / 'scientific-summary.json'
        previous = json.loads(summary.read_text()) if summary.exists() else {}
        if not previous or previous.get('schema') == 'jass.launch_progress.v2':
            atomic_json(summary, dict(schema='jass.launch_progress.v2', state=self.value['state'],
                        phase=self.value['phase'], snapshot_at=self.value['snapshot_at'],
                        completed_phases=self.value['completed_phases'], scientific_verdict=None,
                        actual_side_effects=self.value['actual_side_effects']))

    def begin(self, name: str):
        if not SAFE.fullmatch(name):
            raise ValueError('invalid phase name')
        self.value['phase'] = name
        self.save()

    def complete(self):
        name = self.value['phase']
        if name in self.value['completed_phases']:
            raise ValueError('duplicate phase')
        self.value['completed_phases'].append(name)
        self.save()

    def finish(self):
        self.value['state'] = 'completed'
        self.save()

    def fail(self, exc: BaseException):
        # The raw exception goes to the private stage log. GitOps gets class and
        # source location only: no credentials, target values, or arbitrary log text.
        frames = traceback.extract_tb(exc.__traceback__)[-6:]
        self.value.update(state='failed', error_type=type(exc).__name__,
                          frames=[dict(file=Path(f.filename).name, line=f.lineno,
                                       function=f.name) for f in frames])
        self.save()
