#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from jobs.tools import adaptive_sibling_b2_teacher_merge as merger
from jobs.tools import adaptive_sibling_b2_teacher_publish as publisher


CODE_SHA = "a" * 40
ROWS = 8_000


class TeacherPublishTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.input_manifest = self.root / "teacher-input-manifest.json"
        self.children = self.root / "merged-children.jnnw"
        self.groups = self.root / "merged-groups.tsv"
        self.semantic = self.root / "semantic-actions.jsonl"
        self.report = self.root / "teacher-merge-report.json"
        self.artifacts = self.root / "artifacts"
        self.input_manifest.write_bytes(publisher.canonical_json_bytes({"schema": "fixture"}))
        self.children.write_bytes(b"JNNW-fixture")
        self.groups.write_bytes(b"fixture\n")
        self.semantic.write_bytes(b"{}\n")
        self._write_report()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _desc(self, path: Path, **extra: object) -> dict[str, object]:
        return {"local_name": path.name, "sha256": publisher.sha256_file(path),
                "size_bytes": path.stat().st_size, **extra}

    def _write_report(self, *, missing_actions: int = 0) -> None:
        child_desc = self._desc(self.children, records=ROWS, record_size_bytes=38)
        groups_desc = self._desc(self.groups, rows=ROWS)
        semantic_desc = self._desc(
            self.semantic, rows=ROWS, row_schema=merger.SEMANTIC_SCHEMA)
        native_children = dict(child_desc)
        native_children["local_name"] = self.children.name + ".tmp"
        native_semantic = dict(semantic_desc)
        native_semantic["local_name"] = self.semantic.name + ".tmp"
        native = {
            "schema": merger.NATIVE_SCHEMA, "verification_complete": True,
            "actions_verified": ROWS, "catalogue_actions_generated": ROWS,
            "catalogues_verified": merger.PARENTS, "duplicate_semantic_actions": 0,
            "extra_actions": 0, "forbidden_reordering": 0,
            "missing_actions": missing_actions, "nonzero_child_targets": 0,
            "nonzero_parent_targets": 0, "parent_after_matches": ROWS,
            "parent_count_matches": merger.PARENTS, "parents_verified": merger.PARENTS,
            "semantic_rows_verified": ROWS, "children": native_children,
            "semantic_actions": native_semantic,
        }
        native_raw = publisher.canonical_json_bytes(native)
        counters = {
            "captured_bitboards_reconstructed": ROWS, "children_records": ROWS,
            "duplicate_path_entries": 0, "duplicate_semantic_actions": 0,
            "extra_actions": 0, "forbidden_reordering": 0,
            "full_catalogues_verified": merger.PARENTS, "global_rows_rebased": ROWS,
            "groups_rows": ROWS, "missing_actions": missing_actions,
            "nonzero_child_targets": 0, "parent_child_transitions_verified": ROWS,
            "parents": merger.PARENTS, "parents_with_legal_count_match": merger.PARENTS,
            "processed_parent_rows": merger.PARENTS, "semantic_actions": ROWS,
            "semantic_ledger_rows": ROWS, "shards": merger.SHARDS,
        }
        report = {
            "adapter": {}, "aggregate": {}, "build": {}, "code_sha": CODE_SHA,
            "counters": counters,
            "identity_order": ["from", "to", "captured_square_bitboard_uint64", "promotes"],
            "identity_tuple": ["from", "to", "num_captures", "promotes", "captured_square_bitboard"],
            "input_manifest": self._desc(self.input_manifest),
            "native_verification": {"receipt": native,
                                    "sha256": publisher.sha256_bytes(native_raw),
                                    "size_bytes": len(native_raw)},
            "outputs": {"children_jnnw": child_desc, "groups_tsv": groups_desc,
                        "semantic_actions": semantic_desc},
            "scientific_scope": {"calibration": False, "fits": 0,
                                 "model_selection": False, "promotion_authorized": False,
                                 "strength_games": 0, "training": False, "tuning": False},
            "schema": merger.REPORT_SCHEMA, "selection": {}, "shards": [],
            "teacher_runtime": {},
        }
        self.report.write_bytes(publisher.canonical_json_bytes(report))

    def _publish(self) -> dict[str, object]:
        return publisher.publish(
            input_manifest=self.input_manifest,
            expected_input_manifest_sha256=publisher.sha256_file(self.input_manifest),
            merge_report=self.report,
            expected_merge_report_sha256=publisher.sha256_file(self.report),
            children_jnnw=self.children, groups_tsv=self.groups,
            semantic_actions=self.semantic, code_sha=CODE_SHA,
            artifact_dir=self.artifacts)

    def test_success_seals_closed_payload_and_native_receipt(self) -> None:
        receipt = self._publish()
        self.assertEqual(receipt["schema"], publisher.PUBLICATION_SCHEMA)
        self.assertTrue(receipt["byte_roundtrip_verified"])
        self.assertEqual(set(receipt["artifacts"]),
                         {"children_jnnw", "groups_tsv", "semantic_actions", "merge_report"})
        self.assertTrue((self.artifacts / "native-verification-receipt.json").is_file())
        reread = json.loads((self.artifacts / "teacher-publication-receipt.json").read_text())
        self.assertEqual(reread, receipt)
        self.assertEqual((self.artifacts / self.children.name).read_bytes(), self.children.read_bytes())

    def test_external_merge_sha_mismatch_fails_before_publication(self) -> None:
        with self.assertRaises(publisher.PublishError):
            publisher.publish(
                input_manifest=self.input_manifest,
                expected_input_manifest_sha256=publisher.sha256_file(self.input_manifest),
                merge_report=self.report, expected_merge_report_sha256="0" * 64,
                children_jnnw=self.children, groups_tsv=self.groups,
                semantic_actions=self.semantic, code_sha=CODE_SHA,
                artifact_dir=self.artifacts)
        self.assertFalse(self.artifacts.exists())

    def test_native_or_merge_missing_action_is_rejected(self) -> None:
        self._write_report(missing_actions=1)
        with self.assertRaises(publisher.PublishError):
            self._publish()
        self.assertFalse(self.artifacts.exists())

    def test_existing_artifact_directory_content_is_rejected(self) -> None:
        self.artifacts.mkdir()
        (self.artifacts / "foreign.txt").write_text("x")
        with self.assertRaises(publisher.PublishError):
            self._publish()
        self.assertFalse((self.artifacts / "teacher-publication-receipt.json").exists())


if __name__ == "__main__":
    unittest.main()
