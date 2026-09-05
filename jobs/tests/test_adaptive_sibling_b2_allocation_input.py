import hashlib
import json
import os
import random
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from jobs.tools import adaptive_sibling_b2_allocation_input as allocation
from jobs.tools import adaptive_sibling_b2_exclusions as exclusions
from jobs.tools import adaptive_sibling_b2_projection as projection


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "jobs/tools/adaptive_sibling_b2_allocation_input.py"
PROJECTION_TOOL = ROOT / "jobs/tools/adaptive_sibling_b2_projection.py"
CODE_SHA = "1" * 40


def json_bytes(value):
    return allocation.canonical_json_bytes(value)


def write_json(path, value):
    raw = json_bytes(value)
    path.write_bytes(raw)
    return raw


def descriptor(path, **extra):
    raw = path.read_bytes()
    return {
        "local_name": path.name,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "size_bytes": len(raw),
        **extra,
    }


def fingerprint_from_seed(seed, pieces, stm, used):
    nonce = 0
    while True:
        rng = random.Random((seed << 8) + nonce)
        squares = rng.sample(range(50), pieces)
        split = pieces // 2
        wm = sum(1 << square for square in squares[:split])
        bm = sum(1 << square for square in squares[split:])
        raw = f"{wm:013x}:{0:013x}:{bm:013x}:{0:013x}:{stm}"
        canonical = exclusions.canonical_fingerprint(raw)
        if raw not in used[0] and canonical not in used[1]:
            used[0].add(raw)
            used[1].add(canonical)
            return raw, canonical
        nonce += 1


