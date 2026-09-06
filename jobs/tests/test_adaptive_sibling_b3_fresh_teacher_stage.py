from __future__ import annotations

from argparse import Namespace
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from jobs.tools import adaptive_sibling_b3_fresh_teacher_stage as subject
from jobs.tools import adaptive_sibling_b3_fresh_source_runtime as source_runtime


class FreshB3TeacherTests(unittest.TestCase):
    def _publication(self, root: Path) -> dict:
        parents = root / "parents.jnnw"
        parents.write_bytes(b"JNNW" + (4000).to_bytes(4, "little") + b"\0" * (4000 * 38))
        tsv = root / "parents.tsv"
        tsv.write_text("x\n" * 4000, encoding="utf-8")
        identities = root / "ordered-identities.txt"
        identities.write_text("x\n" * 4000, encoding="ascii")
        return {
            "schema": source_runtime.SUCCESS_SCHEMA,
            "verdict": source_runtime.SUCCESS_VERDICT,
            "selection": {
                "parents": 4000,
                "forbidden_overlap": 0,
                "target_blind": True,
                "cells": {f"c{i}": 500 for i in range(8)},
                "parents_jnnw": subject.descriptor(parents, records=4000, record_size_bytes=38),
                "parents_tsv": subject.descriptor(tsv, rows=4000),
                "ordered_identities": subject.descriptor(
                    identities, rows=4000,
                    serialization="canonical_fingerprint_ascii, one per line, LF terminated"),
            },
        }

    def test_source_publication_requires_balanced_target_blind_4000(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            publication = self._publication(root)
            subject.verify_source_publication(publication, root)
            publication["selection"]["forbidden_overlap"] = 1
            with self.assertRaisesRegex(subject.StageError, "forbidden_overlap"):
                subject.verify_source_publication(publication, root)

    def test_source_publication_consumes_actual_publisher_population_schema(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            publication = self._publication(root)
            self.assertNotIn("selected", publication["selection"])
            self.assertNotIn("cell_quota", publication["selection"])
            subject.verify_source_publication(publication, root)
            publication["selection"].pop("parents")
            publication["selection"]["selected"] = 4000
            publication["selection"]["cell_quota"] = 500
            with self.assertRaisesRegex(subject.StageError, "parents"):
                subject.verify_source_publication(publication, root)

    def test_fetch_source_derives_publication_sha_after_authenticated_fetch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp) / "work"
            work.mkdir()
            target = work / "source"
            publication = target / "source-selection-publication.json"

            def fake_fetch(*_args, **kwargs):
                out_dir = kwargs["out_dir"]
                out_dir.mkdir()
                payload = self._publication(out_dir)
                publication.write_text(json.dumps(payload), encoding="utf-8")

            args = Namespace(
                source_prefix="r2:test", source_job="job", source_attempt="attempt",
                source_code_sha="a" * 40,
            )
            with mock.patch.object(subject.parity_stage, "fetch_completed", side_effect=fake_fetch):
                result_parents, result_publication, digest = subject.fetch_source(args, work)
            self.assertEqual(result_parents, target / "parents.jnnw")
            self.assertEqual(result_publication["verdict"], source_runtime.SUCCESS_VERDICT)
            self.assertEqual(digest, subject.parity_stage.sha_file(publication))

    def test_cli_no_longer_requires_duplicated_publication_sha(self) -> None:
        args = subject.parse_args([
            "--work-dir", "/tmp/work",
            "--artifact-dir", "/tmp/artifacts",
            "--source-job", "job",
            "--source-attempt", "attempt",
            "--source-code-sha", "a" * 40,
            "--source-prefix", "r2:test",
        ])
        self.assertEqual(args.source_job, "job")
        self.assertFalse(hasattr(args, "source_publication_sha256"))

    def test_teacher_contract_is_parity_established(self) -> None:
        self.assertEqual(subject.PARITY_RENDERED_SHA256,
                         "a5f77f92abc7e77a8488c2c4751d71608d90cba04829a44f7c434138cb766d8f")
        self.assertEqual(subject.VERDICT, "B3_FRESH_ADAPTIVE_TEACHER_COMPLETE_V1")


if __name__ == "__main__":
    unittest.main()
