import json
import gc
from pathlib import Path
import struct
import tempfile
from types import SimpleNamespace
import unittest

import numpy as np

from jobs.tools import jfi_active_materialize as materialize
from jobs.tools import jfi_active_readout as readout
from jobs.tools import jfi_active_select_stream as selector
from jobs.tools import jfi_active_targets as targets
from jobs.tools import jfi_candidate_universe as universe
from jobs.tools.tb_frontier_symmetry_dedup import rotate50


def write_counted(path: Path, magic: bytes, rows: np.ndarray) -> None:
    path.write_bytes(magic + struct.pack("<I", len(rows)) + rows.tobytes())


def write_feat(path: Path, rows: np.ndarray) -> None:
    rows = np.asarray(rows, dtype="<f4")
    path.write_bytes(
        b"FEAT" + struct.pack("<II", rows.shape[0], rows.shape[1]) + rows.tobytes()
    )


class CandidateUniverseTests(unittest.TestCase):
    def test_hash_is_target_blind_and_exact_selection_is_deterministic(self):
        rows = np.zeros(5, dtype=universe.JNNW_DTYPE)
        rows["wm"] = np.arange(1, 6, dtype=np.uint64)
        changed = rows.copy()
        changed["score"] = np.arange(5, dtype=np.int32) + 100
        changed["wdl"] = np.asarray([-1, 0, 1, -1, 1], dtype=np.int8)
        ids = np.arange(5, dtype=np.uint64)
        np.testing.assert_array_equal(
            universe.target_blind_hash(ids, rows),
            universe.target_blind_hash(ids, changed),
        )
        hashes = np.asarray([9, 1, 5, 1, 8], dtype=np.uint64)
        np.testing.assert_array_equal(
            universe.select_smallest_hashes(hashes, 3), np.asarray([1, 3, 2])
        )

    def test_small_universe_zeroes_labels_and_keeps_openings_together(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            source = np.zeros(30, dtype=universe.JNNW_DTYPE)
            source["wm"] = np.arange(1, 31, dtype=np.uint64)
            source["score"] = np.arange(30, dtype=np.int32) - 10
            source["wdl"] = np.resize(np.asarray([-1, 0, 1], dtype=np.int8), 30)
            meta = np.zeros(30, dtype=universe.JSM1_DTYPE)
            meta["game_id"] = np.arange(30, dtype=np.uint64)
            meta["opening_id"] = np.repeat(np.arange(10, dtype=np.uint64), 3)
            data_path, meta_path = root / "source.jnnw", root / "source.jsm"
            write_counted(data_path, b"JNNW", source)
            write_counted(meta_path, b"JSM1", meta)
            out_data, out_meta = root / "candidate.jnnw", root / "candidate.jsm"
            origin, roles, manifest = root / "origin.npy", root / "roles.npy", root / "manifest.json"
            args = SimpleNamespace(
                data=str(data_path), meta=str(meta_path), expected_data_sha=None,
                expected_meta_sha=None, records=20, split_seed=2026120102,
                dev_mod=10, chunk=7, out_data=str(out_data), out_meta=str(out_meta),
                origin_indices_out=str(origin), roles_out=str(roles), manifest=str(manifest),
            )
            report = universe.build_universe(args)
            candidate, _ = universe.open_counted(out_data, {b"JNNW": universe.JNNW_DTYPE})
            candidate_meta, _ = universe.open_counted(out_meta, {b"JSM1": universe.JSM1_DTYPE})
            role = np.load(roles, allow_pickle=False)
            self.assertEqual(len(candidate), 20)
            self.assertFalse(np.any(candidate["score"]))
            self.assertFalse(np.any(candidate["wdl"]))
            for opening in np.unique(candidate_meta["opening_id"]):
                self.assertEqual(len(np.unique(role[candidate_meta["opening_id"] == opening])), 1)
            self.assertEqual(report["guards"]["TARGET_READS"], 0)
            self.assertEqual(report["files"]["data"]["sha256"], universe.sha256_file(out_data))
            del candidate, candidate_meta
            gc.collect()


class ActiveSelectorTests(unittest.TestCase):
    def test_reverse50_and_canonical_state_match_scalar_contract(self):
        values = np.asarray([0, 1, 1 << 49, (1 << 3) | (1 << 31)], dtype=np.uint64)
        np.testing.assert_array_equal(
            selector.reverse50(values),
            np.asarray([rotate50(int(value)) for value in values], dtype=np.uint64),
        )
        wm = np.asarray([1 << 2, 1 << 11], dtype=np.uint64)
        wk = np.asarray([1 << 8, 0], dtype=np.uint64)
        bm = np.asarray([1 << 40, 1 << 35], dtype=np.uint64)
        bk = np.asarray([0, 1 << 45], dtype=np.uint64)
        stm = np.asarray([0, 1], dtype=np.uint8)
        folded = selector.canonical_state(wm, wk, bm, bk, stm)
        for index in range(len(wm)):
            raw = tuple(int(field[index]) for field in (wm, wk, bm, bk, stm))
            sym = (
                rotate50(raw[2]), rotate50(raw[3]), rotate50(raw[0]),
                rotate50(raw[1]), 1 - raw[4],
            )
            self.assertEqual(tuple(int(field[index]) for field in folded), min(raw, sym))

    def test_canonical_representative_uses_seeded_tie_key(self):
        raw = (np.asarray([1, 1, 2], dtype=np.uint64),) + tuple(
            np.zeros(3, dtype=dtype)
            for dtype in (np.uint64, np.uint64, np.uint64, np.uint8)
        )
        high = np.asarray([10, 5, 0], dtype=np.uint64)
        low = np.asarray([0, 0, 0], dtype=np.uint64)
        representatives = selector.representative_indices(raw, high, low)
        np.testing.assert_array_equal(representatives, np.asarray([1, 2]))

    def test_hamilton_strata_are_equal_and_arms_are_disjoint(self):
        strata = np.repeat(np.arange(4, dtype=np.int16), 10)
        scores = np.arange(40, dtype=np.float64)
        high = np.arange(40, dtype=np.uint64)[::-1]
        low = np.zeros(40, dtype=np.uint64)
        active, quotas = selector.select_stratified(
            scores, strata, high, low, 12, active=True,
        )
        uniform, same = selector.select_stratified(
            scores, strata, high, low, 12, excluded=active, quotas=quotas,
        )
        np.testing.assert_array_equal(quotas, np.asarray([3, 3, 3, 3]))
        np.testing.assert_array_equal(quotas, same)
        self.assertFalse(np.intersect1d(active, uniform).size)
        np.testing.assert_array_equal(np.bincount(strata[active]), quotas)
        np.testing.assert_array_equal(np.bincount(strata[uniform]), quotas)


class PostSelectionTests(unittest.TestCase):
    def test_materialization_reads_source_labels_only_after_frozen_manifest(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            source = np.zeros(12, dtype=universe.JNNW_DTYPE)
            source["wm"] = np.arange(1, 13, dtype=np.uint64)
            source["score"] = np.arange(12, dtype=np.int32) + 10
            source["wdl"] = np.resize(np.asarray([-1, 0, 1], dtype=np.int8), 12)
            candidate = source.copy(); candidate["score"] = 0; candidate["wdl"] = 0
            meta = np.zeros(12, dtype=universe.JSM1_DTYPE)
            meta["game_id"] = np.arange(12, dtype=np.uint64)
            meta["opening_id"] = np.arange(12, dtype=np.uint64) // 2
            source_data, source_meta = root / "source.jnnw", root / "source.jsm"
            candidate_data, candidate_meta = root / "candidate.jnnw", root / "candidate.jsm"
            write_counted(source_data, b"JNNW", source)
            write_counted(source_meta, b"JSM1", meta)
            write_counted(candidate_data, b"JNNW", candidate)
            write_counted(candidate_meta, b"JSM1", meta)
            feat_path = root / "candidate.feat"
            write_feat(feat_path, np.arange(36, dtype=np.float32).reshape(12, 3))
            origin = root / "origin.npy"; np.save(origin, np.arange(12, dtype=np.uint32))
            active = root / "active.npy"; np.save(active, np.asarray([0, 2], dtype=np.uint32))
            uniform = root / "uniform.npy"; np.save(uniform, np.asarray([1, 3], dtype=np.uint32))
            candidate_manifest = root / "candidate-manifest.json"
            candidate_manifest.write_text(json.dumps({
                "schema": "jass.jfi.candidate_universe.v1",
                "source": {
                    "data_sha256": universe.sha256_file(source_data),
                    "meta_sha256": universe.sha256_file(source_meta),
                },
                "files": {
                    "data": {"sha256": universe.sha256_file(candidate_data)},
                    "meta": {"sha256": universe.sha256_file(candidate_meta)},
                    "origin_indices": {"sha256": universe.sha256_file(origin)},
                },
            }))
            selection_path = root / "selection.json"
            selection_path.write_text(json.dumps({
                "schema": "jass.jfi.c_active_uniform_selection.v1",
                "guards": {"TARGET_READS_BEFORE_MANIFEST_FREEZE": 0},
                "inputs": {
                    "candidate_manifest": {"sha256": universe.sha256_file(candidate_manifest)},
                    "candidate_data": {"sha256": universe.sha256_file(candidate_data)},
                    "origin_indices": {"sha256": universe.sha256_file(origin)},
                },
                "files": {
                    "active_indices": {"sha256": universe.sha256_file(active)},
                    "uniform_indices": {"sha256": universe.sha256_file(uniform)},
                },
            }))
            paths = {
                name: root / name for name in (
                    "reference_data", "reference_meta", "reference_feat",
                    "active_data", "active_meta", "active_feat",
                    "uniform_data", "uniform_meta", "uniform_feat", "manifest",
                )
            }
            args = SimpleNamespace(
                candidate_data=str(candidate_data), candidate_meta=str(candidate_meta),
                candidate_feat=str(feat_path), origin_indices=str(origin),
                candidate_manifest=str(candidate_manifest),
                source_data=str(source_data), source_meta=str(source_meta),
                selection_manifest=str(selection_path), active_indices=str(active),
                uniform_indices=str(uniform), train_count=8, chunk=2, production=False,
                **{key: str(value) for key, value in paths.items()},
            )
            report = materialize.materialize(args)
            active_rows, _ = universe.open_counted(
                paths["active_data"], {b"JNNW": universe.JNNW_DTYPE}
            )
            uniform_rows, _ = universe.open_counted(
                paths["uniform_data"], {b"JNNW": universe.JNNW_DTYPE}
            )
            np.testing.assert_array_equal(active_rows["score"], source["score"][[0, 2, 8, 9, 10, 11]])
            np.testing.assert_array_equal(uniform_rows[-4:]["score"], active_rows[-4:]["score"])
            self.assertTrue(report["ordering"]["common_dev_tail"])
            self.assertEqual(report["guards"]["TARGET_READS_BEFORE_MANIFEST_FREEZE"], 0)
            del active_rows, uniform_rows
            gc.collect()

    def test_common_target_split_preserves_identical_dev_tail(self):
        reference = np.linspace(0.05, 0.95, 11, dtype=np.float32)
        active, uniform = targets.split_targets(reference, arm_count=4, dev_count=3)
        np.testing.assert_array_equal(active[-3:], uniform[-3:])
        np.testing.assert_array_equal(active[:4], reference[:4])
        np.testing.assert_array_equal(uniform[:4], reference[4:8])

    def test_identifiability_gate_uses_frozen_global_scalars(self):
        def report(effective, dominated, posterior):
            return {
                "coordinates": 10,
                "records": 4,
                "selected_l2": 1e-5,
                "effective_df": effective,
                "class_counts": {
                    "UNSEEN": 1, "PRIOR_DOMINATED": 2,
                    "MIXED": 7 - dominated, "DATA_DOMINATED": dominated,
                },
                "posterior_variance_proxy_quantiles": [
                    posterior / 4, posterior / 2, posterior, posterior * 2,
                    posterior * 3, posterior * 4, posterior * 5,
                ],
            }
        active, uniform, tests, passed = readout.compare_identifiability(
            report(5.0, 2, 10.0), report(4.0, 1, 12.0),
        )
        self.assertTrue(passed)
        self.assertTrue(all(tests.values()))
        self.assertEqual(active["data_dominated_fraction"], 0.2)
        self.assertEqual(uniform["posterior_variance_proxy_median"], 12.0)


if __name__ == "__main__":
    unittest.main()
