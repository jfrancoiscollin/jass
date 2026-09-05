#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest

from jobs.tools import adaptive_sibling_b2_source_publish as source_publish
from jobs.tools import adaptive_sibling_b2_teacher_preread as preread
from jobs.tools import adaptive_sibling_b2_teacher_source as teacher


class TeacherPreReadTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        self._git("init", "-q")
        self._git("config", "user.email", "b2-test@example.invalid")
        self._git("config", "user.name", "B2 Test")
        (self.repo / "implementation.txt").write_text("X\n")
        self._git("add", "implementation.txt")
        self._git("commit", "-qm", "X")
        self.x = self._git("rev-parse", "HEAD").strip()

        self.prereg_path = "docs/b2-prereg.md"
        (self.repo / "docs").mkdir()
        self.prereg_raw = b"# B2 prereg\n"
        (self.repo / self.prereg_path).write_bytes(self.prereg_raw)
        self._git("add", self.prereg_path)
        self._git("commit", "-qm", "Y")
        self.y = self._git("rev-parse", "HEAD").strip()

        self.parents = self.root / "parents.jnnw"
        self.parents_tsv = self.root / "parents.tsv"
        self.selection_report = self.root / "selection-report.json"
        self.identities = self.root / "ordered-identities.txt"
        record = struct.pack("<QQQQB", 1, 0, 2, 0, 0) + b"\0" * 5
        self.parents.write_bytes(b"JNNW" + struct.pack("<I", 4_000) + record * 4_000)
        self.parents_tsv.write_bytes(b"fixture\n")
        self.identities.write_bytes(b"fixture\n")
        selection = {
            "schema": teacher.SELECTION_SCHEMA,
            "outputs": {"parents_jnnw": {
                "sha256": preread.sha256_file(self.parents),
                "size_bytes": self.parents.stat().st_size, "records": 4_000}},
        }
        self.selection_report.write_bytes(preread.canonical_json_bytes(selection))

        self.f_path = "docs/b2-source-F.json"
        cells = {f"cell-{index}": 500 for index in range(8)}
        f = {
            "schema": source_publish.SUCCESS_SCHEMA, "status": "VALID",
            "verdict": source_publish.SUCCESS_VERDICT, "job_id": "cpx62-test",
            "attempt_id": "attempt-test", "implementation": {"commit": self.x},
            "preregistration": {"commit": self.y, "path": self.prereg_path,
                "file": {"local_name": Path(self.prereg_path).name,
                         "sha256": preread.sha256_bytes(self.prereg_raw),
                         "size_bytes": len(self.prereg_raw),
                         "schema": source_publish.PREREG_SCHEMA}},
            "top_up": False, "regeneration": False, "new_seed": False,
            "scientific_scope": {"teacher_rows": 0, "teacher_searches": 0,
                "fits": 0, "strength_games": 0, "promotions": 0, "bakes": 0,
                "source_generation": {"producer_processes": 16,
                                      "raw_records": 160_000,
                                      "internal_search_count": None,
                                      "self_play_game_count": None},
                "scientific_verdict": None},
            "selection": {"parents": 4_000, "cells": cells,
                "report": self._desc(self.selection_report),
                "parents_jnnw": self._desc(self.parents, records=4_000,
                                            record_size_bytes=38),
                "parents_tsv": self._desc(self.parents_tsv, rows=4_000),
                "ordered_identities": self._desc(
                    self.identities, rows=4_000,
                    serialization="canonical_fingerprint_ascii, one per line, LF terminated"),
                "forbidden_overlap": 0, "target_blind": True,
                "local_seal": {"local_name": "local-selection-seal.json",
                               "sha256": "0" * 64, "size_bytes": 1}},
        }
        self.f_raw = preread.canonical_json_bytes(f)
        (self.repo / self.f_path).write_bytes(self.f_raw)
        self._git("add", self.f_path)
        self._git("commit", "-qm", "S")
        self.s = self._git("rev-parse", "HEAD").strip()
        self._git("checkout", "-q", self.x)
        self.receipt = self.root / "teacher-preread.json"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _git(self, *args: str) -> str:
        completed = subprocess.run(["git", *args], cwd=self.repo, check=True,
                                   stdout=subprocess.PIPE, text=True)
        return completed.stdout

    def _desc(self, path: Path, **extra: object) -> dict[str, object]:
        return {"local_name": path.name, "sha256": preread.sha256_file(path),
                "size_bytes": path.stat().st_size, **extra}

    def _authenticate(self, **overrides: object) -> dict[str, object]:
        values = dict(
            repo_root=self.repo, implementation_commit=self.x,
            preregistration_commit=self.y, preregistration_path=self.prereg_path,
            preregistration_sha256=preread.sha256_bytes(self.prereg_raw),
            source_documentary_commit=self.s, source_publication_path=self.f_path,
            source_publication_sha256=preread.sha256_bytes(self.f_raw),
            parents_jnnw=self.parents, parents_tsv=self.parents_tsv,
            selection_report=self.selection_report, ordered_identities=self.identities,
            receipt_path=self.receipt, git_timeout_seconds=10)
        values.update(overrides)
        return preread.authenticate(**values)

    def test_valid_chain_authenticates_before_teacher(self) -> None:
        receipt = self._authenticate()
        self.assertEqual(receipt["verdict"], "B2_TEACHER_PREREAD_AUTH_COMPLETE")
        self.assertEqual(receipt["barrier"]["teacher_searches"], 0)
        self.assertEqual(receipt["barrier"]["teacher_scores_read"], 0)
        self.assertEqual(receipt["teacher_input_auth"]["target_bytes_nonzero"], 0)

    def test_wrong_F_sha_is_rejected(self) -> None:
        with self.assertRaises(preread.PreReadError):
            self._authenticate(source_publication_sha256="0" * 64)
        self.assertFalse(self.receipt.exists())

    def test_nonzero_target_byte_is_rejected_before_teacher(self) -> None:
        raw = bytearray(self.parents.read_bytes())
        raw[8 + 33] = 1
        self.parents.write_bytes(raw)
        with self.assertRaises((preread.PreReadError, ValueError)):
            self._authenticate()
        self.assertFalse(self.receipt.exists())

    def test_teacher_checkout_must_be_X(self) -> None:
        self._git("checkout", "-q", self.y)
        with self.assertRaises(preread.PreReadError):
            self._authenticate()
        self.assertFalse(self.receipt.exists())


if __name__ == "__main__":
    unittest.main()
