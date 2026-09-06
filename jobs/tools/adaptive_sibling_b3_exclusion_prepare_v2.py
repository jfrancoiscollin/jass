#!/usr/bin/env python3
"""Run B3 exclusion preparation and bind its immutable artifact identities in summary."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

if __package__ in (None, ""):
    ROOT = Path(__file__).resolve().parents[2]
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))

from jobs.tools import adaptive_sibling_b3_exclusion_prepare as base  # noqa: E402


class SummaryReceiptError(RuntimeError):
    pass


def run(work_dir: Path, artifact_dir: Path) -> dict[str, object]:
    summary = dict(base.run(work_dir, artifact_dir))
    union_path = artifact_dir / "b3-fresh-exclusion-union.txt"
    manifest_path = artifact_dir / "b3-fresh-exclusion-manifest.json"
    summary_path = artifact_dir / "scientific-summary.json"

    manifest = base.read_canonical_json(manifest_path)
    union = manifest.get("union")
    if not isinstance(union, dict):
        raise SummaryReceiptError("exclusion manifest union descriptor missing")
    expected_union_sha = base.sha256_file(union_path)
    if union.get("sha256") != expected_union_sha:
        raise SummaryReceiptError("exclusion union SHA differs from manifest")
    if union.get("unique_canonical") != base.EXPECTED_COMBINED_UNIQUE:
        raise SummaryReceiptError("exclusion union cardinality differs from manifest")

    summary["exclusion_union_sha256"] = expected_union_sha
    summary["exclusion_manifest_sha256"] = base.sha256_file(manifest_path)
    summary["exclusion_union_size_bytes"] = union_path.stat().st_size
    summary["exclusion_manifest_size_bytes"] = manifest_path.stat().st_size
    summary_path.write_bytes(base.canonical_json(summary))
    reread = base.read_canonical_json(summary_path)
    if reread != summary:
        raise SummaryReceiptError("scientific summary roundtrip mismatch")
    return summary


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--artifact-dir", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    try:
        args = parse_args(argv)
        summary = run(args.work_dir, args.artifact_dir)
    except (SummaryReceiptError, base.ExclusionPrepareError, OSError) as exc:
        print(f"adaptive_sibling_b3_exclusion_prepare_v2: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(summary, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
