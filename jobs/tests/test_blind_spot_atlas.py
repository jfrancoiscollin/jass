#!/usr/bin/env python3
from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import os
import struct
import sys
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / "tools" / "blind_spot_atlas.py"
SPEC = importlib.util.spec_from_file_location("blind_spot_atlas", MODULE)
BSA = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = BSA
SPEC.loader.exec_module(BSA)

CODE_SHA = "4" * 40


def bits(*squares: int) -> int:
    value = 0
    for square in squares:
        value |= 1 << (square - 1)
    return value


def record(*, wm=0, wk=0, bm=0, bk=0, stm=0, score=123, wdl=0) -> bytes:
    return struct.pack("<QQQQBib", wm, wk, bm, bk, stm, score, wdl)


def write_pair(
    root: Path,
    name: str,
    records: list[bytes],
    rows: list[tuple[int, int, int]],
) -> tuple[Path, Path]:
    if len(records) != len(rows):
        raise AssertionError("test fixture pair mismatch")
    data = root / f"{name}.jnnw"
    meta = root / f"{name}.jsm"
    data.write_bytes(
        BSA.JNNW_MAGIC + struct.pack("<I", len(records)) + b"".join(records)
    )
    meta.write_bytes(
        BSA.JSM1_MAGIC
        + struct.pack("<I", len(rows))
        + b"".join(struct.pack("<QQB", *row) for row in rows)
    )
    return data, meta


def fixture_pair(root: Path, name: str = "source") -> tuple[Path, Path]:
    records = [
        record(wm=bits(31, 32), bm=bits(10), stm=0, wdl=1),
        record(wm=bits(33, 34), bm=bits(11), stm=0, wdl=0),
        record(wk=bits(20), bk=bits(35), stm=1, wdl=1),
        record(wm=bits(31), bm=bits(10, 11), stm=0, wdl=-1),
        record(wk=bits(25), bm=bits(45), stm=1, wdl=-1),
        record(
            wm=bits(*range(6, 21)),
            bm=bits(*range(31, 46)),
            stm=0,
            wdl=0,
        ),
    ]
    rows = [
        (1, 101, 0),
        (2, 102, 1),
        (3, 103, 0),
        (4, 104, 0),
        (5, 105, 1),
        (6, 106, 0),
    ]
    return write_pair(root, name, records, rows)


def args_for(
    data: Path,
    meta: Path,
    json_out: Path,
    csv_out: Path,
    *,
    probe_size: int = 4,
) -> Namespace:
    return Namespace(
        data=str(data),
        meta=str(meta),
        json_out=str(json_out),
        csv_out=str(csv_out),
        code_sha=CODE_SHA,
        probe_size=probe_size,
        probe_seed=20260728,
    )


def atlas_row(payload: dict, dimension: str, bucket: str) -> dict:
    return next(
        row for row in payload["atlas"]
        if row["dimension"] == dimension and row["bucket"] == bucket
    )