def build_fixture(base, *, q200_token="POISON_Q200_A", bad_terminal=False,
                  bad_nodes200=False, bad_native=False):
    base.mkdir()
    (base / "preregistration.md").write_text("# Future preregistration fixture\n", encoding="utf-8")
    shutil.copyfile(TOOL, base / "allocation-input-tool.py")
    shutil.copyfile(PROJECTION_TOOL, base / "projection-tool.py")
    (base / "teacher-merge-inputs.json").write_bytes(json_bytes({"fixture": True}))
    (base / "selection-contract.json").write_bytes(json_bytes({"fixture": True}))
    for name in ("cmake-cache.txt", "merge-tool.py", "teacher-executable",
                 "verifier", "verifier-source.cpp"):
        (base / name).write_bytes((name + "\n").encode("ascii"))
    (base / "parents.jnnw").write_bytes(
        b"JNNW" + struct.pack("<I", allocation.PARENT_COUNT)
        + b"\0" * (38 * allocation.PARENT_COUNT)
    )

    parents = []
    used = (set(), set())
    parent_lines = ["\t".join(allocation.SELECTION_FIELDS)]
    identity_lines = []
    for phase_index, (phase, (low, _high)) in enumerate(allocation.PHASE_BOUNDS.items()):
        for stm in (0, 1):
            for local in range(allocation.CELL_QUOTA):
                parent_id = len(parents)
                raw, canonical = fingerprint_from_seed(
                    100_000 * phase_index + 10_000 * stm + local, low, stm, used)
                parent = {
                    "parent_id": parent_id, "canonical": canonical, "raw": raw,
                    "stm": stm, "pieces": low, "legal_moves": 2, "phase": phase,
                    "source_shard": parent_id % 16, "source_row_index": parent_id,
                    "selection_hash": hashlib.sha256(f"selection:{parent_id}".encode()).hexdigest(),
                }
                parents.append(parent)
                parent_lines.append("\t".join(str(parent[key]) for key in (
                    "parent_id", "canonical", "raw", "stm", "pieces", "legal_moves",
                    "phase", "source_shard", "source_row_index", "selection_hash",
                )))
                identity_lines.append(canonical)
    (base / "parents.tsv").write_bytes(("\n".join(parent_lines) + "\n").encode("ascii"))
    (base / "ordered-identities.txt").write_bytes(
        ("\n".join(identity_lines) + "\n").encode("ascii"))

    parents_jnnw = descriptor(
        base / "parents.jnnw", records=allocation.PARENT_COUNT, record_size_bytes=38)
    parents_tsv = descriptor(base / "parents.tsv", rows=allocation.PARENT_COUNT)
    selection_contract = descriptor(base / "selection-contract.json")
    ordered = descriptor(
        base / "ordered-identities.txt", rows=allocation.PARENT_COUNT,
        serialization="canonical_fingerprint_ascii, one per line, LF terminated")
    selection_report = {
        "schema": allocation.SELECTION_SCHEMA,
        "code_sha": CODE_SHA,
        "selection_contract_sha256": selection_contract["sha256"],
        "source_manifest_sha256": "3" * 64,
        "curriculum_sha256": "4" * 64,
        "exclusion": {},
        "selection_seed": 2026110716,
        "selection_hash_algorithm": "sha256",
        "selection_hash_payload": "{selection_seed_decimal}:{canonical_fingerprint}",
        "canonicalization": "fixture",
        "representative_order": [],
        "final_order": [],
        "cell_order": list(allocation.CELL_ORDER),
        "cell_quota": allocation.CELL_QUOTA,
        "top_up": False,
        "source_shards": [],
        "counters": {},
        "support_before_sampling": {},
        "selected_by_phase_stm": {cell: allocation.CELL_QUOTA for cell in allocation.CELL_ORDER},
        "selected": allocation.PARENT_COUNT,
        "source_raw_records": 0,
        "unique_selected_canonical": allocation.PARENT_COUNT,
        "forbidden_overlap": 0,
        "target_blind": True,
        "raw_source_jnnw_inputs": 0,
        "source_score_bytes_read": 0,
        "source_wdl_bytes_read": 0,
        "source_labels_read": 0,
        "output_target_nonzero_records": 0,
        "outputs": {
            "parents_jnnw": {
                key: parents_jnnw[key] for key in ("sha256", "size_bytes", "records")},
            "parents_tsv": {
                key: parents_tsv[key] for key in ("sha256", "size_bytes", "rows")},
            "ordered_identities": {
                key: ordered[key] for key in ("sha256", "size_bytes", "rows", "serialization")},
        },
        "fits": 0,
        "training": False,
        "calibration": False,
        "tuning": False,
        "model_selection": False,
        "strength_games": 0,
        "promotion_authorized": False,
    }
    write_json(base / "selection-report.json", selection_report)

    group_lines = ["\t".join(allocation.GROUP_FIELDS)]
    semantic_raws = []
    shard_local = [0] * 16
    row_index = 0
    for parent in parents:
        for action_index in range(2):
            terminal = row_index == 0
            utility = -1 if terminal and bad_terminal else 1 if terminal else 2
            values = {
                "row_index": str(row_index), "parent_id": str(parent["parent_id"]),
                "parent_fingerprint": parent["raw"], "parent_stm": str(parent["stm"]),
                "parent_pieces": str(parent["pieces"]),
                "from": str(1 + 2 * action_index), "to": str(2 + 2 * action_index),
                "num_captures": "0", "promotes": "0", "moving_king": "0",
                "captured_kings": "0", "material_count_delta_parent": "0",
                "child_pieces": str(parent["pieces"]), "child_legal_moves": "2",
                "child_forced_capture": "0", "child_rule_terminal": str(int(terminal)),
                "child_tb_exact": "0", "exact_parent_utility": str(utility),
                "t_baseline_parent": "IGNORED_LABEL", "q5k_parent": str(100-action_index),
                "q50_parent": str(50-action_index), "q200_parent": q200_token,
                "nodes5k": "1", "nodes50k": "2",
                "nodes200k": "200001" if bad_nodes200 and row_index == 0 else "3",
                "completed_depth5k": "1", "completed_depth50k": "2",
                "completed_depth200k": "POISON_DEPTH200", "effective_depth5k": "1",
                "effective_depth50k": "2", "effective_depth200k": "POISON_EFFECTIVE200",
                "aborted5k": "0", "aborted50k": "0", "aborted200k": "POISON_ABORTED200",
                "stop5k": "none", "stop50k": "none", "stop200k": "POISON_STOP200",
                "elapsed_us5k": "1", "elapsed_us50k": "2",
                "elapsed_us200k": "POISON_ELAPSED200", "pv5k_enters_egdb": "0",
                "pv50k_enters_egdb": "0", "pv200k_enters_egdb": "POISON_PV200",
            }
            group_lines.append("\t".join(values[name] for name in allocation.GROUP_FIELDS))
            shard = parent["parent_id"] % 16
            semantic = {
                "captured_kings": 0, "captured_square_bitboard": 0,
                "child_fingerprint": parent["raw"], "child_pieces": parent["pieces"],
                "from": 1 + 2 * action_index, "global_row_index": row_index,
                "local_row_index": shard_local[shard], "material_count_delta_parent": 0,
                "num_captures": 0, "parent_fingerprint": parent["raw"],
                "parent_id": parent["parent_id"], "parent_legal_moves": 2,
                "parent_pieces": parent["pieces"], "promotes": False,
                "schema": allocation.SEMANTIC_SCHEMA, "source_shard": shard,
                "to": 2 + 2 * action_index,
            }
            semantic_raws.append(json_bytes(semantic))
            shard_local[shard] += 1
            row_index += 1
    (base / "groups.tsv").write_bytes(("\n".join(group_lines) + "\n").encode("ascii"))
    (base / "semantic-actions.jsonl").write_bytes(b"".join(semantic_raws))
    (base / "children.jnnw").write_bytes(
        b"JNNW" + struct.pack("<I", row_index) + b"\0" * (38 * row_index))

    children = descriptor(base / "children.jnnw", records=row_index, record_size_bytes=38)
    groups = descriptor(base / "groups.tsv", rows=row_index)
    semantic_desc = descriptor(
        base / "semantic-actions.jsonl", rows=row_index,
        row_schema=allocation.SEMANTIC_SCHEMA)
    build = {
        "build_type": "Release",
        "cmake_cache": descriptor(base / "cmake-cache.txt"),
        "cmake_options": ["-DJASS_NATIVE=OFF"],
        "compiler_id": "fixture-cxx",
        "compiler_version": "1",
        "merge_tool": descriptor(base / "merge-tool.py"),
        "teacher_executable": descriptor(base / "teacher-executable"),
        "verifier_executable": descriptor(base / "verifier"),
        "verifier_source": descriptor(base / "verifier-source.cpp"),
    }
    native_children = dict(children)
    if bad_native:
        native_children["size_bytes"] += 1
    native = {
        "actions_verified": row_index,
        "build_provenance_declared": {
            "build_type": build["build_type"],
            "cmake_cache_sha256": build["cmake_cache"]["sha256"],
            "code_sha": CODE_SHA,
            "compiler_id": build["compiler_id"],
            "compiler_version": build["compiler_version"],
            "verifier_source_sha256": build["verifier_source"]["sha256"],
        },
        "catalogue_actions_generated": row_index,
        "catalogues_verified": allocation.PARENT_COUNT,
        "children": native_children,
        "duplicate_semantic_actions": 0,
        "executable": build["verifier_executable"],
        "extra_actions": 0,
        "forbidden_reordering": 0,
        "identity_order": ["from", "to", "captured_square_bitboard_uint64", "promotes"],
        "identity_tuple": ["from", "to", "num_captures", "promotes", "captured_square_bitboard"],
        "missing_actions": 0,
        "nonzero_child_targets": 0,
        "nonzero_parent_targets": 0,
        "parent_after_matches": row_index,
        "parent_count_matches": allocation.PARENT_COUNT,
        "parents": parents_jnnw,
        "parents_verified": allocation.PARENT_COUNT,
        "schema": allocation.NATIVE_SCHEMA,
        "semantic_actions": semantic_desc,
        "semantic_rows_verified": row_index,
        "verification_complete": True,
    }
    native_raw = write_json(base / "native-verification-receipt.json", native)

    teacher_input = descriptor(base / "teacher-merge-inputs.json")
    selection_desc = descriptor(base / "selection-report.json")
    merge_report = {
        "adapter": {}, "aggregate": {}, "build": build, "code_sha": CODE_SHA,
        "counters": {
            "captured_bitboards_reconstructed": row_index,
            "children_records": row_index, "duplicate_path_entries": 0,
            "duplicate_semantic_actions": 0, "extra_actions": 0,
            "forbidden_reordering": 0, "full_catalogues_verified": allocation.PARENT_COUNT,
            "global_rows_rebased": row_index, "groups_rows": row_index,
            "missing_actions": 0, "nonzero_child_targets": 0,
            "parent_child_transitions_verified": row_index,
            "parents": allocation.PARENT_COUNT,
            "parents_with_legal_count_match": allocation.PARENT_COUNT,
            "processed_parent_rows": allocation.PARENT_COUNT,
            "semantic_actions": row_index, "semantic_ledger_rows": row_index,
            "shards": 16,
        },
        "identity_order": ["from", "to", "captured_square_bitboard_uint64", "promotes"],
        "identity_tuple": ["from", "to", "num_captures", "promotes", "captured_square_bitboard"],
        "input_manifest": teacher_input,
        "native_verification": {
            "receipt": native, "sha256": hashlib.sha256(native_raw).hexdigest(),
            "size_bytes": len(native_raw),
        },
        "outputs": {"children_jnnw": children, "groups_tsv": groups,
                    "semantic_actions": semantic_desc},
        "scientific_scope": {
            "calibration": False, "fits": 0, "model_selection": False,
            "promotion_authorized": False, "strength_games": 0,
            "training": False, "tuning": False,
        },
        "schema": allocation.MERGE_SCHEMA,
        "selection": {
            "contract": selection_contract,
            "ordered_identities": {
                key: ordered[key] for key in ("sha256", "size_bytes", "rows", "serialization")},
            "parents_jnnw": parents_jnnw, "parents_tsv": parents_tsv,
            "report": selection_desc,
        },
        "shards": [], "teacher_runtime": {},
    }
    write_json(base / "teacher-merge-report.json", merge_report)
    merge_report_desc = descriptor(base / "teacher-merge-report.json")
    publication = {
        "artifacts": {
            "children_jnnw": {key: children[key] for key in ("local_name", "sha256", "size_bytes")},
            "groups_tsv": {key: groups[key] for key in ("local_name", "sha256", "size_bytes")},
            "merge_report": merge_report_desc,
            "semantic_actions": {key: semantic_desc[key] for key in ("local_name", "sha256", "size_bytes")},
        },
        "byte_roundtrip_verified": True,
        "code_sha": CODE_SHA,
        "input_manifest": teacher_input,
        "schema": allocation.MERGE_PUBLICATION_SCHEMA,
    }
    write_json(base / "teacher-publication-receipt.json", publication)

    legacy_report = {
        "schema": allocation.LEGACY_SCHEMA,
        "verdict": allocation.LEGACY_VERDICT,
        "source": {"parents": 8000, "rows": 74449},
        "equivalence": {"parents_compared": 8000, "allocation_decision_matches": 8000,
                        "final_b1_result_matches": 8000},
        "information_barrier": {
            "q200_fields_in_projection_decision": 0, "q200_policy_reads": 0,
            "q200_value_reads": 0, "q200_label_reads": 0,
            "q200_policy_branches": 0, "nodes200k_policy_reads": 0,
            "nodes200k_policy_branches": 0,
            "nodes200k_preseal_aggregation_reads": 0,
            "nodes200k_validated_rows": 74449,
            "allocation_hash_excludes_q200_values": True,
            "postseal_join_hash_includes_q200_results": True,
        },
        "published_artifacts": {"empty_diff": {"sha256": "6" * 64}},
        "searches": 0, "fits": 0, "strength_games": 0,
        "promotion_authorized": False, "real_adaptive_teacher_authorized": False,
    }
    write_json(base / "legacy-equivalence-report.json", legacy_report)
    write_json(base / "legacy-terminal-summary.json", {"verdict": allocation.LEGACY_VERDICT})

    manifest = {
        "schema": allocation.INPUT_SCHEMA,
        "code_sha": CODE_SHA,
        "preregistration": {
            "file": descriptor(base / "preregistration.md"),
            "schema": allocation.PREREGISTRATION_SCHEMA,
        },
        "legacy_equivalence": {
            "report": descriptor(base / "legacy-equivalence-report.json"),
            "report_schema": allocation.LEGACY_SCHEMA,
            "terminal_summary": descriptor(base / "legacy-terminal-summary.json"),
            "verdict": allocation.LEGACY_VERDICT,
            "parents": 8000, "rows": 74449, "differences": 0,
        },
        "selection": {
            "report": selection_desc, "report_schema": allocation.SELECTION_SCHEMA,
            "parents_jnnw": parents_jnnw, "parents_tsv": parents_tsv,
            "ordered_identities": ordered, "selected": allocation.PARENT_COUNT,
            "cell_quota": allocation.CELL_QUOTA, "cell_order": list(allocation.CELL_ORDER),
        },
        "teacher_merge": {
            "input_manifest": teacher_input,
            "report": merge_report_desc, "report_schema": allocation.MERGE_SCHEMA,
            "publication_receipt": descriptor(base / "teacher-publication-receipt.json"),
            "publication_schema": allocation.MERGE_PUBLICATION_SCHEMA,
            "native_verification_receipt": descriptor(base / "native-verification-receipt.json"),
            "native_verification_schema": allocation.NATIVE_SCHEMA,
            "children_jnnw": children, "groups_tsv": groups,
            "semantic_actions": semantic_desc,
        },
        "tools": {
            "allocation_input": descriptor(base / "allocation-input-tool.py"),
            "projection": descriptor(base / "projection-tool.py"),
        },
    }
    manifest_raw = write_json(base / "allocation-inputs.json", manifest)
    return base / "allocation-inputs.json", hashlib.sha256(manifest_raw).hexdigest()


class AllocationInputTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        cls.manifest, cls.manifest_sha = build_fixture(cls.root / "base")

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def clone_fixture(self, name):
        base = self.root / name
        shutil.copytree(self.root / "base", base)
        manifest = base / "allocation-inputs.json"
        return manifest, hashlib.sha256(manifest.read_bytes()).hexdigest()

    def test_prepare_full_population_q200_poison_and_report(self):
        out = self.root / "success"
        report = allocation.prepare(self.manifest, self.manifest_sha, out)
        self.assertEqual(report["parents"], 4000)
        self.assertEqual(report["teacher_rows"], 8000)
        self.assertEqual(report["cells"], {cell: 500 for cell in allocation.CELL_ORDER})
        for field in (
            "q200_value_reads", "q200_label_reads", "q200_branches",
            "q200_value_decodes", "q200_metadata_decodes", "nodes200k_policy_reads",
            "nodes200k_policy_branches", "searches", "fits", "games", "promotions", "bakes",
        ):
            self.assertEqual(report[field], 0)
        parents, raw = projection.load_jsonl(out / "allocation-parents-v1.jsonl")
        self.assertEqual(len(parents), 4000)
        self.assertEqual(hashlib.sha256(raw).hexdigest(), report["output"]["sha256"])
        first = json.loads(raw.splitlines()[0])
        self.assertEqual(first["rows"][0]["exact_parent_utility"], 1)
        self.assertNotIn("q200_parent", raw.decode("ascii"))
        self.assertNotIn("POISON", raw.decode("ascii"))

    def test_common_auth_helper_hashes_but_never_parses_teacher_payloads(self):
        with mock.patch.object(
            allocation, "sha256_file", wraps=allocation.sha256_file,
        ) as hasher, mock.patch.object(
            allocation, "_load_semantic_rows", side_effect=AssertionError("row parser invoked"),
        ):
            common = allocation.authenticate_common_manifest(
                self.manifest, self.manifest_sha,
                expected_schema=allocation.INPUT_SCHEMA,
                exact_root_keys=allocation.ALLOCATION_ROOT_KEYS,
                exact_tool_keys=allocation.ALLOCATION_TOOL_KEYS,
            )
        hashed = {Path(call.args[0]).name for call in hasher.call_args_list}
        self.assertIn("groups.tsv", hashed)
        self.assertIn("semantic-actions.jsonl", hashed)
        self.assertEqual(common.teacher_merge_report["schema"], allocation.MERGE_SCHEMA)

    def test_no_q200_observation_token_is_typed(self):
        seen = []
        original = allocation._strict_token
        def recording(tokens, name, low, high):
            seen.append(name)
            return original(tokens, name, low, high)
        with mock.patch.object(allocation, "_strict_token", side_effect=recording):
            allocation.prepare(self.manifest, self.manifest_sha, self.root / "instrumented")
        self.assertIn("nodes200k", seen)
        self.assertNotIn("q200_parent", seen)
        self.assertFalse(any(name.endswith("200k") and name != "nodes200k" for name in seen))

    def test_q200_only_mutation_changes_provenance_not_projection_bytes(self):
        second_manifest, second_sha = build_fixture(
            self.root / "q200-b", q200_token="POISON_Q200_B")
        out_a = self.root / "equivalence-a"
        out_b = self.root / "equivalence-b"
        allocation.prepare(self.manifest, self.manifest_sha, out_a)
        allocation.prepare(second_manifest, second_sha, out_b)
        self.assertEqual(
            (out_a / "allocation-parents-v1.jsonl").read_bytes(),
            (out_b / "allocation-parents-v1.jsonl").read_bytes(),
        )
        self.assertNotEqual(self.manifest_sha, second_sha)

    def test_rule_terminal_utility_and_nodes200_fail_closed(self):
        bad_terminal, terminal_sha = build_fixture(
            self.root / "bad-terminal", bad_terminal=True)
        with self.assertRaisesRegex(allocation.AllocationInputError, r"utility \+1"):
            allocation.prepare(bad_terminal, terminal_sha, self.root / "bad-terminal-out")
        bad_nodes, nodes_sha = build_fixture(self.root / "bad-nodes", bad_nodes200=True)
        with self.assertRaisesRegex(allocation.AllocationInputError, "nodes200k"):
            allocation.prepare(bad_nodes, nodes_sha, self.root / "bad-nodes-out")

    def test_manifest_hash_output_existing_and_dangling_symlink_fail_closed(self):
        with self.assertRaisesRegex(allocation.CommonAuthenticationError, "SHA256 mismatch") as raised:
            allocation.prepare(self.manifest, "0" * 64, self.root / "wrong-sha")
        self.assertIs(
            raised.exception.reason,
            allocation.CommonAuthReason.INPUT_AUTHENTICATION_FAILED,
        )
        existing = self.root / "existing"
        existing.mkdir()
        with self.assertRaisesRegex(allocation.OutputSafetyError, "already exists"):
            allocation.prepare(self.manifest, self.manifest_sha, existing)
        if hasattr(os, "symlink"):
            link = self.root / "dangling-output"
            try:
                link.symlink_to(self.root / "missing-target", target_is_directory=True)
            except OSError:
                self.skipTest("symlink creation unavailable")
            with self.assertRaisesRegex(allocation.OutputSafetyError, "already exists"):
                allocation.prepare(self.manifest, self.manifest_sha, link)
            self.assertTrue(link.is_symlink())

    def test_common_auth_io_failure_remains_technical(self):
        with mock.patch.object(Path, "read_bytes", side_effect=OSError("fixture I/O")):
            with self.assertRaisesRegex(allocation.TechnicalIOError, "cannot read"):
                allocation.authenticate_common_manifest(
                    self.manifest, self.manifest_sha,
                    expected_schema=allocation.INPUT_SCHEMA,
                    exact_root_keys=allocation.ALLOCATION_ROOT_KEYS,
                    exact_tool_keys=allocation.ALLOCATION_TOOL_KEYS,
                )

        missing_manifest = self.root / "missing-common-manifest.json"
        with self.assertRaisesRegex(allocation.TechnicalIOError, "cannot stat input manifest"):
            allocation.authenticate_common_manifest(
                missing_manifest, "0" * 64,
                expected_schema=allocation.INPUT_SCHEMA,
                exact_root_keys=allocation.ALLOCATION_ROOT_KEYS,
                exact_tool_keys=allocation.ALLOCATION_TOOL_KEYS,
            )

        manifest, manifest_sha = self.clone_fixture("missing-common-input")
        (manifest.parent / "preregistration.md").unlink()
        with self.assertRaisesRegex(allocation.TechnicalIOError, "cannot stat preregistration"):
            allocation.authenticate_common_manifest(
                manifest, manifest_sha,
                expected_schema=allocation.INPUT_SCHEMA,
                exact_root_keys=allocation.ALLOCATION_ROOT_KEYS,
                exact_tool_keys=allocation.ALLOCATION_TOOL_KEYS,
            )

        with mock.patch("os.path.samefile", side_effect=OSError("fixture samefile I/O")):
            with self.assertRaisesRegex(allocation.TechnicalIOError, "cannot compare"):
                allocation.authenticate_common_manifest(
                    self.manifest, self.manifest_sha,
                    expected_schema=allocation.INPUT_SCHEMA,
                    exact_root_keys=allocation.ALLOCATION_ROOT_KEYS,
                    exact_tool_keys=allocation.ALLOCATION_TOOL_KEYS,
                )

    def test_common_input_symlink_is_output_safety_failure(self):
        manifest, manifest_sha = self.clone_fixture("symlink-common-input")
        prereg = manifest.parent / "preregistration.md"
        target = manifest.parent / "preregistration-target.md"
        prereg.replace(target)
        try:
            prereg.symlink_to(target)
        except OSError:
            self.skipTest("symlink creation unavailable")
        with self.assertRaisesRegex(allocation.OutputSafetyError, "must not be a symlink"):
            allocation.authenticate_common_manifest(
                manifest, manifest_sha,
                expected_schema=allocation.INPUT_SCHEMA,
                exact_root_keys=allocation.ALLOCATION_ROOT_KEYS,
                exact_tool_keys=allocation.ALLOCATION_TOOL_KEYS,
            )

    def test_legacy_boolean_counter_is_rejected(self):
        base = self.root / "legacy-bool"
        manifest, manifest_sha = build_fixture(base)
        value = json.loads(manifest.read_text(encoding="ascii"))
        value["legacy_equivalence"]["differences"] = False
        manifest_raw = write_json(manifest, value)
        with self.assertRaisesRegex(allocation.AllocationInputError, "legacy equivalence"):
            allocation.prepare(
                manifest, hashlib.sha256(manifest_raw).hexdigest(),
                self.root / "legacy-bool-out",
            )

    def test_generic_output_guard_rejects_aliasing_names(self):
        with self.assertRaisesRegex(allocation.AllocationInputError, "distinct"):
            allocation.guard_new_output_dir(
                self.root / "generic-output", [self.manifest],
                ("parent-stats.jsonl", "PARENT-STATS.JSONL"),
            )

    def test_runtime_tool_binding_and_postparse_stability_fail_closed(self):
        manifest, _ = self.clone_fixture("tool-drift")
        tool = manifest.parent / "allocation-input-tool.py"
        tool.write_bytes(tool.read_bytes() + b"# divergent copy\n")
        value = json.loads(manifest.read_text(encoding="ascii"))
        value["tools"]["allocation_input"] = descriptor(tool)
        manifest_raw = write_json(manifest, value)
        out = self.root / "tool-drift-output"
        with self.assertRaisesRegex(allocation.AllocationInputError, "running implementation"):
            allocation.prepare(manifest, hashlib.sha256(manifest_raw).hexdigest(), out)
        self.assertFalse(os.path.lexists(out))

        manifest, manifest_sha = self.clone_fixture("mutation-during-parse")
        groups = manifest.parent / "groups.tsv"
        original = allocation._build_projection_parents
        def mutate_after_parse(common, selected):
            result = original(common, selected)
            raw = groups.read_bytes()
            groups.write_bytes(raw.replace(b"POISON_Q200_A", b"POISON_Q200_B", 1))
            return result
        out = self.root / "mutation-during-parse-output"
        with mock.patch.object(allocation, "_build_projection_parents", side_effect=mutate_after_parse):
            with self.assertRaisesRegex(allocation.AllocationInputError, "size/SHA mismatch"):
                allocation.prepare(manifest, manifest_sha, out)
        self.assertFalse(os.path.lexists(out))

    def test_native_binding_and_json_numeric_types_fail_closed(self):
        bad_native, native_sha = build_fixture(self.root / "bad-native", bad_native=True)
        out = self.root / "bad-native-output"
        with self.assertRaisesRegex(allocation.AllocationInputError, "native children descriptor"):
            allocation.prepare(bad_native, native_sha, out)
        self.assertFalse(os.path.lexists(out))

        for index, replacement in enumerate((True, 4000.0)):
            manifest, _ = self.clone_fixture(f"numeric-type-{index}")
            value = json.loads(manifest.read_text(encoding="ascii"))
            value["selection"]["selected"] = replacement
            manifest_raw = write_json(manifest, value)
            out = self.root / f"numeric-type-output-{index}"
            with self.assertRaises(allocation.AllocationInputError):
                allocation.prepare(manifest, hashlib.sha256(manifest_raw).hexdigest(), out)
            self.assertFalse(os.path.lexists(out))

    def test_hardlinked_distinct_inputs_are_rejected(self):
        manifest, _ = self.clone_fixture("hardlink-inputs")
        prereg = manifest.parent / "preregistration.md"
        prereg.unlink()
        try:
            os.link(manifest.parent / "teacher-merge-inputs.json", prereg)
        except OSError:
            self.skipTest("hardlink creation unavailable")
        value = json.loads(manifest.read_text(encoding="ascii"))
        value["preregistration"]["file"] = descriptor(prereg)
        manifest_raw = write_json(manifest, value)
        manifest_sha = hashlib.sha256(manifest_raw).hexdigest()
        out = self.root / "hardlink-output"
        with self.assertRaisesRegex(allocation.OutputSafetyError, "filesystem aliases"):
            allocation.prepare(manifest, manifest_sha, out)
        self.assertFalse(os.path.lexists(out))

    def test_cli_from_outside_repo(self):
        out = self.root / "cli-output"
        result = subprocess.run([
            sys.executable, str(TOOL), "prepare",
            "--input-manifest", str(self.manifest),
            "--expected-input-manifest-sha256", self.manifest_sha,
            "--out-dir", str(out),
        ], cwd=self.root, capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        receipt = json.loads(result.stdout)
        self.assertEqual(receipt["parents"], 4000)
        self.assertEqual(receipt["teacher_rows"], 8000)
        self.assertTrue((out / "allocation-input-report-v1.json").is_file())


if __name__ == "__main__":
    unittest.main()
