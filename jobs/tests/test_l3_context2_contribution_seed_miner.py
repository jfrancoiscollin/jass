#!/usr/bin/env python3
import argparse
import json
import struct
import tempfile
import unittest
from pathlib import Path

import numpy as np

from jobs.tools import l3_context2_contribution_seed_miner as miner


class ContributionSeedMinerTests(unittest.TestCase):
    def test_capped_allocation_is_exact_deterministic_and_bounded(self):
        capacities = np.asarray([2, 5, 7, 0, 9], dtype=np.int64)
        weights = np.asarray([10, 4, 3, 100, 1], dtype=np.float64)
        first = miner.allocate_capped_proportional(capacities, weights, 13)
        second = miner.allocate_capped_proportional(capacities, weights, 13)
        np.testing.assert_array_equal(first, second)
        self.assertEqual(int(first.sum()), 13)
        self.assertTrue(bool(np.all(first <= capacities)))
        self.assertEqual(int(first[3]), 0)

    def test_capped_allocation_fails_when_capacity_is_short(self):
        with self.assertRaisesRegex(ValueError, "insufficient"):
            miner.allocate_capped_proportional(
                np.asarray([1, 1]), np.asarray([1.0, 1.0]), 3
            )

    def test_zero_targets_preserves_position_and_clears_labels(self):
        record = struct.pack("<QQQQB", 3, 4, 5, 6, 1) + struct.pack("<ib", -123, -1)
        zeroed = miner.zero_targets(record)
        self.assertEqual(zeroed[:33], record[:33])
        self.assertEqual(zeroed[33:], b"\0\0\0\0\0")

    def test_canonical_position_is_colour_mirror_invariant(self):
        record = struct.pack("<QQQQB", 1 << 2, 1 << 7, 1 << 31, 1 << 44, 0) + struct.pack("<ib", 9, 1)
        mirrored = miner._mirror_position(record) + struct.pack("<ib", -5, -1)
        self.assertEqual(
            miner.canonical_position(record), miner.canonical_position(mirrored)
        )

    def test_pool_writer_roundtrips_and_zeroes_targets(self):
        dtype = miner.JNNW_DTYPE
        rows = np.zeros(2, dtype=dtype)
        rows[0]["wm"], rows[0]["bm"], rows[0]["stm"] = 1, 2, 0
        rows[1]["wm"], rows[1]["bm"], rows[1]["stm"] = 4, 8, 1
        rows["score"] = [100, -50]
        rows["wdl"] = [1, -1]
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            path = Path(directory) / "pool.jnnw"
            digest = miner._write_pool(path, rows, [0, 1])
            raw = path.read_bytes()
            self.assertEqual(raw[:4], b"JNNW")
            self.assertEqual(struct.unpack_from("<I", raw, 4)[0], 2)
            self.assertEqual(len(digest), 64)
            self.assertEqual(raw[8 + 33 : 8 + 38], b"\0\0\0\0\0")
            self.assertEqual(raw[8 + 38 + 33 : 8 + 76], b"\0\0\0\0\0")

    def test_preregistered_targets_are_exact(self):
        self.assertEqual(
            miner.TARGET_COMPONENTS,
            (
                "king_safe_mobility_delta",
                "legal_capture_option_delta",
                "center_presence_delta",
                "king_centrality_delta",
                "blocked_man_delta",
            ),
        )
        self.assertEqual(miner.DOMINANT_COMPONENT, "men_delta")

    def test_allocation_orders_are_deterministic_exhaustive_and_base_first(self):
        base = [4, 1, 3, 0, 2]
        first = miner._allocation_orders(base, 2026081806)
        second = miner._allocation_orders(base, 2026081806)
        self.assertEqual(first, second)
        self.assertEqual(first[0], tuple(base))
        self.assertEqual(len(first), 120)
        self.assertEqual(len(set(first)), 120)
        self.assertEqual(set(first), set(__import__("itertools").permutations(range(5))))

    def test_small_end_to_end_mining_contract(self):
        count = 3000
        train_count = 2700
        records = np.zeros(count, dtype=miner.JNNW_DTYPE)
        for index in range(count):
            # Four men, unique enough for the selected 24-position fixture,
            # while keeping every row in the same phase/material stratum.
            records[index]["wm"] = (1 << (index % 20)) | (1 << (20 + (index // 20) % 10))
            records[index]["bm"] = (1 << (30 + (index // 200) % 10)) | (1 << (40 + (index // 2000) % 10))
            records[index]["stm"] = index % 2
            records[index]["score"] = index - 1500
            records[index]["wdl"] = 0
        metadata = np.zeros(
            count,
            dtype=np.dtype(
                [
                    ("game_id", "<u8"), ("opening_id", "<u8"), ("seeded", "u1"),
                    ("ply", "<u2"), ("game_plies", "<u2"), ("last_eps_ply", "<u2"),
                    ("game_result", "i1"), ("flags", "u1"),
                ]
            ),
        )
        metadata["game_id"] = np.arange(count, dtype=np.uint64)
        metadata["opening_id"] = np.arange(count, dtype=np.uint64)
        metadata["game_plies"] = 1
        metadata["last_eps_ply"] = 65535
        features = np.zeros((count, 30), dtype="<f4")
        men_index = miner.CTX2_BASE_COMPONENTS.index("men_delta")
        features[1500:, men_index] = 10.0
        block = 300
        for component_index, component in enumerate(miner.TARGET_COMPONENTS):
            base_index = miner.CTX2_BASE_COMPONENTS.index(component)
            start = component_index * block
            features[start : start + block // 2, base_index] = -10.0
            features[start + block // 2 : start + block, base_index] = 10.0

        theta = [1.0] * 30
        mapping = {
            "components": list(miner.CTX2_CONTEXT_COMPONENTS),
            "fold_group": "opening_id",
            "row_weighting": "game_equal",
            "fold_local_rms": True,
            "all_groups_fold_disjoint": True,
            "fold_count": 5,
            "fold_seed": 123,
            "folds": [
                {"fold": fold, "fit": {"converged": True}, "theta_raw": theta}
                for fold in range(5)
            ],
            "final_train_fit": {"fit": {"converged": True}, "theta_raw": theta},
        }
        autopsy = {
            "verdict": "JASS_CONTEXT2_INTERVENTION_CONTRIBUTION_AUTOPSY_READY",
            "dominant_component": {"component": "men_delta"},
            "five_weakest_components": [
                {"component": component} for component in miner.TARGET_COMPONENTS
            ],
            "fixed_mapper_quota_lattice": {"quota_only_rescue_predicted": False},
        }

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data = root / "source.jnnw"
            meta = root / "source.jsm"
            feat = root / "source.feat"
            conditional_path = root / "conditional.json"
            autopsy_path = root / "autopsy.json"
            data.write_bytes(b"JNNW" + struct.pack("<I", count) + records.tobytes())
            meta.write_bytes(b"JSM2" + struct.pack("<I", count) + metadata.tobytes())
            feat.write_bytes(b"FEAT" + struct.pack("<II", count, 30) + features.tobytes())
            conditional = {
                "schema": "jass.l3_conditional_targets.v2",
                "context_schema": "ctx2-phase-tactical-30",
                "records": count,
                "train_records": train_count,
                "mapping": mapping,
                "source": {
                    "data_sha256": miner._sha256(data),
                    "meta_sha256": miner._sha256(meta),
                    "feat_sha256": miner._sha256(feat),
                },
            }
            conditional_path.write_text(json.dumps(conditional))
            autopsy_path.write_text(json.dumps(autopsy))
            args = argparse.Namespace(
                data=str(data), meta=str(meta), features=str(feat),
                conditional_report=str(conditional_path), autopsy=str(autopsy_path),
                out_dir=str(root / "pools"), manifest=str(root / "manifest.json"),
                seed=2026081806, per_pool=4,
            )
            payload = miner.mine(args)
            self.assertEqual(payload["verdict"], "JASS_CONTEXT2_CONTRIBUTION_SEEDS_READY")
            self.assertEqual(payload["guards"]["pool_count"], 6)
            self.assertEqual(payload["guards"]["exact_records_total"], 24)
            self.assertTrue(payload["guards"]["all_stratum_histograms_identical"])
            self.assertTrue(payload["guards"]["all_target_signs_balanced_50_50"])
            self.assertEqual(
                payload["selection"]["allocation_algorithm"],
                "deterministic_multistart_exact_v1",
            )
            for row in payload["pools"].values():
                self.assertEqual(row["records"], 4)


if __name__ == "__main__":
    unittest.main()
