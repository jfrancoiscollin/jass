#!/usr/bin/env python3
"""ED2-N1: authenticated TRAIN reuse plus explicitly amended numerical solver."""
from __future__ import annotations
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import sys
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

JOB = 'cpx62-1876-l3-ed2-paired-value-fit-v1'
ATTEMPT = '20260908T182614Z-27c30b3f'
CODE = '27c30b3f5b4bc4ee971bb4acfcf0a423e124f7da'
P0_SEAL = '31f763049fef50544bd1cbb240eeb4f51670728ae0697a77e982186df007152c'
ERROR = ('ED2_PAIRED_VALUE_TECHNICAL_FAILURE: optimizer did not converge: '
         'STOP: TOTAL NO. OF ITERATIONS REACHED LIMIT')


def read(path):
    return json.loads(path.read_text())


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def validate_inventory(inv):
    if (inv.get('job_id'), inv.get('attempt_id'), inv.get('code_sha'),
            inv.get('result_state'), inv.get('exit_code')) != (JOB, ATTEMPT, CODE, 'failed', 2):
        raise ValueError('recovery source identity/state drift')
    # Inspect the COMPLETE authenticated inventory, not just the artifact list.
    forbidden = ('POINT', 'PARTIAL', 'models-sealed', 'test-')
    for item in inv['files']:
        if Path(item['path']).name.startswith(forbidden):
            raise ValueError('recovery source has candidate or TEST evidence')


def validate_bundle(root, original_recipe):
    lines = (root/'execution-logs/pipeline.log').read_text().splitlines()
    if ERROR not in lines or any('phase=fit-partial' in x for x in lines):
        raise ValueError('recovery only admits the authenticated POINT maxiter failure')
    seal = read(root/'train-labels-sealed.json')
    if (seal.get('source_seal') != P0_SEAL or seal.get('recipe') != original_recipe
            or seal.get('test_teacher_calls') != 0):
        raise ValueError('source labels/recipe/information barrier drift')
    expected = {f'train-{i}.jsonl': digest(root/f'train-{i}.jsonl') for i in range(8)}
    if seal.get('teacher_files') != expected:
        raise ValueError('source TRAIN label hash mismatch')
    if seal.get('support') != read(root/'label-support.json'):
        raise ValueError('source label support mismatch')
    if read(root/'wdl-selection.seal.json').get('sha256') != digest(root/'wdl-selection.json'):
        raise ValueError('source WDL selection seal mismatch')
    selection = read(root/'wdl-selection.json')
    for role in ('replay', 'wdl_holdout'):
        if selection['subsets'][role]['data_sha256'] != digest(root/(role+'.jnnw')):
            raise ValueError('source WDL subset hash mismatch')
    return seal


def authenticate(root, art, original_recipe):
    from jobs.tools.fetch_result_files import inspect_result_inventory, fetch_files
    prefix = f'r2:jass-data/runs/{JOB}/{ATTEMPT}'
    inv = inspect_result_inventory(rclone='rclone', prefix=prefix, expected_state='failed')
    validate_inventory(inv)
    names = ([f'train-{i}.jsonl' for i in range(8)] + [
        'execution-logs/pipeline.log', 'train-labels-sealed.json', 'label-support.json',
        'train-teacher.json', 'wdl-selection.json', 'wdl-selection.seal.json',
        'replay.jnnw', 'wdl_holdout.jnnw',
        'native/train-native.tsv.gz', 'native/replay-native.tsv.gz'])
    receipt = fetch_files(rclone='rclone', prefix=prefix,
                          selections=[('artefacts/'+n, n) for n in names],
                          out_dir=root, expected_state='failed')
    validate_bundle(root, original_recipe)
    with (art/'verified-recovery-source.json').open('x') as f:
        json.dump(receipt, f, indent=2, sort_keys=True); f.write('\n')
    return root


