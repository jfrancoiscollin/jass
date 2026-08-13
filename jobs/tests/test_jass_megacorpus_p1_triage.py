# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

from collections import Counter
import gzip
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "jobs" / "tools" / "jass_megacorpus_p1_triage.py"
SPEC = importlib.util.spec_from_file_location("jass_megacorpus_p1_triage", TOOL)
assert SPEC is not None and SPEC.loader is not None
P1 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(P1)


def candidate(
    candidate_id: str,
    *,
    source_id: str,
    path: str,
    disposition: str,
    source_class: str = "runner_attempt",
    reasons: list[str] | None = None,
    risks: list[str] | None = None,
    digest: str | None = None,
    size: int | None = 3808,
    metadata: str | None = "artefacts/data.jsm.gz",
    parents: list[str] | None = None,
) -> dict:
    return {
        "schema": P1.CANDIDATE_SCHEMA,
        "candidate_id": candidate_id,
        "source_id": source_id,
        "source_class": source_class,
        "data": {
            "path": path,
            "r2_uri": f"r2:jass-data/{path}" if source_class != "historical_git_snapshot" else None,
            "size_bytes": size,
            "declared_sha256": digest,
            "payload_bytes_verified": False,
        },
        "metadata": {
            "path": metadata,
            "pairing": "exact_basename" if metadata else "missing_or_ambiguous",
        },
        "origin": {
            "job_id": "home-clean" if source_class == "runner_attempt" else None,
            "attempt_id": "attempt-1" if source_class == "runner_attempt" else None,
            "parent_corpus_ids": parents,
        },
        "quality": {
            "disposition": disposition,
            "reasons": reasons or [],
            "risk_tags": risks or [],
            "strength_or_loss_used_for_classification": False,
            "automatic_training_admission": False,
        },
    }


def attempt(source_id: str, state: str = "verified_completed") -> dict:
    return {
        "schema": P1.ATTEMPT_SCHEMA,
        "source_id": source_id,
        "audit_state": state,
        "audit_errors": [],
    }


def write_jsonl_gz(path: Path, rows: list[dict]) -> None:
    with gzip.open(path, "wt", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line]


class MegaCorpusP1TriageTest(unittest.TestCase):
    def test_triage_is_fail_closed_and_builds_evidence_only_lineage(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            duplicate_sha = "a" * 64
            rows = [
                candidate("c-review", source_id="s-clean", path="runs/clean/data.jnnw.gz",
                          disposition="review", digest="b" * 64),
                candidate("c-risk", source_id="s-clean", path="runs/clean/replay-mix.jnnw.gz",
                          disposition="quarantine",
                          reasons=["derived_or_special_domain_requires_lineage_review"],
                          risks=["derived_mix"], digest=duplicate_sha),
                candidate("c-duplicate", source_id="s-other", path="runs/other/copy.jnnw.gz",
                          disposition="quarantine",
                          reasons=["runner_metadata_not_verified"], digest=duplicate_sha),
                candidate("c-snapshot", source_id="s-snapshot", path="archive/old.jnnw.gz",
                          disposition="quarantine", source_class="historical_git_snapshot",
                          reasons=["historical_git_snapshot_requires_blob_restore_and_lineage_review"],
                          digest=None, size=None),
                candidate("c-reject", source_id="s-failed", path="runs/failed/data.jnnw.gz",
                          disposition="reject", reasons=["failed_runner_attempt"],
                          parents=["c-review"]),
            ]
            candidates = root / "candidates.jsonl.gz"
            attempts = root / "attempts.jsonl.gz"
            write_jsonl_gz(candidates, rows)
            write_jsonl_gz(attempts, [
                attempt("s-clean"), attempt("s-other", "unverified"), attempt("s-failed", "verified_failed")
            ])
            out = root / "out"
            summary = P1.run(type("Args", (), {
                "candidates": str(candidates), "attempts": str(attempts), "out_dir": str(out),
            })())

            self.assertEqual(summary["preliminary_buckets"], {
                "quarantine": 3, "reject": 1, "sample": 1,
            })
            self.assertEqual(summary["payload_sample_candidate_count"], 1)
            self.assertEqual(summary["training_accept_count"], 0)
            self.assertEqual(summary["exact_duplicate_group_count"], 1)
            self.assertEqual(summary["filename_inferred_lineage_edge_count"], 0)
            review = json.loads((out / "review-candidates.json").read_text())
            self.assertEqual([row["candidate_id"] for row in review["candidates"]], ["c-review"])
            self.assertFalse(review["payload_sample_authorized"])

            triage = {row["candidate_id"]: row for row in read_jsonl(out / "candidate-triage.jsonl")}
            self.assertEqual(triage["c-risk"]["recovery_route"], "resolve_derived_lineage")
            self.assertEqual(triage["c-duplicate"]["recovery_route"], "repair_runner_audit")
            self.assertEqual(triage["c-snapshot"]["recovery_route"], "restore_snapshot_metadata_first")
            self.assertTrue(all(not row["accepted_for_training"] for row in triage.values()))

            graph = read_jsonl(out / "lineage-graph.jsonl")
            edge_types = Counter(row["edge_type"] for row in graph if row["kind"] == "edge")
            self.assertEqual(edge_types["source_contains_candidate"], 5)
            self.assertEqual(edge_types["declared_exact_duplicate"], 1)
            self.assertEqual(edge_types["explicit_parent"], 1)
            self.assertFalse(any("filename" in row.get("evidence", "") for row in graph if isinstance(row.get("evidence"), str)))

    def test_rejects_duplicate_ids_and_missing_runner_source(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            candidates = root / "candidates.jsonl.gz"
            attempts = root / "attempts.jsonl.gz"
            row = candidate("same", source_id="missing", path="a.jnnw", disposition="review")
            write_jsonl_gz(candidates, [row, {**row, "data": {**row["data"], "path": "b.jnnw"}}])
            write_jsonl_gz(attempts, [attempt("other")])
            with self.assertRaisesRegex(ValueError, "duplicate candidate_id"):
                P1.run(type("Args", (), {
                    "candidates": str(candidates), "attempts": str(attempts), "out_dir": str(root / "out"),
                })())

            write_jsonl_gz(root / "one.jsonl.gz", [row])
            with self.assertRaisesRegex(ValueError, "runner source is absent"):
                P1.run(type("Args", (), {
                    "candidates": str(root / "one.jsonl.gz"), "attempts": str(attempts),
                    "out_dir": str(root / "out2"),
                })())


if __name__ == "__main__":
    unittest.main()
