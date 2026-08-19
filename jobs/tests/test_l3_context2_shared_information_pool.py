#!/usr/bin/env python3
import json
import struct
import tempfile
import unittest
from pathlib import Path

import numpy as np

from jobs.tools import l3_context2_shared_information_pool as shared
from jobs.tools.l3_conditional_targets import JSM2_DTYPE


class SharedInformationPoolTests(unittest.TestCase):
    def test_concentration_and_gate_ratios(self):
        values = np.asarray([4.0, 3.0, 2.0, 1.0] + [0.5] * 11)
        metrics = shared.concentration(values)
        self.assertAlmostEqual(sum(metrics["component_shares"].values()), 1.0)
        self.assertGreater(metrics["top3_share"], metrics["largest_share"])
        ratios = shared.gate_ratios(metrics, {
            "maximum_largest_share": 0.30,
            "maximum_top3_share": 0.70,
            "minimum_effective_component_count": 4.0,
        })
        self.assertEqual(ratios["worst"], max(value for key, value in ratios.items() if key != "worst"))

    def test_selection_keeps_exact_strata_and_global_guards(self):
        rows = np.zeros(12, dtype=shared.JNNW_DTYPE)
        metadata = np.zeros(
            12, dtype=np.dtype([("game_id", "<u8"), ("opening_id", "<u8")])
        )
        for index in range(12):
            rows[index]["wm"] = 1 << (index % 6)
            rows[index]["bm"] = 1 << (20 + index % 6)
            rows[index]["stm"] = index % 2
            metadata[index]["game_id"] = index // 3
            metadata[index]["opening_id"] = index // 2
        # Make row 6 a canonical duplicate of row 0; a lower-utility unique row
        # must be used instead while the two-per-game ceiling stays intact.
        rows[6] = rows[0]
        strata = np.asarray([0] * 6 + [1] * 6, dtype=np.int16)
        utility = np.arange(12, dtype=np.float64)
        selected = shared.select_with_guards(
            records=rows,
            metadata=metadata,
            strata=strata,
            quotas=np.asarray([2, 2] + [0] * 58, dtype=np.int64),
            utility=utility,
            seed=17,
        )
        self.assertEqual(len(selected), 4)
        np.testing.assert_array_equal(np.bincount(strata[selected], minlength=60)[:2], [2, 2])
        canonicals = [shared.canonical_position(rows[int(index)].tobytes()) for index in selected]
        self.assertEqual(len(canonicals), len(set(canonicals)))
        counts = np.bincount(metadata["game_id"][selected].astype(np.int64))
        self.assertLessEqual(int(counts.max()), 2)

    def test_stratified_null_is_deterministic(self):
        rng = np.random.default_rng(3)
        signed = rng.normal(size=(80, 15)).astype(np.float32)
        weights = np.ones(80)
        strata = np.repeat(np.arange(4), 20).astype(np.int16)
        quotas = np.asarray([5, 5, 5, 5] + [0] * 56, dtype=np.int64)
        thresholds = {
            "maximum_largest_share": 0.20,
            "maximum_top3_share": 0.50,
            "minimum_effective_component_count": 8.0,
        }
        first = shared.stratified_null_screen(
            signed=signed,
            source_weights=weights,
            strata=strata,
            quotas=quotas,
            thresholds=thresholds,
            replicates=32,
            seed=11,
        )
        second = shared.stratified_null_screen(
            signed=signed,
            source_weights=weights,
            strata=strata,
            quotas=quotas,
            thresholds=thresholds,
            replicates=32,
            seed=11,
        )
        np.testing.assert_array_equal(first.pop("_worst"), second.pop("_worst"))
        self.assertEqual(first, second)
        self.assertEqual(first["method"], "exact_without_replacement_within_phase_wdl_material_stratum")

    def test_pool_writer_zeroes_labels(self):
        rows = np.zeros(3, dtype=shared.JNNW_DTYPE)
        rows["wm"] = [1, 2, 4]
        rows["bm"] = [8, 16, 32]
        rows["score"] = [50, -20, 9]
        rows["wdl"] = [1, -1, 0]
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            path = Path(directory) / "shared.jnnw"
            digest = shared._write_pool(path, rows, np.asarray([2, 0], dtype=np.int64))
            raw = path.read_bytes()
            self.assertEqual(raw[:8], struct.pack("<4sI", b"JNNW", 2))
            self.assertEqual(len(digest), 64)
            for offset in (8, 8 + shared.JNNW_DTYPE.itemsize):
                self.assertEqual(raw[offset + 33 : offset + 38], b"\0" * 5)

    def test_mapper_table_rejects_non_opening_folds(self):
        metadata = np.zeros(
            10, dtype=np.dtype([("game_id", "<u8"), ("opening_id", "<u8")])
        )
        report = {
            "schema": "jass.l3_conditional_targets.v2",
            "context_schema": "ctx2-phase-tactical-30",
            "records": 10,
            "train_records": 8,
            "mapping": {
                "components": list(shared.CTX2_CONTEXT_COMPONENTS),
                "fold_group": "game_id",
                "row_weighting": "game_equal",
                "fold_local_rms": True,
                "all_groups_fold_disjoint": True,
            },
        }
        with self.assertRaisesRegex(ValueError, "contract"):
            shared._mapper_table(report, metadata)

    def test_end_to_end_small_screen_writes_a_zero_target_pool(self):
        rng = np.random.default_rng(19)
        count, train_count, pool_size = 400, 360, 60
        records = np.zeros(count, dtype=shared.JNNW_DTYPE)
        metadata = np.zeros(count, dtype=JSM2_DTYPE)
        for index in range(count):
            # Deliberately synthetic but canonical-unique position payloads.
            records[index]["wm"] = index + 1
            records[index]["wk"] = 1 << (30 + index % 10)
            records[index]["bm"] = (index + 1) << 20
            records[index]["bk"] = 1 << (40 + index % 10)
            records[index]["stm"] = index % 2
            records[index]["score"] = index - 200
            records[index]["wdl"] = (-1, 0, 1)[index % 3]
            metadata[index]["game_id"] = 10_000 + index
            metadata[index]["opening_id"] = 20_000 + index
            metadata[index]["ply"] = index % 40
            metadata[index]["game_plies"] = 40
            metadata[index]["game_result"] = records[index]["wdl"]
        features = rng.normal(size=(count, 30)).astype("<f4")
        theta = rng.normal(scale=0.2, size=(6, 30))

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            root = Path(directory)
            data = root / "source.jnnw"
            meta = root / "source.jsm"
            feat = root / "source.feat"
            data.write_bytes(struct.pack("<4sI", b"JNNW", count) + records.tobytes())
            meta.write_bytes(struct.pack("<4sI", b"JSM2", count) + metadata.tobytes())
            feat.write_bytes(struct.pack("<4sII", b"FEAT", count, 30) + features.tobytes())
            mapping = {
                "components": list(shared.CTX2_CONTEXT_COMPONENTS),
                "fold_group": "opening_id",
                "row_weighting": "game_equal",
                "fold_local_rms": True,
                "all_groups_fold_disjoint": True,
                "fold_count": 5,
                "fold_seed": 23,
                "folds": [
                    {"fold": fold, "theta_raw": theta[fold].tolist(), "fit": {"converged": True}}
                    for fold in range(5)
                ],
                "final_train_fit": {
                    "theta_raw": theta[5].tolist(),
                    "fit": {"converged": True},
                },
            }
            conditional = {
                "schema": "jass.l3_conditional_targets.v2",
                "context_schema": "ctx2-phase-tactical-30",
                "records": count,
                "train_records": train_count,
                "mapping": mapping,
                "source": {
                    "data_sha256": shared._sha256(data),
                    "meta_sha256": shared._sha256(meta),
                    "feat_sha256": shared._sha256(feat),
                },
            }
            conditional_path = root / "conditional.json"
            conditional_path.write_text(json.dumps(conditional), encoding="utf-8")
            current = {
                "schema": "jass.l3_context2_fixed_contribution_audit.v1",
                "verdict": "JASS_CONTEXT2_FIXED_CONTRIBUTION_AUDIT_READY",
                "cohorts": {"train_oof": {"base_15_concentration": {
                    "largest_share": 0.90,
                    "top3_share": 0.99,
                    "effective_component_count": 1.0,
                }}},
            }
            current_path = root / "current.json"
            current_path.write_text(json.dumps(current), encoding="utf-8")
            output = root / "shared.jnnw"
            manifest = root / "manifest.json"
            payload = shared.build(__import__("argparse").Namespace(
                data=str(data), meta=str(meta), features=str(feat),
                conditional_report=str(conditional_path), current_audit=str(current_path),
                output=str(output), manifest=str(manifest), pool_size=pool_size,
                seed=29, shuffles=16, shuffle_seed=31,
            ))
            self.assertEqual(payload["output"]["records"], pool_size)
            self.assertEqual(payload["stratified_null"]["replicates"], 16)
            self.assertFalse(payload["guards"]["aligned_beats_10000_stratified_shuffles_p_ge_0_975"])
            raw = output.read_bytes()
            self.assertEqual(struct.unpack_from("<I", raw, 4)[0], pool_size)
            for offset in range(8, len(raw), shared.JNNW_DTYPE.itemsize):
                self.assertEqual(raw[offset + 33 : offset + 38], b"\0" * 5)


if __name__ == "__main__":
    unittest.main()
