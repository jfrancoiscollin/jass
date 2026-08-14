import importlib.util
import json
from pathlib import Path
import struct
import tempfile
import unittest

import numpy as np


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "jobs" / "tools" / "jass_megacorpus_materialize.py"
SPEC = importlib.util.spec_from_file_location("jass_megacorpus_materialize", TOOL)
assert SPEC and SPEC.loader
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


def write_counted(path: Path, magic: bytes, rows: np.ndarray) -> None:
    with path.open("wb") as handle:
        handle.write(magic + struct.pack("<I", len(rows)))
        handle.write(rows.tobytes(order="C"))


def make_pair(root: Path, name: str, source_bias: int, *, jsm2: bool = False):
    data_rows = []
    meta_rows = []
    for game_id in range(30):
        opening_id = game_id // 2
        for ply in range(3):
            data_rows.append(
                (
                    1 << ((source_bias + game_id + ply) % 20),
                    0,
                    1 << (20 + ((source_bias + game_id + ply) % 20)),
                    0,
                    ply % 2,
                    game_id - ply,
                    (-1, 0, 1)[game_id % 3],
                )
            )
            if jsm2:
                meta_rows.append(
                    (game_id, opening_id, game_id % 2, ply, 3, 0xFFFF, 0, 0)
                )
            else:
                meta_rows.append((game_id, opening_id, game_id % 2))
    data = np.array(data_rows, dtype=module.JNNW_DTYPE)
    meta_dtype = module.JSM2_DTYPE if jsm2 else module.JSM1_DTYPE
    meta = np.array(meta_rows, dtype=meta_dtype)
    data_path = root / f"{name}.jnnw"
    meta_path = root / f"{name}.jsm"
    write_counted(data_path, b"JNNW", data)
    write_counted(meta_path, b"JSM2" if jsm2 else b"JSM1", meta)
    return data_path, meta_path, data, meta


class MegaCorpusMaterializeTest(unittest.TestCase):
    def source_spec(self, root: Path, *, duplicate: bool = False) -> Path:
        a_data, a_meta, _, _ = make_pair(root, "a", 0)
        if duplicate:
            b_data, b_meta = a_data, a_meta
        else:
            b_data, b_meta, _, _ = make_pair(root, "b", 7, jsm2=True)
        document = {
            "schema": "jass.megacorpus.source_selection.v1",
            "selection_policy": "unit-test general sources",
            "sources": [
                {
                    "source_id": 3,
                    "name": "current",
                    "data_path": str(a_data),
                    "meta_path": str(a_meta),
                    "expected_data_raw_sha256": module.sha256(a_data),
                    "expected_meta_raw_sha256": module.sha256(a_meta),
                    "expected_records": 90,
                    "sampling": {"mode": "all"},
                    "source_uri": "r2:test/current",
                },
                {
                    "source_id": 9,
                    "name": "historical",
                    "data_path": str(b_data),
                    "meta_path": str(b_meta),
                    "expected_data_raw_sha256": module.sha256(b_data),
                    "expected_meta_raw_sha256": module.sha256(b_meta),
                    "expected_records": 90,
                    "sampling": {
                        "mode": "game_hash_mod",
                        "modulus": 2,
                        "residue": 0,
                        "seed": 4242,
                    },
                    "source_uri": "r2:test/historical",
                },
            ],
        }
        path = root / "selection.json"
        path.write_text(json.dumps(document), encoding="utf-8")
        return path

    def run_materialize(self, root: Path, selection: Path, prefix: str = "mega"):
        paths = {
            "data": root / f"{prefix}.jnnw",
            "meta": root / f"{prefix}.jsm",
            "source": root / f"{prefix}-source.npy",
            "index": root / f"{prefix}-index.npy",
            "table": root / f"{prefix}-sources.json",
            "manifest": root / f"{prefix}-manifest.json",
        }
        result = module.materialize(
            selection,
            paths["data"],
            paths["meta"],
            paths["source"],
            paths["index"],
            paths["table"],
            paths["manifest"],
            holdout_mod=3,
            split_seed=577215,
            chunk_rows=7,
        )
        return paths, result

    def test_game_aware_materialization_provenance_and_split(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            selection = self.source_spec(root)
            paths, result = self.run_materialize(root, selection)
            output = module.open_counted(paths["data"], b"JNNW", module.JNNW_DTYPE)
            meta, schema = module.open_meta(paths["meta"], len(output))
            sources = np.load(paths["source"])
            indices = np.load(paths["index"])

            self.assertEqual(schema, "JSM1")
            self.assertEqual(result["records"], len(output))
            self.assertEqual(result["records"], result["train_records"] + result["holdout_records"])
            self.assertEqual(sources.dtype, np.uint32)
            self.assertEqual(indices.dtype, np.uint64)
            self.assertEqual(set(np.unique(sources)), {3, 9})
            self.assertEqual(len(np.unique(meta["game_id"])), result["games"])

            train_openings = set(int(v) for v in meta["opening_id"][:result["train_records"]])
            holdout_openings = set(int(v) for v in meta["opening_id"][result["train_records"]:])
            self.assertFalse(train_openings & holdout_openings)

            source_paths = json.loads(selection.read_text())["sources"]
            originals = {
                int(spec["source_id"]): module.open_counted(
                    Path(spec["data_path"]), b"JNNW", module.JNNW_DTYPE
                )
                for spec in source_paths
            }
            for row, source_id, index in zip(output, sources, indices):
                self.assertEqual(row.tobytes(), originals[int(source_id)][int(index)].tobytes())

            source_table = json.loads(paths["table"].read_text())
            self.assertEqual(
                [row["meta_schema"] for row in source_table["sources"]],
                ["JSM1", "JSM2"],
            )
            self.assertTrue(all(
                row["original_metadata_preserved_at_source"]
                for row in source_table["sources"]
            ))
            del row, output, meta, originals

    def test_output_is_deterministic(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            selection = self.source_spec(root)
            first, first_result = self.run_materialize(root, selection, "first")
            second, second_result = self.run_materialize(root, selection, "second")
            self.assertEqual(first_result["records"], second_result["records"])
            for key in ("data", "meta", "source", "index"):
                self.assertEqual(module.sha256(first[key]), module.sha256(second[key]))

    def test_exact_duplicate_source_blob_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            selection = self.source_spec(root, duplicate=True)
            with self.assertRaisesRegex(ValueError, "exact duplicate data blob"):
                self.run_materialize(root, selection)

    def test_game_hash_sampling_never_splits_a_game(self):
        spec = {
            "sampling": {"mode": "game_hash_mod", "modulus": 5, "residue": 2, "seed": 9}
        }
        decisions = [module.sampling_accepts(spec, 7, game_id) for game_id in range(100)]
        self.assertGreater(sum(decisions), 0)
        self.assertLess(sum(decisions), len(decisions))
        self.assertEqual(decisions, [
            module.sampling_accepts(spec, 7, game_id) for game_id in range(100)
        ])


if __name__ == "__main__":
    unittest.main()
