#!/usr/bin/env python3
from __future__ import annotations
import argparse, gzip, hashlib, json, os, pathlib, shutil, subprocess, tarfile, tempfile

def rclone_bytes(rclone: str, remote: str) -> bytes:
    return subprocess.check_output([rclone, 'cat', remote])

def main() -> int:
    p = argparse.ArgumentParser(description='Restore one file from a Jass R2 historical snapshot')
    p.add_argument('--archive-prefix', required=True)
    p.add_argument('--branch', choices=('main', 'develop'), required=True)
    p.add_argument('--path', required=True)
    p.add_argument('--dest')
    p.add_argument('--rclone', default=os.environ.get('RCLONE_BIN', 'rclone'))
    a = p.parse_args()
    prefix = a.archive_prefix.rstrip('/')
    paths_raw = gzip.decompress(rclone_bytes(a.rclone, prefix + '/manifests/paths.jsonl.gz')).decode('utf-8')
    entries = [json.loads(line) for line in paths_raw.splitlines() if line]
    matches = [e for e in entries if e['branch'] == a.branch and e['path'] == a.path]
    if len(matches) != 1:
        raise SystemExit(f'expected one archived path, found {len(matches)}')
    target = matches[0]
    oids = sorted({e['oid'] for e in entries})
    index = oids.index(target['oid'])
    packs = json.loads(rclone_bytes(a.rclone, prefix + '/manifests/packs.json'))
    cursor = 0
    pack = None
    for item in packs:
        count = int(item['blob_count'])
        if cursor <= index < cursor + count:
            pack = item
            break
        cursor += count
    if pack is None:
        raise SystemExit('blob pack not found')
    dest = pathlib.Path(a.dest or a.path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.Popen([a.rclone, 'cat', pack['remote']], stdout=subprocess.PIPE)
    assert proc.stdout is not None
    found = False
    with tarfile.open(fileobj=proc.stdout, mode='r|gz') as tf:
        for member in tf:
            if member.name != 'blobs/' + target['oid']:
                continue
            source = tf.extractfile(member)
            if source is None:
                raise SystemExit('archived blob unreadable')
            algo = hashlib.sha1 if len(target['oid']) == 40 else hashlib.sha256
            digest = algo()
            digest.update(f'blob {member.size}\0'.encode())
            with dest.open('wb') as output:
                while True:
                    chunk = source.read(8 * 1024 * 1024)
                    if not chunk:
                        break
                    output.write(chunk)
                    digest.update(chunk)
            if digest.hexdigest() != target['oid']:
                dest.unlink(missing_ok=True)
                raise SystemExit('restored Git blob checksum mismatch')
            found = True
            break
    rc = proc.wait()
    if rc != 0 or not found:
        dest.unlink(missing_ok=True)
        raise SystemExit('blob extraction failed')
    if target.get('mode') == '100755':
        dest.chmod(dest.stat().st_mode | 0o111)
    print(dest)
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
