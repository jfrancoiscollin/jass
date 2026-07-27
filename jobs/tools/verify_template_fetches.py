#!/usr/bin/env python3
"""Vérifie que chaque `--file <source>` d'un template existe dans le run épinglé.

Extrait les paires (prefix variable, source path) du template, résout les
prefixes depuis le lanceur, puis interroge l'object store. Ferme la classe de
bug de home-0994 : un renommage global avait réécrit le chemin SOURCE d'un
fetch amont, que la vérification manuelle ne pouvait pas voir puisqu'elle
portait sur une liste tapée à la main plutôt que sur le template.
"""
from __future__ import annotations

import os
import re
import sys

import boto3
import botocore.config


def parse_template(path: str) -> list[tuple[str, str]]:
    text = open(path, encoding="utf-8").read()
    out, current = [], None
    for line in text.splitlines():
        m = re.search(r'fetch_result_files\.py --prefix "\$\{?(\w+)', line)
        if m:
            current = m.group(1)
        f = re.search(r'--file\s+(\S+?)=', line)
        if f and current:
            out.append((current, f.group(1)))
        if "--out-dir" in line:
            current = None
    return out


def parse_launcher(path: str) -> dict[str, str]:
    text = open(path, encoding="utf-8").read()
    return dict(re.findall(r'^export (\w+)="([^"]+)"$', text, re.M))


def main() -> int:
    template, launcher = sys.argv[1], sys.argv[2]
    pairs = parse_template(template)
    env = parse_launcher(launcher)
    s3 = boto3.client(
        "s3",
        endpoint_url=os.environ["RCLONE_CONFIG_R2_ENDPOINT"],
        aws_access_key_id=os.environ["RCLONE_CONFIG_R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["RCLONE_CONFIG_R2_SECRET_ACCESS_KEY"],
        config=botocore.config.Config(signature_version="s3v4", region_name="auto"),
    )
    cache: dict[str, set[str]] = {}
    bad = 0
    for var, src in pairs:
        prefix = env.get(var)
        if not prefix:
            print(f"  ?? {var} absent du lanceur ({src})")
            bad += 1
            continue
        key = prefix.replace("r2:jass-data/", "")
        if key not in cache:
            keys, token = set(), None
            while True:
                kw = {"Bucket": "jass-data", "Prefix": key + "/"}
                if token:
                    kw["ContinuationToken"] = token
                r = s3.list_objects_v2(**kw)
                keys |= {o["Key"][len(key) + 1 :] for o in r.get("Contents", [])}
                if not r.get("IsTruncated"):
                    break
                token = r["NextContinuationToken"]
            cache[key] = keys
        ok = src in cache[key]
        bad += 0 if ok else 1
        print(f"  {'OK  ' if ok else 'MANQUE'} {var}: {src}")
    print(f"\n{len(pairs)} fetches extraits DU TEMPLATE — {'TOUS RÉSOLUS' if not bad else f'{bad} EN ÉCHEC'}")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