def reuse_train(pipeline, source, root, art, work, original_recipe):
    """No Scan process can be launched through this function."""
    seal = validate_bundle(root, original_recipe)
    if read(art/'wdl-selection.json') != read(root/'wdl-selection.json'):
        raise ValueError('reproduced WDL selection differs from sealed original')
    for role in ('replay', 'wdl_holdout'):
        if digest(art/(role+'.jnnw')) != digest(root/(role+'.jnnw')):
            raise ValueError('reproduced WDL rows differ from original')
    for name in ('train-native.tsv', 'replay-native.tsv'):
        with gzip.open(root/'native'/(name+'.gz'), 'rb') as f:
            expected = hashlib.sha256(f.read()).hexdigest()
        if digest(work/name) != expected:
            raise ValueError('native BASE feature/value replay differs from original')
    groups = pipeline.groups_for(source, 'train')
    files = [root/f'train-{i}.jsonl' for i in range(8)]
    values, cost = pipeline.load_scores(files, groups, (5000, 50000))
    historical = read(root/'train-teacher.json')
    if any(historical.get(k) != v for k, v in cost.items()):
        raise ValueError('reused TRAIN coverage/cost does not match original receipt')
    for arm in pipeline.ARMS:
        _, support = pipeline.m.pair_edges(groups, values, arm)
        if support != seal['support'][arm]:
            raise ValueError('reconstructed label support differs from original')
    for src in files:
        with src.open('rb') as inp, (art/src.name).open('xb') as out:
            shutil.copyfileobj(inp, out)
    cost.update(reused=True, source_job=JOB, source_attempt=ATTEMPT,
                new_searches=0, new_requested_nodes=0,
                historical_wall_seconds=historical.get('wall_seconds'))
    pipeline.m.write_new(art/'train-teacher.json', cost)
    pipeline.m.write_new(art/'recovery-reuse.json', dict(
        source_job=JOB, source_attempt=ATTEMPT, source_code=CODE,
        label_seal_sha256=digest(root/'train-labels-sealed.json'),
        wdl_selection_identical=True, native_base_tables_identical=True,
        teacher_bytes_identical=True, new_train_searches=0,
        avoided_train_requested_nodes=cost['requested_nodes']))
    return values, cost


def main():
    from jobs.tools import ed2_value_pipeline as pipeline
    from jobs.tools import ed2_value_trust_exact as solver
    from jobs.tools.ed2_value_entrypoint import install_shutdown_handlers
    if len(sys.argv) < 2 or sys.argv[1] != 'run':
        raise ValueError('recovery entrypoint supports run only')
    install_shutdown_handlers()
    original_run = pipeline.run
    original_search = pipeline.role_search
    original_terminal = pipeline.terminal
    original_recipe = dict(pipeline.m.RECIPE)
    new_recipe = {k: v for k, v in original_recipe.items()
                  if k not in ('maxiter', 'maxcor', 'gtol', 'ftol', 'maxls')}
    new_recipe.update(numerical_version='ED2-N1', optimizer=solver.SOLVER)

    def run(args):
        root = args.work/'reuse-1876'
        authenticate(root, args.art, original_recipe)
        if digest(args.source_seal) != P0_SEAL:
            raise ValueError('P0 source seal is not the original immutable dataset')
        def search(source, scan, role, art, work, pre):
            if role == 'train':
                return reuse_train(pipeline, source, root, art, work, original_recipe)
            return original_search(source, scan, role, art, work, pre)
        pipeline.role_search = search
        pipeline.m.RECIPE = new_recipe
        pipeline.m.fit = solver.fit
        return original_run(args)

    def terminal(art, verdict, **kw):
        # Distinct tokens: never overwrite or reinterpret ED2-P1's failed run.
        verdict = verdict.replace('ED2_', 'ED2_N1_', 1)
        kw.update(numerical_version='ED2-N1', original_failed_job=JOB,
                  original_failed_attempt=ATTEMPT, new_train_teacher_searches=0,
                  optimizer_amendment=solver.SOLVER)
        return original_terminal(art, verdict, **kw)
    pipeline.run = run
    pipeline.terminal = terminal
    return pipeline.main()


if __name__ == '__main__':
    raise SystemExit(main())
