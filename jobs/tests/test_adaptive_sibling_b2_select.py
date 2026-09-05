#!/usr/bin/env python3
from __future__ import annotations

import argparse
import contextlib
import csv
import functools
import hashlib
import io
import json
import os
import random
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

from jobs.tools import adaptive_sibling_b2_select as tool
from jobs.tools.adaptive_sibling_b2_exclusions import (
    ContractError,
    canonical_fingerprint,
    canonical_json_bytes,
    format_fingerprint,
    rotate50,
    sha256_bytes,
    sha256_file,
)


ROOT = Path(__file__).resolve().parents[2]
CONTRACT_PATH = ROOT / "jobs/manifests/adaptive_sibling_b2_selection_contract_v1.json"


def descriptor(path: Path) -> dict:
    return {"local_name": path.name, "sha256": sha256_file(path), "size_bytes": path.stat().st_size}


def argv_sha(argv: list[str]) -> str:
    return sha256_bytes(canonical_json_bytes(argv))


class SyntheticInputs:
    def __init__(self, root: Path):
        self.root = root
        self.contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
        self.jnnw: list[Path] = []
        self.meta: list[Path] = []
        self.reports: list[Path] = []
        self.exclusion_union = root / "historical-parent-canonical-union.txt"
        self.exclusion_manifest = root / "historical-parent-exclusion-manifest.json"
        self.exclusion_receipt = root / "verified-historical-exclusions.json"
        self.source_manifest = root / "source-manifest.json"
        self._build()

    @staticmethod
    @functools.lru_cache(maxsize=1)
    def _positions() -> tuple[tuple[str, bytes, int, int, int], ...]:
        requested = [("P0", 0)] * 501
        requested += [(phase, stm) for phase in tool.PHASES for stm in (0, 1)
                      for _ in range(500) if not (phase == "P0" and stm == 0)]
        # The expansion above intentionally omits the second P0/stm0 block.
        pieces_for = {"P0": 30, "P1": 20, "P2": 12, "P3": 9}
        seen: set[str] = set()
        out: list[tuple[str, bytes, int, int, int]] = []
        nonce = 0
        for phase, stm in requested:
            pieces = pieces_for[phase]
            while True:
                rng = random.Random(0xB2000000 + nonce)
                nonce += 1
                squares = rng.sample(range(50), pieces)
                split = pieces // 2
                wm = sum(1 << square for square in squares[:split])
                bm = sum(1 << square for square in squares[split:])
                raw_fp = format_fingerprint(wm, 0, bm, 0, stm)
                canonical = canonical_fingerprint(raw_fp)
                if canonical not in seen:
                    seen.add(canonical)
                    record = struct.pack("<QQQQB", wm, 0, bm, 0, stm) + b"\0" * 5
                    out.append((raw_fp, record, pieces, 2, stm))
                    break
        # Cross-shard duplicate occurrences exercise the normative representative rule.
        out.append(out[2])
        for original_index, (raw_fp, _, pieces, legal_moves, stm) in enumerate(out[3:100], 3):
            wm, wk, bm, bk, _ = tool.parse_fingerprint(raw_fp)
            symmetric = format_fingerprint(
                rotate50(bm), rotate50(bk), rotate50(wm), rotate50(wk), 1 - stm
            )
            if raw_fp < symmetric and original_index % 16 != len(out) % 16:
                swm, swk, sbm, sbk, sstm = tool.parse_fingerprint(symmetric)
                record = struct.pack("<QQQQB", swm, swk, sbm, sbk, sstm) + b"\0" * 5
                out.append((symmetric, record, pieces, legal_moves, sstm))
                break
        else:
            raise AssertionError("synthetic fixture lacked a stable symmetry representative")
        return tuple(out)

    def _build(self) -> None:
        positions = self._positions()
        excluded = canonical_fingerprint(positions[0][0])
        self.exclusion_union.write_bytes((excluded + "\n").encode("ascii"))
        self.contract["exclusion"]["union_sha256"] = sha256_file(self.exclusion_union)
        self.contract["exclusion"]["union_unique_canonical"] = 1

        exclusion_manifest = {
            "schema": tool.EXCLUSION_MANIFEST_SCHEMA,
            "universe": self.contract["exclusion"]["universe"],
            "source_count": 40,
            "union_unique_canonical": 1,
            "union_sha256": sha256_file(self.exclusion_union),
            "canonicalization": self.contract["canonicalization"],
            "historical_authentication_only": True,
            "confirmation_freeze": False,
            "scores_or_labels_read": 0,
            "M1_alias_of_RichD_C": True,
        }
        self.exclusion_manifest.write_bytes(canonical_json_bytes(exclusion_manifest))
        self.contract["exclusion"]["manifest_sha256"] = sha256_file(self.exclusion_manifest)
        receipt = {
            "schema": 1,
            "state": "verified",
            "prefix": self.contract["exclusion"]["prefix"],
            "job_id": self.contract["exclusion"]["job_id"],
            "attempt_id": self.contract["exclusion"]["attempt_id"],
            "code_sha": self.contract["exclusion"]["code_sha"],
            "result_state": "completed",
            "exit_code": 0,
            "files": [
                {"path": self.contract["exclusion"]["union_artifact_path"], **descriptor(self.exclusion_union)},
                {"path": self.contract["exclusion"]["manifest_artifact_path"], **descriptor(self.exclusion_manifest)},
            ],
        }
        self.exclusion_receipt.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")

        per_shard: list[list[tuple[str, bytes, int, int, int]]] = [[] for _ in range(16)]
        for index, item in enumerate(positions):
            per_shard[index % 16].append(item)
        jass = "/opt/jass/bin/jass"
        filter_exe = "/opt/jass/bin/jass_deep_sibling_parent_filter"
        curriculum = "/opt/jass/models/curriculum.pjtw"
        shards = []
        for shard_index, rows in enumerate(per_shard):
            raw_name = f"shard-{shard_index:02d}.jnnw"
            jnnw = self.root / f"shard-{shard_index:02d}.filtered.jnnw"
            meta = self.root / f"shard-{shard_index:02d}.filtered.tsv"
            report_path = self.root / f"shard-{shard_index:02d}.filter-report.json"
            jnnw.write_bytes(b"JNNW" + struct.pack("<I", len(rows)) + b"".join(row[1] for row in rows))
            with meta.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.writer(stream, delimiter="\t", lineterminator="\n")
                writer.writerow(tool.FILTER_FIELDS)
                for row_index, (fingerprint, _, pieces, legal_moves, stm) in enumerate(rows):
                    writer.writerow([row_index, row_index, fingerprint, stm, pieces, legal_moves])
            filter_report = {
                "schema": "jass.deep_sibling.parent_filter.v1",
                "input": raw_name,
                "labels_used_from_sources": False,
                "source_score_bytes_read": False,
                "source_wdl_bytes_read": False,
                "min_pieces": 9,
                "max_pieces": 40,
                "min_semantic_legal_moves": 2,
                "max_semantic_legal_moves": 16,
                "source_rows": 10000,
                "invalid_rows": 0,
                "piece_eligible_rows": len(rows),
                "exact_duplicates": 0,
                "below_min_moves": 0,
                "above_max_moves": 0,
                "duplicate_move_entries": 0,
                "selected_parents": len(rows),
            }
            report_path.write_text(json.dumps(filter_report, indent=2) + "\n", encoding="utf-8")
            self.jnnw.append(jnnw)
            self.meta.append(meta)
            self.reports.append(report_path)
            seed = tool.SOURCE_SEED_BASE + shard_index
            producer_argv = [
                jass, "--gen-data-wdl", "10000", raw_name, "4", "8", "260", str(seed),
                "--nnue", curriculum, "--wdl-zero-score", "--random-open-plies", "8",
                "--explore-eps", "8", "--explore-decay-plies", "60", "--pair-openings",
                "--drop-plycap",
            ]
            filter_argv = [
                filter_exe, raw_name, jnnw.name, meta.name, report_path.name, "9", "40", "2", "16",
            ]
            raw_sha = hashlib.sha256(f"synthetic raw shard {shard_index}".encode()).hexdigest()
            shards.append({
                "source_shard": shard_index,
                "seed": seed,
                "producer": {
                    "argv": producer_argv,
                    "argv_sha256": argv_sha(producer_argv),
                    "duration_milliseconds": 1000 + shard_index,
                    "exit_code": 0,
                    "launch_monotonic_ns": 1_000_000 + shard_index,
                    "log": {"local_name": f"shard-{shard_index:02d}.log", "sha256": hashlib.sha256(f"log {shard_index}".encode()).hexdigest(), "size_bytes": 0},
                    "pid": 2000 + shard_index,
                    "post_exec": {
                        "argv_sha256": argv_sha(producer_argv),
                        "executable_sha256": hashlib.sha256(b"jass").hexdigest(),
                        "resolved_executable": jass,
                        "verified": True,
                    },
                    "ppid": 1000,
                    "proc_starttime": 3000 + shard_index,
                    "process_state": "S",
                    "raw_jnnw": {
                        "local_name": raw_name, "sha256": raw_sha, "size_bytes": 380008,
                        "magic": "JNNW", "header_count": 10000, "record_size_bytes": 38,
                        "trailing_bytes": 0,
                    },
                },
                "filter": {
                    "argv": filter_argv,
                    "argv_sha256": argv_sha(filter_argv),
                    "duration_milliseconds": 100,
                    "exit_code": 0,
                    "source_jnnw_sha256": raw_sha,
                    "filtered_jnnw": descriptor(jnnw),
                    "filtered_meta": descriptor(meta),
                    "report": descriptor(report_path),
                },
            })
        source_manifest = {
            "schema": tool.SOURCE_MANIFEST_SCHEMA,
            "selection_contract_sha256": sha256_bytes(canonical_json_bytes(self.contract)),
            "build": {
                "build_type": "Release",
                "cmake_cache_sha256": hashlib.sha256(b"cache").hexdigest(),
                "cmake_options": ["-DJASS_NNUE=ON"],
                "code_sha": "a" * 40,
                "compiler_id": "GNU",
                "compiler_version": "14.2.0",
            },
            "curriculum": {"resolved_path": curriculum, "sha256": self.contract["curriculum"]["decompressed_sha256"]},
            "jass_executable": {"resolved_path": jass, "sha256": hashlib.sha256(b"jass").hexdigest()},
            "parent_filter_executable": {"resolved_path": filter_exe, "sha256": hashlib.sha256(b"filter").hexdigest()},
            "producer_environment": {
                "egdb_source": "none", "jass_prefixed_environment": [],
                "required_absent": tool.REQUIRED_ABSENT_ENV,
                "transmitted_names": [],
            },
            "producer_barrier": {
                "alive_barrier_count": 16, "child_count": 16, "child_exec_preserves_pid": True,
                "distinct_identity": ["pid", "proc_starttime"], "direct_child_ppid_required": True,
                "launcher_pid": 1000, "non_zombie_required": True, "passed": True,
                "records_per_child": 10000, "seeds": "2026110700+source_shard",
                "unique_pids_at_barrier": True,
            },
            "shards": shards,
        }
        self.source_manifest.write_bytes(canonical_json_bytes(source_manifest))

    def args(self, suffix: str = "") -> argparse.Namespace:
        return argparse.Namespace(
            contract=CONTRACT_PATH,
            source_manifest=self.source_manifest,
            filtered_jnnw=list(self.jnnw),
            filtered_meta=list(self.meta),
            filter_report=list(self.reports),
            exclusion_union=self.exclusion_union,
            exclusion_manifest=self.exclusion_manifest,
            exclusion_receipt=self.exclusion_receipt,
            out_jnnw=self.root / f"parents{suffix}.jnnw",
            out_tsv=self.root / f"parents{suffix}.tsv",
            report=self.root / f"selection-report{suffix}.json",
        )

    def refresh_descriptor(self, path: Path, kind: str) -> None:
        manifest = json.loads(self.source_manifest.read_text(encoding="utf-8"))
        for shard in manifest["shards"]:
            if shard["filter"][kind]["local_name"] == path.name:
                shard["filter"][kind] = descriptor(path)
                break
        else:
            raise AssertionError(path)
        self.source_manifest.write_bytes(canonical_json_bytes(manifest))

    def reverse_filtered_occurrences(self, shard: int) -> None:
        jnnw = self.jnnw[shard]
        raw = jnnw.read_bytes()
        count = struct.unpack_from("<I", raw, 4)[0]
        records = [raw[8 + index * 38:8 + (index + 1) * 38] for index in range(count)]
        rows = list(csv.reader(io.StringIO(self.meta[shard].read_text(encoding="utf-8")), delimiter="\t"))
        header, body = rows[0], list(reversed(rows[1:]))
        for row_index, row in enumerate(body):
            row[0] = str(row_index)
        jnnw.write_bytes(b"JNNW" + struct.pack("<I", count) + b"".join(reversed(records)))
        with self.meta[shard].open("w", encoding="utf-8", newline="") as stream:
            csv.writer(stream, delimiter="\t", lineterminator="\n").writerows([header, *body])
        self.refresh_descriptor(jnnw, "filtered_jnnw")
        self.refresh_descriptor(self.meta[shard], "filtered_meta")

    def remove_one_from_cell(self, phase: str, stm: int) -> Path:
        for shard, meta in enumerate(self.meta):
            rows = list(csv.reader(io.StringIO(meta.read_text(encoding="utf-8")), delimiter="\t"))
            for row_index, row in enumerate(rows[1:]):
                if tool.phase_for(int(row[4])) != phase or int(row[3]) != stm:
                    continue
                jnnw = self.jnnw[shard]
                raw = jnnw.read_bytes()
                count = struct.unpack_from("<I", raw, 4)[0]
                records = [raw[8 + index * 38:8 + (index + 1) * 38] for index in range(count)]
                del records[row_index]
                del rows[row_index + 1]
                for compact_index, remaining in enumerate(rows[1:]):
                    remaining[0] = str(compact_index)
                jnnw.write_bytes(b"JNNW" + struct.pack("<I", count - 1) + b"".join(records))
                with meta.open("w", encoding="utf-8", newline="") as stream:
                    csv.writer(stream, delimiter="\t", lineterminator="\n").writerows(rows)
                report_path = self.reports[shard]
                report = json.loads(report_path.read_text(encoding="utf-8"))
                report["piece_eligible_rows"] -= 1
                report["selected_parents"] -= 1
                report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
                self.refresh_descriptor(jnnw, "filtered_jnnw")
                self.refresh_descriptor(meta, "filtered_meta")
                self.refresh_descriptor(report_path, "report")
                return meta
        raise AssertionError(f"synthetic fixture lacks {phase}_stm{stm}")


