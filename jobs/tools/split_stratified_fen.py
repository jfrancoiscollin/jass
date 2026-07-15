#!/usr/bin/env python3
"""Split a frozen FEN gauge by ``palier=p1_net|p2_moyen|p3_mince|p4_egal``.

Every non-comment position must carry exactly one supported palier. The command
fails if a position is unclassified or if any required stratum is empty.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

STRATA = ("p1_net", "p2_moyen", "p3_mince", "p4_egal")
PALIER_RE = re.compile(r"(?:^|\s)palier=(p1_net|p2_moyen|p3_mince|p4_egal)(?:\s|$)")


def split_lines(lines: list[str]) -> dict[str, list[str]]:
    groups: dict[str, list[str]] = defaultdict(list)
    for line_number, raw in enumerate(lines, 1):
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        fen, sep, comment = raw.partition("#")
        fen = fen.strip()
        if not fen:
            continue
        match = PALIER_RE.search(comment if sep else "")
        if not match:
            raise ValueError(f"line {line_number}: missing/invalid palier metadata")
        groups[match.group(1)].append(fen)
    for stratum in STRATA:
        if not groups.get(stratum):
            raise ValueError(f"required stratum {stratum} is empty")
    return {stratum: groups[stratum] for stratum in STRATA}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--manifest", required=True)
    args = parser.parse_args(argv)
    try:
        groups = split_lines(Path(args.input).read_text(encoding="utf-8").splitlines())
        out_dir = Path(args.out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        files = {}
        for stratum, fens in groups.items():
            target = out_dir / f"{stratum}.fen"
            target.write_text("\n".join(fens) + "\n", encoding="utf-8")
            files[stratum] = {"path": str(target), "records": len(fens)}
        manifest = {"strata": files, "total": sum(v["records"] for v in files.values())}
        Path(args.manifest).write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 4
    print(json.dumps(manifest, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