class BlindSpotAtlasTests(unittest.TestCase):
    def test_deterministic_sorted_round_trip_and_objective_metrics(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            data, meta = fixture_pair(root)
            outputs = []
            summaries = []
            for suffix in ("a", "b"):
                json_out = root / f"atlas-{suffix}.json"
                csv_out = root / f"atlas-{suffix}.csv"
                summaries.append(
                    BSA.do_atlas(args_for(data, meta, json_out, csv_out))
                )
                outputs.append((json_out.read_bytes(), csv_out.read_bytes()))

            self.assertEqual(outputs[0], outputs[1])
            self.assertEqual(summaries[0], summaries[1])
            json_bytes, csv_bytes = outputs[0]
            payload = json.loads(json_bytes)
            self.assertEqual(payload["schema"], BSA.ATLAS_SCHEMA)
            self.assertEqual(payload["schema_version"], 1)
            self.assertTrue(payload["diagnostic_only"])
            self.assertFalse(payload["gate_authorized"])
            self.assertFalse(payload["promotion_authorized"])
            self.assertFalse(payload["automatic_continuation_authorized"])
            self.assertEqual(payload["decision"], "diagnostic_only_no_gate")
            self.assertEqual(payload["score_field_policy"], "ignored_without_explicit_provenance")
            self.assertEqual(payload["records"], 6)
            self.assertEqual(payload["games"], 6)
            self.assertEqual(payload["openings"], 6)
            self.assertEqual(
                payload["input"]["data"]["sha256"],
                hashlib.sha256(data.read_bytes()).hexdigest(),
            )
            self.assertEqual(
                payload["input"]["meta"]["sha256"],
                hashlib.sha256(meta.read_bytes()).hexdigest(),
            )
            self.assertEqual(
                payload["outputs"]["csv_sha256"],
                hashlib.sha256(csv_bytes).hexdigest(),
            )

            row_keys = [
                (row["dimension"], row["bucket"]) for row in payload["atlas"]
            ]
            self.assertEqual(row_keys, sorted(row_keys))
            for dimension in BSA.TAXONOMY_DEFINITIONS:
                self.assertEqual(
                    sum(
                        row["records"] for row in payload["atlas"]
                        if row["dimension"] == dimension
                    ),
                    6,
                )
            thin = atlas_row(payload, "material_stratum", "p3_thin")
            self.assertEqual(thin["records"], 3)
            self.assertEqual(thin["conversion"]["eligible_records"], 3)
            self.assertEqual(thin["conversion"]["converted_records"], 2)
            self.assertEqual(thin["conversion"]["drawn_records"], 1)
            self.assertEqual(thin["conversion"]["reversed_records"], 0)
            self.assertAlmostEqual(thin["conversion"]["rate"], 2 / 3, places=12)
            self.assertEqual(
                atlas_row(payload, "king_configuration", "both_sides_kings")["records"],
                1,
            )
            self.assertEqual(
                atlas_row(payload, "phase", "opening")["records"],
                1,
            )
            self.assertEqual(
                atlas_row(payload, "source", "frontier")["records"],
                2,
            )

            probe = payload["probe"]
            self.assertEqual(probe["schema"], BSA.PROBE_SCHEMA)
            self.assertEqual(probe["selected_positions"], 4)
            selection_hashes = [
                entry["selection_sha256"] for entry in probe["entries"]
            ]
            self.assertEqual(selection_hashes, sorted(selection_hashes))
            self.assertTrue(all(len(entry["position_hex"]) == 66 for entry in probe["entries"]))
            self.assertEqual(summaries[0]["probe_sha256"], probe["probe_sha256"])

            csv_rows = list(csv.DictReader(io_text(csv_bytes)))
            self.assertEqual(
                [(row["dimension"], row["bucket"]) for row in csv_rows],
                row_keys,
            )
            self.assertTrue(all(row["diagnostic_only"] == "true" for row in csv_rows))
            self.assertTrue(all(row["gate_authorized"] == "false" for row in csv_rows))
            self.assertEqual(
                int(next(
                    row["records"] for row in csv_rows
                    if row["dimension"] == "source" and row["bucket"] == "frontier"
                )),
                2,
            )
            extension_names = [
                extension["metric"] for extension in payload["extensions_not_in_v1"]
            ]
            self.assertEqual(extension_names, sorted(extension_names))

    def test_probe_and_atlas_are_independent_of_input_order(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            original_data, original_meta = fixture_pair(root, "original")
            data_raw = original_data.read_bytes()
            meta_raw = original_meta.read_bytes()
            count = struct.unpack_from("<I", data_raw, 4)[0]
            records = [
                data_raw[8 + index * BSA.JNNW_RECORD_SIZE:
                         8 + (index + 1) * BSA.JNNW_RECORD_SIZE]
                for index in range(count)
            ]
            rows = [
                BSA.JSM1_RECORD.unpack_from(meta_raw, 8 + index * BSA.JSM1_RECORD_SIZE)
                for index in range(count)
            ]
            order = [4, 1, 5, 0, 3, 2]
            shuffled_data, shuffled_meta = write_pair(
                root,
                "shuffled",
                [records[index] for index in order],
                [rows[index] for index in order],
            )

            reports = []
            for name, data, meta in (
                ("original", original_data, original_meta),
                ("shuffled", shuffled_data, shuffled_meta),
            ):
                json_out = root / f"{name}.json"
                csv_out = root / f"{name}.csv"
                BSA.do_atlas(args_for(data, meta, json_out, csv_out))
                reports.append(json.loads(json_out.read_text(encoding="utf-8")))
            self.assertEqual(reports[0]["atlas"], reports[1]["atlas"])
            self.assertEqual(reports[0]["probe"], reports[1]["probe"])
            self.assertNotEqual(
                reports[0]["input"]["data"]["sha256"],
                reports[1]["input"]["data"]["sha256"],
            )

    def test_rejects_count_mismatch_without_outputs(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            records = [
                record(wm=bits(31), bm=bits(10), wdl=1),
                record(wm=bits(32), bm=bits(11), wdl=0),
            ]
            data, _meta = write_pair(
                root,
                "bad",
                records,
                [(1, 1, 0), (2, 2, 0)],
            )
            meta = root / "short.jsm"
            meta.write_bytes(
                BSA.JSM1_MAGIC
                + struct.pack("<I", 1)
                + struct.pack("<QQB", 1, 1, 0)
            )
            json_out, csv_out = root / "atlas.json", root / "atlas.csv"
            with self.assertRaisesRegex(ValueError, "count mismatch"):
                BSA.do_atlas(args_for(data, meta, json_out, csv_out))
            self.assertFalse(json_out.exists())
            self.assertFalse(csv_out.exists())

    def test_rejects_bad_magic_truncation_zero_and_seeded_domain(self):
        cases = {}

        with tempfile.TemporaryDirectory() as td:
            # Build raw case payloads while their helper directory is alive.
            root = Path(td)
            valid_data, valid_meta = write_pair(
                root,
                "valid",
                [record(wm=bits(31), bm=bits(10), wdl=0)],
                [(1, 1, 0)],
            )
            data_bytes = valid_data.read_bytes()
            meta_bytes = valid_meta.read_bytes()
            cases = {
                "bad_magic": (b"NOPE" + data_bytes[4:], meta_bytes),
                "truncated": (data_bytes[:-1], meta_bytes),
                "zero": (
                    BSA.JNNW_MAGIC + struct.pack("<I", 0),
                    BSA.JSM1_MAGIC + struct.pack("<I", 0),
                ),
                "bad_seeded": (
                    data_bytes,
                    BSA.JSM1_MAGIC
                    + struct.pack("<I", 1)
                    + struct.pack("<QQB", 1, 1, 2),
                ),
            }

        for name, (data_bytes, meta_bytes) in cases.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as td:
                root = Path(td)
                data, meta = root / "source.jnnw", root / "source.jsm"
                data.write_bytes(data_bytes)
                meta.write_bytes(meta_bytes)
                json_out, csv_out = root / "atlas.json", root / "atlas.csv"
                with self.assertRaises(ValueError):
                    BSA.do_atlas(args_for(data, meta, json_out, csv_out))
                self.assertFalse(json_out.exists())
                self.assertFalse(csv_out.exists())

    def test_rejects_invalid_record_domains_without_outputs(self):
        cases = {
            "bad_wdl": record(wm=bits(31), bm=bits(10), wdl=2),
            "overlap": record(wm=bits(31), bm=bits(31), wdl=0),
            "white_man_promoted": record(wm=bits(1), bm=bits(10), wdl=0),
            "outside_board": record(wm=1 << 55, bm=bits(10), wdl=0),
        }
        for name, bad_record in cases.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as td:
                root = Path(td)
                data, meta = write_pair(root, name, [bad_record], [(1, 1, 0)])
                json_out, csv_out = root / "atlas.json", root / "atlas.csv"
                with self.assertRaises(ValueError):
                    BSA.do_atlas(args_for(data, meta, json_out, csv_out))
                self.assertFalse(json_out.exists())
                self.assertFalse(csv_out.exists())

    def test_rejects_inconsistent_game_metadata(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            data, meta = write_pair(
                root,
                "bad-game",
                [
                    record(wm=bits(31), bm=bits(10), stm=0, wdl=1),
                    record(wm=bits(32), bm=bits(11), stm=0, wdl=-1),
                ],
                [(7, 9, 0), (7, 10, 0)],
            )
            json_out, csv_out = root / "atlas.json", root / "atlas.csv"
            with self.assertRaisesRegex(ValueError, "inconsistent"):
                BSA.do_atlas(args_for(data, meta, json_out, csv_out))
            self.assertFalse(json_out.exists())
            self.assertFalse(csv_out.exists())

    def test_refuses_overwrite_and_input_output_alias(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            data, meta = fixture_pair(root)
            json_out, csv_out = root / "atlas.json", root / "atlas.csv"
            json_out.write_text("sentinel", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "overwrite"):
                BSA.do_atlas(args_for(data, meta, json_out, csv_out))
            self.assertEqual(json_out.read_text(encoding="utf-8"), "sentinel")
            self.assertFalse(csv_out.exists())

            with self.assertRaisesRegex(ValueError, "distinct"):
                BSA.do_atlas(args_for(data, meta, data, root / "other.csv"))
            self.assertTrue(data.read_bytes().startswith(BSA.JNNW_MAGIC))

    def test_atomic_pair_publish_rolls_back_first_output(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            json_out, csv_out = root / "atlas.json", root / "atlas.csv"
            real_link = os.link
            calls = 0

            def fail_second_link(source, destination):
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise OSError("synthetic second publish failure")
                return real_link(source, destination)

            with mock.patch.object(BSA.os, "link", side_effect=fail_second_link):
                with self.assertRaisesRegex(OSError, "synthetic"):
                    BSA._publish_pair_no_clobber(
                        json_out,
                        b"{}\n",
                        csv_out,
                        b"a,b\n",
                    )
            self.assertFalse(json_out.exists())
            self.assertFalse(csv_out.exists())
            self.assertEqual(list(root.glob(".*.tmp")), [])


def io_text(payload: bytes):
    import io

    return io.StringIO(payload.decode("utf-8"), newline="")


if __name__ == "__main__":
    unittest.main()