class SelectionTests(unittest.TestCase):
    def test_hash_golden_and_rotation(self) -> None:
        canonical = "000000000000f:0000000000000:00000000001f0:0000000000000:0"
        self.assertEqual(tool.selection_hash(canonical), "fc336259243545692ab5497c2265437d1d729ed6ada6fdd3bfcbf6a3d14fbe43")
        wm, wk, bm, bk, stm = tool.parse_fingerprint(canonical)
        rotated = format_fingerprint(rotate50(bm), rotate50(bk), rotate50(wm), rotate50(wk), 1 - stm)
        self.assertEqual(canonical_fingerprint(rotated), canonical_fingerprint(canonical))

    def test_contract_is_canonical_and_pinned(self) -> None:
        contract, raw = tool.load_contract(CONTRACT_PATH)
        self.assertEqual(contract["cell_quota"], 500)
        self.assertEqual(sha256_bytes(raw), tool.EXPECTED_CONTRACT_SHA256)

    def test_standalone_cli_imports_outside_repository_cwd(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            completed = subprocess.run(
                [sys.executable, str(Path(tool.__file__).resolve()), "--help"],
                cwd=temporary, capture_output=True, text=True, check=False,
            )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("--source-manifest", completed.stdout)

    def test_contract_byte_drift_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            drifted = Path(temporary) / "contract.json"
            value = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
            value["cell_quota"] = 499
            drifted.write_bytes(canonical_json_bytes(value))
            with self.assertRaisesRegex(ContractError, "reviewed v1"):
                tool.load_contract(drifted)

    def test_end_to_end_is_deterministic_under_cli_permutation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = SyntheticInputs(Path(temporary))
            first = fixture.args("-a")
            result_a = tool.run(first, contract_override=fixture.contract)
            fixture.reverse_filtered_occurrences(7)
            second = fixture.args("-b")
            second.filtered_jnnw.reverse()
            second.filtered_meta = second.filtered_meta[3:] + second.filtered_meta[:3]
            second.filter_report = second.filter_report[::2] + second.filter_report[1::2]
            result_b = tool.run(second, contract_override=fixture.contract)
            self.assertEqual(first.out_jnnw.read_bytes(), second.out_jnnw.read_bytes())
            self.assertEqual(first.out_tsv.read_bytes(), second.out_tsv.read_bytes())
            report_a = json.loads(first.report.read_text())
            report_b = json.loads(second.report.read_text())
            self.assertEqual(report_a["selected_by_phase_stm"], {cell: 500 for cell in tool.CELL_ORDER})
            self.assertEqual(report_a["outputs"], report_b["outputs"])
            self.assertEqual(result_a["ordered_identities_sha256"], result_b["ordered_identities_sha256"])
            self.assertEqual(first.out_jnnw.stat().st_size, 8 + 4000 * 38)
            self.assertEqual(first.out_jnnw.read_bytes()[4:8], struct.pack("<I", 4000))
            self.assertEqual(report_a["counters"]["historical_excluded_occurrences"], 1)
            self.assertEqual(report_a["counters"]["exact_duplicate_occurrences_removed"], 1)
            self.assertEqual(report_a["counters"]["symmetry_duplicate_occurrences_removed"], 1)
            self.assertEqual(report_a["forbidden_overlap"], 0)
            with second.out_tsv.open(encoding="utf-8", newline="") as stream:
                output_rows = list(csv.DictReader(stream, delimiter="\t"))
            output_keys = [(bytes.fromhex(row["selection_hash"]), row["canonical_fingerprint"]) for row in output_rows]
            self.assertEqual(output_keys, sorted(output_keys))
            expected_representatives: dict[str, tuple[str, int, int]] = {}
            for shard, meta in enumerate(fixture.meta):
                with meta.open(encoding="utf-8", newline="") as stream:
                    for row in csv.DictReader(stream, delimiter="\t"):
                        canonical = canonical_fingerprint(row["parent_fingerprint"])
                        key = (row["parent_fingerprint"], shard, int(row["source_row_index"]))
                        if canonical not in expected_representatives or key < expected_representatives[canonical]:
                            expected_representatives[canonical] = key
            for row in output_rows:
                self.assertEqual(
                    (row["raw_fingerprint"], int(row["source_shard"]), int(row["source_row_index"])),
                    expected_representatives[row["canonical_fingerprint"]],
                )

    def test_nonzero_target_is_rejected_and_outputs_absent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = SyntheticInputs(Path(temporary))
            poisoned = bytearray(fixture.jnnw[0].read_bytes())
            poisoned[8 + 33] = 1
            fixture.jnnw[0].write_bytes(poisoned)
            fixture.refresh_descriptor(fixture.jnnw[0], "filtered_jnnw")
            args = fixture.args()
            with self.assertRaisesRegex(ContractError, "nonzero target"):
                tool.run(args, contract_override=fixture.contract)
            self.assertFalse(args.out_jnnw.exists() or args.out_tsv.exists() or args.report.exists())

    def test_forbidden_extra_tsv_column_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = SyntheticInputs(Path(temporary))
            path = fixture.meta[0]
            lines = path.read_text(encoding="utf-8").splitlines()
            lines = [lines[0] + "\tq200"] + [line + "\t29900" for line in lines[1:]]
            path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="")
            fixture.refresh_descriptor(path, "filtered_meta")
            with self.assertRaisesRegex(ContractError, "fields mismatch"):
                tool.run(fixture.args(), contract_override=fixture.contract)

    def test_unaligned_metadata_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = SyntheticInputs(Path(temporary))
            path = fixture.meta[0]
            rows = list(csv.reader(io.StringIO(path.read_text(encoding="utf-8")), delimiter="\t"))
            rows[1][1] = "9999"
            with path.open("w", encoding="utf-8", newline="") as stream:
                csv.writer(stream, delimiter="\t", lineterminator="\n").writerows(rows)
            fixture.refresh_descriptor(path, "filtered_meta")
            # Alignment to the raw source is represented by the preserved index; it may differ
            # from compact row_index, so force a board mismatch as the independently observable fault.
            rows[1][2] = rows[2][2]
            with path.open("w", encoding="utf-8", newline="") as stream:
                csv.writer(stream, delimiter="\t", lineterminator="\n").writerows(rows)
            fixture.refresh_descriptor(path, "filtered_meta")
            with self.assertRaisesRegex(ContractError, "board/fingerprint mismatch"):
                tool.run(fixture.args(), contract_override=fixture.contract)

    def test_duplicate_raw_provenance_index_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = SyntheticInputs(Path(temporary))
            path = fixture.meta[0]
            rows = list(csv.reader(io.StringIO(path.read_text(encoding="utf-8")), delimiter="\t"))
            rows[2][1] = rows[1][1]
            with path.open("w", encoding="utf-8", newline="") as stream:
                csv.writer(stream, delimiter="\t", lineterminator="\n").writerows(rows)
            fixture.refresh_descriptor(path, "filtered_meta")
            with self.assertRaisesRegex(ContractError, "duplicate source_row_index"):
                tool.run(fixture.args(), contract_override=fixture.contract)

    def test_manifest_environment_and_process_identity_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = SyntheticInputs(Path(temporary))
            manifest = json.loads(fixture.source_manifest.read_text(encoding="utf-8"))
            manifest["producer_environment"]["transmitted_names"] = ["PATH"]
            fixture.source_manifest.write_bytes(canonical_json_bytes(manifest))
            with self.assertRaisesRegex(ContractError, "must be empty"):
                tool.validate_source_manifest(fixture.source_manifest, fixture.contract)
            manifest["producer_environment"]["transmitted_names"] = []
            manifest["shards"][1]["producer"]["pid"] = manifest["shards"][0]["producer"]["pid"]
            fixture.source_manifest.write_bytes(canonical_json_bytes(manifest))
            with self.assertRaisesRegex(ContractError, "PID"):
                tool.validate_source_manifest(fixture.source_manifest, fixture.contract)

    def test_manifest_bool_overflow_and_forbidden_score_field_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = SyntheticInputs(Path(temporary))
            original = json.loads(fixture.source_manifest.read_text(encoding="utf-8"))
            value = json.loads(json.dumps(original))
            value["shards"][0]["seed"] = True
            fixture.source_manifest.write_bytes(canonical_json_bytes(value))
            with self.assertRaisesRegex(ContractError, "seed"):
                tool.validate_source_manifest(fixture.source_manifest, fixture.contract)
            value = json.loads(json.dumps(original))
            value["shards"][0]["producer"]["proc_starttime"] = 1 << 63
            fixture.source_manifest.write_bytes(canonical_json_bytes(value))
            with self.assertRaisesRegex(ContractError, "proc_starttime"):
                tool.validate_source_manifest(fixture.source_manifest, fixture.contract)
            value = json.loads(json.dumps(original))
            value["shards"][0]["producer"]["q200"] = 0
            fixture.source_manifest.write_bytes(canonical_json_bytes(value))
            with self.assertRaisesRegex(ContractError, "fields mismatch"):
                tool.validate_source_manifest(fixture.source_manifest, fixture.contract)

    def test_wrong_historical_receipt_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = SyntheticInputs(Path(temporary))
            receipt = json.loads(fixture.exclusion_receipt.read_text())
            receipt["attempt_id"] = "wrong"
            fixture.exclusion_receipt.write_text(json.dumps(receipt) + "\n", encoding="utf-8")
            args = fixture.args()
            with self.assertRaisesRegex(ContractError, "attempt_id"):
                tool.run(args, contract_override=fixture.contract)
            self.assertFalse(args.out_jnnw.exists() or args.out_tsv.exists() or args.report.exists())

    def test_historical_receipt_bool_is_not_integer(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = SyntheticInputs(Path(temporary))
            receipt = json.loads(fixture.exclusion_receipt.read_text())
            receipt["schema"] = True
            fixture.exclusion_receipt.write_text(json.dumps(receipt) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ContractError, "schema"):
                tool._load_exclusion_receipt(
                    fixture.exclusion_receipt, fixture.exclusion_union,
                    fixture.exclusion_manifest, fixture.contract,
                )

    def test_output_temp_alias_is_rejected_without_touching_sentinel(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = SyntheticInputs(Path(temporary))
            args = fixture.args()
            args.report = Path(str(args.out_jnnw) + ".tmp")
            args.report.write_text("sentinel", encoding="utf-8")
            with self.assertRaisesRegex(ContractError, "alias"):
                tool.run(args, contract_override=fixture.contract)
            self.assertEqual(args.report.read_text(encoding="utf-8"), "sentinel")
            self.assertFalse(args.out_jnnw.exists() or args.out_tsv.exists())

    def test_output_input_alias_preserves_source_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = SyntheticInputs(Path(temporary))
            original = fixture.source_manifest.read_bytes()
            args = fixture.args()
            args.out_jnnw = fixture.source_manifest
            with self.assertRaisesRegex(ContractError, "alias"):
                tool.run(args, contract_override=fixture.contract)
            self.assertEqual(fixture.source_manifest.read_bytes(), original)
            self.assertFalse(args.out_tsv.exists() or args.report.exists())

    def test_canonical_class_metadata_disagreement_is_rejected(self) -> None:
        canonical = "0000000000001:0000000000000:0000000000002:0000000000000:0"
        base = tool.Candidate(
            canonical=canonical, raw_fingerprint=canonical, record=b"\0" * 38,
            stm=0, pieces=2, legal_moves=2, phase="P3", source_shard=0,
            source_row_index=0, selection_hash=tool.selection_hash(canonical),
        )
        disagree = tool.Candidate(
            canonical=canonical, raw_fingerprint=canonical, record=b"\0" * 38,
            stm=0, pieces=2, legal_moves=3, phase="P3", source_shard=1,
            source_row_index=0, selection_hash=tool.selection_hash(canonical),
        )
        with self.assertRaisesRegex(ContractError, "disagrees"):
            tool.select_candidates([base, disagree], set())

    def test_insufficient_single_cell_never_tops_up(self) -> None:
        candidates = []
        for phase in tool.PHASES:
            for stm in (0, 1):
                count = 499 if (phase, stm) == ("P3", 1) else 500
                for index in range(count):
                    canonical = f"{len(candidates) + 1:013x}:0000000000000:0000000000000:0000000000000:{stm}"
                    candidates.append(tool.Candidate(
                        canonical=canonical, raw_fingerprint=canonical, record=b"\0" * 38,
                        stm=stm, pieces={"P0": 30, "P1": 20, "P2": 12, "P3": 9}[phase],
                        legal_moves=2, phase=phase, source_shard=0, source_row_index=index,
                        selection_hash=tool.selection_hash(canonical),
                    ))
        with self.assertRaises(tool.InsufficientSupportError) as raised:
            tool.select_candidates(candidates, set())
        payload = raised.exception.payload()
        self.assertEqual(payload["schema"], tool.SUPPORT_REPORT_SCHEMA)
        self.assertEqual(payload["cell_order"], tool.CELL_ORDER)
        self.assertEqual(payload["support_before_sampling"]["P3_stm1"], 499)
        self.assertEqual(payload["insufficient_cells"], ["P3_stm1"])
        self.assertEqual(payload["cell_quota"], 500)
        self.assertEqual(payload["outputs_created"], 0)
        self.assertIs(payload["target_blind"], True)
        self.assertIs(payload["top_up"], False)

    def test_full_input_path_returns_typed_support_only_after_reauthentication(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = SyntheticInputs(Path(temporary))
            fixture.remove_one_from_cell("P3", 1)
            args = fixture.args()
            with self.assertRaises(tool.InsufficientSupportError) as raised:
                tool.run(args, contract_override=fixture.contract)
            payload = raised.exception.payload()
            self.assertEqual(payload["support_before_sampling"], {
                **{cell: 500 for cell in tool.CELL_ORDER}, "P3_stm1": 499,
            })
            self.assertEqual(payload["insufficient_cells"], ["P3_stm1"])
            self.assertFalse(args.out_jnnw.exists() or args.out_tsv.exists() or args.report.exists())

    def test_cli_maps_only_typed_support_to_canonical_stdout_rc4(self) -> None:
        support = {cell: 500 for cell in tool.CELL_ORDER}
        support["P2_stm0"] = 499
        error = tool.InsufficientSupportError(support, {
            "filtered_occurrences": 3999,
            "historical_excluded_occurrences": 0,
            "exact_duplicate_occurrences_removed": 0,
            "symmetry_duplicate_occurrences_removed": 0,
            "unique_canonical_after_exclusion": 3999,
        })
        stdout = io.StringIO()
        stderr = io.StringIO()
        with mock.patch.object(tool, "parse_args", return_value=object()), \
                mock.patch.object(tool, "run", side_effect=error), \
                contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            result = tool.main([])
        self.assertEqual(result, 4)
        self.assertEqual(stdout.getvalue().encode("ascii"), canonical_json_bytes(error.payload()))
        self.assertEqual(stderr.getvalue(), "")

    def test_cli_keeps_contract_error_on_technical_rc2_stderr(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with mock.patch.object(tool, "parse_args", return_value=object()), \
                mock.patch.object(tool, "run", side_effect=ContractError("technical")), \
                contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            result = tool.main([])
        self.assertEqual(result, 2)
        self.assertEqual(stdout.getvalue(), "")
        self.assertEqual(stderr.getvalue(), "error: technical\n")

    def test_mutation_before_support_receipt_becomes_technical(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = SyntheticInputs(Path(temporary))
            mutated = fixture.remove_one_from_cell("P3", 1)
            args = fixture.args()
            original = tool.select_candidates

            def mutate_then_select(candidates, excluded):
                try:
                    return original(candidates, excluded)
                except tool.InsufficientSupportError:
                    mutated.write_bytes(mutated.read_bytes() + b"\n")
                    raise

            with mock.patch.object(tool, "select_candidates", side_effect=mutate_then_select):
                with self.assertRaisesRegex(ContractError, "input changed after parsing"):
                    tool.run(args, contract_override=fixture.contract)
            self.assertFalse(args.out_jnnw.exists() or args.out_tsv.exists() or args.report.exists())

    def test_existing_output_prevents_support_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = SyntheticInputs(Path(temporary))
            fixture.remove_one_from_cell("P3", 1)
            args = fixture.args()
            args.out_jnnw.write_bytes(b"sentinel")
            with self.assertRaisesRegex(ContractError, "existing output"):
                tool.run(args, contract_override=fixture.contract)
            self.assertEqual(args.out_jnnw.read_bytes(), b"sentinel")
            self.assertFalse(args.out_tsv.exists() or args.report.exists())

    def test_hardlinked_inputs_are_technical_before_support(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = SyntheticInputs(Path(temporary))
            fixture.remove_one_from_cell("P3", 1)
            fixture.reports[1].unlink()
            os.link(fixture.reports[0], fixture.reports[1])
            with self.assertRaisesRegex(ContractError, "input filesystem alias"):
                tool.run(fixture.args(), contract_override=fixture.contract)


if __name__ == "__main__":
    unittest.main()
