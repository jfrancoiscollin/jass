#!/usr/bin/env python3
"""Fail CI when active code introduces legacy branch or clone references.

Archives and historical result snapshots are intentionally excluded. During the
physical tools/ migration, existing findings can be supplied as a baseline; new
findings always fail.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

PATTERNS = {
    "hardcoded_root_clone": re.compile(r"/root/jass"),
    "legacy_remote_ref": re.compile(r"origin/main"),
    "legacy_head_ref": re.compile(r"HEAD:main"),
    "legacy_full_ref": re.compile(r"refs/heads/main"),
}
EXCLUDED_PREFIXES = ("archive/", "archives/", "jobs/results/", ".git/")
TEXT_SUFFIXES = {".sh", ".py", ".yml", ".yaml", ".md", ".txt", ".cmake", ".json", ".toml", ".ini", ".service", ".timer"}


def tracked_files(root: Path) -> list[str]:
    out = subprocess.check_output(["git", "-C", str(root), "ls-files"], text=True)
    return [p for p in out.splitlines() if p and not p.startswith(EXCLUDED_PREFIXES)]


def findings(root: Path) -> list[dict[str, object]]:
    found: list[dict[str, object]] = []
    for rel in tracked_files(root):
        path = root / rel
        if path.suffix.lower() not in TEXT_SUFFIXES and path.name not in {"Makefile", "CMakeLists.txt"}:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for lineno, line in enumerate(text.splitlines(), 1):
            for kind, rx in PATTERNS.items():
                if rx.search(line):
                    found.append({"kind": kind, "path": rel, "line": lineno})
    return found


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--write", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    current = findings(root)
    if args.write:
        args.write.write_text(json.dumps(current, indent=2, sort_keys=True) + "\n")
    baseline = []
    if args.baseline and args.baseline.exists():
        baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
    baseline_keys = {(x["kind"], x["path"], x["line"]) for x in baseline}
    new = [x for x in current if (x["kind"], x["path"], x["line"]) not in baseline_keys]
    if new:
        print(json.dumps(new, indent=2, sort_keys=True))
        return 1
    print(f"legacy-reference guard: {len(current)} baseline finding(s), no new finding")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
