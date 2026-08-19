#!/usr/bin/env python3
import argparse
import importlib.util
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

    def test_global_rank_prefers_owned_then_exclusive_openings(self):
        metadata = np.zeros(
            4,
            dtype=np.dtype([("game_id", "<u8"), ("opening_id", "<u8")]),
        )
        metadata["game_id"] = [10, 11, 12, 13]
        metadata["opening_id"] = [100, 101, 102, 103]
        ranked = miner._rank_global_candidates(
            np.arange(4, dtype=np.int64),
            metadata,
            pool="king_centrality",
            opening_owner={100: "king_centrality", 103: "blocked_man"},
            opening_masks={100: 0b11000, 101: 0b01000, 102: 0b11000, 103: 0b01000},
            seed=2026081806,
            salt=0,
        )
        self.assertEqual(int(ranked[0]), 0)  # already owned by this pool
        self.assertEqual(int(ranked[1]), 1)  # unowned and exclusive
        self.assertEqual(int(ranked[2]), 2)  # unowned but shared
        self.assertEqual(int(ranked[3]), 3)  # owned by another pool

    def test_global_request_order_prioritizes_shared_only_bucket(self):
        metadata = np.zeros(
            14,
            dtype=np.dtype([("game_id", "<u8"), ("opening_id", "<u8")]),
        )
        metadata["opening_id"] = np.arange(14, dtype=np.uint64)
        eligible = {
            (component, sign, stratum): np.asarray([], dtype=np.int64)
            for component in range(5)
            for sign in range(2)
            for stratum in range(60)
        }
        # Component 0 has two exclusive openings.  Component 1 can only use
        # two openings shared with component 0, so it must be served first.
        eligible[(0, 0, 0)] = np.asarray([0, 1, 2, 3], dtype=np.int64)
        eligible[(1, 0, 0)] = np.asarray([2, 3], dtype=np.int64)
        eligible[(2, 0, 0)] = np.asarray([4, 5, 6, 7], dtype=np.int64)
        eligible[(3, 0, 0)] = np.asarray([8, 9, 10, 11], dtype=np.int64)
        eligible[(4, 0, 0)] = np.asarray([12, 13, 4, 5], dtype=np.int64)
        quotas = np.zeros((2, 60), dtype=np.int64)
        quotas[0, 0] = 2
        masks = miner._opening_pool_masks(eligible, metadata)
        order = miner._global_request_order(
            eligible_by_bucket=eligible,
            common_sign_quotas=quotas,
            metadata=metadata,
            opening_masks=masks,
            seed=2026081806,
        )
        self.assertEqual(order[0][:3], (1, 0, 0))

    def test_current_capacity_respects_opening_ownership_and_game_cap(self):
        metadata = np.zeros(
            6,
            dtype=np.dtype([("game_id", "<u8"), ("opening_id", "<u8")]),
        )
        metadata["game_id"] = [10, 10, 10, 11, 11, 12]
        metadata["opening_id"] = [100, 100, 100, 101, 101, 102]
        capacity = miner._current_request_capacity(
            candidates=np.arange(6, dtype=np.int64),
            pool="king_centrality",
            metadata=metadata,
            opening_owner={101: "blocked_man", 102: "king_centrality"},
            game_counts=__import__("collections").Counter({10: 1}),
        )
        # One remaining row from game 10, none from the foreign opening 101,
        # and one from game 12 already owned by the current pool.
        self.assertEqual(capacity, 2)

    def test_global_rank_protects_opening_that_would_break_pending_request(self):
        metadata = np.zeros(
            3,
            dtype=np.dtype([("game_id", "<u8"), ("opening_id", "<u8")]),
        )
        metadata["game_id"] = [10, 11, 12]
        metadata["opening_id"] = [100, 101, 102]
        ranked = miner._rank_global_candidates(
            np.arange(3, dtype=np.int64),
            metadata,
            pool="king_centrality",
            opening_owner={},
            opening_masks={100: 0b01001, 101: 0b01001, 102: 0b01000},
            seed=2026081806,
            salt=0,
            pending_requests={0, 1},
            request_order=[(0, 0, 0, 4), (3, 0, 0, 2)],
            feasible_capacity=np.asarray([5, 10], dtype=np.int64),
            remaining_required=np.asarray([4, 2], dtype=np.int64),
            opening_request_capacities={100: [(0, 2)], 101: [(0, 1)]},
        )
        self.assertEqual(int(ranked[0]), 2)  # exclusive to current pool
        self.assertEqual(int(ranked[1]), 1)  # shared but non-critical
        self.assertEqual(int(ranked[2]), 0)  # would make request 0 infeasible

    def test_opening_repair_replaces_displaced_row_and_frees_capacity(self):
        records = np.zeros(3, dtype=miner.JNNW_DTYPE)
        records[0]["wm"], records[0]["bm"] = 1, 2
        records[1]["wm"], records[1]["bm"] = 4, 8
        records[2]["wm"], records[2]["bm"] = 16, 32
        metadata = np.zeros(
            3,
            dtype=np.dtype([("game_id", "<u8"), ("opening_id", "<u8")]),
        )
        metadata["game_id"] = [10, 11, 12]
        metadata["opening_id"] = [100, 100, 200]
        request_order = [(0, 0, 0, 1), (1, 0, 0, 1)]
        eligible = {
            (0, 0, 0): np.asarray([1], dtype=np.int64),
            (1, 0, 0): np.asarray([0, 2], dtype=np.int64),
        }
        selected = {1: [0]}
        cache: dict[int, bytes] = {}
        owners, games, canonicals = miner._rebuild_target_selection_state(
            selected_by_request=selected,
            request_order=request_order,
            records=records,
            metadata=metadata,
            canonical_cache=cache,
        )
        repaired = miner._repair_blocked_request(
            request_index=0,
            required=1,
            selected_by_request=selected,
            request_order=request_order,
            eligible_by_bucket=eligible,
            records=records,
            metadata=metadata,
            opening_owner=owners,
            game_counts=games,
            canonical_used=canonicals,
            canonical_cache=cache,
            opening_masks={100: 0b11, 200: 0b10},
            seed=2026081806,
            salt=0,
        )
        self.assertIsNotNone(repaired)
        selection, owners, games, canonicals, freed = repaired
        self.assertEqual(selection[1], [2])
        self.assertEqual(owners[100], miner.POOL_NAMES[miner.TARGET_COMPONENTS[0]])
        self.assertEqual(freed, [100])
        self.assertEqual(
            miner._current_request_capacity(
                candidates=eligible[(0, 0, 0)],
                pool=miner.POOL_NAMES[miner.TARGET_COMPONENTS[0]],
                metadata=metadata,
                opening_owner=owners,
                game_counts=games,
                records=records,
                canonical_used=canonicals,
                canonical_cache=cache,
            ),
            1,
        )

    def test_opening_repair_follows_recursive_augmenting_chain(self):
        records = np.zeros(5, dtype=miner.JNNW_DTYPE)
        for index in range(5):
            records[index]["wm"] = 1 << (index * 2)
            records[index]["bm"] = 1 << (index * 2 + 1)
        metadata = np.zeros(
            5,
            dtype=np.dtype([("game_id", "<u8"), ("opening_id", "<u8")]),
        )
        metadata["game_id"] = np.arange(20, 25, dtype=np.uint64)
        metadata["opening_id"] = [100, 100, 200, 200, 300]
        request_order = [(0, 0, 0, 1), (1, 0, 0, 1), (2, 0, 0, 1)]
        eligible = {
            (0, 0, 0): np.asarray([1], dtype=np.int64),
            (1, 0, 0): np.asarray([0, 3], dtype=np.int64),
            (2, 0, 0): np.asarray([2, 4], dtype=np.int64),
        }
        selected = {1: [0], 2: [2]}
        cache: dict[int, bytes] = {}
        owners, games, canonicals = miner._rebuild_target_selection_state(
            selected_by_request=selected,
            request_order=request_order,
            records=records,
            metadata=metadata,
            canonical_cache=cache,
        )
        repaired = miner._repair_blocked_request(
            request_index=0,
            required=1,
            selected_by_request=selected,
            request_order=request_order,
            eligible_by_bucket=eligible,
            records=records,
            metadata=metadata,
            opening_owner=owners,
            game_counts=games,
            canonical_used=canonicals,
            canonical_cache=cache,
            opening_masks={100: 0b011, 200: 0b110, 300: 0b100},
            seed=2026081806,
            salt=0,
        )
        self.assertIsNotNone(repaired)
        selection, owners, _games, _canonicals, transferred = repaired
        self.assertEqual(selection[1], [3])
        self.assertEqual(selection[2], [4])
        self.assertEqual(transferred, [100, 200])
        self.assertEqual(owners[100], miner.POOL_NAMES[miner.TARGET_COMPONENTS[0]])
        self.assertEqual(owners[200], miner.POOL_NAMES[miner.TARGET_COMPONENTS[1]])

    @unittest.skipUnless(importlib.util.find_spec("scipy"), "scipy unavailable")
    def test_exact_reallocation_solves_cross_pool_opening_chain(self):
        records = np.zeros(5, dtype=miner.JNNW_DTYPE)
        for index in range(5):
            records[index]["wm"] = 1 << (index * 2)
            records[index]["bm"] = 1 << (index * 2 + 1)
        metadata = np.zeros(
            5,
            dtype=np.dtype([("game_id", "<u8"), ("opening_id", "<u8")]),
        )
        metadata["game_id"] = np.arange(20, 25, dtype=np.uint64)
        metadata["opening_id"] = [100, 100, 200, 200, 300]
        request_order = [(0, 0, 0, 1), (1, 0, 0, 1), (2, 0, 0, 1)]
        eligible = {
            (0, 0, 0): np.asarray([1], dtype=np.int64),
            (1, 0, 0): np.asarray([0, 3], dtype=np.int64),
            (2, 0, 0): np.asarray([2, 4], dtype=np.int64),
        }
        selection, owners, games, canonicals, report = (
            miner._exact_reallocate_selected_requests(
                request_index=0,
                required=1,
                selected_by_request={1: [0], 2: [2]},
                request_order=request_order,
                eligible_by_bucket=eligible,
                records=records,
                metadata=metadata,
                opening_masks={100: 0b011, 200: 0b110, 300: 0b100},
                canonical_cache={},
                seed=2026081806,
                salt=0,
            )
        )
        self.assertEqual(selection[0], [1])
        self.assertEqual(selection[1], [3])
        self.assertEqual(selection[2], [4])
        self.assertLessEqual(max(games.values()), 2)
        self.assertEqual(len(canonicals), 3)
        self.assertEqual(report["status"], 0)
        self.assertEqual(owners[100], miner.POOL_NAMES[miner.TARGET_COMPONENTS[0]])

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
                "deterministic_recursive_repair_exact_milp_v7",
            )
            for row in payload["pools"].values():
                self.assertEqual(row["records"], 4)


if __name__ == "__main__":
    unittest.main()
