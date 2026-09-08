#!/usr/bin/env python3
"""Retain ED2 binaries/logs, remove only reproducible source/build scratch."""
from __future__ import annotations
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import sys

BINARIES=('jass_ed2_source','jass_ed2_value_probe')

def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1<<20),b''): h.update(chunk)
    return h.hexdigest()

def cleanup(work: Path, artifact: Path):
    if work.is_symlink() or artifact.is_symlink():
        raise ValueError('refusing symlink work/artifact root')
    work=work.resolve(strict=True); artifact=artifact.resolve(strict=True)
    if work.name!='work' or artifact!=work.parent/'artefacts':
        raise ValueError('expected sibling run/work and run/artefacts')
    targets=[work/'src',work/'build']
    if any(p.is_symlink() or (p.exists() and not p.is_dir()) for p in targets):
        raise ValueError('scratch target is not an ordinary directory')
    if (artifact/'build-outputs').is_symlink():
        raise ValueError('refusing symlink binary archive')
    archive=artifact/'build-outputs'; archive.mkdir(exist_ok=True)
    binary_receipts={}
    for name in BINARIES:
        source=work/'build'/name
        if source.is_symlink(): raise ValueError('refusing symlink build binary')
        if not source.is_file(): continue
        dest=archive/(name+'.gz')
        with source.open('rb') as src, dest.open('xb') as raw:
            with gzip.GzipFile(filename='',mode='wb',fileobj=raw,mtime=0) as out:
                shutil.copyfileobj(src,out)
        binary_receipts[name]=dict(sha256=digest(source),size_bytes=source.stat().st_size,
                                  archive_sha256=digest(dest))
    # Keep build-specific failure diagnostics before removing the build tree.
    build=work/'build'
    if build.exists():
        for source in build.rglob('*'):
            if source.is_symlink() or not source.is_file(): continue
            if source.suffix!='.log' and source.name!='CMakeConfigureLog.yaml': continue
            dest=archive/'logs'/source.relative_to(build)
            dest.parent.mkdir(parents=True,exist_ok=True)
            with source.open('rb') as src, dest.open('xb') as out: shutil.copyfileobj(src,out)
    removed={}
    for target in targets:
        if not target.exists(): continue
        files=[p for p in target.rglob('*') if p.is_file() and not p.is_symlink()]
        removed[target.name]=dict(files=len(files),bytes=sum(p.stat().st_size for p in files))
        shutil.rmtree(target)
    report=dict(schema='jass.ed2.scratch_publication_cleanup.v1',removed=removed,
                retained_binaries=binary_receipts,scientific_artifacts_modified=False,
                inputs_and_other_work_files_preserved=True)
    receipt=artifact/'scratch-cleanup.json'
    # Reentry with no remaining scratch is a no-op, preserving the first receipt.
    if receipt.exists():
        if removed or binary_receipts: raise ValueError('refusing cleanup receipt overwrite')
        return json.loads(receipt.read_text())
    with receipt.open('x') as f: json.dump(report,f,sort_keys=True,indent=2);f.write('\n')
    return report

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--work',type=Path,required=True)
    p.add_argument('--artifact',type=Path,required=True)
    a=p.parse_args()
    try:
        print(json.dumps(cleanup(a.work,a.artifact),sort_keys=True));return 0
    except (OSError,ValueError) as e:
        print('ED2_SCRATCH_CLEANUP_FAILURE: '+str(e),file=sys.stderr);return 2
if __name__=='__main__':raise SystemExit(main())
