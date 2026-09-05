from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest
from unittest import mock

from jobs.tools import adaptive_sibling_b2_select as selector
from jobs.tools import adaptive_sibling_b2_teacher_merge as merger
from jobs.tools import adaptive_sibling_b2_teacher_source as teacher
from jobs.tools.adaptive_sibling_b2_exclusions import canonical_fingerprint, format_fingerprint


ROOT = Path(__file__).resolve().parents[2]


def descriptor(path: Path, **extra: object) -> dict[str, object]:
    return {
        "local_name": path.name,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "size_bytes": path.stat().st_size,
        **extra,
    }


def record(board: tuple[int, int, int, int, int]) -> bytes:
    return struct.pack("<QQQQB", *board) + b"\0" * 5


def make_report(shard: int, emitted: int = 500) -> dict[str, object]:
    return {
        "schema": teacher.SHARD_SCHEMA, "input_parents": 4000, "shard": shard,
        "nshards": 16, "book_enabled": False, "threads_per_search": 1,
        "fresh_tt_each_search": True, "fresh_engine_each_search": True,
        "engine_constructions": 3 * emitted, "jass_prefixed_environment_count": 0,
        "egdb_configuration_source": "explicit_positional_arguments",
        "egdb_required_available": True, "egdb_cache_mb": 256,
        "node_limit_mode": "exact", "cheap_budget_nodes": 5000,
        "screen_budget_nodes": 50000, "teacher_budget_nodes": 200000,
        "tt_mb": 16, "egdb_max_pieces": 6, "source_rows": 4000,
        "processed_parent_rows": 250, "invalid_rows": 0,
        "duplicate_move_entries": 0, "emitted_siblings": emitted,
        "rule_terminal_children": 0, "exact_tb_children": 0,
        "cheap_searches": emitted, "screen_searches": emitted,
        "teacher_searches": emitted, "cheap_nodes": emitted * 5000,
        "screen_nodes": emitted * 50000, "teacher_nodes": emitted * 200000,
        "teacher_scores_produced": True, "stable_pairs_selected": False,
        "fits": 0, "strength_games": 0, "promotion_authorized": False,
    }


