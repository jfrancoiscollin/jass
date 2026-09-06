#!/usr/bin/env python3
"""Run the parity-established real B3 adaptive teacher on a sealed fresh cohort.

The fresh source cohort is authenticated from its publication receipt. This
stage reuses the exact B3 teacher renderer/runtime proven by job 1833 and does
not read or execute any full-ladder audit reference. No fit, game, promotion or
bake is reachable here.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import sys
from typing import Any, Mapping, Sequence

if __package__ in (None, ""):
    ROOT = Path(__file__).resolve().parents[2]
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
else:
    ROOT = Path(__file__).resolve().parents[2]

from jobs.tools import adaptive_sibling_b3_parity_stage as parity_stage  # noqa: E402
from jobs.tools import adaptive_sibling_b3_fresh_source_runtime as source_runtime  # noqa: E402

SCHEMA = "jass.adaptive_sibling_b3_fresh_teacher_stage.v1"
VERDICT = "B3_FRESH_ADAPTIVE_TEACHER_COMPLETE_V1"
PARITY_RENDERED_SHA256 = "a5f77f92abc7e77a8488c2c4751d71608d90cba04829a44f7c434138cb766d8f"


class StageError(RuntimeError):
    pass


def canonical(value: object) -> bytes:
    return parity_stage.canonical(value)


def write_new(path: Path, raw: bytes) -> None:
    parity_stage.write_new(path, raw)


def descriptor(path: Path, **extra: object) -> dict[str, object]:
    if path.is_symlink() or not path.is_file():
        raise StageError(f"not a regular file: {path}")
    return {"local_name": path.name, "sha256": parity_stage.sha_file(path),
            "size_bytes": path.stat().st_size, **extra}


def fetch_source(args: argparse.Namespace, work: Path) -> tuple[Path, dict[str, Any]]:
    target = work / "source"
    mappings = [
        ("artefacts/source-selection-publication.json", "source-selection-publication.json"),
        ("artefacts/parents.jnnw", "parents.jnnw"),
        ("artefacts/parents.tsv", "parents.tsv"),
        ("artefacts/ordered-identities.txt", "ordered-identities.txt"),
    ]
    parity_stage.fetch_completed(
        args.source_prefix, job=args.source_job, attempt=args.source_attempt,
        expected_code=args.source_code_sha, mappings=mappings,
        out_dir=target, report=work / "source-fetch.json",
    )
    publication_path = target / "source-selection-publication.json"
    if parity_stage.sha_file(publication_path) != args.source_publication_sha256:
        raise StageError("source publication SHA mismatch")
    try:
        publication = json.loads(publication_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise StageError("invalid source publication JSON") from exc
    verify_source_publication(publication, target)
    return target / "parents.jnnw", publication


def _matches_descriptor(value: object, path: Path, **extras: object) -> bool:
    if not isinstance(value, Mapping):
        return False
    expected = descriptor(path, **extras)
    return all(value.get(key) == item for key, item in expected.items())


def verify_source_publication(publication: Mapping[str, Any], root: Path) -> None:
    if publication.get("schema") != source_runtime.SUCCESS_SCHEMA \
            or publication.get("verdict") != source_runtime.SUCCESS_VERDICT:
        raise StageError("fresh source publication schema/verdict mismatch")
    selection = publication.get("selection")
    if not isinstance(selection, Mapping):
        raise StageError("fresh source selection receipt missing")
    checks = {
        "selected": 4000,
        "cell_quota": 500,
        "forbidden_overlap": 0,
        "target_blind": True,
    }
    for key, expected in checks.items():
        if selection.get(key) != expected or type(selection.get(key)) is not type(expected):
            raise StageError(f"fresh source selection {key} mismatch")
    if not _matches_descriptor(selection.get("parents_jnnw"), root / "parents.jnnw",
                               records=4000, record_size_bytes=38):
        raise StageError("fresh source parents.jnnw descriptor mismatch")
    if not _matches_descriptor(selection.get("parents_tsv"), root / "parents.tsv", rows=4000):
        raise StageError("fresh source parents.tsv descriptor mismatch")
    if not _matches_descriptor(
        selection.get("ordered_identities"), root / "ordered-identities.txt",
        rows=4000,
        serialization="canonical_fingerprint_ascii, one per line, LF terminated",
    ):
        raise StageError("fresh source ordered identities descriptor mismatch")
    cells = selection.get("cells")
    if not isinstance(cells, Mapping) or set(cells.values()) != {500} or len(cells) != 8:
        raise StageError("fresh source cell balance mismatch")


def run_stage(args: argparse.Namespace) -> dict[str, object]:
    work = args.work_dir
    artifacts = args.artifact_dir
    if work.exists() or work.is_symlink():
        raise StageError("work-dir must be absent")
    work.mkdir(parents=True)
    artifacts.mkdir(parents=True, exist_ok=True)

    parents, source_publication = fetch_source(args, work)
    curriculum = parity_stage.fetch_curriculum(work)
    exe, render_receipt = parity_stage.build_teacher(work)
    if render_receipt.get("rendered_source_sha256") != PARITY_RENDERED_SHA256:
        raise StageError("B3 rendered teacher differs from parity-established bytes")
    reports = parity_stage.run_shards(exe, parents, curriculum, work)
    merged = parity_stage.merge_groups(work)
    aggregate = parity_stage.aggregate_reports(reports)
    if not (aggregate["teacher_searches"] <= aggregate["screen_searches"] <=
            aggregate["cheap_searches"] <= aggregate["emitted_siblings"]):
        raise StageError("fresh B3 nested search-count invariant failed")
    if aggregate["engine_constructions"] != (
        aggregate["cheap_searches"] + aggregate["screen_searches"] + aggregate["teacher_searches"]
    ):
        raise StageError("fresh B3 Engine construction invariant failed")

    groups_out = artifacts / "b3-fresh-adaptive-groups.tsv"
    if groups_out.exists() or groups_out.is_symlink():
        raise StageError("fresh adaptive groups output already exists")
    shutil.copyfile(merged, groups_out)
    source_identity = {
        "job_id": args.source_job,
        "attempt_id": args.source_attempt,
        "code_sha": args.source_code_sha,
        "prefix": args.source_prefix,
        "publication_sha256": args.source_publication_sha256,
        "parents_jnnw": source_publication["selection"]["parents_jnnw"],
        "ordered_identities": source_publication["selection"]["ordered_identities"],
    }
    summary = {
        "schema": SCHEMA,
        "state": "completed",
        "verdict": VERDICT,
        "source": source_identity,
        "fresh_b3_parents": 4000,
        "policy": {"M5": 100, "M50": 60, "minimum_survivors": 2},
        "budgets_nodes": [5000, 50000, 200000],
        "teacher": aggregate,
        "adaptive_groups": descriptor(groups_out, rows=aggregate["emitted_siblings"]),
        "rendered_source_sha256": render_receipt["rendered_source_sha256"],
        "reference_audit_reads": 0,
        "full_ladder_backfill": False,
        "fits": 0,
        "strength_games": 0,
        "promotions": 0,
        "bakes": 0,
        "next_stage": "B3_FRESH_AUDIT_SUBSET_SEAL",
    }
    for name, value in (
        ("b3-fresh-teacher-aggregate.json", aggregate),
        ("b3-fresh-render-receipt.json", render_receipt),
        ("b3-fresh-source-identity.json", source_identity),
        ("scientific-summary.json", summary),
    ):
        write_new(artifacts / name, canonical(value))
    return summary


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--artifact-dir", type=Path, required=True)
    parser.add_argument("--source-job", required=True)
    parser.add_argument("--source-attempt", required=True)
    parser.add_argument("--source-code-sha", required=True)
    parser.add_argument("--source-prefix", required=True)
    parser.add_argument("--source-publication-sha256", required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    try:
        summary = run_stage(parse_args(argv))
    except Exception as exc:
        print(f"adaptive_sibling_b3_fresh_teacher_stage: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({"state": summary["state"], "verdict": summary["verdict"],
                      "next_stage": summary["next_stage"]},
                     sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
