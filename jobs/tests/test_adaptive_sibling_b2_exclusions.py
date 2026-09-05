from __future__ import annotations

import copy
import csv
import gzip
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from jobs.tools import adaptive_sibling_b2_exclusions as subject


ROOT = Path(__file__).resolve().parents[2]
REAL_CATALOG = ROOT / "jobs/manifests/adaptive_sibling_b2_exclusion_sources_v1.json"
RAW_FP = "0000000000001:0000000000000:0000000000002:0000000000000:0"
CANONICAL = subject.canonical_fingerprint(RAW_FP)
FEN = "W:W1:B2"


class Fixture:
    def __init__(self, root: Path):
        self.root = root
        self.inputs = root / "inputs"
        self.receipts = root / "receipts"
        self.inputs.mkdir()
        self.receipts.mkdir()
        self.catalog = json.loads(REAL_CATALOG.read_text(encoding="utf-8"))
        self.catalog_path = root / "catalog.json"
        for source in self.catalog["sources"]:
            self.write_source(source)
        self.write_catalog()

    def write_catalog(self) -> None:
        self.catalog_path.write_text(
            json.dumps(self.catalog, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

    def write_source(self, source: dict, *, fen: str = FEN) -> None:
        artifact = self.inputs / source["local_name"]
        if source["type"] == "fen":
            artifact.write_text(fen + "\n", encoding="utf-8")
        else:
            if source["type"] == "home_scan_parent_tsv":
                fields = subject.HOME_SCAN_FIELDS
            elif source["source_id"] in subject.CATALOG_PARENT_SOURCE_IDS:
                fields = subject.CATALOG_PARENT_FIELDS
            else:
                fields = subject.COMPACT_PARENT_FIELDS
            row = {field: "0" for field in fields}
            row.update({
                "parent_id": "0",
                "canonical_fingerprint": CANONICAL,
                "raw_fingerprint": RAW_FP,
                "parent_stm": "0",
            })
            if "phase" in row:
                row["phase"] = "P3"
            opener = (lambda: gzip.open(artifact, "wt", encoding="utf-8", newline="")) \
                if artifact.name.endswith(".gz") else \
                (lambda: artifact.open("w", encoding="utf-8", newline=""))
            with opener() as stream:
                writer = csv.DictWriter(stream, fieldnames=fields, delimiter="\t", lineterminator="\n")
                writer.writeheader()
                writer.writerow(row)
        self.write_receipt(source)

    def write_receipt(self, source: dict, **overrides) -> None:
        artifact = self.inputs / source["local_name"]
        payload = {
            "schema": 1,
            "state": "verified",
            "prefix": source["prefix"],
            "job_id": source["job_id"],
            "attempt_id": source["attempt_id"],
            "code_sha": source["code_sha"],
            "result_state": "completed",
            "exit_code": 0,
            "files": [{
                "path": source["artifact_path"],
                "local_name": source["local_name"],
                "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
                "size_bytes": artifact.stat().st_size,
            }],
        }
        payload.update(overrides)
        (self.receipts / source["receipt_name"]).write_text(
            json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8"
        )

    def compile(self, suffix: str = "one") -> tuple[dict, Path, Path]:
        union = self.root / f"union-{suffix}.txt"
        manifest = self.root / f"manifest-{suffix}.json"
        result = subject.compile_exclusions(
            catalog_path=self.catalog_path,
            input_dir=self.inputs,
            receipt_dir=self.receipts,
            out_union=union,
            out_manifest=manifest,
        )
        return result, union, manifest


class IdentityTests(unittest.TestCase):
    def test_rotation_colour_alias_and_fen_agree(self):
        symmetric = "1000000000000:0000000000000:2000000000000:0000000000000:1"
        self.assertEqual(subject.canonical_fingerprint(RAW_FP),
                         subject.canonical_fingerprint(symmetric))
        self.assertEqual(subject.canonical_fen("W:W1:B2"),
                         subject.canonical_fen("B:W49:B50"))
        self.assertEqual(subject.canonical_fen(FEN), CANONICAL)
        self.assertEqual(subject.verify_reference_canonicalization(512), 512)

    def test_fingerprint_and_fen_validity_fail_closed(self):
        invalid_fingerprints = [
            "1:0:1:0:0", "4000000000000:0:0:0:0", "1:0:2:0:2", "not:a:fp",
        ]
        for value in invalid_fingerprints:
            with self.subTest(value=value), self.assertRaises(subject.ContractError):
                subject.canonical_fingerprint(value)
        invalid_fens = [
            "X:W1:B2", "W:W1:W2", "W:W0:B2", "W:W2-1:B3",
            "W:W1,,2:B3", "W:W1:B1", "W:WK1,K1:B2", "W:W1:B2:extra",
        ]
        for value in invalid_fens:
            with self.subTest(value=value), self.assertRaises(subject.ContractError):
                subject.canonical_fen(value)


class CatalogTests(unittest.TestCase):
    def test_real_catalog_is_exact_closed_universe(self):
        catalog, _ = subject.load_catalog(REAL_CATALOG)
        self.assertEqual(len(catalog["sources"]), 40)
        self.assertEqual(
            {kind: sum(row["type"] == kind for row in catalog["sources"])
             for kind in subject.SOURCE_TYPES},
            {"parent_tsv": 10, "home_scan_parent_tsv": 1, "fen": 29},
        )
        self.assertEqual(catalog["sources"][10]["source_id"], "10-home-scan-ceiling")
        self.assertEqual(catalog["sources"][39]["source_id"], "39-sb1-pool1")
        for source in catalog["sources"]:
            self.assertEqual(
                source["prefix"],
                f"r2:jass-data/runs/{source['job_id']}/{source['attempt_id']}",
            )

    def test_catalog_rejects_missing_source_and_prefix_drift(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = Fixture(Path(temporary))
            fixture.catalog["sources"].pop()
            fixture.write_catalog()
            with self.assertRaisesRegex(subject.ContractError, "exactly 40"):
                subject.load_catalog(fixture.catalog_path)
        with tempfile.TemporaryDirectory() as temporary:
            fixture = Fixture(Path(temporary))
            fixture.catalog["sources"][0]["prefix"] += "-wrong"
            fixture.write_catalog()
            with self.assertRaisesRegex(subject.ContractError, "prefix mismatch"):
                subject.load_catalog(fixture.catalog_path)


class CompilerTests(unittest.TestCase):
    def test_boolean_metadata_cannot_impersonate_integer_receipts_or_ordinals(self):
        for field, value in (("schema", True), ("exit_code", False)):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as temporary:
                fixture = Fixture(Path(temporary))
                fixture.write_receipt(fixture.catalog["sources"][0], **{field: value})
                with self.assertRaisesRegex(subject.ContractError, f"{field} mismatch"):
                    fixture.compile()
        with tempfile.TemporaryDirectory() as temporary:
            fixture = Fixture(Path(temporary))
            fixture.catalog["sources"][1]["ordinal"] = True
            fixture.write_catalog()
            with self.assertRaisesRegex(subject.ContractError, "ordinal drift"):
                fixture.compile()

    def test_compile_is_nonempty_deterministic_and_reports_aliases(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = Fixture(Path(temporary))
            first, union_one, manifest_one = fixture.compile("one")
            second, union_two, manifest_two = fixture.compile("two")
            self.assertEqual(union_one.read_bytes(), union_two.read_bytes())
            self.assertEqual(manifest_one.read_bytes(), manifest_two.read_bytes())
            self.assertEqual(first, second)
            self.assertEqual(first["source_count"], 40)
            self.assertEqual(first["union_unique_canonical"], 1)
            self.assertEqual(first["input_rows"], 40)
            self.assertEqual(first["sources"][0]["overlap_with_prior_sources"], 0)
            self.assertTrue(all(row["overlap_with_prior_sources"] == 1
                                for row in first["sources"][1:]))
            self.assertEqual(first["union_sha256"], hashlib.sha256(
                union_one.read_bytes()).hexdigest())
            self.assertEqual(union_one.read_text(encoding="ascii"), CANONICAL + "\n")
            self.assertEqual(first["scores_or_labels_read"], 0)
            self.assertFalse(first["confirmation_freeze"])
            self.assertTrue(first["M1_alias_of_RichD_C"])
            self.assertEqual(first["m1_alias_attestation"]["source_id"], "02-rich-d-c")
            self.assertFalse(first["m1_alias_attestation"]["new_source_added"])
            self.assertTrue(first["canonicalization_reference"]["byte_equivalent"])

    def test_missing_artifact_and_missing_receipt_fail_before_output(self):
        for missing in ("artifact", "receipt"):
            with self.subTest(missing=missing), tempfile.TemporaryDirectory() as temporary:
                fixture = Fixture(Path(temporary))
                source = fixture.catalog["sources"][7]
                target = ((fixture.inputs / source["local_name"]) if missing == "artifact"
                          else (fixture.receipts / source["receipt_name"]))
                target.unlink()
                with self.assertRaises(subject.ContractError):
                    fixture.compile()
                self.assertFalse((fixture.root / "union-one.txt").exists())
                self.assertFalse((fixture.root / "manifest-one.json").exists())

    def test_receipt_identity_and_payload_mismatches_fail(self):
        cases = {
            "job_id": "wrong-job",
            "attempt_id": "wrong-attempt",
            "code_sha": "0" * 40,
            "prefix": "r2:wrong",
            "result_state": "failed",
            "exit_code": 1,
        }
        for field, value in cases.items():
            with self.subTest(field=field), tempfile.TemporaryDirectory() as temporary:
                fixture = Fixture(Path(temporary))
                source = fixture.catalog["sources"][0]
                fixture.write_receipt(source, **{field: value})
                with self.assertRaisesRegex(subject.ContractError, f"{field} mismatch"):
                    fixture.compile()
        with tempfile.TemporaryDirectory() as temporary:
            fixture = Fixture(Path(temporary))
            source = fixture.catalog["sources"][0]
            artifact = fixture.inputs / source["local_name"]
            artifact.write_bytes(artifact.read_bytes() + b"corruption")
            with self.assertRaisesRegex(subject.ContractError, "differs from receipt"):
                fixture.compile()

    def test_empty_and_malformed_payloads_fail(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = Fixture(Path(temporary))
            source = fixture.catalog["sources"][11]
            artifact = fixture.inputs / source["local_name"]
            artifact.write_text("# comments only\n", encoding="utf-8")
            fixture.write_receipt(source)
            with self.assertRaisesRegex(subject.ContractError, "FEN source is empty"):
                fixture.compile()
        with tempfile.TemporaryDirectory() as temporary:
            fixture = Fixture(Path(temporary))
            source = fixture.catalog["sources"][11]
            fixture.write_source(source, fen="W:W1:B1")
            with self.assertRaisesRegex(subject.ContractError, "both colours"):
                fixture.compile()

    def test_home_scan_exact_schema_and_general_score_field_guard(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = Fixture(Path(temporary))
            source = fixture.catalog["sources"][10]
            artifact = fixture.inputs / source["local_name"]
            artifact.write_text("parent_id\tcanonical_fingerprint\traw_fingerprint\tparent_stm\n",
                                encoding="utf-8")
            fixture.write_receipt(source)
            with self.assertRaisesRegex(subject.ContractError, "parent TSV field drift"):
                fixture.compile()
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "bad.tsv"
            path.write_text(
                "parent_id\tcanonical_fingerprint\traw_fingerprint\tparent_stm\tscore\n"
                f"0\t{CANONICAL}\t{RAW_FP}\t0\t99\n", encoding="utf-8",
            )
            with self.assertRaisesRegex(subject.ContractError, "parent TSV field drift"):
                subject.load_parent_tsv(path, expected_fields=subject.COMPACT_PARENT_FIELDS)

    def test_q200_lookalike_column_is_rejected_by_exact_allowlist(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "bad.tsv"
            fields = subject.COMPACT_PARENT_FIELDS + ["q200_parent"]
            row = {field: "0" for field in fields}
            row.update({
                "parent_id": "0", "canonical_fingerprint": CANONICAL,
                "raw_fingerprint": RAW_FP, "parent_stm": "0",
            })
            with path.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=fields, delimiter="\t")
                writer.writeheader(); writer.writerow(row)
            with self.assertRaisesRegex(subject.ContractError, "parent TSV field drift"):
                subject.load_parent_tsv(path, expected_fields=subject.COMPACT_PARENT_FIELDS)

    def test_output_temporary_alias_is_rejected_without_touching_sentinels(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = Fixture(Path(temporary))
            # manifest_tmp == out_union reproduces the reviewed x.tmp/x collision.
            out_manifest = fixture.root / "x"
            out_union = fixture.root / "x.tmp"
            sentinel = fixture.root / "unrelated-sentinel"
            sentinel.write_text("keep", encoding="ascii")
            with self.assertRaisesRegex(subject.ContractError, "pairwise distinct"):
                subject.compile_exclusions(
                    catalog_path=fixture.catalog_path,
                    input_dir=fixture.inputs,
                    receipt_dir=fixture.receipts,
                    out_union=out_union,
                    out_manifest=out_manifest,
                )
            self.assertFalse(out_union.exists())
            self.assertFalse(out_manifest.exists())
            self.assertEqual(sentinel.read_text(encoding="ascii"), "keep")
        with tempfile.TemporaryDirectory() as temporary:
            fixture = Fixture(Path(temporary))
            source = fixture.catalog["sources"][0]
            protected_input = fixture.inputs / source["local_name"]
            before = protected_input.read_bytes()
            with self.assertRaisesRegex(subject.ContractError, "aliases a catalog, source, or receipt"):
                subject.compile_exclusions(
                    catalog_path=fixture.catalog_path,
                    input_dir=fixture.inputs,
                    receipt_dir=fixture.receipts,
                    out_union=protected_input,
                    out_manifest=fixture.root / "safe-manifest.json",
                )
            self.assertEqual(protected_input.read_bytes(), before)
            self.assertFalse((fixture.root / "safe-manifest.json").exists())

    def test_cli_returns_two_on_failure_and_writes_no_outputs(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = Fixture(Path(temporary))
            source = fixture.catalog["sources"][0]
            (fixture.receipts / source["receipt_name"]).unlink()
            union = fixture.root / "cli-union.txt"
            manifest = fixture.root / "cli-manifest.json"
            result = subprocess.run([
                sys.executable, str(ROOT / "jobs/tools/adaptive_sibling_b2_exclusions.py"),
                "--catalog", str(fixture.catalog_path),
                "--input-dir", str(fixture.inputs),
                "--receipt-dir", str(fixture.receipts),
                "--out-union", str(union),
                "--out-manifest", str(manifest),
            ], check=False, capture_output=True, text=True)
            self.assertEqual(result.returncode, 2)
            self.assertIn("adaptive_sibling_b2_exclusions:", result.stderr)
            self.assertFalse(union.exists())
            self.assertFalse(manifest.exists())


if __name__ == "__main__":
    unittest.main()