class Fixture:
    def __init__(self, root: Path):
        self.root = root
        self.inputs = root / "inputs"
        self.outputs = root / "outputs"
        self.inputs.mkdir()
        self.outputs.mkdir()
        self.code_sha = "a" * 40
        self._make_static_files()
        self.parents = self._make_parents()
        self._make_shards()
        self._write_selection_report()
        self.write_manifest()

    def _copy(self, source: Path, name: str) -> Path:
        target = self.inputs / name
        shutil.copyfile(source, target)
        return target

    def _make_static_files(self) -> None:
        self.contract = self._copy(
            ROOT / "jobs/manifests/adaptive_sibling_b2_selection_contract_v1.json",
            "selection-contract.json",
        )
        self.base = self._copy(ROOT / "src/deep_sibling_teacher.cpp", "deep_sibling_teacher.cpp")
        self.adapter_tool = self._copy(
            ROOT / "jobs/tools/adaptive_sibling_b2_teacher_source.py", "adaptive_sibling_b2_teacher_source.py"
        )
        self.rendered = self.inputs / "adaptive-sibling-b2-teacher.cpp"
        self.adapter_receipt = self.inputs / "teacher-adapter-receipt.json"
        teacher.render_file(self.base, self.rendered, self.adapter_receipt)
        self.merge_tool = self._copy(Path(merger.__file__), "adaptive_sibling_b2_teacher_merge.py")
        self.verifier_source = self._copy(
            ROOT / "src/adaptive_sibling_b2_teacher_merge_verify.cpp",
            "adaptive_sibling_b2_teacher_merge_verify.cpp",
        )
        self.teacher_exe = self.inputs / "jass_adaptive_sibling_b2_teacher"
        self.teacher_exe.write_bytes(b"synthetic teacher executable fixture\n")
        self.verifier = self.inputs / "jass_adaptive_sibling_b2_teacher_merge_verify"
        self.verifier.write_bytes(b"synthetic native verifier stub; subprocess is mocked\n")
        if os.name != "nt":
            self.verifier.chmod(0o755)
        self.curriculum = self.inputs / "CURRICULUM.pjtw"
        self.curriculum.write_bytes(b"synthetic curriculum identity only\n")
        self.cmake_cache = self.inputs / "CMakeCache.txt"
        self.cmake_cache.write_text("CMAKE_BUILD_TYPE:STRING=Release\n", encoding="ascii")
        self.egdb_identity = self.inputs / "egdb-identity.json"
        self.egdb_identity.write_bytes(merger.canonical_json_bytes({"fixture": "no EGDB opened"}))

    def _board(self, pieces: int, stm: int, nonce: int) -> tuple[int, int, int, int, int]:
        pool = list(range(4, 50))
        ranked = sorted(pool, key=lambda square: hashlib.sha256(f"{pieces}:{stm}:{nonce}:{square}".encode()).digest())
        chosen = ranked[:pieces - 2]
        own_total = min(20, max(2, pieces // 2))
        own_extra = own_total - 2
        own = (1 << 0) | (1 << 1) | sum(1 << square for square in chosen[:own_extra])
        opponent = sum(1 << square for square in chosen[own_extra:])
        return (own, 0, opponent, 0, stm) if stm == 0 else (opponent, 0, own, 0, stm)

    def _make_parents(self) -> list[dict[str, object]]:
        candidates: list[dict[str, object]] = []
        seen: set[str] = set()
        phase_pieces = {"P0": 30, "P1": 20, "P2": 12, "P3": 9}
        for phase in selector.PHASES:
            for stm in (0, 1):
                accepted = 0
                nonce = 0
                while accepted < 500:
                    board = self._board(phase_pieces[phase], stm, nonce)
                    raw_fp = format_fingerprint(*board)
                    canonical = canonical_fingerprint(raw_fp)
                    nonce += 1
                    if canonical in seen:
                        continue
                    seen.add(canonical)
                    candidates.append({
                        "board": board, "raw_fingerprint": raw_fp,
                        "canonical_fingerprint": canonical, "parent_stm": stm,
                        "pieces": phase_pieces[phase], "legal_moves": 2, "phase": phase,
                        "source_shard": (nonce - 1) % 16, "source_row_index": nonce - 1,
                        "selection_hash": selector.selection_hash(canonical),
                    })
                    accepted += 1
        candidates.sort(key=lambda item: (bytes.fromhex(str(item["selection_hash"])), str(item["canonical_fingerprint"])))
        parent_jnnw = self.inputs / "parents.jnnw"
        parent_jnnw.write_bytes(
            b"JNNW" + struct.pack("<I", 4000) + b"".join(record(item["board"]) for item in candidates)
        )
        self.parents_jnnw = parent_jnnw
        self.parents_tsv = self.inputs / "parents.tsv"
        lines = ["\t".join(selector.OUTPUT_FIELDS)]
        for parent_id, item in enumerate(candidates):
            values = {
                "parent_id": parent_id, "canonical_fingerprint": item["canonical_fingerprint"],
                "raw_fingerprint": item["raw_fingerprint"], "parent_stm": item["parent_stm"],
                "pieces": item["pieces"], "legal_moves": 2, "phase": item["phase"],
                "source_shard": item["source_shard"], "source_row_index": item["source_row_index"],
                "selection_hash": item["selection_hash"],
            }
            lines.append("\t".join(str(values[field]) for field in selector.OUTPUT_FIELDS))
            item["parent_id"] = parent_id
        self.parents_tsv.write_text("\n".join(lines) + "\n", encoding="ascii", newline="")
        return candidates

    @staticmethod
    def _child(board: tuple[int, int, int, int, int], action: int) -> tuple[int, int, int, int, int]:
        wm, wk, bm, bk, stm = board
        from_bit = 1 << action
        to_bit = 1 << (action + 2)
        if stm == 0:
            wm = (wm & ~from_bit) | to_bit
        else:
            bm = (bm & ~from_bit) | to_bit
        return wm, wk, bm, bk, 1 - stm

    def _group(self, parent: dict[str, object], action: int, local: int) -> dict[str, str]:
        child = self._child(parent["board"], action)
        values: dict[str, object] = {
            "row_index": local, "parent_id": parent["parent_id"],
            "parent_fingerprint": parent["raw_fingerprint"], "parent_stm": parent["parent_stm"],
            "parent_pieces": parent["pieces"], "from": action + 1, "to": action + 3,
            "num_captures": 0, "promotes": 0, "moving_king": 0, "captured_kings": 0,
            "material_count_delta_parent": 0, "child_pieces": parent["pieces"],
            "child_legal_moves": 0, "child_forced_capture": 0, "child_rule_terminal": 0,
            "child_tb_exact": 0, "exact_parent_utility": 2,
            "t_baseline_parent": int(parent["parent_id"]) % 31 - 15,
            "q5k_parent": action * 10 + 1, "q50_parent": action * 10 + 2,
            "q200_parent": action * 10 + 3, "nodes5k": 5000, "nodes50k": 50000,
            "nodes200k": 200000, "completed_depth5k": 1, "completed_depth50k": 2,
            "completed_depth200k": 3, "effective_depth5k": 1, "effective_depth50k": 2,
            "effective_depth200k": 3, "aborted5k": 0, "aborted50k": 0,
            "aborted200k": 0, "stop5k": "nodes", "stop50k": "nodes",
            "stop200k": "nodes", "elapsed_us5k": 1, "elapsed_us50k": 2,
            "elapsed_us200k": 3, "pv5k_enters_egdb": 0, "pv50k_enters_egdb": 0,
            "pv200k_enters_egdb": 0,
        }
        self.child_board = child
        return {key: str(values[key]) for key in merger.GROUP_FIELDS}

    def _make_shards(self) -> None:
        self.shards: list[dict[str, object]] = []
        self.shard_paths: dict[str, list[Path]] = {"children": [], "groups": [], "report": []}
        for shard in range(16):
            children: list[bytes] = []
            groups: list[dict[str, str]] = []
            for parent in self.parents:
                if int(parent["parent_id"]) % 16 != shard:
                    continue
                for action in range(2):
                    local = len(children)
                    group = self._group(parent, action, local)
                    children.append(record(self.child_board))
                    groups.append(group)
            children_path = self.inputs / f"shard-{shard:02d}.children.jnnw"
            children_path.write_bytes(b"JNNW" + struct.pack("<I", len(children)) + b"".join(children))
            groups_path = self.inputs / f"shard-{shard:02d}.groups.tsv"
            groups_path.write_text(
                "\t".join(merger.GROUP_FIELDS) + "\n"
                + "".join("\t".join(row[field] for field in merger.GROUP_FIELDS) + "\n" for row in groups),
                encoding="ascii", newline="",
            )
            report_path = self.inputs / f"shard-{shard:02d}.report.json"
            report_path.write_bytes(teacher._json_bytes(make_report(shard, len(children))))
            item = {
                "children_jnnw": descriptor(children_path, records=len(children), record_size_bytes=38),
                "command_argv": [str(self.teacher_exe), str(self.parents_jnnw), str(children_path),
                    str(groups_path), str(report_path), str(self.curriculum), str(self.inputs / "egdb"),
                    str(shard), "16", "16", "256"],
                "exit_code": 0, "groups_tsv": descriptor(groups_path, rows=len(groups)),
                "report_json": descriptor(report_path), "report_schema": teacher.SHARD_SCHEMA,
                "shard": shard, "state": "completed",
            }
            self.shards.append(item)
            self.shard_paths["children"].append(children_path)
            self.shard_paths["groups"].append(groups_path)
            self.shard_paths["report"].append(report_path)

    def _write_selection_report(self) -> None:
        identities = "".join(f"{item['canonical_fingerprint']}\n" for item in self.parents).encode("ascii")
        self.identities_descriptor = {
            "sha256": hashlib.sha256(identities).hexdigest(), "size_bytes": len(identities),
            "rows": 4000, "serialization": "canonical_fingerprint_ascii, one per line, LF terminated",
        }
        contract_sha = hashlib.sha256(self.contract.read_bytes()).hexdigest()
        contract = json.loads(self.contract.read_text(encoding="ascii"))
        selected_by = {cell: 500 for cell in selector.CELL_ORDER}
        source_shards = []
        for shard in range(16):
            source_shards.append({
                "source_shard": shard, "seed": selector.SOURCE_SEED_BASE + shard,
                "producer_argv": ["jass", "--gen-data"], "producer_argv_sha256": "5" * 64,
                "raw_jnnw_sha256": f"{shard + 16:064x}",
                "filter_argv": ["parent-filter", str(shard)], "filter_argv_sha256": "6" * 64,
                "filtered_jnnw": {"local_name": f"source-{shard:02d}.filtered.jnnw", "sha256": "7" * 64, "size_bytes": 8},
                "filtered_meta": {"local_name": f"source-{shard:02d}.filtered.tsv", "sha256": "8" * 64, "size_bytes": 1},
                "filter_report": {"local_name": f"source-{shard:02d}.filter-report.json", "sha256": "9" * 64, "size_bytes": 1},
                "filter_counters": {"source_rows": 10000, "invalid_rows": 0,
                    "piece_eligible_rows": 500, "exact_duplicates": 0, "below_min_moves": 0,
                    "above_max_moves": 0, "duplicate_move_entries": 0, "selected_parents": 500},
            })
        report = {
            "schema": selector.SELECTION_REPORT_SCHEMA, "code_sha": self.code_sha,
            "selection_contract_sha256": contract_sha, "source_manifest_sha256": "1" * 64,
            "curriculum_sha256": hashlib.sha256(self.curriculum.read_bytes()).hexdigest(),
            "exclusion": {"receipt_sha256": "2" * 64,
                "manifest_sha256": contract["exclusion"]["manifest_sha256"],
                "union_sha256": contract["exclusion"]["union_sha256"],
                "union_unique_canonical": contract["exclusion"]["union_unique_canonical"]},
            "selection_seed": selector.SELECTION_SEED, "selection_hash_algorithm": "sha256",
            "selection_hash_payload": "{selection_seed_decimal}:{canonical_fingerprint}",
            "canonicalization": "min(exact,rotate180_plus_colour_swap_and_invert_stm)",
            "representative_order": ["raw_fingerprint_ascii", "source_shard_uint", "source_row_index_uint"],
            "final_order": ["selection_hash_bytes", "canonical_fingerprint_ascii"],
            "cell_order": selector.CELL_ORDER, "cell_quota": 500, "top_up": False,
            "source_shards": source_shards,
            "counters": {"filtered_occurrences": 8000, "historical_excluded_occurrences": 0,
                "exact_duplicate_occurrences_removed": 4000, "symmetry_duplicate_occurrences_removed": 0,
                "unique_canonical_after_exclusion": 4000},
            "support_before_sampling": selected_by, "selected_by_phase_stm": selected_by,
            "selected": 4000, "source_raw_records": 160000, "unique_selected_canonical": 4000,
            "forbidden_overlap": 0, "target_blind": True, "raw_source_jnnw_inputs": 0,
            "source_score_bytes_read": 0, "source_wdl_bytes_read": 0, "source_labels_read": 0,
            "output_target_nonzero_records": 0,
            "outputs": {"parents_jnnw": {key: value for key, value in descriptor(self.parents_jnnw, records=4000).items() if key != "local_name"},
                "parents_tsv": {key: value for key, value in descriptor(self.parents_tsv, rows=4000).items() if key != "local_name"},
                "ordered_identities": self.identities_descriptor},
            "fits": 0, "training": False, "calibration": False, "tuning": False,
            "model_selection": False, "strength_games": 0, "promotion_authorized": False,
        }
        self.selection_report = self.inputs / "selection-report.json"
        self.selection_report.write_bytes(merger.canonical_json_bytes(report))

    def manifest_value(self) -> dict[str, object]:
        return {
            "schema": merger.INPUT_SCHEMA, "code_sha": self.code_sha,
            "selection": {"cell_order": selector.CELL_ORDER, "cell_quota": 500,
                "contract": descriptor(self.contract), "forbidden_overlap": 0,
                "ordered_identities": self.identities_descriptor,
                "parents_jnnw": descriptor(self.parents_jnnw, records=4000, record_size_bytes=38),
                "parents_tsv": descriptor(self.parents_tsv, rows=4000),
                "report": descriptor(self.selection_report),
                "report_schema": selector.SELECTION_REPORT_SCHEMA, "selected": 4000, "target_blind": True},
            "adapter": {"base_source": descriptor(self.base),
                "base_source_normalized_sha256": teacher.BASE_SOURCE_NORMALIZED_SHA256,
                "receipt": descriptor(self.adapter_receipt), "receipt_schema": teacher.ADAPTER_SCHEMA,
                "rendered_source": descriptor(self.rendered), "tool": descriptor(self.adapter_tool)},
            "build": {"build_type": "Release", "cmake_cache": descriptor(self.cmake_cache),
                "cmake_options": ["-DCMAKE_BUILD_TYPE=Release", "-DJASSD=ON"],
                "compiler_id": "SyntheticCC", "compiler_version": "1",
                "merge_tool": descriptor(self.merge_tool), "teacher_executable": descriptor(self.teacher_exe),
                "verifier_executable": descriptor(self.verifier), "verifier_source": descriptor(self.verifier_source)},
            "teacher_runtime": {"curriculum": descriptor(self.curriculum),
                "egdb": {"cache_mb": 256, "directory_local_name": "egdb",
                    "identity_manifest": descriptor(self.egdb_identity), "max_pieces": 6},
                "jass_prefixed_environment": [], "node_limit_mode": "exact",
                "threads_per_search": 1, "tt_mb": 16},
            "shards": self.shards,
        }

    def write_manifest(self) -> None:
        self.manifest = self.inputs / "teacher-merge-inputs.json"
        self.manifest.write_bytes(merger.canonical_json_bytes(self.manifest_value()))

    def args(self) -> argparse.Namespace:
        return argparse.Namespace(
            input_manifest=self.manifest,
            expected_input_manifest_sha256=hashlib.sha256(self.manifest.read_bytes()).hexdigest(),
            selection_report=self.selection_report,
            expected_selection_report_sha256=hashlib.sha256(self.selection_report.read_bytes()).hexdigest(),
            parents_jnnw=self.parents_jnnw, parents_tsv=self.parents_tsv,
            shard_children=list(reversed(self.shard_paths["children"])),
            shard_groups=self.shard_paths["groups"][3:] + self.shard_paths["groups"][:3],
            shard_report=list(reversed(self.shard_paths["report"])), legal_verifier=self.verifier,
            out_children=self.outputs / "children.jnnw", out_groups=self.outputs / "groups.tsv",
            out_semantic_actions=self.outputs / "semantic-actions.jsonl",
            report=self.outputs / "teacher-merge-report.json",
        )

    def install_real_native_catalogues(self, helper: Path, verifier: Path) -> None:
        """Replace the structural stub payload with real movegen fixture bytes."""
        pool_rows: list[bytes] = []
        for phase, pieces in (("P0", 30), ("P1", 20), ("P2", 12), ("P3", 9)):
            del phase
            for stm in (0, 1):
                for nonce in range(1_500):
                    pool_rows.append(record(self._board(pieces, stm, nonce + 200_000)))
        pool = self.root / "native-pool.jnnw"
        pool.write_bytes(b"JNNW" + struct.pack("<I", len(pool_rows)) + b"".join(pool_rows))
        catalog = self.root / "native-catalog.tsv"
        subprocess.run([str(helper), "catalog", str(pool), str(catalog)], check=True)
        lines = catalog.read_text(encoding="ascii").splitlines()
        expected_catalog = ["pool_row_index", "parent_fingerprint", "parent_stm", "pieces", "legal_semantic_moves"]
        if not lines or lines[0].split("\t") != expected_catalog:
            raise AssertionError("native catalog header drift")
        candidates: list[selector.Candidate] = []
        for line in lines[1:]:
            values = line.split("\t")
            if len(values) != len(expected_catalog):
                raise AssertionError("native catalog width drift")
            row = dict(zip(expected_catalog, values))
            pool_index = int(row["pool_row_index"])
            raw_record = pool_rows[pool_index]
            wm, wk, bm, bk, stm = struct.unpack_from("<QQQQB", raw_record)
            raw_fp = format_fingerprint(wm, wk, bm, bk, stm)
            if row["parent_fingerprint"] != raw_fp or int(row["parent_stm"]) != stm:
                raise AssertionError("native catalog parent identity drift")
            pieces = int(row["pieces"])
            legal = int(row["legal_semantic_moves"])
            canonical = canonical_fingerprint(raw_fp)
            candidates.append(selector.Candidate(
                canonical=canonical, raw_fingerprint=raw_fp, record=raw_record, stm=stm,
                pieces=pieces, legal_moves=legal, phase=selector.phase_for(pieces),
                source_shard=pool_index % 16, source_row_index=pool_index // 16,
                selection_hash=selector.selection_hash(canonical),
            ))
        selected, _selection_receipt = selector.select_candidates(candidates, set())
        selector._write_jnnw(self.parents_jnnw, selected)
        selector._write_tsv(self.parents_tsv, selected)
        selector._verify_outputs(self.parents_jnnw, self.parents_tsv, selected)
        self.parents = []
        for parent_id, candidate in enumerate(selected):
            board = struct.unpack_from("<QQQQB", candidate.record)
            self.parents.append({
                "board": board, "raw_fingerprint": candidate.raw_fingerprint,
                "canonical_fingerprint": candidate.canonical, "parent_stm": candidate.stm,
                "pieces": candidate.pieces, "legal_moves": candidate.legal_moves,
                "phase": candidate.phase, "source_shard": candidate.source_shard,
                "source_row_index": candidate.source_row_index,
                "selection_hash": candidate.selection_hash, "parent_id": parent_id,
            })
        shutil.copyfile(verifier, self.verifier)
        if os.name != "nt":
            self.verifier.chmod(0o755)
        native_dir = self.root / "native-export"
        native_dir.mkdir()
        subprocess.run([str(helper), "export", str(self.parents_jnnw), str(native_dir)], check=True)
        action_fields = [
            "local_row_index", "parent_id", "parent_fingerprint", "parent_stm",
            "parent_pieces", "from", "to", "num_captures", "promotes",
            "moving_king", "captured_kings", "captured_square_bitboard",
            "material_count_delta_parent", "child_fingerprint", "child_pieces",
        ]
        self.shards = []
        self.shard_paths = {"children": [], "groups": [], "report": []}
        for shard in range(16):
            exported_children = native_dir / f"shard-{shard:02d}.children.jnnw"
            exported_actions = native_dir / f"shard-{shard:02d}.actions.tsv"
            children_path = self.inputs / f"shard-{shard:02d}.children.jnnw"
            shutil.copyfile(exported_children, children_path)
            action_lines = exported_actions.read_text(encoding="ascii").splitlines()
            if not action_lines or action_lines[0].split("\t") != action_fields:
                raise AssertionError("native action fixture header drift")
            groups: list[dict[str, str]] = []
            for line in action_lines[1:]:
                values = line.split("\t")
                if len(values) != len(action_fields):
                    raise AssertionError("native action fixture width drift")
                action = dict(zip(action_fields, values))
                parent_id = int(action["parent_id"])
                parent = self.parents[parent_id]
                group_values: dict[str, object] = {
                    "row_index": action["local_row_index"], "parent_id": parent_id,
                    "parent_fingerprint": action["parent_fingerprint"],
                    "parent_stm": action["parent_stm"], "parent_pieces": action["parent_pieces"],
                    "from": action["from"], "to": action["to"],
                    "num_captures": action["num_captures"], "promotes": action["promotes"],
                    "moving_king": action["moving_king"], "captured_kings": action["captured_kings"],
                    "material_count_delta_parent": action["material_count_delta_parent"],
                    "child_pieces": action["child_pieces"], "child_legal_moves": 0,
                    "child_forced_capture": 0, "child_rule_terminal": 0, "child_tb_exact": 0,
                    "exact_parent_utility": 2, "t_baseline_parent": parent_id % 31 - 15,
                    "q5k_parent": 1, "q50_parent": 2, "q200_parent": 3,
                    "nodes5k": 5000, "nodes50k": 50000, "nodes200k": 200000,
                    "completed_depth5k": 1, "completed_depth50k": 2,
                    "completed_depth200k": 3, "effective_depth5k": 1,
                    "effective_depth50k": 2, "effective_depth200k": 3,
                    "aborted5k": 0, "aborted50k": 0, "aborted200k": 0,
                    "stop5k": "nodes", "stop50k": "nodes", "stop200k": "nodes",
                    "elapsed_us5k": 1, "elapsed_us50k": 2, "elapsed_us200k": 3,
                    "pv5k_enters_egdb": 0, "pv50k_enters_egdb": 0,
                    "pv200k_enters_egdb": 0,
                }
                groups.append({key: str(group_values[key]) for key in merger.GROUP_FIELDS})
            groups_path = self.inputs / f"shard-{shard:02d}.groups.tsv"
            groups_path.write_text(
                "\t".join(merger.GROUP_FIELDS) + "\n"
                + "".join("\t".join(row[field] for field in merger.GROUP_FIELDS) + "\n" for row in groups),
                encoding="ascii", newline="",
            )
            report_path = self.inputs / f"shard-{shard:02d}.report.json"
            report_path.write_bytes(teacher._json_bytes(make_report(shard, len(groups))))
            item = {
                "children_jnnw": descriptor(children_path, records=len(groups), record_size_bytes=38),
                "command_argv": [str(self.teacher_exe), str(self.parents_jnnw), str(children_path),
                    str(groups_path), str(report_path), str(self.curriculum), str(self.inputs / "egdb"),
                    str(shard), "16", "16", "256"],
                "exit_code": 0, "groups_tsv": descriptor(groups_path, rows=len(groups)),
                "report_json": descriptor(report_path), "report_schema": teacher.SHARD_SCHEMA,
                "shard": shard, "state": "completed",
            }
            self.shards.append(item)
            self.shard_paths["children"].append(children_path)
            self.shard_paths["groups"].append(groups_path)
            self.shard_paths["report"].append(report_path)
        self._write_selection_report()
        self.write_manifest()


def fake_native(completed_receipt_tamper: str | None = None):
    def invoke(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[bytes]:
        values = {command[index]: command[index + 1] for index in range(2, len(command), 2)}
        expected_flags = {
            "--parents-jnnw", "--children-jnnw", "--semantic-actions",
            "--verifier-executable", "--expected-parents-sha256",
            "--expected-children-sha256", "--expected-semantic-actions-sha256",
            "--expected-verifier-executable-sha256", "--code-sha",
            "--verifier-source-sha256", "--cmake-cache-sha256", "--build-type",
            "--compiler-id", "--compiler-version", "--receipt",
        }
        if command[1] != "verify" or set(values) != expected_flags or len(command) != 32:
            raise AssertionError(f"native verifier CLI drift: {command!r}")
        parents = Path(values["--parents-jnnw"])
        children = Path(values["--children-jnnw"])
        semantic = Path(values["--semantic-actions"])
        executable = Path(values["--verifier-executable"])
        n = struct.unpack_from("<I", children.read_bytes(), 4)[0]
        receipt = {
            "actions_verified": n,
            "build_provenance_declared": {"build_type": values["--build-type"],
                "cmake_cache_sha256": values["--cmake-cache-sha256"], "code_sha": values["--code-sha"],
                "compiler_id": values["--compiler-id"], "compiler_version": values["--compiler-version"],
                "verifier_source_sha256": values["--verifier-source-sha256"]},
            "catalogue_actions_generated": n, "catalogues_verified": 4000,
            "children": descriptor(children, records=n, record_size_bytes=38),
            "duplicate_semantic_actions": 0, "executable": descriptor(executable),
            "extra_actions": 0, "forbidden_reordering": 0,
            "identity_order": ["from", "to", "captured_square_bitboard_uint64", "promotes"],
            "identity_tuple": ["from", "to", "num_captures", "promotes", "captured_square_bitboard"],
            "missing_actions": 0, "nonzero_child_targets": 0, "nonzero_parent_targets": 0,
            "parent_after_matches": n, "parent_count_matches": 4000,
            "parents": descriptor(parents, records=4000, record_size_bytes=38),
            "parents_verified": 4000, "schema": merger.NATIVE_SCHEMA,
            "semantic_actions": descriptor(semantic, rows=n, row_schema=merger.SEMANTIC_SCHEMA),
            "semantic_rows_verified": n, "verification_complete": True,
        }
        if completed_receipt_tamper:
            receipt[completed_receipt_tamper] = 1
        Path(values["--receipt"]).write_bytes(merger.canonical_json_bytes(receipt))
        return subprocess.CompletedProcess(command, 0, b"", b"")
    return invoke


class TeacherMergeTests(unittest.TestCase):
    def test_full_16_shard_4000_parent_merge_and_rebase(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = Fixture(Path(temporary))
            args = fixture.args()
            with mock.patch.object(merger.subprocess, "run", side_effect=fake_native()) as called:
                report = merger.run(args)
            self.assertEqual(called.call_count, 1)
            self.assertEqual(report["counters"]["parents"], 4000)
            self.assertEqual(report["counters"]["semantic_actions"], 8000)
            self.assertEqual(set(report["outputs"]), {"children_jnnw", "groups_tsv", "semantic_actions"})
            self.assertNotIn("report", report["outputs"])
            groups = args.out_groups.read_text(encoding="ascii").splitlines()
            self.assertEqual(len(groups), 8001)
            for index, line in enumerate(groups[1:]):
                fields = line.split("\t")
                self.assertEqual(int(fields[0]), index)
                self.assertEqual(int(fields[1]), index // 2)
            semantics = [json.loads(line) for line in args.out_semantic_actions.read_text(encoding="ascii").splitlines()]
            self.assertEqual([row["global_row_index"] for row in semantics], list(range(8000)))
            self.assertEqual([row["local_row_index"] for row in semantics[:4]], [0, 1, 0, 1])
            self.assertFalse((fixture.outputs / "native-verification-receipt.json.tmp").exists())

    def test_score_mutation_cannot_change_inclusion_order_or_semantic_ledger(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = Fixture(Path(temporary))
            args = fixture.args()
            with mock.patch.object(merger.subprocess, "run", side_effect=fake_native()):
                merger.run(args)
            children_before = args.out_children.read_bytes()
            semantic_before = args.out_semantic_actions.read_bytes()
            for path in (args.out_children, args.out_groups, args.out_semantic_actions, args.report):
                path.unlink()
            groups = fixture.shard_paths["groups"][0]
            raw = groups.read_text(encoding="ascii")
            raw = raw.replace("\t1\t2\t3\t5000\t", "\t-2147483648\t2147483647\t-7\t5000\t", 1)
            groups.write_text(raw, encoding="ascii", newline="")
            fixture.shards[0]["groups_tsv"] = descriptor(groups, rows=500)
            fixture.write_manifest()
            args.expected_input_manifest_sha256 = hashlib.sha256(fixture.manifest.read_bytes()).hexdigest()
            with mock.patch.object(merger.subprocess, "run", side_effect=fake_native()):
                merger.run(args)
            self.assertEqual(args.out_children.read_bytes(), children_before)
            self.assertEqual(args.out_semantic_actions.read_bytes(), semantic_before)

    def test_parent_block_drift_fails_before_native_and_publishes_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = Fixture(Path(temporary))
            groups = fixture.shard_paths["groups"][0]
            lines = groups.read_text(encoding="ascii").splitlines()
            fields = lines[1].split("\t")
            fields[1] = "16"
            lines[1] = "\t".join(fields)
            groups.write_text("\n".join(lines) + "\n", encoding="ascii", newline="")
            fixture.shards[0]["groups_tsv"] = descriptor(groups, rows=500)
            fixture.write_manifest()
            args = fixture.args()
            with mock.patch.object(merger.subprocess, "run", side_effect=AssertionError("native invoked")):
                with self.assertRaisesRegex(merger.MergeError, "parent blocks"):
                    merger.run(args)
            self.assertEqual(list(fixture.outputs.iterdir()), [])

    def test_nonzero_child_target_and_unknown_stop_fail_closed(self) -> None:
        for corruption in ("target", "stop"):
            with self.subTest(corruption=corruption), tempfile.TemporaryDirectory() as temporary:
                fixture = Fixture(Path(temporary))
                if corruption == "target":
                    path = fixture.shard_paths["children"][0]
                    raw = bytearray(path.read_bytes())
                    raw[8 + 33] = 1
                    path.write_bytes(raw)
                    fixture.shards[0]["children_jnnw"] = descriptor(path, records=500, record_size_bytes=38)
                else:
                    path = fixture.shard_paths["groups"][0]
                    raw = path.read_text(encoding="ascii").replace("\tnodes\tnodes\tnodes\t", "\tnonsense\tnodes\tnodes\t", 1)
                    path.write_text(raw, encoding="ascii", newline="")
                    fixture.shards[0]["groups_tsv"] = descriptor(path, rows=500)
                fixture.write_manifest()
                with self.assertRaises(merger.MergeError):
                    merger.run(fixture.args())
                self.assertEqual(list(fixture.outputs.iterdir()), [])

    def test_alias_existing_output_and_native_receipt_tamper_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = Fixture(Path(temporary))
            args = fixture.args()
            args.out_children = fixture.parents_jnnw
            with self.assertRaisesRegex(merger.MergeError, "alias"):
                merger.run(args)
        with tempfile.TemporaryDirectory() as temporary:
            fixture = Fixture(Path(temporary))
            args = fixture.args()
            with mock.patch.object(merger.subprocess, "run", side_effect=fake_native("missing_actions")):
                with self.assertRaisesRegex(merger.MergeError, "missing_actions"):
                    merger.run(args)
            self.assertEqual(list(fixture.outputs.iterdir()), [])

    def test_bool_integer_constants_and_dangling_output_symlink_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = Fixture(Path(temporary))
            base = fixture.manifest_value()
            for path, value in ((["selection", "forbidden_overlap"], False),
                                (["teacher_runtime", "threads_per_search"], True)):
                mutated = copy.deepcopy(base)
                mutated[path[0]][path[1]] = value
                fixture.manifest.write_bytes(merger.canonical_json_bytes(mutated))
                with self.assertRaises(merger.MergeError):
                    merger.run(fixture.args())
            if hasattr(os, "symlink"):
                fixture.write_manifest()
                args = fixture.args()
                try:
                    os.symlink(fixture.outputs / "absent-target", args.out_children)
                except OSError:
                    pass
                else:
                    with self.assertRaisesRegex(merger.MergeError, "existing output/temporary"):
                        merger.run(args)

    def test_actual_parent_cells_are_recounted_against_declared_balanced_report(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = Fixture(Path(temporary))
            victim = next(index for index, item in enumerate(fixture.parents)
                          if item["phase"] == "P0" and item["parent_stm"] == 0)
            seen = {str(item["canonical_fingerprint"]) for item in fixture.parents}
            nonce = 100_000
            while True:
                board = fixture._board(20, 0, nonce)
                raw_fp = format_fingerprint(*board)
                canonical = canonical_fingerprint(raw_fp)
                nonce += 1
                if canonical not in seen:
                    break
            item = fixture.parents[victim]
            item.update({"board": board, "raw_fingerprint": raw_fp,
                "canonical_fingerprint": canonical, "pieces": 20, "phase": "P1",
                "selection_hash": selector.selection_hash(canonical)})
            fixture.parents.sort(key=lambda row: (bytes.fromhex(str(row["selection_hash"])), str(row["canonical_fingerprint"])))
            fixture.parents_jnnw.write_bytes(
                b"JNNW" + struct.pack("<I", 4000)
                + b"".join(record(row["board"]) for row in fixture.parents)
            )
            lines = ["\t".join(selector.OUTPUT_FIELDS)]
            for parent_id, row in enumerate(fixture.parents):
                row["parent_id"] = parent_id
                values = {"parent_id": parent_id, "canonical_fingerprint": row["canonical_fingerprint"],
                    "raw_fingerprint": row["raw_fingerprint"], "parent_stm": row["parent_stm"],
                    "pieces": row["pieces"], "legal_moves": 2, "phase": row["phase"],
                    "source_shard": row["source_shard"], "source_row_index": row["source_row_index"],
                    "selection_hash": row["selection_hash"]}
                lines.append("\t".join(str(values[field]) for field in selector.OUTPUT_FIELDS))
            fixture.parents_tsv.write_text("\n".join(lines) + "\n", encoding="ascii", newline="")
            fixture._write_selection_report()  # deliberately still declares 500 in every cell
            fixture.write_manifest()
            with self.assertRaisesRegex(merger.MergeError, "cell counts"):
                merger.run(fixture.args())

    def test_selection_exclusion_hashes_must_match_sealed_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = Fixture(Path(temporary))
            report = json.loads(fixture.selection_report.read_text(encoding="ascii"))
            report["exclusion"]["union_sha256"] = "f" * 64
            fixture.selection_report.write_bytes(merger.canonical_json_bytes(report))
            fixture.write_manifest()
            with self.assertRaisesRegex(merger.MergeError, "exclusion provenance"):
                merger.run(fixture.args())

    def test_native_production_fixture_integration_when_explicitly_available(self) -> None:
        helper = os.environ.get("JASS_B2_NATIVE_FIXTURE_HELPER")
        verifier = os.environ.get("JASS_B2_NATIVE_VERIFIER")
        if not helper or not verifier:
            self.skipTest("real native catalogue helper/verifier not supplied")
        with tempfile.TemporaryDirectory() as temporary:
            fixture = Fixture(Path(temporary))
            fixture.install_real_native_catalogues(Path(helper), Path(verifier))
            report = merger.run(fixture.args())
            self.assertEqual(report["counters"]["parents"], 4000)
            self.assertGreaterEqual(report["counters"]["semantic_actions"], 8000)
            self.assertLessEqual(report["counters"]["semantic_actions"], 64000)
            self.assertTrue(report["native_verification"]["receipt"]["verification_complete"])


if __name__ == "__main__":
    unittest.main()
